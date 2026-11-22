#!/usr/bin/env python3
"""Build support-check tasks and assemble citation_audit.csv.

Subcommands:
  tasks  Write support_tasks.jsonl: one task per (cited paper, sentence) with only
         the sentence and the abstract, for subagents that have not seen the manuscript.
  build  Merge citations, existence, abstracts and subagent judgments
         (support.jsonl: {"task_id", "support", "rationale"}) into citation_audit.csv
         and citation_report.md. Keeps any author_signoff already filled in.
         Exit 1 while any flagged row lacks an author_signoff, any reference
         failed the existence check, or a \\cite key has no bib entry.

Example:
    python assemble_audit.py tasks --audits workspace/audits
    python assemble_audit.py build --audits workspace/audits
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from c2p.common import C2PError, guard_output, read_csv, run_main, write_csv  # noqa: E402

COLUMNS = ["cite_key", "sentence", "tex_line", "doi", "exists", "metadata_match", "abstract_source",
           "support", "rationale", "author_signoff"]
SUPPORT = {"supports", "partial", "unsupported"}


def task_id(key: str, sentence: str) -> str:
    return "T" + hashlib.sha256(f"{key}\x00{sentence}".encode()).hexdigest()[:10]


def load(audits: Path) -> tuple[dict, dict, dict]:
    paths = [audits / "citations.json", audits / "existence.json", audits / "abstracts.json"]
    for p in paths:
        if not p.exists():
            raise C2PError(f"missing {p}; run the earlier citation-audit scripts first")
    cit = json.loads(paths[0].read_text())
    ex = json.loads(paths[1].read_text())["results"]
    ab = json.loads(paths[2].read_text())["abstracts"]
    return cit, ex, ab


def cmd_tasks(audits: Path) -> int:
    cit, ex, ab = load(audits)
    seen: set[str] = set()
    out = guard_output(audits / "support_tasks.jsonl")
    n = 0
    with open(out, "w", encoding="utf-8") as f:
        for c in cit["cites"]:
            k = c["cite_key"]
            if ex.get(k, {}).get("exists") != "yes" or not ab.get(k, {}).get("abstract"):
                continue
            tid = task_id(k, c["sentence"])
            if tid in seen:
                continue
            seen.add(tid)
            m = ex[k].get("matched") or {}
            f.write(json.dumps({"task_id": tid, "cited_title": m.get("title", ""), "sentence": c["sentence"],
                                "abstract": ab[k]["abstract"]}, ensure_ascii=False) + "\n")
            n += 1
    print(f"{n} support tasks -> {out}")
    return 0


def cmd_build(audits: Path, out_csv: Path | None) -> int:
    cit, ex, ab = load(audits)
    support: dict[str, dict[str, Any]] = {}
    sp = audits / "support.jsonl"
    errs: list[str] = []
    if sp.exists():
        for ln, line in enumerate(sp.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            j = json.loads(line)
            if j.get("support") not in SUPPORT:
                errs.append(f"support.jsonl:{ln}: support must be one of {sorted(SUPPORT)}")
                continue
            support[j["task_id"]] = j
    out_csv = out_csv or audits / "citation_audit.csv"
    previous = {}
    if out_csv.exists():
        for r in read_csv(out_csv):
            previous[(r["cite_key"], r["tex_line"], r["sentence"])] = r.get("author_signoff", "")
    rows = []
    for c in cit["cites"]:
        k = c["cite_key"]
        e = ex.get(k)
        a = ab.get(k, {})
        if not c["in_bib"] or e is None:
            exists, mm, src, sup, rat, doi = "no", "cite key has no bib entry", "", "no_abstract", "", ""
        else:
            entry = next(x for x in cit["entries"] if x["key"] == k)
            doi = ((e.get("matched") or {}).get("doi") or entry["fields"].get("doi", ""))
            exists, mm = e["exists"], e["metadata_match"]
            src = a.get("source", "none")
            if exists != "yes" or not a.get("abstract"):
                sup, rat = "no_abstract", ("reference failed existence check" if exists != "yes" else "no abstract found")
            else:
                j = support.get(task_id(k, c["sentence"]))
                if j is None:
                    errs.append(f"no support judgment for {k} at line {c['tex_line']} (task {task_id(k, c['sentence'])})")
                    sup, rat = "", "PENDING support check"
                else:
                    sup, rat = j["support"], j.get("rationale", "")
        rows.append({"cite_key": k, "sentence": c["sentence"], "tex_line": c["tex_line"], "doi": doi,
                     "exists": exists, "metadata_match": mm, "abstract_source": src, "support": sup,
                     "rationale": rat,
                     "author_signoff": previous.get((k, str(c["tex_line"]), c["sentence"]), "")})
    write_csv(out_csv, COLUMNS, rows)

    flagged = [r for r in rows if r["exists"] != "yes" or r["support"] != "supports"]
    unsigned = [r for r in flagged if not r["author_signoff"].strip()]
    rep = cit["report"]
    failed_refs = sorted({k for k, e in ex.items() if e["exists"] != "yes"})
    md = ["# Citation audit report", "",
          f"- Citation uses: {len(rows)}; flagged: {len(flagged)}; flagged without sign-off: {len(unsigned)}",
          f"- References failing existence check: {', '.join(failed_refs) or 'none'}",
          f"- `\\cite` keys with no bib entry: {', '.join(rep['missing_bib_entries']) or 'none'}",
          f"- Bib entries never cited: {', '.join(rep['uncited_bib_entries']) or 'none'}",
          "- Closest prior work (notes.md) not cited:"]
    md += [f"  - {p}" for p in rep["prior_work_not_cited"]] or ["  - none"]
    md += ["", "## Flagged rows", "", "| key | line | exists | support | rationale | sign-off |", "|---|---|---|---|---|---|"]
    for r in flagged:
        md.append(f"| {r['cite_key']} | {r['tex_line']} | {r['exists']} | {r['support']} | "
                  f"{r['rationale'][:100].replace('|', '/')} | {r['author_signoff'] or '—'} |")
    rp = guard_output(audits / "citation_report.md")
    rp.write_text("\n".join(md) + "\n", encoding="utf-8")
    for e in errs:
        print(f"FAIL {e}")
    print(f"citation audit: {len(rows)} rows, {len(flagged)} flagged, {len(unsigned)} unsigned -> {out_csv}")
    problems = errs or unsigned or failed_refs or rep["missing_bib_entries"]
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tasks", help="write support_tasks.jsonl")
    t.add_argument("--audits", required=True, type=Path)
    b = sub.add_parser("build", help="assemble citation_audit.csv")
    b.add_argument("--audits", required=True, type=Path)
    b.add_argument("--out", type=Path)
    a = ap.parse_args()
    return cmd_tasks(a.audits) if a.cmd == "tasks" else cmd_build(a.audits, a.out)


if __name__ == "__main__":
    run_main(main)
