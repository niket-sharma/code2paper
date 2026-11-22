"""Scholarly API lookups (Crossref, Semantic Scholar, OpenAlex, arXiv) and metadata comparison."""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from typing import Any

from .http import CachedClient
from .latex import bib_plain, first_author_last

S2 = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = "title,authors,year,externalIds,venue,abstract"


def norm(s: str) -> str:
    s = bib_plain(s).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def title_sim(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def norm_name(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())


def candidate_from_crossref(item: dict[str, Any]) -> dict[str, Any]:
    authors = item.get("author") or []
    year = None
    for k in ("published-print", "published-online", "issued", "created"):
        parts = (item.get(k) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            year = parts[0][0]
            break
    title = (item.get("title") or [""])[0]
    sub = (item.get("subtitle") or [""])[0]
    if sub and sub.lower() not in title.lower():
        title = f"{title}: {sub}"
    return {
        "source": "crossref",
        "title": title,
        "first_author": (authors[0].get("family") or authors[0].get("name") or "") if authors else "",
        "year": year,
        "doi": (item.get("DOI") or "").lower(),
        "abstract": re.sub(r"<[^>]+>", " ", item.get("abstract") or "").strip(),
    }


def candidate_from_s2(p: dict[str, Any]) -> dict[str, Any]:
    authors = p.get("authors") or []
    ext = p.get("externalIds") or {}
    name = authors[0].get("name", "") if authors else ""
    return {
        "source": "semantic_scholar",
        "title": p.get("title") or "",
        "first_author": name.split()[-1] if name.split() else "",
        "year": p.get("year"),
        "doi": (ext.get("DOI") or "").lower(),
        "arxiv": ext.get("ArXiv") or "",
        "s2_id": p.get("paperId") or "",
        "abstract": p.get("abstract") or "",
    }


def crossref_doi(client: CachedClient, doi: str) -> dict[str, Any] | None:
    r = client.get(f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='/:')}")
    if r.status != 200:
        return None
    msg = (r.json() or {}).get("message")  # type: ignore[union-attr]
    return candidate_from_crossref(msg) if msg else None


def crossref_search(client: CachedClient, title: str, author: str, rows: int = 5) -> list[dict[str, Any]]:
    q = urllib.parse.urlencode({"query.bibliographic": f"{title} {author}".strip(), "rows": rows})
    r = client.get(f"https://api.crossref.org/works?{q}")
    if r.status != 200:
        return []
    items = ((r.json() or {}).get("message") or {}).get("items") or []  # type: ignore[union-attr]
    return [candidate_from_crossref(i) for i in items]


def s2_search(client: CachedClient, title: str, limit: int = 5) -> list[dict[str, Any]]:
    q = urllib.parse.urlencode({"query": norm(title)[:300], "limit": limit, "fields": S2_FIELDS})
    r = client.get(f"{S2}/paper/search?{q}")
    if r.status != 200:
        return []
    return [candidate_from_s2(p) for p in ((r.json() or {}).get("data") or [])]  # type: ignore[union-attr]


def s2_paper(client: CachedClient, ident: str) -> dict[str, Any] | None:
    r = client.get(f"{S2}/paper/{urllib.parse.quote(ident, safe=':')}?fields={S2_FIELDS}")
    if r.status != 200:
        return None
    return candidate_from_s2(r.json())  # type: ignore[arg-type]


def candidate_from_openalex(w: dict[str, Any]) -> dict[str, Any]:
    auths = w.get("authorships") or []
    name = ((auths[0].get("author") or {}).get("display_name") or "") if auths else ""
    ids = w.get("ids") or {}
    return {
        "source": "openalex",
        "title": w.get("display_name") or w.get("title") or "",
        "first_author": name.split()[-1] if name.split() else "",
        "year": w.get("publication_year"),
        "doi": (w.get("doi") or "").lower().removeprefix("https://doi.org/"),
        "openalex_id": ids.get("openalex", ""),
        "abstract": _inverted_to_text(w.get("abstract_inverted_index")),
    }


def _inverted_to_text(inv: dict[str, list[int]] | None) -> str:
    if not inv:
        return ""
    pos: dict[int, str] = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))


