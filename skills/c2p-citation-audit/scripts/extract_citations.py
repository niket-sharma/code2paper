#!/usr/bin/env python3
"""Parse the .bib file and every \\cite* in the manuscript with its full sentence.

Writes citations.json with: bib entries, one record per (cite key, sentence),
bib entries never cited, cite keys with no bib entry, and (with --notes) papers
from the notes' "Closest prior work" list that are not cited.

Example:
    python extract_citations.py --tex workspace/paper/final/paper.tex --bib workspace/paper/refs.bib \\
        --notes workspace/notes.md --out workspace/audits/citations.json
"""

from __future__ import annotations

import argparse
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from c2p.common import C2PError, read_text, run_main, write_json  # noqa: E402
from c2p.latex import (  # noqa: E402
    bib_plain,
    clean_prose,
    load_document,
    parse_bib,
    sentence_bounds,
    strip_for_sentences,
)
from c2p.notes import parse_notes  # noqa: E402

CITE_CMDS = [
    "cite", "citep", "citet", "citealp", "citealt", "citeauthor", "citeyear", "citeyearpar",
    "parencite", "textcite", "autocite", "footcite", "supercite", "Cite", "Citep", "Citet",
    "Parencite", "Textcite", "Autocite", "nocite",
]
CITE_RE = re.compile(r"\\(" + "|".join(CITE_CMDS) + r")\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]*)\}")


def norm_title(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", bib_plain(s).lower()).strip()


def find_bib_files(tex_files: list, explicit: list[Path]) -> list[Path]:
    if explicit:
        return explicit
    out = []
    for tf in tex_files:
        for m in re.finditer(r"\\(?:bibliography|addbibresource)\{([^}]+)\}", tf.text):
            for name in m.group(1).split(","):
                p = tf.path.parent / name.strip()
                if p.suffix != ".bib":
                    p = p.with_suffix(".bib")
                out.append(p)
    return out


def extract(tex: Path, bibs: list[Path], notes: Path | None) -> dict:
    files = load_document(tex)
    bib_paths = find_bib_files(files, bibs)
    if not bib_paths:
        raise C2PError("no .bib file given and no \\bibliography{} found")
    entries = []
    for bp in bib_paths:
        if not bp.exists():
            raise C2PError(f"bib file not found: {bp}")
        for e in parse_bib(read_text(bp)):
            entries.append({"key": e.key, "type": e.type, "fields": e.fields, "bib_file": bp.name, "line": e.line})
    keys = {e["key"] for e in entries}

    cites = []
    nocite_all = False
    for tf in files:
        text = strip_for_sentences(tf)
        for m in CITE_RE.finditer(text):
            if m.group(1) == "nocite":
                nocite_all = nocite_all or "*" in m.group(2)
                continue
            s, e = sentence_bounds(text, m.start())
            raw = text[s:e]
            # show other citations in the sentence as [key] so the sentence stays readable
            shown = CITE_RE.sub(lambda mm: "[" + mm.group(2).replace(" ", "") + "]", raw)
            sentence = clean_prose(shown)
            for key in [k.strip() for k in m.group(2).split(",") if k.strip()]:
                cites.append(
                    {
                        "cite_key": key,
                        "sentence": sentence,
                        "tex_file": tf.rel,
                        "tex_line": tf.lines.line_of(m.start()),
                        "command": m.group(1),
                        "in_bib": key in keys,
                    }
                )
    cited = {c["cite_key"] for c in cites}
    report = {
        "uncited_bib_entries": [] if nocite_all else sorted(keys - cited),
        "missing_bib_entries": sorted(cited - keys),
        "prior_work_not_cited": [],
    }
    if notes:
        n = parse_notes(notes)
        cited_entries = [e for e in entries if e["key"] in cited]
        for pw in n.prior_work:
            hit = None
            for e in cited_entries:
                f = e["fields"]
                doi = f.get("doi", "").lower()
                arx = f.get("eprint", "") or re.sub(r"^.*arxiv[:./]", "", f.get("journal", "") + f.get("url", ""), flags=re.I)
                if (pw.doi and doi and pw.doi == doi) or (pw.arxiv and pw.arxiv.split("v")[0] in arx):
                    hit = e["key"]
                    break
                t = norm_title(f.get("title", ""))
                if t and len(t) > 15 and SequenceMatcher(None, t, norm_title(pw.text)).find_longest_match().size >= max(15, int(0.6 * len(t))):
                    hit = e["key"]
                    break
            if hit is None:
                report["prior_work_not_cited"].append(pw.text)
    return {"bib_files": [str(p) for p in bib_paths], "entries": entries, "cites": cites, "report": report}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tex", required=True, type=Path)
    ap.add_argument("--bib", type=Path, action="append", default=[], help="repeatable; default: from \\bibliography")
    ap.add_argument("--notes", type=Path, help="notes.md, to check closest prior work is cited")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    data = extract(a.tex, a.bib, a.notes)
    write_json(a.out, data)
    r = data["report"]
    print(
        f"{len(data['entries'])} bib entries, {len(data['cites'])} citation uses; "
        f"uncited={r['uncited_bib_entries']} missing={r['missing_bib_entries']} "
        f"prior_work_not_cited={len(r['prior_work_not_cited'])}"
    )
    return 0


if __name__ == "__main__":
    run_main(main)
