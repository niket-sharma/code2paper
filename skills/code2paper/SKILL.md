---
name: code2paper
description: Turn a code repository plus a one-page notes.md into an audited journal LaTeX manuscript - ingest the repo into an evidence map, check gaps with the author, write with PaperOrchestra, audit every number and citation, compile, and produce REVIEW.md for author sign-off. Use when asked to "run code2paper on <workspace>", "write a paper from this repo", or to resume a code2paper workspace.
---

# code2paper (driver)

Runs the whole pipeline on one workspace. It stops at the two author decision points and resumes from whatever step is next.

```
[1] c2p-repo-ingest → [2] c2p-gap-check → AUTHOR DECISION → [3] paper-orchestra
→ [4] c2p-numbers-audit ‖ [5] c2p-citation-audit → (≤2 fix rounds) → [6] c2p-compile-check
→ [7] REVIEW.md + overleaf.zip → AUTHOR SIGN-OFF
```

## Rules (always)

1. Scripts are deterministic. Judgement lives in the skills.
2. Never write a number into any pipeline file without an evidence ID.
3. Never change `evidence_map.csv` to make an audit pass. Fix the paper, or report the conflict. Adding a correct `derived` row is allowed.
4. Never add a reference that failed the existence check.
5. Never execute code from the target repo (`$WS/repo`) without the author's approval for that specific command.
6. Never modify files under the code2paper `vendor/` directory. Steer PaperOrchestra through its input files.
7. Write only inside the workspace.

## Start / resume

`$WS` is the workspace path the user gave. If it does not exist, ask for the repo URL or path and run, from the code2paper repo root:
```bash
python scripts/init_workspace.py --repo <url|path> --out $WS [--guidelines elsarticle|achemso|generic-journal]
```
Then ask the author to fill in `$WS/notes.md` and stop.

Otherwise check where things stand:
```bash
python <skill-dir>/scripts/pipeline_status.py --workspace $WS
```
Start at the first step that is not `done`. `stale` means an input changed after the output was made, so redo that step and every step after it.

## Steps

1. **Ingest.** Follow the `c2p-repo-ingest` skill. Its validator must exit 0 before you continue.
2. **Gap check.** Follow the `c2p-gap-check` skill. It writes `evidence/gap_report.md`.
   **STOP: author decision 1.** Present the gaps and options, then wait. Continue only after `evidence/gap_decisions.md` records the author's answer. If they chose "add evidence", stop until the evidence exists, then go back to step 1.
3. **Write with PaperOrchestra** (upstream, unmodified). The PaperOrchestra workspace is `$WS/paper`, and its `inputs/` symlinks to `$WS/inputs`. Before you start:
   - `inputs/template.tex` and `inputs/conference_guidelines.md` must match the target journal. Copy them from `templates/guidelines/<family>.md` and `templates/latex/<class>.tex` if needed (`Guidelines:` line in notes.md).
   - Fill the statement sections of `inputs/template.tex` (title, authors and affiliations, AI-use disclosure, funding, competing interests, data and code availability, CRediT) from `notes.md`. Leave `TODO` wherever the notes give no information. The section writer leaves filled sections alone, so it cannot invent author contributions.
   - Run upstream's input validator: `python <code2paper>/vendor/PaperOrchestra/skills/paper-orchestra/scripts/validate_inputs.py --workspace $WS/paper`.
   - Then follow the `paper-orchestra` skill with **workspace = `$WS/paper`**. It must not run `agent-research-aggregator`: `idea.md` and `experimental_log.md` already exist.
   - Tell PaperOrchestra to keep each `[Exxxx]` tag's number exact and to **drop the tags from the LaTeX**. The audit re-derives provenance.
   - Its output is `$WS/paper/final/paper.tex`, `$WS/paper/refs.bib` and `$WS/paper/figures/`.
4. **and 5. Audits, in parallel.** Run `c2p-numbers-audit` and `c2p-citation-audit`. They are independent, so you can run them as two parallel subagents. The citation audit's support check always uses isolated subagents.
6. **Fix rounds (at most two).** If either audit flags rows:
   - Numbers: edit `paper.tex` so each `conflict` or `unmatched` value matches its evidence row, or rephrase or remove the claim when there is no evidence. Never touch `evidence_map.csv`, except to add a correct `derived` row.
   - Citations: for `unsupported`, replace the reference with one that passed the existence check and supports the claim, or rewrite or drop the sentence. For `exists=no`, remove the reference and every sentence that depends on it, or replace it with a verified one. Add a `\cite` key with no bib entry to the `.bib` only after the key passes the existence check. Leave `partial` and `no_abstract` for the author.
   - Rerun both audits after each round. After the second round, stop fixing: whatever remains goes into REVIEW.md.
7. **Compile, package, review.** Follow `c2p-compile-check`. It writes `final/paper.pdf`, `final/overleaf.zip` and `final/REVIEW.md`.
   **STOP: author decision 2.** Tell the author to read `final/REVIEW.md`, fill the `author_signoff` column in `audits/citation_audit.csv`, and tick the checklist. Once the author confirms, rerun `assemble_audit.py build` and `build_review.py`. Then write `final/SIGNOFF.md` with their name, the date and the checklist state. Nothing is final before that.

## Reporting

After each step, tell the user in two or three lines what was produced, what was flagged, and what comes next. At a stop point, say exactly what the author needs to do.
