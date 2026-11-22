# code2paper — Implementation Plan

Version 0.1 · 2026-11-15 · Owner: Niket

Give this file to Claude Code in an empty repo named `code2paper` and implement it one milestone at a time. Each milestone has acceptance criteria; do not start the next one until they pass.

---

## 1. What this is

`code2paper` is a **pack of Claude Code skills plus Python helper scripts**. Given a code repository and a one-page author notes file, it produces a journal-format LaTeX manuscript with a literature review, and audit reports that show where every number and every citation came from.

It is not a standalone app and has no LLM SDK calls of its own. The coding agent (Claude Code) is the runtime. Skills hold the instructions; scripts do the deterministic work (parsing, API lookups, matching, compiling).

### Design decision

Do not build the writer. Reuse **PaperOrchestra** (https://github.com/Ar9av/PaperOrchestra) for outline, plotting, literature review, section writing and refinement. `code2paper` adds what it lacks:

1. **Repo ingest**: turn a code repo into PaperOrchestra's input files, with every number traced to a file, line and commit.
2. **Gap check**: tell the author what the evidence cannot support before any writing happens.
3. **Audits**: check that each citation exists and supports the sentence it is attached to, and that every number in the paper matches the evidence.
4. **Human gate**: nothing is final until the author signs off on flagged rows.

### Non-goals for v1

- Running new experiments automatically.
- Inventing results, baselines or ablations that are not in the repo.
- Auto-submitting to a journal.
- Supporting private papers behind paywalls (abstracts only).

---

## 2. Pipeline

```
repo URL/path + notes.md + journal template
        │
        ▼
[1] c2p-repo-ingest ──► inventory.json, evidence_map.csv,
        │                idea.md, experimental_log.md, figures/
        ▼
[2] c2p-gap-check ────► gap_report.md   ── AUTHOR DECISION ──
        │
        ▼
[3] paper-orchestra (upstream, unmodified) ──► paper.tex, refs.bib, figures
        │
        ▼
[4] c2p-numbers-audit ─► numbers_audit.csv      (fails build on mismatch)
[5] c2p-citation-audit ► citation_audit.csv     (existence + support)
[6] c2p-compile-check ─► paper.pdf, compile_report.md
        │
        ▼
[7] REVIEW.md + overleaf.zip   ── AUTHOR SIGN-OFF ──
```

Steps 4 and 5 are independent and can run in parallel.

---

## 3. Upstream facts to rely on, and to verify

Known from the PaperOrchestra README (checked 2026-11-15):

- Inputs live in `workspace/inputs/`: `idea.md`, `experimental_log.md`, `template.tex`, `conference_guidelines.md`, optional `figures/`.
- Install: clone, `pip install -r requirements.txt`, symlink the skill folders into `~/.claude/skills/`.
- Workspace scaffold: `python skills/paper-orchestra/scripts/init_workspace.py --out workspace/`.
- It has an optional `agent-research-aggregator` skill that builds `idea.md` and `experimental_log.md` from raw materials. It is skipped when both files already exist, so our ingest output takes precedence.
- Citations are checked against Semantic Scholar by fuzzy title match. `SEMANTIC_SCHOLAR_API_KEY` is optional and raises the rate limit.

**Verify during M0 by reading the upstream repo, and record the answers in `docs/upstream-notes.md`:**

- [ ] Exact required structure of `idea.md` and `experimental_log.md` (headings, fields).
- [ ] Where the final `.tex`, `.bib` and figures are written.
- [ ] Which prompts control section order and length (needed for M8).
- [ ] The licence. Treat PaperOrchestra as an external dependency (clone at a pinned commit). Do not copy its code into this repo unless the licence allows it.

---

## 4. Repository layout

```
code2paper/
├── README.md
├── CLAUDE.md                     # conventions for Claude Code in this repo
├── PLAN.md                       # this file
├── requirements.txt
├── pyproject.toml
├── docs/
│   └── upstream-notes.md
├── skills/
│   ├── code2paper/               # top-level driver
│   │   └── SKILL.md
│   ├── c2p-repo-ingest/
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       ├── inventory_repo.py
│   │       ├── extract_results.py
│   │       └── validate_evidence_map.py
│   ├── c2p-gap-check/
│   │   └── SKILL.md
│   ├── c2p-numbers-audit/
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       ├── extract_numbers.py
│   │       └── match_evidence.py
│   ├── c2p-citation-audit/
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       ├── extract_citations.py
│   │       ├── verify_existence.py
│   │       └── fetch_abstracts.py
│   └── c2p-compile-check/
│       ├── SKILL.md
│       └── scripts/
│           ├── compile.py
│           └── package_overleaf.py
├── scripts/
│   ├── install.sh                # symlinks skills, installs upstream
│   └── init_workspace.py
├── templates/
│   ├── notes.md
│   ├── guidelines/               # one .md per journal family
│   └── REVIEW.md
└── tests/
    ├── fixtures/toy_repo/        # tiny repo with known numbers
    ├── fixtures/toy_paper/       # .tex with seeded errors
    └── test_*.py
```

Each `SKILL.md` starts with YAML frontmatter (`name`, `description`) and then states: when to use it, inputs, exact steps, outputs, and stop conditions.

### Workspace layout (one per paper)

```
workspace/
├── repo/                 # target repo, cloned at a pinned commit
├── notes.md              # written by the author
├── inputs/               # PaperOrchestra inputs
│   ├── idea.md
│   ├── experimental_log.md
│   ├── template.tex
│   ├── conference_guidelines.md
│   └── figures/
├── evidence/
│   ├── inventory.json
│   ├── evidence_map.csv
│   └── gap_report.md
├── paper/                # PaperOrchestra output
├── audits/
│   ├── numbers_audit.csv
│   ├── citation_audit.csv
│   └── compile_report.md
└── final/
    ├── paper.pdf
    ├── overleaf.zip
    └── REVIEW.md
```

---

## 5. Data contracts

### 5.1 `notes.md` (author-written, required)

```markdown
# Paper notes
## Working title
## Target journal            (name + article type)
## Novelty claim             (2–3 sentences: what is new and versus what)
## Key results               (3–5 bullets, each pointing at a file in the repo)
## Closest prior work        (3–10 papers, DOI or arXiv ID where known)
## Out of scope / limitations
## Authors, affiliations, funding, AI-use disclosure
```

The pipeline stops if the novelty claim or target journal is empty.

### 5.2 `evidence_map.csv`

One row per quantitative fact.

| column | meaning |
|---|---|
| `evidence_id` | `E0001`, `E0002`, … stable across reruns |
| `value` | numeric value as found, full precision |
| `unit` | `%`, `s`, `K`, `-` … |
| `metric` | e.g. `test_rmse`, `mean_episode_return` |
| `condition` | model / dataset / seed / config the value belongs to |
| `kind` | `result`, `hyperparameter`, `dataset_stat`, `derived` |
| `source_file` | path relative to repo root |
| `line_start`, `line_end` | location in the file (or cell reference for CSV/notebook) |
| `commit` | full commit hash of the target repo |
| `file_sha256` | hash of the source file |
| `quote` | the exact text the value was read from |
| `method` | `parsed` (script) or `read` (agent read it) |
| `derived_from` | for `derived` rows: list of evidence IDs |
| `formula` | for `derived` rows: e.g. `(E0012 - E0015) / E0015 * 100` |

Rules:

- A number with no source file does not get a row, and does not go into `experimental_log.md`.
- `derived` rows must recompute correctly from their parents. `validate_evidence_map.py` checks this.
- `method=read` rows are re-verified by the script: the `quote` must appear at the stated location.

### 5.3 `numbers_audit.csv`

`tex_file, line, context, value_in_paper, status, evidence_id, note`

Status: `matched`, `derived_ok`, `rounding_ok`, `ignored` (with reason), `unmatched`, `conflict`.

### 5.4 `citation_audit.csv`

`cite_key, sentence, tex_line, doi, exists, metadata_match, abstract_source, support, rationale, author_signoff`

- `exists`: `yes` / `no` / `ambiguous`
- `support`: `supports` / `partial` / `unsupported` / `no_abstract`
- `author_signoff`: blank until the author fills it in.

---

## 6. Milestones

### M0 — Scaffold and upstream install

- Create the layout in section 4, `requirements.txt`, `pyproject.toml`, `CLAUDE.md`.
- `scripts/install.sh`: clone PaperOrchestra at a pinned commit into `vendor/` (git-ignored), install its requirements, symlink its skills and ours into `~/.claude/skills/`.
- `scripts/init_workspace.py --repo <url|path> --out workspace/`: clones the target repo, records the commit hash, copies `templates/notes.md`, and calls upstream's `init_workspace.py`.
- Fill in `docs/upstream-notes.md` (section 3 checklist).

**Accept:** fresh machine → `install.sh` → `init_workspace.py` gives the workspace tree; upstream notes complete.

### M1 — Baseline run with hand-written inputs

- Pick the pilot repo. Write `idea.md` and `experimental_log.md` by hand. Run PaperOrchestra unmodified.
- Save the output as `examples/baseline/` with a short `OBSERVATIONS.md`: what was good, what was wrong, which numbers and citations were bad.

**Accept:** a compiled PDF exists; observations list at least the wrong numbers and wrong citations found by hand. This list becomes the test set for M4 and M5.

### M2 — `c2p-repo-ingest`

Scripts:

- `inventory_repo.py`: walks the repo and writes `inventory.json` with file type, size, and a role guess (`readme`, `core_code`, `config`, `log`, `result_table`, `notebook`, `figure`, `test`, `other`). Skips `.git`, virtualenvs, binaries over a size limit.
- `extract_results.py`: parses machine-readable results without the agent: CSV/TSV, JSON/JSONL metrics, YAML/TOML configs, notebook output cells, common log patterns (`metric: value`, `metric=value`). Emits candidate evidence rows.
- `validate_evidence_map.py`: checks schema, quote locations, hashes and derived formulas. Non-zero exit on any failure.

Skill steps:

1. Run inventory.
2. Read the README, core modules and configs. Write a method summary with file references.
3. Run `extract_results.py`. Read anything it could not parse and add `method=read` rows.
4. Copy existing figures into `inputs/figures/` and record which script produced each one.
5. Write `idea.md` and `experimental_log.md` in the upstream format. Every number in the log carries its evidence ID in brackets, e.g. `0.912 [E0031]`.
6. Run the validator.

Safety rule: **read the target repo, do not execute it.** Running its code needs explicit author approval for that specific command.

**Accept:** on `tests/fixtures/toy_repo`, all known numbers appear in the evidence map with correct locations; validator passes; no number in `experimental_log.md` lacks an evidence ID.

### M3 — `c2p-gap-check`

Compares `notes.md` against the evidence and writes `gap_report.md`:

- Each key result in the notes: supported / partly supported / not found.
- Missing: baselines, ablations, multiple seeds, error bars, dataset description, compute details, statistical tests.
- Novelty claim versus the closest prior work listed: what comparison the paper will need.
- For each gap, two options: "add evidence" (what to run) or "narrow the claim" (suggested wording).

Then stop and ask the author how to proceed.

**Accept:** on the toy repo with one unsupported key result, the report flags it and the pipeline stops.

### M4 — `c2p-numbers-audit`

- `extract_numbers.py`: strips comments, `\cite`, `\ref`, `\label`, bibliography and graphics options; extracts numbers from prose, tables and captions with file, line and ±10 words of context. Default ignore rules (each recorded as `ignored` with a reason): years in citation context, section/figure/table numbering, small counts written as integers in prose.
- `match_evidence.py`: matches by value with rounding tolerance (a paper value must equal the evidence value rounded to the shown precision). Checks metric and condition words in the context when several rows share a value. Percent changes and differences are matched against `derived` rows, or recomputed from candidate parents.
- The skill resolves remaining ambiguous rows by reading the context, and may add a `derived` row with a formula. It may never mark an unmatched number as matched without an evidence ID.

**Accept:** on `fixtures/toy_paper` with three seeded errors (one changed digit, one swapped condition, one invented number), all three are reported and the script exits non-zero. On the M1 baseline, it finds the wrong numbers listed in `OBSERVATIONS.md`.

### M5 — `c2p-citation-audit`

- `extract_citations.py`: parses the `.bib` and every `\cite*` with its full sentence.
- `verify_existence.py`: for each entry, look up by DOI in Crossref (`https://api.crossref.org/works/{doi}`), else search by title in Crossref (`/works?query.bibliographic=`) and Semantic Scholar (`https://api.semanticscholar.org/graph/v1/paper/search`). Compare title, first author and year. Result: `yes`, `no`, `ambiguous`. Cache responses on disk, respect rate limits, send a `mailto` to Crossref, use `SEMANTIC_SCHOLAR_API_KEY` if set.
- `fetch_abstracts.py`: Semantic Scholar first, OpenAlex and arXiv as fallbacks. Record the source.
- Support check: for each (sentence, cited paper) pair, a **separate subagent that has not seen the manuscript** gets only the sentence and the abstract, and returns `supports` / `partial` / `unsupported` with a one-line reason. No abstract → `no_abstract`, which needs the author to check.
- Also report: bib entries never cited, `\cite` keys with no bib entry, papers from `notes.md` "closest prior work" that are not cited.

**Accept:** on the toy paper with one fabricated reference and one real paper cited for a claim it does not make, both are flagged. Rerun uses the cache and makes no network calls.

### M6 — `c2p-compile-check` and packaging

- `compile.py`: build with `latexmk` (fall back to `tectonic`). Parse the log for undefined references and citations, missing figures, overfull boxes above a threshold. Check page or word count against the guidelines file.
- `package_overleaf.py`: zip the `.tex`, `.bib`, figures and class files.
- Fill `final/REVIEW.md`: counts of flagged numbers and citations, the gap decisions, the AI-use disclosure text, and a sign-off checklist.

**Accept:** clean compile on the pilot paper; the zip builds on Overleaf without edits.

### M7 — `code2paper` driver skill and end-to-end run

- The driver runs steps 1–7 in section 2, stops at the two author decision points, and can resume from any step based on which files exist.
- After audits, it may run **at most two** fix rounds: correct numbers to match evidence, replace or drop unsupported citations, then re-audit. It never edits `evidence_map.csv` to make a number pass.
- One command for the user: "Run code2paper on ./workspace".

**Accept:** pilot repo goes from URL to `final/` with both audits passing or every remaining flag listed in `REVIEW.md`.

### M8 — Journal adaptation

- Guidelines files for the journal families needed first (e.g. Elsevier `elsarticle`, ACS `achemso`): section order, abstract limits, reference style, required statements (data availability, CRediT, competing interests, AI-use disclosure).
- Adjust the outline step so journals get a fuller Methods section, a Nomenclature section when equations are heavy, and a Conclusions section; record exactly which upstream prompt or input was changed in `docs/upstream-notes.md`. Prefer steering through `conference_guidelines.md` over editing upstream files.

**Accept:** the pilot paper compiles in the target journal's class with the right section order and all required statements present.

---

## 7. Testing

- `tests/fixtures/toy_repo`: about ten files, a results CSV, a JSON metrics file, a training log, a config, one figure script. Known ground-truth list of numbers.
- `tests/fixtures/toy_paper`: a short `.tex` and `.bib` with seeded errors for M4 and M5.
- Unit tests for every script. Network tests use recorded responses.
- A regression file per real paper: the errors found by hand in M1 must keep being caught.

---

## 8. Rules for Claude Code (copy into `CLAUDE.md`)

1. Scripts are deterministic and have no LLM calls. Judgement lives in skills.
2. Never write a number into any pipeline file without an evidence ID.
3. Never change `evidence_map.csv` to make an audit pass. Fix the paper, or report the conflict.
4. Never add a reference that failed the existence check.
5. Do not execute code from the target repo without the author's approval.
6. Do not modify files under `vendor/`. Record needed upstream changes in `docs/upstream-notes.md`.
7. Every script: `--help`, non-zero exit on failure, writes only inside the workspace.
8. Python 3.11+, type hints, `pytest`, `ruff`.

---

## 9. Risks

| Risk | Handling |
|---|---|
| Repo has thin or no logged results | Gap check stops early; author adds evidence or narrows claims |
| A real paper is cited for something it does not say | Support check on abstracts; author signs off on `partial` and `no_abstract` rows |
| Abstract is not enough to judge support | Marked `no_abstract` or `partial`; never auto-passed |
| Writer rounds or rephrases numbers | Rounding-aware matching; derived rows with formulas |
| Upstream changes its input format | Pinned commit; formats recorded in `docs/upstream-notes.md` |
| API rate limits | On-disk cache, backoff, Semantic Scholar API key |
| Journal AI-use policy | Disclosure text in `notes.md`, carried into the manuscript and `REVIEW.md` |

---

## 10. Before starting, the author provides

- [ ] Pilot repo URL and commit.
- [ ] Target journal and article type.
- [ ] Filled `notes.md`.
- [ ] Semantic Scholar API key (optional, recommended).
- [ ] A working LaTeX install (`latexmk` or `tectonic`).