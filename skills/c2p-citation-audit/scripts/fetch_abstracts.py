#!/usr/bin/env python3
"""Fetch an abstract for every bib entry that passed the existence check.

Order: Semantic Scholar (by DOI, arXiv ID or S2 paper ID; also reuses an
abstract returned during the existence check), then OpenAlex (DOI), then arXiv.
Records the source. Entries with no abstract get source `none` and are marked
`no_abstract` in the support check (author must verify).

Example:
    python fetch_abstracts.py --existence workspace/audits/existence.json \\
        --cache-dir workspace/audits/cache --out workspace/audits/abstracts.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from c2p.common import C2PError, run_main, write_json  # noqa: E402
from c2p.http import CachedClient  # noqa: E402
from c2p.scholar import arxiv_abstract, openalex_abstract, openalex_search, s2_paper, title_sim  # noqa: E402


def fetch(client: CachedClient, res: dict[str, Any]) -> dict[str, str]:
    m = res.get("matched") or {}
    if res.get("exists") != "yes":
        return {"abstract": "", "source": "none", "note": f"exists={res.get('exists')}"}
    if res.get("matched_abstract") and m.get("source") == "semantic_scholar":
        return {"abstract": res["matched_abstract"], "source": "semantic_scholar"}
    for ident in ([f"DOI:{m['doi']}"] if m.get("doi") else []) + ([f"ARXIV:{m['arxiv']}"] if m.get("arxiv") else []) + (
        [m["s2_id"]] if m.get("s2_id") else []
    ):
        p = s2_paper(client, ident)
        if p and p.get("abstract"):
            return {"abstract": p["abstract"], "source": "semantic_scholar"}
        if p and p.get("arxiv") and not m.get("arxiv"):
            m = {**m, "arxiv": p["arxiv"]}
    if m.get("doi"):
        a = openalex_abstract(client, m["doi"])
        if a:
            return {"abstract": a, "source": "openalex"}
    if m.get("arxiv"):
        a = arxiv_abstract(client, m["arxiv"])
        if a:
            return {"abstract": a, "source": "arxiv"}
    if res.get("matched_abstract"):
        return {"abstract": res["matched_abstract"], "source": m.get("source", "crossref")}
    if m.get("title"):  # no DOI/arXiv route worked: OpenAlex title search, strict title match
        for c in openalex_search(client, m["title"], limit=3):
            if c.get("abstract") and title_sim(c["title"], m["title"]) >= 0.95:
                return {"abstract": c["abstract"], "source": "openalex"}
    return {"abstract": "", "source": "none", "note": "no abstract found"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--existence", required=True, type=Path)
    ap.add_argument("--cache-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    if not a.existence.exists():
        raise C2PError(f"not found: {a.existence}")
    results = json.loads(a.existence.read_text())["results"]
    client = CachedClient(a.cache_dir, offline=a.offline)
    out = {k: fetch(client, r) for k, r in results.items()}
    write_json(a.out, {"abstracts": out, "network_calls": client.network_calls})
    for k, v in out.items():
        print(f"{k}: {v['source']} ({len(v['abstract'])} chars)")
    print(f"network calls this run: {client.network_calls}; failed or uncached requests: {len(client.failures)}")
    return 0


if __name__ == "__main__":
    run_main(main)
