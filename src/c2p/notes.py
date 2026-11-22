"""Parse the author's notes.md (data contract 5.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

SECTIONS = {
    "working title": "title",
    "target journal": "journal",
    "novelty claim": "novelty",
    "key results": "key_results",
    "closest prior work": "prior_work",
    "out of scope / limitations": "limitations",
    "out of scope": "limitations",
    "limitations": "limitations",
    "authors, affiliations, funding, ai-use disclosure": "authors",
    "authors": "authors",
}

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s,;\]\)>]+)", re.I)
ARXIV_RE = re.compile(r"(?:arxiv[:\s/]*|arxiv\.org/abs/)(\d{4}\.\d{4,5}(?:v\d+)?|[a-z\-]+/\d{7})", re.I)
PATH_RE = re.compile(r"`([^`]+)`|\(([^()\s]+\.[A-Za-z0-9]{1,6}(?::\d+)?)\)|\b([\w./-]+/[\w.-]+\.[A-Za-z0-9]{1,6})\b")


@dataclass
class PriorWork:
    text: str
    doi: str = ""
    arxiv: str = ""


@dataclass
class KeyResult:
    text: str
    files: list[str] = field(default_factory=list)


@dataclass
class Notes:
    sections: dict[str, str]
    title: str = ""
    journal: str = ""
    novelty: str = ""
    key_results: list[KeyResult] = field(default_factory=list)
    prior_work: list[PriorWork] = field(default_factory=list)
    limitations: str = ""
    authors: str = ""
    guidelines: str = ""

    @property
    def ai_disclosure(self) -> str:
        m = re.search(r"AI[- ]use(?: disclosure)?\s*[:\-—]\s*(.+?)(?:\n\s*\n|\Z)", self.authors, re.I | re.S)
        return m.group(1).strip() if m else ""

    def blocking_problems(self) -> list[str]:
        probs = []
        if not self.novelty:
            probs.append("Novelty claim is empty")
        if not self.journal:
            probs.append("Target journal is empty")
        return probs


def _strip_comments(s: str) -> str:
    return re.sub(r"<!--.*?-->", "", s, flags=re.S).strip()


def _bullets(s: str) -> list[str]:
    items: list[str] = []
    for line in s.splitlines():
        m = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$", line)
        if m:
            items.append(m.group(1).strip())
        elif items and line.strip() and line.startswith((" ", "\t")):
            items[-1] += " " + line.strip()
    return [i for i in items if i]


def parse_notes(path: Path) -> Notes:
    text = path.read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    cur = None
    buf: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if cur:
                sections[cur] = _strip_comments("\n".join(buf))
            heading = re.sub(r"\s*\(.*\)\s*$", "", m.group(1)).strip().lower()
            cur = SECTIONS.get(heading, heading)
            buf = []
        elif cur:
            buf.append(line)
    if cur:
        sections[cur] = _strip_comments("\n".join(buf))

    n = Notes(sections=sections)
    n.title = sections.get("title", "")
    journal = sections.get("journal", "")
    gm = re.search(r"^\s*Guidelines\s*:\s*(\S+)\s*$", journal, re.M | re.I)
    if gm:
        n.guidelines = gm.group(1)
        journal = (journal[: gm.start()] + journal[gm.end() :]).strip()
    n.journal = journal
    n.novelty = sections.get("novelty", "")
    n.limitations = sections.get("limitations", "")
    n.authors = sections.get("authors", "")
    for b in _bullets(sections.get("key_results", "")):
        files = []
        for m in PATH_RE.finditer(b):
            f = next(g for g in m.groups() if g)
            if "." in Path(f.split(":")[0]).name:
                files.append(f.split(":")[0])
        n.key_results.append(KeyResult(b, files))
    for b in _bullets(sections.get("prior_work", "")):
        doi = DOI_RE.search(b)
        ax = ARXIV_RE.search(b)
        n.prior_work.append(
            PriorWork(b, doi.group(1).rstrip(".").lower() if doi else "", ax.group(1) if ax else "")
        )
    return n
