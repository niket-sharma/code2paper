#!/usr/bin/env python3
"""Fill final/REVIEW.md from the audits, gap decisions and notes.

Example:
    python build_review.py --workspace workspace/
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from c2p.common import C2PError, guard_output, read_csv, run_main  # noqa: E402
from c2p.notes import parse_notes  # noqa: E402

TEMPLATE = Path(__file__).resolve().parents[3] / "templates" / "REVIEW.md"


def md_table(rows: list[dict[str, str]], cols: list[str], limit: int = 200) -> str:
    if not rows:
        return "_None._"
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows[:limit]:
        out.append("| " + " | ".join(str(r.get(c, "")).replace("|", "/").replace("\n", " ")[:160] for c in cols) + " |")
    if len(rows) > limit:
        out.append(f"\n_{len(rows) - limit} more rows in the CSV._")
    return "\n".join(out)


def build(ws: Path) -> tuple[str, int]:
    meta = json.loads((ws / "workspace.json").read_text()) if (ws / "workspace.json").exists() else {}
    notes = parse_notes(ws / "notes.md") if (ws / "notes.md").exists() else None
    num_path, cit_path = ws / "audits" / "numbers_audit.csv", ws / "audits" / "citation_audit.csv"
    nums = read_csv(num_path) if num_path.exists() else []
    cits = read_csv(cit_path) if cit_path.exists() else []
    comp_path = ws / "audits" / "compile_report.json"
    comp = json.loads(comp_path.read_text()) if comp_path.exists() else {}
    num_flag = [r for r in nums if r["status"] in {"unmatched", "conflict"}]
    cit_flag = [r for r in cits if r["exists"] != "yes" or r["support"] != "supports"]
    signed = [r for r in cit_flag if r.get("author_signoff", "").strip()]
    refs_missing = sorted({r["cite_key"] for r in cits if r["exists"] != "yes"})
    gap = ws / "evidence" / "gap_decisions.md"
    disclosure = (notes.ai_disclosure if notes else "") or "_Missing: add an AI-use disclosure to notes.md._"
    vals = {
        "title": (notes.title if notes else "") or "Untitled",
        "date": dt.date.today().isoformat(),
        "workspace": str(ws),
        "commit": meta.get("repo_commit", "") or "unknown",
        "n_numbers": str(len(nums)),
        "n_num_ok": str(sum(r["status"] in {"matched", "rounding_ok", "derived_ok"} for r in nums)),
        "n_num_ignored": str(sum(r["status"] == "ignored" for r in nums)),
        "n_num_flagged": str(len(num_flag)),
        "n_cites": str(len(cits)),
        "n_cite_flagged": str(len(cit_flag) - len(signed)),
        "n_cite_signed": str(len(signed)),
        "n_ref_missing": f"{len(refs_missing)}" + (f" ({', '.join(refs_missing)})" if refs_missing else ""),
        "compile_status": comp.get("status", "not run") + (f", {comp.get('pages')} pages" if comp.get("pages") else ""),
        "limits_status": "; ".join(comp.get("over_limits", [])) or ("within limits" if comp else "not checked"),
        "numbers_table": md_table(num_flag, ["tex_file", "line", "value_in_paper", "status", "evidence_id", "note"]),
        "citations_table": md_table(cit_flag, ["cite_key", "tex_line", "exists", "support", "rationale", "author_signoff"]),
        "gap_decisions": gap.read_text(encoding="utf-8").strip() if gap.exists() else "_No gap decisions recorded._",
        "ai_disclosure": disclosure,
    }
    text = TEMPLATE.read_text(encoding="utf-8")
    for k, v in vals.items():
        text = text.replace("{{" + k + "}}", v)
    open_items = len(num_flag) + len(cit_flag) - len(signed)
    return text, open_items


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", required=True, type=Path)
    ap.add_argument("--out", type=Path, help="default: <workspace>/final/REVIEW.md")
    a = ap.parse_args()
    ws = a.workspace.resolve()
    if not ws.is_dir():
        raise C2PError(f"workspace not found: {ws}")
    text, open_items = build(ws)
    out = guard_output(a.out or ws / "final" / "REVIEW.md", ws)
    out.write_text(text, encoding="utf-8")
    print(f"REVIEW.md written ({open_items} open item(s)) -> {out}")
    return 0


if __name__ == "__main__":
    run_main(main)
