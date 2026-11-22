#!/usr/bin/env python3
"""Parse machine-readable results in a repo into evidence rows (method=parsed).

Handles CSV/TSV tables, JSON/JSONL metrics, YAML/TOML configs, notebook output
cells and common log patterns (`metric: value`, `metric=value`). Merges into an
existing evidence_map.csv so evidence IDs stay stable across reruns: rows the
agent added by reading (`method=read`) and `derived` rows are kept untouched.

Example:
    python extract_results.py --repo workspace/repo \\
        --inventory workspace/evidence/inventory.json \\
        --evidence-map workspace/evidence/evidence_map.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from c2p.common import (  # noqa: E402
    C2PError,
    format_evidence_id,
    git_head,
    next_evidence_id,
    read_evidence,
    run_main,
    sha256_file,
    write_evidence,
    write_json,
)

NUM = r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?"
FULL_NUM = re.compile(rf"^\s*({NUM})\s*(%?)\s*$")
CONDITION_KEYS = {"epoch", "step", "iter", "iteration", "seed", "fold", "run", "split", "trial",
                  "global_step", "batch_idx", "rank", "id", "idx", "index"}
PHASES = r"(train|training|val|valid|validation|dev|test|testing|eval|evaluation|final)"
LOG_KV = re.compile(rf"""['"]?(?P<key>[A-Za-z][\w./\-]*)['"]?\s*[:=]\s*(?P<val>{NUM})(?P<pct>%)?(?![\w.:/-])""")
PHASE_RE = re.compile(rf"(?:\[|\b){PHASES}(?:\]|\b)", re.I)
DATASET_STAT = re.compile(
    r"^(n|num|number_of)_(train|test|val|valid|dev|samples|examples|rows|classes|tokens|instances|features)"
    r"|(^|_)(samples|examples|instances|dataset_size)($|_)",
    re.I,
)
STICKY_KEYS = {"dataset", "data", "model", "task", "env", "environment", "config", "split", "method"}
STICKY_KV = re.compile(r"\b(?P<key>[A-Za-z][\w-]*)\s*[:=]\s*(?P<val>[A-Za-z][\w.\-/]*)")


class Num(str):
    """JSON number kept as its exact source text."""


def unit_for(header: str, pct: bool) -> str:
    h = header.lower()
    if pct or "%" in h or "pct" in h or "percent" in h:
        return "%"
    if re.search(r"(\(ms\)|_ms\b|millisec)", h):
        return "ms"
    if re.search(r"(\(s\)|_s\b|_sec\b|seconds|\btime\b|runtime)", h):
        return "s"
    if re.search(r"(\(k\)|kelvin|temp_k\b|temperature_k\b)", h):
        return "K"
    return "-"


def kind_for(metric: str, role: str) -> str:
    if role == "config":
        return "hyperparameter"
    if DATASET_STAT.search(metric):
        return "dataset_stat"
    return "result"


def cond_str(parts: list[str], kv: dict[str, str]) -> str:
    items = [p for p in parts if p] + [f"{k}={v}" for k, v in kv.items()]
    return ";".join(items)


# ---------------------------------------------------------------- parsers
# Each yields dicts with value, unit, metric, condition, line_start, line_end, quote.


