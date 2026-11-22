---
name: c2p-repo-ingest
description: Turn a code repository into PaperOrchestra inputs (idea.md, experimental_log.md, figures/) with every number traced to a file, line and commit in evidence_map.csv. Use as step 1 of code2paper, or when asked to "ingest a repo for a paper" or "build the evidence map".
---

# c2p-repo-ingest

Turn the target repo in a code2paper workspace into PaperOrchestra's input files. Every number must be traceable to a file, line and commit.

## When to use

- Step 1 of the `code2paper` pipeline.
- When `evidence/evidence_map.csv`, `inputs/idea.md` or `inputs/experimental_log.md` is missing or stale.

## Inputs

- `$WS/repo/`: the target repo, cloned at a pinned commit by `scripts/init_workspace.py`.
- `$WS/notes.md`: the author's notes. Use them to decide what matters. Never take numbers from them.
- `$WS/workspace.json`: holds `repo_commit`.

`$WS` is the workspace directory. `<skill-dir>` is the directory containing this SKILL.md.

## Hard rules

1. **Read the target repo; do not execute it.** Do not run its scripts, notebooks, tests, `pip install` or `make`. If running something would produce missing evidence, stop and ask the author for approval of that exact command.
2. **No number without an evidence ID.** A number goes into `experimental_log.md` only as `value [E0001]`, and every ID must exist in `evidence_map.csv`. A number with no source file gets no row and does not go in the log.
3. Never invent baselines, ablations, seeds, error bars or results that are not in the repo.
4. Write only inside `$WS`.

## Steps

1. **Inventory.**
   ```bash
   python <skill-dir>/scripts/inventory_repo.py --repo $WS/repo --out $WS/evidence/inventory.json
   ```
   Look at the role counts. If `result_table`, `log` and `notebook` are all zero, warn the author that the repo has little logged evidence.

2. **Understand the method.** Read the `readme` file(s), the main `core_code` modules (entry points, model and algorithm definitions) and the `config` files. Write `$WS/evidence/method_summary.md`: what problem the code solves, the method's components, the data pipeline and the evaluation protocol. Give a `path:line` reference for each claim.

3. **Parse results.**
   ```bash
   python <skill-dir>/scripts/extract_results.py --repo $WS/repo \
       --inventory $WS/evidence/inventory.json --evidence-map $WS/evidence/evidence_map.csv
   ```
   This handles CSV/TSV, JSON/JSONL, YAML/TOML, notebook outputs and `key: value` / `key=value` log lines. It lists files it could not parse in `$WS/evidence/unparsed_files.json`. Reruns keep evidence IDs stable.

4. **Add `method=read` rows** for numbers the parser missed: values in unparsed files, in README tables, in code constants (for example a default `hidden_dim=64` that the config does not set), and in figure-generating scripts. Append each one to `evidence_map.csv` with:
   - the next free `evidence_id`
   - `source_file` relative to the repo root, and `line_start`/`line_end`
   - `quote`: the exact text copied from those lines (the validator checks it)
   - `commit` from `workspace.json` and `file_sha256` (`sha256sum`)
   - `method=read` and the right `kind`: `result`, `hyperparameter` or `dataset_stat`
   - `metric` and `condition` written so a reader can tell rows apart (for example `model=X;dataset=Y;seed=0`)

   If a key quantity is the mean of several runs, or the difference between two rows, add a `derived` row with `derived_from` (a list of IDs) and `formula` (for example `(E0012 - E0015) / E0015 * 100`). Leave `source_file` empty on derived rows.

5. **Figures.** Copy existing result figures into `$WS/inputs/figures/`. For each one, record in `$WS/evidence/figures.md` the producing script (found by reading for `savefig`/`write_image` calls) and the data file it reads. Skip logos and screenshots.

6. **Write the PaperOrchestra inputs** in the upstream format (see `docs/upstream-notes.md`):
   - `$WS/inputs/idea.md` has the four headings `## Problem Statement`, `## Core Hypothesis`, `## Proposed Methodology (Detailed Technical Approach)` (or `(High-Level Technical Approach)`) and `## Expected Contribution`. Build it from `method_summary.md` and the notes' novelty claim. Phrase it as a hypothesis, with no results. If equations appear in the code, write them out (the Dense variant).
   - `$WS/inputs/experimental_log.md` has exactly the headings `# Experimental Log`, `## 1. Experimental Setup` (bullets **Datasets**, **Evaluation Metrics**, **Baselines Compared**, **Implementation Details**), `## 2. Raw Numeric Data` (markdown tables) and `## 3. Qualitative Observations`. Write it in the past tense, with no citations, no URLs and no "Table N"/"Figure N" references.
   - Every number carries its evidence ID right after it: `0.912 [E0031]`, or `2.31 [E0027]` in a table cell. Put labels that contain digits but are not quantities in backticks: `` `ResNet-50` ``, `` `K=64` ``.
   - Values may be rounded for readability, but they must round correctly from the evidence value.

7. **Validate.**
   ```bash
   python <skill-dir>/scripts/validate_evidence_map.py --evidence-map $WS/evidence/evidence_map.csv \
       --repo $WS/repo --experimental-log $WS/inputs/experimental_log.md
   ```
   Fix every `FAIL`, then rerun until it exits 0. Never "fix" a failure by deleting the quote check or changing a value away from what the file says.

## Outputs

`evidence/inventory.json`, `evidence/evidence_map.csv`, `evidence/method_summary.md`, `evidence/figures.md`, `inputs/idea.md`, `inputs/experimental_log.md` and `inputs/figures/`.

## Stop conditions

- The validator exits non-zero after two honest fix attempts: report the failures and stop.
- The repo has no machine-readable or readable results at all: write what you found and stop. The gap check will tell the author.
- Evidence would need the target code to be run: ask the author and wait.
