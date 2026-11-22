#!/usr/bin/env python3
"""Report which code2paper steps are done in a workspace and which step to run next.

A step is done when its output files exist and are newer than its inputs.
Author decision points are done when the author's decision file exists
(evidence/gap_decisions.md, final/SIGNOFF.md).

Example:
    python pipeline_status.py --workspace workspace/ [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from c2p.common import C2PError, run_main  # noqa: E402

# (step id, name, outputs, inputs)
STEPS = [
    ("0", "init workspace", ["workspace.json", "notes.md", "repo"], []),
    ("1", "c2p-repo-ingest", ["evidence/inventory.json", "evidence/evidence_map.csv", "inputs/idea.md",
                              "inputs/experimental_log.md"], ["notes.md"]),
    ("2", "c2p-gap-check", ["evidence/gap_report.md"], ["evidence/evidence_map.csv", "notes.md"]),
    ("2a", "AUTHOR DECISION on gaps", ["evidence/gap_decisions.md"], ["evidence/gap_report.md"]),
    ("3", "paper-orchestra (upstream)", ["paper/final/paper.tex"], ["evidence/gap_decisions.md",
                                                                    "inputs/experimental_log.md"]),
    ("4", "c2p-numbers-audit", ["audits/numbers_audit.csv"], ["paper/final/paper.tex", "evidence/evidence_map.csv"]),
    ("5", "c2p-citation-audit", ["audits/citation_audit.csv"], ["paper/final/paper.tex"]),
    ("6", "c2p-compile-check", ["audits/compile_report.json", "final/overleaf.zip"], ["paper/final/paper.tex"]),
    ("7", "REVIEW.md", ["final/REVIEW.md"], ["audits/numbers_audit.csv", "audits/citation_audit.csv",
                                            "audits/compile_report.json"]),
    ("7a", "AUTHOR SIGN-OFF", ["final/SIGNOFF.md"], ["final/REVIEW.md"]),
]


def mtime(p: Path) -> float:
    return p.stat().st_mtime if p.exists() else 0.0


def status(ws: Path) -> list[dict]:
    out = []
    for sid, name, outputs, inputs in STEPS:
        missing = [o for o in outputs if not (ws / o).exists()]
        newest_in = max((mtime(ws / i) for i in inputs), default=0.0)
        oldest_out = min((mtime(ws / o) for o in outputs), default=0.0)
        if missing:
            st = "todo"
        elif newest_in > oldest_out + 1:
            st = "stale"
        else:
            st = "done"
        out.append({"step": sid, "name": name, "status": st, "missing": missing})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", required=True, type=Path)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    ws = a.workspace.resolve()
    if not ws.is_dir():
        raise C2PError(f"workspace not found: {ws}")
    st = status(ws)
    nxt = next((s for s in st if s["status"] != "done"), None)
    if a.json:
        print(json.dumps({"steps": st, "next": nxt}, indent=2))
        return 0
    for s in st:
        extra = f" (missing: {', '.join(s['missing'])})" if s["missing"] else ""
        print(f"[{s['status']:5}] {s['step']:>2} {s['name']}{extra}")
    print(f"\nnext: {nxt['step']} {nxt['name']}" if nxt else "\nall steps done")
    return 0


if __name__ == "__main__":
    run_main(main)