def parse_table(text: str, delim: str) -> Iterator[dict[str, Any]]:
    lines = text.splitlines()
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        header = next(reader)
    except StopIteration:
        return
    header = [h.strip() for h in header]
    lower = [h.lower() for h in header]
    metric_col = next((i for i, h in enumerate(lower) if h in {"metric", "metric_name", "measure"}), None)
    prev = reader.line_num
    for row in reader:
        start, end = prev + 1, reader.line_num
        prev = reader.line_num
        if not any(c.strip() for c in row):
            continue
        cells = [c.strip() for c in row] + [""] * (len(header) - len(row))
        cond: dict[str, str] = {}
        numeric: list[tuple[int, str, bool]] = []
        for i, c in enumerate(cells[: len(header)]):
            m = FULL_NUM.match(c)
            if i == metric_col:
                continue
            if m and lower[i] not in CONDITION_KEYS:
                numeric.append((i, m.group(1), bool(m.group(2))))
            elif c:
                cond[header[i] or f"col{i}"] = c
        base = cells[metric_col] if metric_col is not None else None
        quote = "\n".join(lines[start - 1 : end]).strip()
        for i, val, pct in numeric:
            if base:
                metric = base if lower[i] in {"value", "score", "result"} else f"{base}_{header[i]}"
            else:
                metric = header[i] or f"col{i}"
            yield {
                "value": val,
                "unit": unit_for(header[i] + " " + (base or ""), pct),
                "metric": metric,
                "condition": cond_str([], cond) or f"row={start}",
                "line_start": start,
                "line_end": end,
                "quote": quote,
            }


def _json_walk(obj: Any, path: list[str], cond: dict[str, str]) -> Iterator[tuple[list[str], dict[str, str], str, Num]]:
    if isinstance(obj, dict):
        local = dict(cond)
        for k, v in obj.items():
            if (isinstance(v, str) and not isinstance(v, Num)) or (
                isinstance(v, Num) and k.lower() in CONDITION_KEYS
            ):
                local[k] = str(v)
        for k, v in obj.items():
            if isinstance(v, Num) and k.lower() not in CONDITION_KEYS:
                yield path, local, k, v
            elif isinstance(v, (dict, list)):
                yield from _json_walk(v, path + [k], local)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, dict):
                has_label = any(isinstance(x, str) and not isinstance(x, Num) for x in v.values())
                yield from _json_walk(v, path if has_label else path + [str(i)], cond)
            elif isinstance(v, list):
                yield from _json_walk(v, path + [str(i)], cond)
            elif isinstance(v, Num):
                yield path[:-1], cond, f"{path[-1] if path else 'value'}[{i}]", v


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def parse_json(text: str) -> Iterator[dict[str, Any]]:
    try:
        obj = json.loads(text, parse_float=Num, parse_int=Num)
    except json.JSONDecodeError:
        return
    cursor = 0
    for path, cond, key, val in _json_walk(obj, [], {}):
        leaf = re.sub(r"\[\d+\]$", "", key)
        if leaf != key:
            pat = re.compile(rf"(?<![\w.]){re.escape(val)}(?![\w.])")
        else:
            pat = re.compile(rf'"{re.escape(leaf)}"\s*:\s*{re.escape(val)}(?![\w.])')
        m = pat.search(text, cursor) or pat.search(text)
        if not m:
            continue
        cursor = m.end()
        ln = _line(text, m.start())
        yield {
            "value": str(val),
            "unit": unit_for(key, False),
            "metric": key,
            "condition": cond_str(["/".join(path)], cond),
            "line_start": ln,
            "line_end": _line(text, m.end()),
            "quote": m.group(0),
        }


def parse_jsonl(text: str) -> Iterator[dict[str, Any]]:
    for ln, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line, parse_float=Num, parse_int=Num)
        except json.JSONDecodeError:
            continue
        for path, cond, key, val in _json_walk(obj, [], {}):
            yield {
                "value": str(val),
                "unit": unit_for(key, False),
                "metric": key,
                "condition": cond_str(["/".join(path)], cond) or f"line={ln}",
                "line_start": ln,
                "line_end": ln,
                "quote": line.strip(),
            }


YAML_KV = re.compile(rf"^(?P<ind>\s*)(?P<dash>-\s+)?(?P<key>[\w.\-]+)\s*:\s*(?P<val>{NUM})\s*(?:#.*)?$")
YAML_KEY = re.compile(r"^(?P<ind>\s*)(?P<dash>-\s+)?(?P<key>[\w.\-]+)\s*:\s*(?:#.*)?$")


