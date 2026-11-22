#!/usr/bin/env python3
"""Deterministic first pass of the gap check: notes.md versus the evidence map.

Writes gap_scan.json with: blocking problems in notes.md, a status guess for
each key result, heuristic checks for missing evidence (baselines, ablations,
seeds, error bars, dataset stats, compute details, statistical tests), and the
prior-work list. The c2p-gap-check skill turns this into gap_report.md.

Exit codes: 0 ok, 1 error, 3 notes.md is missing a required field (stop the pipeline).

Example:
    python gap_scan.py --notes workspace/notes.md --evidence-map workspace/evidence/evidence_map.csv \\
        --inventory workspace/evidence/inventory.json --repo workspace/repo --out workspace/evidence/gap_scan.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from c2p.common import C2PError, read_evidence, rounds_to, run_main, to_decimal, write_json  # noqa: E402
from c2p.notes import parse_notes  # noqa: E402

NUM_IN_TEXT = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?![\w])")


def cond_values(rows: list[dict[str, str]], key: str) -> set[str]:
    out = set()
    pat = re.compile(rf"(?:^|;){key}=([^;]+)", re.I)
    for r in rows:
        for m in pat.finditer(r["condition"]):
            out.add(m.group(1))
    return out


def check_key_result(text: str, files: list[str], rows: list[dict[str, str]], repo: Path) -> dict:
    res: dict = {"text": text, "files": files, "problems": []}
    if not files:
        res["status"] = "not_found"
        res["problems"].append("no repo file referenced")
        return res
    present = [f for f in files if (repo / f).exists()]
    missing = [f for f in files if f not in present]
    if missing:
        res["problems"].append(f"files not in repo: {missing}")
    file_rows = [r for r in rows if r["source_file"] in present]
    res["evidence_ids"] = [r["evidence_id"] for r in file_rows][:50]
    if not present:
        res["status"] = "not_found"
        return res
    if not file_rows:
        res["status"] = "partly_supported"
        res["problems"].append("referenced file has no evidence rows (agent must read it)")
        return res
    stated = [m.group(0) for m in NUM_IN_TEXT.finditer(text) if "." in m.group(0) or len(m.group(0)) > 2]
    unmatched = []
    for s in stated:
        if not any(
            (v := to_decimal(r["value"])) is not None and (rounds_to(v, s) or rounds_to(v * 100, s))
            for r in rows
        ):
            unmatched.append(s)
    if unmatched:
        res["status"] = "partly_supported"
        res["problems"].append(f"numbers stated in notes not found in evidence: {unmatched}")
    else:
        res["status"] = "supported_candidate"
    return res


def evidence_checks(rows: list[dict[str, str]], inventory: dict, repo: Path) -> list[dict]:
    results = [r for r in rows if r["kind"] == "result"]
    paths = " ".join(f["path"].lower() for f in inventory.get("files", []))
    conds = " ".join(r["condition"].lower() for r in rows)
    metrics = " ".join(r["metric"].lower() for r in rows)
    text_blob = ""
    for f in inventory.get("files", []):
        if f["role"] in {"readme", "config"} and not f["binary"]:
            text_blob += (repo / f["path"]).read_text(encoding="utf-8", errors="replace").lower()

    out = []

    def add(check: str, ok: bool, detail: str) -> None:
        out.append({"check": check, "status": "present" if ok else "possibly_missing", "detail": detail})

    models = cond_values(results, "model") | cond_values(results, "method")
    add("baselines", len(models) >= 2, f"distinct model/method conditions in results: {sorted(models)}")
    add("ablations", "ablat" in paths or "ablat" in conds, "files or conditions mentioning 'ablation'")
    seeds = cond_values(rows, "seed") | {r["value"] for r in rows if r["metric"].lower() == "seed"}
    add("multiple_seeds", len(seeds) >= 2, f"seed values seen: {sorted(seeds)}")
    add(
        "error_bars",
        bool(re.search(r"(^|[_\s])(std|stderr|sem|ci|ci95|conf|variance|var)([_\s]|$)", metrics)),
        "metrics named std/stderr/sem/ci",
    )
    stats = [r for r in rows if r["kind"] == "dataset_stat"]
    add("dataset_description", bool(stats), f"{len(stats)} dataset_stat rows")
    compute = re.findall(r"\b(gpu|cpu|a100|v100|h100|rtx\s?\d+|tpu|cores?|ram|gb|hours?)\b", text_blob)
    timing = [r for r in rows if r["unit"] in {"s", "ms"} or "time" in r["metric"].lower()]
    add("compute_details", bool(compute) and bool(timing),
        f"hardware words in README/configs: {sorted(set(compute))}; timing rows: {len(timing)}")
    add(
        "statistical_tests",
        bool(re.search(r"p_?value|ttest|t_test|wilcoxon|mann|bootstrap", metrics + " " + paths)),
        "metrics/files mentioning p-values or tests",
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--notes", required=True, type=Path)
    ap.add_argument("--evidence-map", required=True, type=Path)
    ap.add_argument("--inventory", required=True, type=Path)
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    if not a.notes.exists():
        raise C2PError(f"notes not found: {a.notes}")
    notes = parse_notes(a.notes)
    blocking = notes.blocking_problems()
    rows = read_evidence(a.evidence_map) if a.evidence_map.exists() else []
    inv = json.loads(a.inventory.read_text()) if a.inventory.exists() else {"files": []}
    repo = a.repo.resolve()
    scan = {
        "blocking": blocking,
        "title": notes.title,
        "journal": notes.journal,
        "guidelines": notes.guidelines,
        "novelty": notes.novelty,
        "key_results": [check_key_result(k.text, k.files, rows, repo) for k in notes.key_results],
        "evidence_checks": evidence_checks(rows, inv, repo),
        "prior_work": [
            {"text": p.text, "doi": p.doi, "arxiv": p.arxiv, "has_identifier": bool(p.doi or p.arxiv)}
            for p in notes.prior_work
        ],
        "n_evidence_rows": len(rows),
    }
    if len(notes.key_results) < 3:
        scan["warnings"] = [f"notes list {len(notes.key_results)} key results; expected 3–5"]
    write_json(a.out, scan)
    for b in blocking:
        print(f"BLOCKING: {b}")
    for k in scan["key_results"]:
        print(f"key result [{k['status']}]: {k['text'][:80]}")
    for c in scan["evidence_checks"]:
        print(f"{c['check']}: {c['status']}")
    return 3 if blocking else 0


if __name__ == "__main__":
    run_main(main)
