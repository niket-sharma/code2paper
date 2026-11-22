#!/usr/bin/env python3
"""Compile the manuscript (latexmk, falling back to tectonic) and check the log and limits.

Reports undefined references and citations, missing files/figures, LaTeX errors,
overfull boxes above a threshold, page count, and word counts versus the limits
in the guidelines file (`<!-- c2p:limits ... -->` block, or prose like "9 pages").
Writes compile_report.md and compile_report.json; copies the PDF to --pdf-out.

Exit 1 on compile failure, undefined refs/cites, missing files, or a limit
exceeded; 2 if no LaTeX engine is installed.

Example:
    python compile.py --tex workspace/paper/final/paper.tex \\
        --guidelines workspace/inputs/conference_guidelines.md \\
        --report workspace/audits/compile_report.md --pdf-out workspace/final/paper.pdf
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from c2p.common import C2PError, guard_output, run_main  # noqa: E402
from c2p.latex import TexFile, body_start, clean_prose, env_spans, load_document, strip_comments  # noqa: E402


def parse_limits(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    lim: dict[str, Any] = {}
    m = re.search(r"<!--\s*c2p:limits(.*?)-->", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                v = v.strip()
                if re.fullmatch(r"\d[\d,]*", v):
                    lim[k.strip()] = int(v.replace(",", ""))
                elif v:
                    lim[k.strip()] = v
    if "page_limit" not in lim and "page_limit" not in (m.group(1) if m else ""):
        pm = re.search(r"(?:limited to|limit(?:ed)?(?: of)?|at most|maximum of)\s*\**\s*(\d+)\s*\**\s*pages", text, re.I)
        if pm:
            lim["page_limit"] = int(pm.group(1))
    if "abstract_word_limit" not in lim:
        am = re.search(r"abstract[^\n]{0,60}?(?:at most|max(?:imum)?|~|up to|≤)?\s*(?:\d+\s*[-–]\s*)?(\d{2,4})\s*words", text, re.I)
        if am:
            lim["abstract_word_limit"] = int(am.group(1))
    return lim


def parse_log(log: str, overfull_pt: float) -> dict[str, Any]:
    joined = re.sub(r"\n(?=[^\n]{0,79}$)", "\n", log)
    undefined_refs = sorted(set(re.findall(r"Reference [`']([^']+)' on page \d+ undefined", joined)))
    undefined_cites = sorted(set(re.findall(r"Citation [`']([^']+)' on page \d+ undefined", joined)))
    undefined_cites += [c for c in re.findall(r"I didn't find a database entry for \"([^\"]+)\"", joined)
                        if c not in undefined_cites]
    missing = sorted(set(re.findall(r"File [`']([^']+)' not found", joined)))
    missing += sorted(set(re.findall(r"LaTeX Error: File [`']([^']+)' not found", joined)) - set(missing))
    errors = re.findall(r"^! (.+)$", log, re.M)
    errors += [m for m in re.findall(r"^[^\s:]+\.tex:\d+: (.+)$", log, re.M) if m not in errors]
    overfull = []
    for m in re.finditer(r"Overfull \\[hv]box \((\d+(?:\.\d+)?)pt too (?:wide|high)\)[^\n]*?(?:lines? (\d+)(?:--(\d+))?)?", log):
        if float(m.group(1)) > overfull_pt:
            overfull.append({"pt": float(m.group(1)), "line": m.group(2) or ""})
    pages = None
    pm = re.search(r"Output written on .*?\((\d+) pages?", joined, re.S)
    if pm:
        pages = int(pm.group(1))
    return {"undefined_refs": undefined_refs, "undefined_cites": undefined_cites, "missing_files": missing,
            "errors": errors[:20], "overfull": overfull, "pages": pages,
            "rerun_needed": "Rerun to get cross-references right" in log}


def pdf_pages(pdf: Path) -> int | None:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]

        return len(PdfReader(str(pdf)).pages)
    except Exception:  # noqa: BLE001 - pypdf optional
        data = pdf.read_bytes()
        n = len(re.findall(rb"/Type\s*/Page(?!s)", data))
        return n or None


def word_counts(files: list[TexFile]) -> dict[str, int]:
    body = ""
    abstract = ""
    for tf in files:
        t = strip_comments(tf.text)
        t = t[body_start(t):] if "\\begin{document}" in t else t
        for s, e in env_spans(t, "abstract"):
            abstract += t[s:e]
        for env in ("abstract", "thebibliography", "table", "table*", "figure", "figure*", "equation",
                    "align", "align*", "tabular"):
            for s, e in env_spans(t, env):
                t = t[:s] + " " * (e - s) + t[e:]
        t = re.sub(r"\\(?:cite\w*|ref|eqref|label|autoref|cref|bibliography\w*|includegraphics)\*?(\[[^\]]*\])?\{[^}]*\}", " ", t)
        body += t
    def count(s: str) -> int:
        return len([w for w in clean_prose(re.sub(r"\\(?:begin|end)\{[^}]*\}", " ", s)).split() if re.search(r"[A-Za-z0-9]", w)])
    return {"main_text_words": count(body), "abstract_words": count(abstract)}


def run_engine(tex: Path, engine: str) -> tuple[str, str, int]:
    cwd = tex.parent
    if engine in ("auto", "latexmk") and shutil.which("latexmk"):
        cmd = ["latexmk", "-pdf", "-interaction=nonstopmode", "-file-line-error", "-f", tex.name]
        name = "latexmk"
    elif engine in ("auto", "tectonic") and shutil.which("tectonic"):
        cmd = ["tectonic", "--keep-logs", "--keep-intermediates", tex.name]
        name = "tectonic"
    else:
        return "", "none", 127
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=900)
    log_path = tex.with_suffix(".log")
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    return log + "\n" + p.stdout + p.stderr, name, p.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tex", required=True, type=Path)
    ap.add_argument("--guidelines", type=Path)
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--pdf-out", type=Path)
    ap.add_argument("--engine", choices=["auto", "latexmk", "tectonic"], default="auto")
    ap.add_argument("--overfull-threshold", type=float, default=10.0, help="pt")
    ap.add_argument("--log", type=Path, help="parse this existing log instead of compiling")
    a = ap.parse_args()
    if not a.tex.exists():
        raise C2PError(f"not found: {a.tex}")
    if a.log:
        log, engine, rc = a.log.read_text(encoding="utf-8", errors="replace"), "log-only", 0
    else:
        log, engine, rc = run_engine(a.tex.resolve(), a.engine)
    if engine == "none":
        guard_output(a.report).write_text(
            "# Compile report\n\n**No LaTeX engine found.** Install TeX Live (latexmk) or tectonic.\n", encoding="utf-8")
        print("ERROR: no LaTeX engine (latexmk or tectonic) found", file=sys.stderr)
        return 2
    res = parse_log(log, a.overfull_threshold)
    pdf = a.tex.with_suffix(".pdf")
    if res["pages"] is None and pdf.exists() and not a.log:
        res["pages"] = pdf_pages(pdf)
    res.update(word_counts(load_document(a.tex)))
    limits = parse_limits(a.guidelines)
    over = []
    if isinstance(limits.get("page_limit"), int) and res["pages"] and res["pages"] > limits["page_limit"]:
        over.append(f"{res['pages']} pages > limit {limits['page_limit']} (limit usually excludes references; check)")
    if isinstance(limits.get("word_limit"), int) and res["main_text_words"] > limits["word_limit"]:
        over.append(f"main text {res['main_text_words']} words > limit {limits['word_limit']}")
    if isinstance(limits.get("abstract_word_limit"), int) and res["abstract_words"] > limits["abstract_word_limit"]:
        over.append(f"abstract {res['abstract_words']} words > limit {limits['abstract_word_limit']}")
    pdf_ok = a.log is not None or pdf.exists()
    failed = (rc != 0 and not pdf.exists()) or not pdf_ok
    blocking = failed or res["undefined_refs"] or res["undefined_cites"] or res["missing_files"] or over
    status = "FAILED" if failed else ("ISSUES" if blocking else "OK")
    summary = {"status": status, "engine": engine, "return_code": rc, "limits": limits, "over_limits": over, **res}
    if pdf.exists() and a.pdf_out and not a.log:
        shutil.copy2(pdf, guard_output(a.pdf_out))
        summary["pdf"] = str(a.pdf_out)

    md = [f"# Compile report — {status}", "", f"- Engine: {engine} (exit {rc})",
          f"- Pages: {res['pages']}; main-text words: {res['main_text_words']}; abstract words: {res['abstract_words']}",
          f"- Limits: {limits or 'none found in guidelines'}",
          f"- Over limits: {'; '.join(over) or 'none'}",
          f"- Undefined references: {', '.join(res['undefined_refs']) or 'none'}",
          f"- Undefined citations: {', '.join(res['undefined_cites']) or 'none'}",
          f"- Missing files: {', '.join(res['missing_files']) or 'none'}",
          f"- Overfull boxes > {a.overfull_threshold}pt: {len(res['overfull'])}"
          + (" (lines " + ", ".join(str(o['line']) for o in res['overfull'][:10]) + ")" if res["overfull"] else ""),
          f"- Errors: {len(res['errors'])}"]
    md += [f"  - `{e[:150]}`" for e in res["errors"][:10]]
    guard_output(a.report).write_text("\n".join(md) + "\n", encoding="utf-8")
    guard_output(a.report.with_suffix(".json")).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 1 if blocking else 0


if __name__ == "__main__":
    run_main(main)