def parse_yaml(text: str) -> Iterator[dict[str, Any]]:
    stack: list[tuple[int, str]] = []
    for ln, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = YAML_KV.match(line) or YAML_KEY.match(line)
        if not m:
            continue
        ind = len(m.group("ind")) + (len(m.group("dash")) if m.group("dash") else 0)
        while stack and stack[-1][0] >= ind:
            stack.pop()
        if "val" in m.groupdict() and m.group("val") is not None:
            yield {
                "value": m.group("val"),
                "unit": unit_for(m.group("key"), False),
                "metric": m.group("key"),
                "condition": ".".join(k for _, k in stack),
                "line_start": ln,
                "line_end": ln,
                "quote": line.strip(),
            }
        else:
            stack.append((ind, m.group("key")))


TOML_SEC = re.compile(r"^\s*\[+([^\]]+)\]+\s*$")
TOML_KV = re.compile(rf"^\s*(?P<key>[\w.\-\"]+)\s*=\s*(?P<val>{NUM})\s*(?:#.*)?$")


def parse_toml(text: str) -> Iterator[dict[str, Any]]:
    section = ""
    for ln, line in enumerate(text.splitlines(), 1):
        if m := TOML_SEC.match(line):
            section = m.group(1).strip()
        elif m := TOML_KV.match(line):
            yield {
                "value": m.group("val"),
                "unit": unit_for(m.group("key"), False),
                "metric": m.group("key").strip('"'),
                "condition": section,
                "line_start": ln,
                "line_end": ln,
                "quote": line.strip(),
            }


def kv_line(line: str, sticky: dict[str, str] | None = None) -> tuple[dict[str, str], list[re.Match[str]]]:
    """Metric matches on a line plus their condition. `sticky` carries string context
    such as `dataset=HousingLite` from earlier lines and is updated in place."""
    if sticky is not None:
        for sm in STICKY_KV.finditer(line):
            if sm.group("key").lower() in STICKY_KEYS:
                sticky[sm.group("key")] = sm.group("val")
    cond: dict[str, str] = dict(sticky or {})
    metrics = []
    for m in LOG_KV.finditer(line):
        if m.group("key").lower() in CONDITION_KEYS:
            cond[m.group("key")] = m.group("val")
        else:
            metrics.append(m)
    if metrics:
        ph = PHASE_RE.search(line[: metrics[0].start()])
        if ph:
            cond["phase"] = ph.group(1).lower()
    return cond, metrics


def parse_log(text: str) -> Iterator[dict[str, Any]]:
    sticky: dict[str, str] = {}
    for ln, line in enumerate(text.splitlines(), 1):
        cond, metrics = kv_line(line, sticky)
        for m in metrics:
            yield {
                "value": m.group("val"),
                "unit": unit_for(m.group("key"), bool(m.group("pct"))),
                "metric": m.group("key"),
                "condition": cond_str([], cond),
                "line_start": ln,
                "line_end": ln,
                "quote": line.strip(),
            }


def parse_notebook(text: str) -> Iterator[dict[str, Any]]:
    try:
        nb = json.loads(text)
    except json.JSONDecodeError:
        return
    cursor = 0
    sticky: dict[str, str] = {}
    for ci, cell in enumerate(nb.get("cells", [])):
        for out in cell.get("outputs", []):
            src = out.get("text") or out.get("data", {}).get("text/plain") or []
            out_lines = src if isinstance(src, list) else src.splitlines(keepends=True)
            for ol in out_lines:
                cond, metrics = kv_line(ol, sticky)
                if not metrics:
                    continue
                esc = json.dumps(ol)[1:-1]
                pos = text.find(esc, cursor)
                if pos == -1:
                    pos = text.find(esc)
                if pos == -1:
                    continue
                cursor = pos + len(esc)
                ln = _line(text, pos)
                cond = {"cell": str(ci), **cond}
                for m in metrics:
                    yield {
                        "value": m.group("val"),
                        "unit": unit_for(m.group("key"), bool(m.group("pct"))),
                        "metric": m.group("key"),
                        "condition": cond_str([], cond),
                        "line_start": ln,
                        "line_end": ln,
                        "quote": ol.strip(),
                    }


