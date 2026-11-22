#!/usr/bin/env python3
"""Check that every bib entry exists: DOI lookup in Crossref, else title search in Crossref
and Semantic Scholar. Compares title, first author and year -> exists = yes / no / ambiguous.

Responses are cached on disk (--cache-dir); a rerun makes no network calls.
--offline fails on any uncached request. Set SEMANTIC_SCHOLAR_API_KEY for a
higher S2 rate limit and --mailto (or C2P_MAILTO) for Crossref's polite pool.

Example:
    python verify_existence.py --citations workspace/audits/citations.json \\
        --cache-dir workspace/audits/cache --out workspace/audits/existence.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from c2p.common import C2PError, run_main, write_json  # noqa: E402
from c2p.http import CachedClient  # noqa: E402
from c2p.latex import bib_plain, first_author_last  # noqa: E402
from c2p.scholar import (  # noqa: E402
    arxiv_lookup,
    bib_arxiv_id,
    compare,
    crossref_doi,
    crossref_search,
    openalex_search,
    s2_paper,
    s2_search,
    verdict,
)

RANK = {"yes": 2, "ambiguous": 1, "no": 0}


def check_entry(client: CachedClient, fields: dict[str, str]) -> dict[str, Any]:
    n_fail = len(client.failures)
    title = bib_plain(fields.get("title", ""))
    notes: list[str] = []
    cands: list[dict[str, Any]] = []
    if not title:
        return {"exists": "ambiguous", "metadata_match": "bib entry has no title", "candidates_checked": 0}
    doi = fields.get("doi", "").strip().lower().removeprefix("https://doi.org/")
    if doi:
        c = crossref_doi(client, doi)
        if c:
            cands.append(c)
        else:
            notes.append(f"DOI {doi} not found in Crossref")
    arx = bib_arxiv_id(fields)
    if arx:
        c = s2_paper(client, f"ARXIV:{arx}") or arxiv_lookup(client, arx)
        if c:
            cands.append(c)
        else:
            notes.append(f"arXiv {arx} not found")

    def best_of(cs: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
        best: tuple[str, dict[str, Any] | None, dict[str, Any] | None] = ("no", None, None)
        for c in cs:
            cmp = compare(fields, c)
            v = verdict(cmp)
            if best[1] is None or (RANK[v], cmp["title_sim"]) > (RANK[best[0]], best[2]["title_sim"]):  # type: ignore[index]
                best = (v, c, cmp)
        return best

    v, c, cmp = best_of(cands)
    if v != "yes":
        author = first_author_last(fields.get("author", ""))
        cands += crossref_search(client, title, author)
        v, c, cmp = best_of(cands)
    if v != "yes":
        cands += s2_search(client, title)
        v, c, cmp = best_of(cands)
    if v != "yes":
        cands += openalex_search(client, title)
        v, c, cmp = best_of(cands)
    failed = client.failures[n_fail:]
    if failed and v == "no":
        v = "ambiguous"
        notes.append("lookup incomplete (HTTP " + ",".join(str(st) for _, st in failed)
                     + "); rerun later or set SEMANTIC_SCHOLAR_API_KEY")
    if doi and c and c.get("doi") and c["doi"] != doi and v == "yes":
        notes.append(f"bib DOI {doi} differs from matched DOI {c['doi']}")
    if doi and cands and cands[0].get("source") == "crossref" and cands[0].get("doi") == doi:
        first = compare(fields, cands[0])
        if first["title_sim"] < 0.75:
            notes.append(f"DOI resolves to a different work: {cands[0]['title'][:80]!r}")
            if v == "yes" and c is not cands[0]:
                v = "ambiguous"
    parts = []
    if cmp:
        parts.append(f"title={cmp['title_sim']:.2f}")
        parts.append("first_author=" + ("ok" if cmp["author_ok"] else f"MISMATCH({c.get('first_author', '') if c else ''})"))
        parts.append("year=" + ("ok" if cmp["year_exact"] else ("±1" if cmp["year_ok"] else f"MISMATCH({c.get('year') if c else ''})")))
        parts.append(f"via={c['source'] if c else ''}")
    else:
        parts.append("no candidates found")
    return {
        "exists": v,
        "metadata_match": "; ".join(parts + notes),
        "matched": {k: c.get(k) for k in ("source", "title", "first_author", "year", "doi", "arxiv", "s2_id")} if c else None,
        "matched_abstract": (c or {}).get("abstract", "") if v == "yes" else "",
        "candidates_checked": len(cands),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--citations", required=True, type=Path, help="citations.json from extract_citations.py")
    ap.add_argument("--cache-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--offline", action="store_true", help="use cached responses only")
    ap.add_argument("--mailto", default=os.environ.get("C2P_MAILTO"), help="contact address for Crossref")
    a = ap.parse_args()
    if not a.citations.exists():
        raise C2PError(f"not found: {a.citations}")
    data = json.loads(a.citations.read_text())
    client = CachedClient(a.cache_dir, offline=a.offline, mailto=a.mailto)
    out: dict[str, Any] = {}
    for e in data["entries"]:
        res = check_entry(client, e["fields"])
        out[e["key"]] = res
        print(f"{e['key']}: {res['exists']} — {res['metadata_match']}")
    write_json(a.out, {"results": out, "network_calls": client.network_calls})
    print(f"existence check done; network calls this run: {client.network_calls}; "
          f"failed or uncached requests: {len(client.failures)}")
    return 0


if __name__ == "__main__":
    run_main(main)
