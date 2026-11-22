#!/usr/bin/env python3
"""Validate evidence_map.csv against the target repo; optionally check experimental_log.md.

Checks: schema, unique IDs, value parses, source file exists, file hash and
commit match, the quote appears at the stated lines and contains the value,
and derived rows recompute from their parents. With --experimental-log, every
number in the log must carry an evidence ID (`0.912 [E0031]`) whose value
matches at the shown precision. Exits 1 on any failure.

Example:
    python validate_evidence_map.py --evidence-map workspace/evidence/evidence_map.csv \\
        --repo workspace/repo --experimental-log workspace/inputs/experimental_log.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from c2p.common import (  # noqa: E402
    EVIDENCE_ID_RE,
    KINDS,
    METHODS,
    C2PError,
    eval_formula,
    formula_ids,
    git_head,
    parse_derived_from,
    read_evidence,
    rounds_to,
    run_main,
    sha256_file,
    to_decimal,
)

LOG_NUM = re.compile(r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?")
TAG = re.compile(r"^\s*(%|[A-Za-z]{1,3}\b)?\s*\[(E\d{4,}(?:\s*[,;]\s*E\d{4,})*)\]")


def _unescape(line: str) -> str:
    s = line.strip().rstrip(",")
    if s.startswith('"') and s.endswith('"'):
        try:
            return str(json.loads(s))
        except json.JSONDecodeError:
            return s
    return s


def value_in_quote(value: str, quote: str) -> bool:
    if value in quote:
        return True
    v = to_decimal(value)
    for m in re.finditer(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?", quote):
        d = to_decimal(m.group(0))
        if v is not None and d is not None and d == v:
            return True
    return False


def check_rows(rows: list[dict[str, str]], repo: Path) -> list[str]:
    errs: list[str] = []
    head = git_head(repo)
    ids: dict[str, dict[str, str]] = {}
    file_cache: dict[str, list[str]] = {}
    sha_cache: dict[str, str] = {}
    for r in rows:
        eid = r["evidence_id"]
        where = f"{eid or '<no id>'}"
        if not EVIDENCE_ID_RE.match(eid):
            errs.append(f"{where}: bad evidence_id format")
        if eid in ids:
            errs.append(f"{where}: duplicate evidence_id")
        ids[eid] = r
        if to_decimal(r["value"]) is None:
            errs.append(f"{where}: value {r['value']!r} is not a number")
        if r["kind"] not in KINDS:
            errs.append(f"{where}: kind {r['kind']!r} not in {sorted(KINDS)}")
        if r["kind"] != "derived" and r["method"] not in METHODS:
            errs.append(f"{where}: method {r['method']!r} not in {sorted(METHODS)}")
        if not r["metric"]:
            errs.append(f"{where}: metric is empty")

    for r in rows:
        eid = r["evidence_id"]
        if r["kind"] == "derived":
            parents = parse_derived_from(r["derived_from"])
            if not parents or not r["formula"]:
                errs.append(f"{eid}: derived row needs derived_from and formula")
                continue
            missing = [p for p in parents if p not in ids]
            if missing:
                errs.append(f"{eid}: derived_from references unknown ids {missing}")
                continue
            try:
                extra = formula_ids(r["formula"]) - set(parents)
                if extra:
                    errs.append(f"{eid}: formula uses ids not in derived_from: {sorted(extra)}")
                    continue
                vals = {p: to_decimal(ids[p]["value"]) or Decimal(0) for p in parents}
                got = eval_formula(r["formula"], vals)
            except (C2PError, SyntaxError, ZeroDivisionError, ArithmeticError) as e:
                errs.append(f"{eid}: formula error: {e}")
                continue
            if rounds_to(got, r["value"]) is None:
                errs.append(f"{eid}: formula {r['formula']} = {got:.10g}, row says {r['value']}")
            continue

        src = r["source_file"]
        if not src:
            errs.append(f"{eid}: non-derived row has no source_file (numbers without a source do not get a row)")
            continue
        p = repo / src
        if not p.is_file():
            errs.append(f"{eid}: source_file {src} not found in repo")
            continue
        if src not in sha_cache:
            sha_cache[src] = sha256_file(p)
            file_cache[src] = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if r["file_sha256"] != sha_cache[src]:
            errs.append(f"{eid}: file_sha256 mismatch for {src} (file changed since extraction?)")
        if head and r["commit"] != head:
            errs.append(f"{eid}: commit {r['commit'][:12] or '<empty>'} != repo HEAD {head[:12]}")
        try:
            a, b = int(r["line_start"]), int(r["line_end"] or r["line_start"])
        except ValueError:
            errs.append(f"{eid}: line_start/line_end must be integers")
            continue
        lines = file_cache[src]
        if not (1 <= a <= b <= len(lines)):
            errs.append(f"{eid}: lines {a}-{b} out of range for {src} ({len(lines)} lines)")
            continue
        seg = lines[a - 1 : b]
        raw = "\n".join(seg)
        unesc = "\n".join(_unescape(s) for s in seg)
        q = r["quote"]
        if not q:
            errs.append(f"{eid}: quote is empty")
        elif q not in raw and q not in unesc and q.strip() not in " ".join(raw.split()):
            errs.append(f"{eid}: quote not found at {src}:{a}-{b} ({r['method']})")
        elif not value_in_quote(r["value"], q):
            errs.append(f"{eid}: value {r['value']} does not appear in its quote")
    return errs


def check_log(log: Path, rows: list[dict[str, str]]) -> list[str]:
    ids = {r["evidence_id"]: r for r in rows}
    errs: list[str] = []
    in_code = False
    for ln, line in enumerate(log.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        work = re.sub(r"`[^`]*`", lambda m: " " * len(m.group(0)), line)  # labels in backticks
        work = re.sub(r"\[E\d{4,}(?:\s*[,;]\s*E\d{4,})*\]", lambda m: "[" + "#" * (len(m.group(0)) - 2) + "]", work)
        work = re.sub(r"^(\s*#+\s*)(\d+(?:\.\d+)*\.?)", lambda m: m.group(1) + " " * len(m.group(2)), work)
        work = re.sub(r"^(\s*)(\d+\.)(\s)", lambda m: m.group(1) + " " * len(m.group(2)) + m.group(3), work)
        if re.fullmatch(r"\s*\|?[\s:|-]+\|?\s*", work):
            continue
        for m in LOG_NUM.finditer(work):
            after = line[m.end():]
            s = m.start()
            prev = line[s - 1] if s > 0 else ""
            prev2 = line[s - 2] if s > 1 else ""
            if re.match(r"[A-Za-z]", after) or prev.isalpha() or (prev == "-" and prev2.isalpha()):
                continue  # identifiers like 3D, A100, ResNet-50
            t = TAG.match(after)
            if not t:
                errs.append(f"{log.name}:{ln}: number {m.group(0)} has no evidence ID")
                continue
            tagged = re.split(r"\s*[,;]\s*", t.group(2))
            unknown = [e for e in tagged if e not in ids]
            if unknown:
                errs.append(f"{log.name}:{ln}: {m.group(0)} tagged with unknown ids {unknown}")
                continue
            shown = m.group(0).replace(",", "")
            ok = False
            for e in tagged:
                v = to_decimal(ids[e]["value"])
                if v is None:
                    continue
                if rounds_to(v, shown) or rounds_to(v * 100, shown) or rounds_to(v / 100, shown):
                    ok = True
            if not ok:
                errs.append(
                    f"{log.name}:{ln}: {m.group(0)} does not match "
                    + ", ".join(f"{e}={ids[e]['value']}" for e in tagged)
                )
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--evidence-map", required=True, type=Path)
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--experimental-log", type=Path, help="also check every number in this log has an ID")
    a = ap.parse_args()
    if not a.evidence_map.exists():
        raise C2PError(f"not found: {a.evidence_map}")
    rows = read_evidence(a.evidence_map)
    errs = check_rows(rows, a.repo.resolve())
    if a.experimental_log:
        errs += check_log(a.experimental_log, rows)
    for e in errs:
        print(f"FAIL {e}")
    print(f"{len(rows)} rows checked, {len(errs)} problem(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    run_main(main)