def parser_for(path: str, role: str):  # type: ignore[no-untyped-def]
    ext = Path(path).suffix.lower()
    if ext == ".csv":
        return lambda t: parse_table(t, ",")
    if ext == ".tsv":
        return lambda t: parse_table(t, "\t")
    if ext == ".jsonl":
        return parse_jsonl
    if ext == ".json":
        return parse_json
    if ext in {".yaml", ".yml"}:
        return parse_yaml
    if ext == ".toml":
        return parse_toml
    if ext == ".ipynb":
        return parse_notebook
    if role == "log" or ext in {".log", ".out", ".txt"}:
        return parse_log
    return None


PARSE_ROLES = {"result_table", "log", "config", "notebook"}


def extract(repo: Path, inventory: dict, max_rows: int) -> tuple[list[dict[str, Any]], list[str]]:
    commit = git_head(repo)
    rows: list[dict[str, Any]] = []
    unparsed: list[str] = []
    for f in inventory["files"]:
        if f["role"] not in PARSE_ROLES or f["binary"]:
            continue
        parser = parser_for(f["path"], f["role"])
        if parser is None:
            unparsed.append(f["path"])
            continue
        p = repo / f["path"]
        text = p.read_text(encoding="utf-8", errors="replace")
        sha = sha256_file(p)
        found = 0
        for r in parser(text):
            if found >= max_rows:
                unparsed.append(f"{f['path']} (truncated at {max_rows} rows)")
                break
            r.update(
                kind=kind_for(r["metric"], f["role"]),
                source_file=f["path"],
                commit=commit,
                file_sha256=sha,
                method="parsed",
                derived_from="",
                formula="",
            )
            rows.append(r)
            found += 1
        if found == 0:
            unparsed.append(f["path"])
    return rows, unparsed


def row_key(r: dict[str, Any]) -> tuple[str, str, str, str]:
    return (str(r["source_file"]), str(r["metric"]), str(r["condition"]), str(r["line_start"]))


def merge(existing: list[dict[str, str]], new: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    kept = [r for r in existing if r["method"] == "read" or r["kind"] == "derived"]
    by_key = {row_key(r): r["evidence_id"] for r in existing if r not in kept}
    nxt = next_evidence_id(r["evidence_id"] for r in existing)
    out = list(kept)
    stats = {"reused": 0, "new": 0, "kept_read_or_derived": len(kept)}
    used: set[str] = set()
    for r in new:
        k = row_key(r)
        if k in by_key and by_key[k] not in used:
            r["evidence_id"] = by_key[k]
            stats["reused"] += 1
        else:
            r["evidence_id"] = format_evidence_id(nxt)
            nxt += 1
            stats["new"] += 1
        used.add(r["evidence_id"])
        out.append(r)
    stats["dropped_stale"] = len(set(by_key.values()) - used)
    out.sort(key=lambda r: int(r["evidence_id"][1:]))
    return out, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--inventory", required=True, type=Path)
    ap.add_argument("--evidence-map", required=True, type=Path, help="created or merged in place")
    ap.add_argument("--unparsed-out", type=Path, help="JSON list of result-like files that were not parsed")
    ap.add_argument("--max-rows-per-file", type=int, default=2000)
    a = ap.parse_args()
    if not a.inventory.exists():
        raise C2PError(f"inventory not found: {a.inventory} (run inventory_repo.py first)")
    inv = json.loads(a.inventory.read_text())
    rows, unparsed = extract(a.repo.resolve(), inv, a.max_rows_per_file)
    existing = read_evidence(a.evidence_map) if a.evidence_map.exists() else []
    merged, stats = merge(existing, rows)
    write_evidence(a.evidence_map, merged)
    unparsed_out = a.unparsed_out or a.evidence_map.with_name("unparsed_files.json")
    write_json(unparsed_out, unparsed)
    print(f"evidence rows: {len(merged)} ({stats}); unparsed result-like files: {len(unparsed)} -> {unparsed_out}")
    return 0


if __name__ == "__main__":
    run_main(main)
