---
name: c2p-compile-check
description: Compile the manuscript with latexmk/tectonic, check the log for undefined references, missing figures and overfull boxes, check page/word limits against the journal guidelines, package an Overleaf zip, and fill final/REVIEW.md. Use as step 6–7 of code2paper, or when asked to "compile and package the paper".
---

# c2p-compile-check

## Inputs

- `$WS/paper/final/paper.tex`, its `.bib`, and figures (PaperOrchestra references them as `../figures/...`).
- `$WS/inputs/conference_guidelines.md`, which holds the limits in a `<!-- c2p:limits ... -->` block.
- `$WS/audits/numbers_audit.csv`, `$WS/audits/citation_audit.csv`, `$WS/evidence/gap_decisions.md` and `$WS/notes.md`, all used for REVIEW.md.

## Steps

1. **Compile and check.**
   ```bash
   python <skill-dir>/scripts/compile.py --tex $WS/paper/final/paper.tex \
       --guidelines $WS/inputs/conference_guidelines.md \
       --report $WS/audits/compile_report.md --pdf-out $WS/final/paper.pdf
   ```
   - Exit 2: no LaTeX engine. Tell the author to install TeX Live (`latexmk`) or `tectonic`, and stop.
   - Exit 1: fix what you can **in the `.tex` only**. Examples: a missing `\label`, a wrong figure path, a `\cite` key spelled differently from the `.bib`, an overlong abstract. Then recompile. Never add a bib entry to silence an undefined citation unless that reference passed the existence check in `citation_audit.csv`.
   - Overfull boxes are warnings. Fix the large ones (wide tables: `\resizebox` or `tabularx`).
2. **Package for Overleaf.**
   ```bash
   python <skill-dir>/scripts/package_overleaf.py --tex $WS/paper/final/paper.tex \
       --search $WS/paper --search $WS/inputs --out $WS/final/overleaf.zip
   ```
   Paths outside the paper directory are copied into `figures/` and rewritten in the zipped `.tex`. Exit 1 lists missing files.
3. **Fill REVIEW.md.**
   ```bash
   python <skill-dir>/scripts/build_review.py --workspace $WS
   ```
   This lists the flagged numbers and citations, the gap decisions, the AI-use disclosure from notes.md, and the sign-off checklist.

## Outputs

`audits/compile_report.md`, `audits/compile_report.json`, `final/paper.pdf`, `final/overleaf.zip` and `final/REVIEW.md`.

## Stop conditions

Stop after step 3. Report the compile status, the page and word counts versus the limits, and the number of open items in REVIEW.md.
