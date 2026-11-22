# PaperOrchestra upstream notes

Checked 2026-11-17 against https://github.com/Ar9av/PaperOrchestra at commit
`6a319132932ee031e2d759b0f7f5075cf77bd1cf` (2026-11-04). That commit is pinned in
`scripts/install.sh`. If you move the pin, re-check every item below.

## Licence

MIT (Copyright (c) 2026 ar9av). Copying with attribution would be allowed, but
code2paper still treats PaperOrchestra as an external dependency. It is cloned
into `vendor/` (git-ignored) and nothing from it is copied into this repo.

## Install facts

- `requirements.txt`: jsonschema, python-Levenshtein, reportlab, matplotlib, pypdf. No LLM SDKs.
- Upstream's `setup.sh` is interactive. It prompts for API keys and writes to `~/.paperorchestra/`,
  `.cursor/`, `.windsurf/`, `~/.codex/` and others. `scripts/install.sh` does **not** call it. It symlinks
  the skill folders that contain a `SKILL.md` into `~/.claude/skills/`. `skills/shared/` has no
  SKILL.md and is skipped, but the skills reference it by relative path, and that still works
  because the symlink points into the vendor checkout.
- Skills: `paper-orchestra` (driver), `outline-agent`, `plotting-agent`, `literature-review-agent`,
  `section-writing-agent`, `content-refinement-agent`, `paper-autoraters`, `paper-writing-bench`, and the
  optional `agent-research-aggregator`.

## Workspace scaffold

`python skills/paper-orchestra/scripts/init_workspace.py --out <dir> [--force]` creates
`inputs/`, `inputs/figures/`, `figures/`, `drafts/`, `refinement/`, `final/` and `cache/`. It writes
`inputs/README.md` and, only if absent, a fallback `inputs/template.tex` (article class, sections
Introduction / Related Work / Method / Experiments / Conclusion).

**Collision with our layout.** Upstream writes `final/`, `figures/`, `drafts/`, `refs.bib`,
`outline.json` and `citation_pool.json` at *its* workspace root, and its `final/` would clash with
ours. So `scripts/init_workspace.py` makes `<ws>/paper/` the PaperOrchestra workspace, symlinks
`<ws>/paper/inputs → ../inputs`, and runs upstream's init with `--force` (it uses
`makedirs(exist_ok=True)`, so it works through the symlink).

## Input formats (from `skills/paper-orchestra/references/io-contract.md`)

### `idea.md`

Four `##` headings. Sparse variant:
`## Problem Statement`, `## Core Hypothesis`, `## Proposed Methodology (High-Level Technical Approach)`,
`## Expected Contribution`. The Dense variant uses `(Detailed Technical Approach)` and keeps equations
and variable definitions. The outline agent accepts either.

### `experimental_log.md`

Strict structure:

```markdown
# Experimental Log
## 1. Experimental Setup
* **Datasets:** ...
* **Evaluation Metrics:** ...
* **Baselines Compared:** ...
* **Implementation Details:** ...
## 2. Raw Numeric Data
(markdown tables, | col | col |, no "Table N" / "Figure N" references)
## 3. Qualitative Observations
* ...
```

Rules: no figure or table numbers, past tense, no citations, URLs or author names, and numbers
100% accurate. The numbers become the refinement agent's ground truth.
`skills/paper-orchestra/scripts/validate_inputs.py --workspace <dir>` checks all four inputs.

Our addition: each number carries an evidence tag, `0.912 [E0031]`. Upstream treats it as text.
The driver tells PaperOrchestra to drop the tags from the LaTeX, and the numbers audit re-derives
provenance.

### `agent-research-aggregator`

`paper-orchestra/SKILL.md` runs it only when `idea.md` or `experimental_log.md` is missing or
empty. Our ingest always writes both, so it is skipped.

## Outputs

| Artifact | Path (relative to the PaperOrchestra workspace = `<ws>/paper/`) |
|---|---|
| Outline | `outline.json` |
| Generated figures + captions | `figures/*.png`, `figures/captions.json` |
| Bibliography | `refs.bib` (Step 3). The example also has a copy in `final/refs.bib` |
| Verified citation pool (S2 metadata, abstracts) | `citation_pool.json` |
| Intro + related work draft | `drafts/intro_relwork.tex` |
| Full draft | `drafts/paper.tex` |
| Refinement iterations | `refinement/iterN/` |
| **Final manuscript** | `final/paper.tex`, `final/paper.pdf` |

Figures are referenced from `final/paper.tex` as `../figures/<name>.png` (see
`examples/agentic-security-report/workspace/final/paper.tex`). `package_overleaf.py` rewrites
these to `figures/<name>.png` in the zip.

## Prompts that control section order and length (for M8)

- `skills/outline-agent/references/prompt.md`, input 3: *"template.tex: … You must use the
  section commands (e.g., \section{...}) found here as your primary skeleton."* Input 4 is
  `conference_guidelines.md` (page limits, mandatory sections).
- The same file's **Directive 3** names "Abstract, Methodology, Experiments, Conclusion, Appendix" as
  the sections to plan. This is a conference default, but the template skeleton takes precedence.
- `skills/section-writing-agent/references/prompt.md`: fills the *empty* sections of
  `template.tex` and must **not** modify sections that are already filled. Tables and figures go
  before the Conclusion.
- `skills/literature-review-agent/SKILL.md` §0 derives `cutoff_date` from the submission deadline
  in `conference_guidelines.md`.

### How code2paper steers journals (no upstream edits)

1. **Section order** comes from `inputs/template.tex`. We ship journal skeletons in
   `templates/latex/` (`article`, `elsarticle`, `achemso`) with the journal's section order:
   Methods, Results, Discussion, Conclusions, Nomenclature where relevant, and the statement sections.
2. **Fuller Methods, Nomenclature, Conclusions** are requested in
   `templates/guidelines/*.md` ("Mandatory sections"), which is passed as `conference_guidelines.md`.
3. **Statements** (CRediT, competing interests, data/code availability, AI-use) are filled into
   `template.tex` from `notes.md` *before* PaperOrchestra runs. Because the section writer does not
   modify filled sections, it cannot invent author contributions. Statements with no information
   in notes.md stay `TODO` and show up in REVIEW.md.
4. **Literature cutoff**: the journal guidelines say "no deadline; use the run date".

No upstream file was changed. If that ever becomes necessary, record the file, the change and the
reason here, and apply it as a patch in `scripts/install.sh`. Never edit `vendor/` by hand.

## Things upstream already does that overlap with ours

- The `literature-review-agent` verifies citations by S2 title match (Levenshtein > 70) and
  cross-checks Crossref/OpenAlex. That covers existence only. Our citation audit adds the
  sentence-level *support* check and the author sign-off.
- `paper-orchestra/scripts/claim_evidence_gate.py` and the content-refinement agent check claims
  against the experimental log. Our numbers audit goes further and traces every number to a repo
  file, line and commit.

## Checklist (plan §3)

- [x] Exact structure of `idea.md` and `experimental_log.md`
- [x] Where the final `.tex`, `.bib` and figures are written
- [x] Which prompts control section order and length
- [x] Licence: MIT; kept as an external pinned dependency