def openalex_search(client: CachedClient, title: str, limit: int = 5) -> list[dict[str, Any]]:
    q = urllib.parse.urlencode({"search": norm(title)[:300], "per-page": limit})
    r = client.get(f"https://api.openalex.org/works?{q}")
    if r.status != 200:
        return []
    return [candidate_from_openalex(w) for w in ((r.json() or {}).get("results") or [])]  # type: ignore[union-attr]


def arxiv_lookup(client: CachedClient, arxiv_id: str) -> dict[str, Any] | None:
    r = client.get(f"http://export.arxiv.org/api/query?id_list={urllib.parse.quote(arxiv_id)}")
    if r.status != 200 or not r.body:
        return None
    try:
        root = ET.fromstring(r.body)
    except ET.ParseError:
        return None
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("a:entry", ns):
        title = re.sub(r"\s+", " ", entry.findtext("a:title", "", ns) or "").strip()
        if not title or title.lower() == "error":
            continue
        author = entry.find("a:author/a:name", ns)
        name = author.text if author is not None and author.text else ""
        pub = entry.findtext("a:published", "", ns) or ""
        return {
            "source": "arxiv",
            "title": title,
            "first_author": name.split()[-1] if name.split() else "",
            "year": int(pub[:4]) if pub[:4].isdigit() else None,
            "doi": "",
            "arxiv": arxiv_id,
            "abstract": re.sub(r"\s+", " ", entry.findtext("a:summary", "", ns) or "").strip(),
        }
    return None


def openalex_abstract(client: CachedClient, doi: str) -> str:
    r = client.get(f"https://api.openalex.org/works/doi:{urllib.parse.quote(doi, safe='/:')}")
    if r.status != 200:
        return ""
    return _inverted_to_text((r.json() or {}).get("abstract_inverted_index"))  # type: ignore[union-attr]


def arxiv_abstract(client: CachedClient, arxiv_id: str) -> str:
    r = client.get(f"http://export.arxiv.org/api/query?id_list={urllib.parse.quote(arxiv_id)}")
    if r.status != 200 or not r.body:
        return ""
    try:
        root = ET.fromstring(r.body)
    except ET.ParseError:
        return ""
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("a:entry", ns):
        s = entry.find("a:summary", ns)
        if s is not None and s.text and "Error" not in (entry.findtext("a:title", "", ns) or ""):
            return re.sub(r"\s+", " ", s.text).strip()
    return ""


def bib_arxiv_id(fields: dict[str, str]) -> str:
    if fields.get("eprint") and re.match(r"^(\d{4}\.\d{4,5}|[a-z\-]+/\d{7})(v\d+)?$", fields["eprint"].strip()):
        return fields["eprint"].strip()
    for k in ("journal", "url", "note", "volume", "howpublished"):
        m = re.search(r"arxiv[:./\s]*(?:abs/)?(\d{4}\.\d{4,5})", fields.get(k, ""), re.I)
        if m:
            return m.group(1)
    return ""


def compare(entry: dict[str, str], cand: dict[str, Any]) -> dict[str, Any]:
    t = title_sim(entry.get("title", ""), cand.get("title", ""))
    ea = norm_name(first_author_last(entry.get("author", "")))
    ca = norm_name(cand.get("first_author", ""))
    author_ok = bool(ea and ca and (ea == ca or ea in ca or ca in ea))
    try:
        ey = int(re.sub(r"\D", "", entry.get("year", ""))[:4])
    except ValueError:
        ey = None
    cy = cand.get("year")
    year_ok = ey is not None and cy is not None and abs(int(cy) - ey) <= 1
    return {"title_sim": round(t, 3), "author_ok": author_ok, "year_ok": year_ok,
            "year_exact": ey is not None and cy == ey}


def verdict(cmp: dict[str, Any]) -> str:
    if cmp["title_sim"] >= 0.9 and (cmp["author_ok"] or cmp["year_ok"]):
        return "yes"
    if cmp["title_sim"] >= 0.75:
        return "ambiguous"
    return "no"
