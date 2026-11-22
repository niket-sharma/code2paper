#!/usr/bin/env python3
"""Match numbers extracted from the paper against evidence_map.csv -> numbers_audit.csv.

A paper value matches an evidence row when it equals the evidence value rounded
to the precision shown in the paper (fractions shown as percentages are also
accepted). When several rows share a value, metric and condition words in the
context (table row/column labels and caption, or ±10 words of prose) pick the
row. If the context points at a different row than the value does, the number
is a `conflict`. Numbers with no match are `unmatched`; possible derivations
(differences, percent changes, ratios of same-metric results) are suggested in
the note but are not accepted until a `derived` row exists in the evidence map.

Resolutions made by the agent go in a CSV (tex_file,line,value,status,evidence_id,note)
passed with --resolutions. A resolution to matched/rounding_ok/derived_ok must
name an evidence ID whose value really matches; `ignored` needs a reason.

Exit 1 if any `unmatched` or `conflict` row remains.

Example:
    python match_evidence.py --numbers workspace/audits/numbers.json \\
        --evidence-map workspace/evidence/evidence_map.csv --out workspace/audits/numbers_audit.csv
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal
from itertools import permutations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from c2p.common import C2PError, read_csv, read_evidence, rounds_to, run_main, to_decimal, write_csv  # noqa: E402

AUDIT_COLUMNS = ["tex_file", "line", "context", "value_in_paper", "status", "evidence_id", "note"]
OK_STATUSES = {"matched", "derived_ok", "rounding_ok", "ignored"}
ALIASES = {
    "accuracy": "acc", "parameters": "params", "param": "params", "seconds": "time", "sec": "time",
    "runtime": "time", "duration": "time", "errors": "error", "err": "error", "coefficient": "r2",
    "validation": "val", "valid": "val", "testing": "test", "training": "train",
}
STOP = {"the", "of", "and", "a", "an", "in", "on", "for", "to", "with", "by", "is", "was", "were", "at",
        "from", "as", "row", "line", "cell", "col", "vs", "versus", "our", "we", "this", "that", "its"}
CONDITION_SKIP = re.compile(r"^(row|line|cell|col|idx|index)=", re.I)
CONFLICT_MARGIN = 0.25


def norm_tokens(text: str) -> set[str]:
    raw = [t.lower() for t in re.findall(r"[A-Za-z0-9]+", text)]
    toks = set()
    for t in raw:
        if len(t) >= 2 or t.isdigit():
            toks.add(ALIASES.get(t, t))
    for a, b in zip(raw, raw[1:], strict=False):
        toks.add(a + b)
    return toks - STOP


def row_token_sets(r: dict[str, str]) -> tuple[set[str], list[set[str]]]:
    metric = norm_tokens(r["metric"].replace("_", " ")) | {r["metric"].lower().replace("_", "")}
    conds: list[set[str]] = []
    for item in re.split(r"[;/]", r["condition"]):
        item = item.strip()
        if not item or CONDITION_SKIP.match(item):
            continue
        val = item.split("=", 1)[-1]
        ts = norm_tokens(val) | {re.sub(r"[^a-z0-9]", "", val.lower())}
        ts.discard("")
        if ts:
            conds.append(ts)
    return metric - STOP, conds


def score(r: dict[str, str], ctx: set[str], cache: dict[str, tuple]) -> tuple[float, float]:
    if r["evidence_id"] not in cache:
        cache[r["evidence_id"]] = row_token_sets(r)
    metric, conds = cache[r["evidence_id"]]
    m = len(metric & ctx) / len(metric) if metric else 0.0
    m = 1.0 if (r["metric"].lower().replace("_", "") in ctx) else m
    c = (sum(1 for cs in conds if cs & ctx) / len(conds)) if conds else 0.0
    return m, c


def value_match(v: Decimal, r: dict[str, str], shown: str, paper_unit: str) -> str | None:
    hit = rounds_to(abs(v), shown)
    if hit:
        return hit
    if paper_unit == "%" and r["unit"] != "%" and abs(v) <= 1:
        if rounds_to(abs(v) * 100, shown):
            return "scaled"
    if r["unit"] == "%" and paper_unit != "%" and rounds_to(abs(v) / 100, shown):
        return "scaled"
    return None


def suggest_derivations(shown: str, rows: list[dict[str, str]]) -> list[str]:
    by_metric: dict[str, list[tuple[str, Decimal]]] = {}
    for r in rows:
        if r["kind"] == "result" and (v := to_decimal(r["value"])) is not None:
            by_metric.setdefault(r["metric"], []).append((r["evidence_id"], v))
    out = []
    for group in by_metric.values():
        if len(group) > 60:
            continue
        for (ia, a), (ib, b) in permutations(group, 2):
            cands = {f"{ia} - {ib}": a - b}
            if b != 0:
                cands[f"({ia} - {ib}) / {ib} * 100"] = (a - b) / b * 100
                cands[f"{ia} / {ib}"] = a / b
            for f, x in cands.items():
                if x != 0 and rounds_to(abs(x), shown):
                    out.append(f)
    return out[:3]


def contexts(n: dict) -> tuple[set[str], set[str], set[str]]:
    """(metric context, condition context, ranking context) token sets for a paper number.

    Tables: row/column labels plus the caption. Prose: the sentence for metric
    words, the clause holding the number for condition words (so "2.87 for a
    linear baseline" is not attributed to the model named in another clause).
    """
    if n["where"] == "table" and (n.get("row_label") or n.get("col_label")):
        labels = norm_tokens(" ".join([n.get("row_label", ""), n.get("col_label", "")]))
        cap = norm_tokens(n.get("caption", ""))
        return labels | cap, labels | cap, labels | cap
    sentence = n.get("sentence") or n["context"]
    clause = n.get("clause") or sentence
    if n["where"] == "caption":
        sentence = sentence + " " + n.get("caption", "")
    return norm_tokens(sentence), norm_tokens(clause), norm_tokens(n["context"])


def classify(n: dict, rows: list[dict[str, str]], cache: dict) -> dict:
    shown = n["value"]
    rec = {"tex_file": n["tex_file"], "line": n["line"], "context": n["context"],
           "value_in_paper": n["shown"] + ("%" if n["unit"] == "%" else ""), "evidence_id": "", "note": n.get("note", "")}
    if n["status"] == "ignored":
        return {**rec, "status": "ignored"}
    if to_decimal(shown) is None:
        return {**rec, "status": "unmatched", "note": "could not parse value"}
    mctx, cctx, rctx = contexts(n)

    def mc(r: dict[str, str]) -> tuple[float, float]:
        return score(r, mctx, cache)[0], score(r, cctx, cache)[1]

    vmatch: list[tuple[dict[str, str], str]] = []
    for r in rows:
        v = to_decimal(r["value"])
        if v is not None and (hit := value_match(v, r, shown, n["unit"])):
            vmatch.append((r, hit))

    if vmatch:
        # rank by clause/sentence fit, then by the wider ±10-word context
        ranked = sorted(vmatch, key=lambda rh: (-sum(mc(rh[0])), -sum(score(rh[0], rctx, cache))))
        r, hit = ranked[0]
        m_r, c_r = mc(r)
        vm_ids = {x[0]["evidence_id"] for x in vmatch}
        # swapped condition: another row of the same metric fits every condition word, r does not
        for x in rows:
            if x["evidence_id"] in vm_ids or x["metric"] != r["metric"] or x["kind"] != r["kind"]:
                continue
            m_x, c_x = mc(x)
            if c_x >= 0.999 and c_x > c_r + CONFLICT_MARGIN and m_x >= m_r:
                return {**rec, "status": "conflict", "evidence_id": x["evidence_id"],
                        "note": f"context points to {x['evidence_id']} ({x['metric']}, {x['condition']}) = {x['value']}, "
                                f"but the value matches {r['evidence_id']} ({r['metric']}, {r['condition']}) = {r['value']}"}
        status = "derived_ok" if r["kind"] == "derived" else ("matched" if hit == "exact" else "rounding_ok")
        note = "scaled x100 (fraction shown as %)" if hit == "scaled" else ""
        others = [x[0]["evidence_id"] for x in ranked[1:] if mc(x[0]) == (m_r, c_r)
                  and x[0]["value"] != r["value"]]
        if others:
            note = (note + "; " if note else "") + f"ambiguous: same context fit for {', '.join(others[:5])}"
        return {**rec, "status": status, "evidence_id": r["evidence_id"], "note": note}

    sugg = suggest_derivations(shown, rows)
    hint = f"; possible derivation: {' | '.join(sugg)} (add a derived row if correct)" if sugg else ""
    # changed value: context identifies one row (metric words present, every condition word present)
    best = None
    for x in rows:
        m_x, c_x = mc(x)
        has_cond = bool(cache[x["evidence_id"]][1])
        if m_x >= 0.5 and (c_x >= 0.999 or not has_cond) and has_cond:
            if best is None or m_x + c_x > best[0]:
                best = (m_x + c_x, x)
    if best:
        cr = best[1]
        return {**rec, "status": "conflict", "evidence_id": cr["evidence_id"],
                "note": f"context points to {cr['evidence_id']} ({cr['metric']}, {cr['condition']}) = {cr['value']}; "
                        f"paper says {n['shown']}{hint}"}
    return {**rec, "status": "unmatched", "note": f"no evidence row has this value{hint}"}


def apply_resolutions(audit: list[dict], res_path: Path, rows: list[dict[str, str]], numbers: list[dict]) -> list[str]:
    by_id = {r["evidence_id"]: r for r in rows}
    errs = []
    num_unit = {(n["tex_file"], str(n["line"]), n["shown"]): n["unit"] for n in numbers}
    for res in read_csv(res_path):
        key = (res["tex_file"], str(res["line"]), res["value"].rstrip("%"))
        targets = [a for a in audit if (a["tex_file"], str(a["line"]), a["value_in_paper"].rstrip("%")) == key]
        if not targets:
            errs.append(f"resolution for {key} matches no audited number")
            continue
        st = res["status"]
        if st not in OK_STATUSES:
            errs.append(f"resolution {key}: status must be one of {sorted(OK_STATUSES)}")
            continue
        if st == "ignored":
            if not res.get("note"):
                errs.append(f"resolution {key}: 'ignored' needs a reason in note")
                continue
        else:
            r = by_id.get(res["evidence_id"])
            v = to_decimal(r["value"]) if r else None
            unit = num_unit.get(key, "-")
            if r is None or v is None or not value_match(v, r, key[2], unit):
                errs.append(f"resolution {key}: {res['evidence_id'] or '<none>'} does not match value {key[2]}")
                continue
            if st == "derived_ok" and r["kind"] != "derived":
                errs.append(f"resolution {key}: derived_ok needs a derived row, {r['evidence_id']} is {r['kind']}")
                continue
        for t in targets:
            t.update(status=st, evidence_id=res.get("evidence_id", ""),
                     note=("resolved: " + (res.get("note") or "")).strip())
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--numbers", required=True, type=Path)
    ap.add_argument("--evidence-map", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--resolutions", type=Path)
    a = ap.parse_args()
    for p in (a.numbers, a.evidence_map):
        if not p.exists():
            raise C2PError(f"not found: {p}")
    numbers = json.loads(a.numbers.read_text())
    rows = read_evidence(a.evidence_map)
    cache: dict = {}
    audit = [classify(n, rows, cache) for n in numbers]
    errs = apply_resolutions(audit, a.resolutions, rows, numbers) if a.resolutions and a.resolutions.exists() else []
    write_csv(a.out, AUDIT_COLUMNS, audit)
    counts: dict[str, int] = {}
    for r in audit:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    for e in errs:
        print(f"FAIL {e}")
    bad = [r for r in audit if r["status"] in {"unmatched", "conflict"}]
    for r in bad:
        print(f"{r['status'].upper()} {r['tex_file']}:{r['line']} {r['value_in_paper']} — {r['note']}")
    print(f"numbers audit: {counts} -> {a.out}")
    return 1 if bad or errs else 0


if __name__ == "__main__":
    run_main(main)
