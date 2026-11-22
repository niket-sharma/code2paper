#!/usr/bin/env python3
"""Extract every number from a LaTeX manuscript with file, line and context.

Strips comments, preamble, \\cite/\\ref/\\label, bibliography, graphics options
and lengths, then extracts numbers from prose, tables and captions. Default
ignore rules (kept as `ignored` with a reason): years in citation context,
section/figure/table numbering, small integer counts in prose, identifiers
such as ResNet-50 or A100.

Example:
    python extract_numbers.py --tex workspace/paper/final/paper.tex --out workspace/audits/numbers.json
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from c2p.common import C2PError, run_main, write_json  # noqa: E402
from c2p.latex import (  # noqa: E402
    TexFile,
    blank_spans,
    clean_prose,
    command_spans,
    env_spans,
    find_brace_end,
    load_document,
    sentence_bounds,
    strip_comments,
    strip_for_numbers,
)

NUMBER = re.compile(
    r"(?<![\d.])(?:\d{1,3}(?:(?:,|\{,\})\d{3})+|\d+)(?:\.\d+)?(?![\d])|(?<![\w.])\.\d+"
)
SCI = re.compile(
    r"(?:(?P<mant>\d+(?:\.\d+)?)\s*(?:\\times|\\cdot|x)\s*)?10\s*\^\s*\{?\s*(?P<exp>[-−]?\s*\d+)\s*\}?"
)
UNIT_SUFFIX = re.compile(r"^(?:s|ms|x|k|K|M|B|GB|MB|h|min)\b")
NUMBERING_WORDS = re.compile(
    r"(?:Section|Sections|Sec\.|Figure|Figures|Fig\.|Figs\.|Table|Tables|Tab\.|Eq\.|Eqs\.|Equation|"
    r"Appendix|Chapter|Step|Algorithm|Line|Stage|Phase|Lemma|Theorem|Definition|Proposition|"
    r"Corollary|Remark|Example|Part|Item|Hypothesis|RQ|Q)\s*~?\s*\(?$",
    re.I,
)
CLAUSE_SPLIT = re.compile(
    r"[,;:()]|\b(?:versus|vs\.?|compared (?:with|to)|whereas|while|but|than|against|relative to)\b", re.I
)
CITE_CONTEXT = re.compile(r"\\cite\w*|et al\.?|\(\s*\d{4}\s*\)", re.I)
TABULAR_ENVS = ("tabular", "tabular*", "tabularx", "longtable")
SMALL_COUNT_MAX = 10


def words(s: str) -> list[str]:
    return clean_prose(s).split()


def table_cells(text: str) -> list[dict]:
    """For each tabular env: list of rows, each a list of (start, end, cell_text)."""
    tables = []
    for env in TABULAR_ENVS:
        for s, e in env_spans(text, env):
            body_start = text.find("}", s) + 1
            # skip column spec {..}
            j = body_start
            while j < e and text[j] in " \t\n":
                j += 1
            if j < e and text[j] in "[{":
                if text[j] == "[":
                    j = text.find("]", j) + 1
                if j < e and text[j] == "{":
                    j = find_brace_end(text, j)
            rows = []
            row_start = j
            for m in re.finditer(r"\\\\(?:\[[^\]]*\])?|\\end\{" + re.escape(env) + r"\}", text[j:e + 1]):
                rs, re_ = row_start, j + m.start()
                cells = []
                cs = rs
                for cm in re.finditer(r"(?<!\\)&", text[rs:re_]):
                    cells.append((cs, rs + cm.start(), text[cs : rs + cm.start()]))
                    cs = rs + cm.end()
                cells.append((cs, re_, text[cs:re_]))
                rows.append(cells)
                row_start = j + m.end()
            tables.append({"span": (s, e), "rows": rows})
    return tables


def clean_cell(s: str) -> str:
    s = re.sub(r"\\(?:toprule|midrule|bottomrule|hline|cline\{[^}]*\}|cmidrule(?:\([^)]*\))?\{[^}]*\})", " ", s)
    s = re.sub(r"\\multicolumn\{[^}]*\}\{[^}]*\}", " ", s)
    s = re.sub(r"\\multirow\{[^}]*\}\{[^}]*\}", " ", s)
    return clean_prose(s)


def is_numeric_cell(s: str) -> bool:
    return bool(re.fullmatch(r"[\s\d.,±\\pm%$()\-+{}]*\d[\s\d.,±\\pm%$()\-+{}]*", s or "")) or not s.strip()


def locate_in_table(tables: list[dict], pos: int) -> tuple[bool, str, str]:
    for t in tables:
        s, e = t["span"]
        if not (s <= pos < e):
            continue
        rows = t["rows"]
        header_cells: list[str] = []
        for r in rows:
            texts = [clean_cell(c[2]) for c in r]
            if any(x and not is_numeric_cell(x) for x in texts[1:]) or (len(texts) == 1 and texts[0]):
                header_cells = texts
                break
        for r in rows:
            for ci, (cs, ce, _) in enumerate(r):
                if cs <= pos < ce:
                    row_label = clean_cell(r[0][2]) if ci > 0 else ""
                    col_label = header_cells[ci] if ci < len(header_cells) else ""
                    return True, row_label, col_label
        return True, "", ""
    return False, "", ""


def enclosing_caption(text: str, pos: int) -> str:
    for env in ("table", "table*", "figure", "figure*"):
        for s, e in env_spans(text, env):
            if s <= pos < e:
                for cs, ce in command_spans(text[s:e], ["caption"], 1):
                    return clean_prose(re.sub(r"^\\caption\*?(\[[^\]]*\])?", "", text[s + cs : s + ce]))
    return ""


def extract_file(tf: TexFile) -> list[dict]:
    stripped = strip_for_numbers(tf)
    original_nc = strip_comments(tf.text)
    tables = table_cells(original_nc)
    captions = command_spans(original_nc, ["caption"], 1)
    results: list[dict] = []

    # scientific notation first, then blank it so its parts are not re-extracted
    sci_spans = []
    for m in SCI.finditer(stripped):
        exp = m.group("exp").replace("−", "-").replace(" ", "")
        mant = m.group("mant") or "1"
        results.append({"_pos": m.start(), "_end": m.end(), "value": f"{mant}e{exp}", "shown": m.group(0), "unit": "-"})
        sci_spans.append((m.start(), m.end()))
    scan = blank_spans(stripped, sci_spans)

    for m in NUMBER.finditer(scan):
        results.append({"_pos": m.start(), "_end": m.end(), "value": m.group(0).replace("{,}", "").replace(",", ""),
                        "shown": m.group(0), "unit": ""})

    out = []
    for r in sorted(results, key=lambda x: x["_pos"]):
        pos, end = r.pop("_pos"), r.pop("_end")
        line_no = tf.lines.line_of(pos)
        line_text = tf.text.split("\n")[line_no - 1]
        before = scan[max(0, pos - 40) : pos]
        after = scan[end : end + 12]
        if not r["unit"]:
            r["unit"] = "%" if re.match(r"\s*\\?%", after) else "-"
        in_table, row_label, col_label = locate_in_table(tables, pos)
        in_caption = any(s <= pos < e for s, e in captions)
        where = "table" if in_table else "caption" if in_caption else "prose"
        ss, se = sentence_bounds(scan, pos)
        sentence = scan[ss:se]
        rel = pos - ss
        cuts = [0] + [m.start() for m in CLAUSE_SPLIT.finditer(sentence)] + [len(sentence)]
        cs = max(c for c in cuts if c <= rel)
        ce = min(c for c in cuts if c > rel) if any(c > rel for c in cuts) else len(sentence)
        # don't cut at the decimal comma/point of the number itself
        clause = sentence[cs:ce]
        left = words(scan[max(0, pos - 400) : pos])[-10:]
        right = words(scan[end : end + 400])[:10]
        rec = {
            "tex_file": tf.rel,
            "line": line_no,
            "value": r["value"],
            "shown": r["shown"],
            "unit": r["unit"],
            "where": where,
            "context": " ".join(left + [f"[[{r['shown']}]]"] + right),
            "sentence": clean_prose(sentence) if where != "table" else "",
            "clause": clean_prose(clause) if where != "table" else "",
            "row_label": row_label,
            "col_label": col_label,
            "caption": enclosing_caption(original_nc, pos) if where != "prose" else "",
            "status": "candidate",
            "note": "",
        }
        prev = scan[pos - 1] if pos > 0 else ""
        prev2 = scan[pos - 2] if pos > 1 else ""
        is_int = re.fullmatch(r"\d+", r["value"]) is not None
        if prev.isalpha() or prev in "_^" or (prev == "-" and prev2.isalpha()):
            rec.update(status="ignored", note="part of an identifier or math index")
        elif re.match(r"[A-Za-z]", after) and not UNIT_SUFFIX.match(after):
            rec.update(status="ignored", note="part of an identifier")
        elif NUMBERING_WORDS.search(before.rstrip()):
            rec.update(status="ignored", note="section/figure/table numbering")
        elif is_int and 1900 <= int(r["value"]) <= 2099 and CITE_CONTEXT.search(line_text):
            rec.update(status="ignored", note="year in citation context")
        elif is_int and where == "prose" and int(r["value"]) <= SMALL_COUNT_MAX:
            rec.update(status="ignored", note="small integer count in prose")
        out.append(rec)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tex", required=True, type=Path, help="main .tex file (\\input files are followed)")
    ap.add_argument("--out", required=True, type=Path, help="numbers.json")
    a = ap.parse_args()
    if not a.tex.exists():
        raise C2PError(f"not found: {a.tex}")
    numbers = []
    for tf in load_document(a.tex):
        numbers.extend(extract_file(tf))
    for i, n in enumerate(numbers, 1):
        n["id"] = f"N{i:04d}"
    write_json(a.out, numbers)
    n_ign = sum(1 for n in numbers if n["status"] == "ignored")
    print(f"{len(numbers)} numbers extracted ({n_ign} ignored by default rules) -> {a.out}")
    return 0


if __name__ == "__main__":
    run_main(main)
