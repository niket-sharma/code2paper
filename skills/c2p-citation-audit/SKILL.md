---
name: c2p-citation-audit
description: Check that every citation in a LaTeX manuscript exists (Crossref / Semantic Scholar / OpenAlex) and that the cited abstract supports the sentence it is attached to, using isolated subagents. Produces citation_audit.csv for author sign-off. Use as step 5 of code2paper, or when asked to "verify the references".
---

# c2p-citation-audit

Check that each cited paper exists and supports the sentence it is attached to.

## Inputs

- `$WS/paper/final/paper.tex` and its `.bib` (found from `\bibliography{}`; PaperOrchestra writes `$WS/paper/refs.bib`).
- `$WS/notes.md`, for the closest-prior-work check.
- Optional environment variables: `SEMANTIC_SCHOLAR_API_KEY` (higher rate limit) and `C2P_MAILTO` (Crossref polite pool). Use the author's email for `C2P_MAILTO` only if they gave it for this purpose.

## Hard rules

- Never add a reference to the paper that failed the existence check (`exists` is not `yes`).
- The support check runs in **separate subagents that have not seen the manuscript**. Each one gets only the sentence, the cited title and the abstract.
- `no_abstract`, `partial` and `ambiguous` are never auto-passed. They need the author's sign-off.

## Steps

1. **Extract citations.**
   ```bash
   python <skill-dir>/scripts/extract_citations.py --tex $WS/paper/final/paper.tex \
       --notes $WS/notes.md --out $WS/audits/citations.json
   ```
2. **Existence check.** Responses are cached, so a rerun makes no network calls.
   ```bash
   python <skill-dir>/scripts/verify_existence.py --citations $WS/audits/citations.json \
       --cache-dir $WS/audits/cache --out $WS/audits/existence.json
   ```
   If entries come back `ambiguous` with "lookup incomplete (HTTP 429)", wait a minute and rerun. Only the failed requests are retried.
3. **Abstracts** (Semantic Scholar, then OpenAlex, then arXiv):
   ```bash
   python <skill-dir>/scripts/fetch_abstracts.py --existence $WS/audits/existence.json \
       --cache-dir $WS/audits/cache --out $WS/audits/abstracts.json
   ```
4. **Support tasks.**
   ```bash
   python <skill-dir>/scripts/assemble_audit.py tasks --audits $WS/audits
   ```
   Each line of `support_tasks.jsonl` has `task_id`, `cited_title`, `sentence` and `abstract`.
5. **Support check with isolated subagents.** For each task, or in batches of up to 10 tasks per subagent, start a subagent (the Agent tool) with **only** this prompt and the task fields. Do not include the manuscript, the notes or other sentences:

   > You check whether a cited paper supports a sentence, using only the paper's abstract.
   > For each task, answer with one JSON object per line:
   > `{"task_id": "...", "support": "supports" | "partial" | "unsupported", "rationale": "<one line>"}`
   > - `supports`: the abstract states or directly implies what the sentence attributes to the paper.
   > - `partial`: the abstract supports part of the claim, or a weaker or related version.
   > - `unsupported`: the abstract does not support the claim, or contradicts it.
   > When a sentence cites several papers, judge only whether *this* paper supports its share of the claim.
   > A sentence that just names the paper's method ("we use Adam [x]") is `supports` if the abstract introduces that method.
   > Do not use outside knowledge of the paper beyond the abstract.

   Append each returned line, unchanged, to `$WS/audits/support.jsonl`.
6. **Assemble.**
   ```bash
   python <skill-dir>/scripts/assemble_audit.py build --audits $WS/audits
   ```
   This writes `citation_audit.csv` (`cite_key, sentence, tex_line, doi, exists, metadata_match, abstract_source, support, rationale, author_signoff`) and `citation_report.md`. The report also lists bib entries never cited, `\cite` keys with no bib entry, and closest prior work from notes.md that is not cited. Reruns keep any `author_signoff` the author has already filled in.

## Outputs

`audits/citations.json`, `audits/existence.json`, `audits/abstracts.json`, `audits/support_tasks.jsonl`, `audits/support.jsonl`, `audits/citation_audit.csv`, `audits/citation_report.md` and `audits/cache/`.

## Stop conditions

Finish after step 6 and report the flagged rows. Exit code 1 from `build` means some rows still need the author's sign-off or a fix. That is expected before sign-off.
