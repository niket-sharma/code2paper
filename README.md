# code2paper

Turn a code repository plus a one-page `notes.md` into a journal-format LaTeX manuscript, with
audit reports that show where every number and every citation came from.

code2paper is a **pack of Claude Code skills plus deterministic Python helpers**. It makes no LLM API
calls of its own: Claude Code is the runtime. The writing itself is done by
[PaperOrchestra](https://github.com/Ar9av/PaperOrchestra), used unmodified at a pinned commit.
code2paper adds what PaperOrchestra lacks:

1. **Repo ingest**: the repo becomes PaperOrchestra's input files, and every number is traced to a file, line and commit (`evidence_map.csv`).
2. **Gap check**: before any writing, the author is told what the evidence cannot support.
3. **Audits**: every number must match the evidence (rounding-aware). Every citation must exist, and its abstract must support the sentence it is attached to. Isolated subagents judge support.
4. **Human gate**: nothing is final until the author signs off on the flagged rows in `REVIEW.md`.

```
repo + notes.md + journal template
  → [1] c2p-repo-ingest      evidence_map.csv, idea.md, experimental_log.md
  → [2] c2p-gap-check        gap_report.md            ── AUTHOR DECISION
  → [3] paper-orchestra      paper.tex, refs.bib, figures
  → [4] c2p-numbers-audit    numbers_audit.csv  ┐ parallel
  → [5] c2p-citation-audit   citation_audit.csv ┘
  → [6] c2p-compile-check    paper.pdf, overleaf.zip
  → [7] REVIEW.md                                     ── AUTHOR SIGN-OFF
```

## Install

Requirements: Python 3.11+, git, Claude Code, and a LaTeX engine (`latexmk` from TeX Live, or `tectonic`).

```bash
git clone <this repo> code2paper && cd code2paper
scripts/install.sh            # clones PaperOrchestra@pinned into vendor/, pip installs, links skills into ~/.claude/skills
```

Optional: `export SEMANTIC_SCHOLAR_API_KEY=...` for a higher rate limit, and
`export C2P_MAILTO=you@example.org` for Crossref's polite pool.

## Use

```bash
python scripts/init_workspace.py --repo https://github.com/org/project --out workspace/ --guidelines elsarticle
$EDITOR workspace/notes.md    # working title, target journal, novelty claim, key results, prior work, authors, AI-use disclosure
```

Then, in Claude Code:

> Run code2paper on ./workspace

The `code2paper` skill runs each step and stops twice for you: after the gap report, and before
anything is final. You can resume at any time. It checks which outputs exist
(`skills/code2paper/scripts/pipeline_status.py`).

Guidelines and templates for journal families are in `templates/guidelines/` (`generic-journal`,
`elsarticle`, `achemso`) and `templates/latex/`.

## Workspace layout

```
workspace/
├── repo/        target repo at a pinned commit (read, never executed without approval)
├── notes.md     written by the author
├── inputs/      PaperOrchestra inputs (idea.md, experimental_log.md, template.tex, conference_guidelines.md, figures/)
├── evidence/    inventory.json, evidence_map.csv, gap_report.md, gap_decisions.md
├── paper/       PaperOrchestra's workspace (inputs/ → ../inputs); final manuscript in paper/final/
├── audits/      numbers_audit.csv, citation_audit.csv, compile_report.md, API cache
└── final/       paper.pdf, overleaf.zip, REVIEW.md
```

## Development

```bash
python -m pytest     # offline; HTTP responses are recorded in tests/fixtures/http_cache
uvx ruff check .
```

See `CLAUDE.md` for the rules, `PLAN.md` for the milestones, and `docs/upstream-notes.md` for what
code2paper relies on from PaperOrchestra.

## Status

| Milestone | State |
|---|---|
| M0 scaffold + upstream install | done |
| M1 baseline run on a pilot repo | **needs the pilot repo** (see PLAN.md §10) |
| M2 repo ingest | done; passes on `tests/fixtures/toy_repo` |
| M3 gap check | done; flags the unsupported key result in the toy notes |
| M4 numbers audit | done; catches all three seeded errors in `toy_paper` |
| M5 citation audit | done; flags the fabricated and the mis-cited reference; reruns are offline |
| M6 compile + package | done; untested against a real LaTeX engine here (none installed) |
| M7 driver skill | done; end-to-end run needs the pilot repo |
| M8 journal adaptation | guidelines and templates for elsarticle / achemso; needs the pilot paper to confirm |
