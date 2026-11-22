# code2paper — conventions for Claude Code

code2paper is a pack of Claude Code skills (`skills/*/SKILL.md`) plus deterministic Python
helpers (`skills/*/scripts/`, shared code in `src/c2p/`). It has no LLM SDK calls. Claude Code is
the runtime. PLAN.md is the implementation plan. docs/upstream-notes.md records what we rely on
from PaperOrchestra.

## Rules

1. Scripts are deterministic and have no LLM calls. Judgement lives in skills.
2. Never write a number into any pipeline file without an evidence ID.
3. Never change `evidence_map.csv` to make an audit pass. Fix the paper, or report the conflict.
   (Adding a correct `derived` row that recomputes from existing rows is allowed.)
4. Never add a reference that failed the existence check.
5. Do not execute code from the target repo without the author's approval.
6. Do not modify files under `vendor/`. Record needed upstream changes in `docs/upstream-notes.md`.
7. Every script: `--help`, non-zero exit on failure, writes only inside the workspace
   (`c2p.common.guard_output`).
8. Python 3.11+, type hints, `pytest`, `ruff`.

## Layout

- `src/c2p/`: shared helpers: `common.py` (evidence schema, rounding, safe formulas, write guard),
  `latex.py` (offset-preserving stripping, sentences, BibTeX), `http.py` (cached and rate-limited
  GET), `scholar.py` (Crossref/S2/OpenAlex/arXiv), `notes.py` (notes.md parser).
- Scripts put `src/` on `sys.path` relative to their real path, so they also work through the
  `~/.claude/skills/` symlinks with no install step.
- `tests/fixtures/toy_repo`: a repo with known numbers (`toy_repo_truth.json`).
  `tests/fixtures/toy_paper`: seeded errors (`SEEDED_ERRORS.md`).
  `tests/fixtures/http_cache`: recorded API responses, so tests never use the network.

## Commands

```bash
python -m pytest            # all tests, offline
ruff check .                # lint
scripts/install.sh          # clone PaperOrchestra (pinned) into vendor/, link skills
python scripts/init_workspace.py --repo <url|path> --out workspace/
```

To re-record HTTP fixtures after changing a lookup, run `verify_existence.py` and
`fetch_abstracts.py` against `tests/fixtures/toy_paper` with `--cache-dir tests/fixtures/http_cache`
(no `--offline`) until both report 0 failed requests.
