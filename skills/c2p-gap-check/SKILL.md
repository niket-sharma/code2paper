---
name: c2p-gap-check
description: Compare the author's notes.md (key results, novelty claim, prior work) against the evidence map and report what the evidence cannot support, before any writing. Use as step 2 of code2paper, or when asked "what can this repo support?" / "check gaps before writing". Always stops for an author decision.
---

# c2p-gap-check

Tell the author what the evidence cannot support before any writing happens. Then stop and ask them how to proceed.

## Inputs

- `$WS/notes.md`
- `$WS/evidence/evidence_map.csv`, `$WS/evidence/inventory.json`, `$WS/evidence/method_summary.md` (from c2p-repo-ingest)
- `$WS/repo/`, which you read only. Never execute it.

## Steps

1. **Deterministic scan.**
   ```bash
   python <skill-dir>/scripts/gap_scan.py --notes $WS/notes.md \
       --evidence-map $WS/evidence/evidence_map.csv --inventory $WS/evidence/inventory.json \
       --repo $WS/repo --out $WS/evidence/gap_scan.json
   ```
   Exit code 3 means the novelty claim or target journal is empty. Tell the author which field is missing and **stop**.

2. **Judge each key result** in the notes. The scan's status is only a first guess. Open the cited file and the evidence rows and decide:
   - **supported**: the claim, including its direction and size, follows from evidence rows. List their IDs.
   - **partly supported**: the evidence exists but is weaker than the claim. Examples: one dataset where the claim says "datasets", one seed, a smaller margin than stated, or a number in the notes that does not match the evidence.
   - **not found**: no evidence. The file is missing or holds nothing relevant.

3. **Check for missing evidence types.** Start from `evidence_checks` in the scan and confirm each one by reading the repo:
   - baselines
   - ablations
   - multiple seeds
   - error bars or variance
   - dataset description
   - compute details (hardware, runtime)
   - statistical tests

   For each, say whether it is present (give the IDs) or missing, and why it matters for this paper.

4. **Novelty versus prior work.** For each paper in the notes' "Closest prior work", say what comparison a reviewer will expect: a head-to-head result, a qualitative difference, or a related-work paragraph only. Say whether the repo has it. Flag prior work entries with no DOI or arXiv ID.

5. **Write `$WS/evidence/gap_report.md`** with these sections: Summary (a one-paragraph verdict), Key results (a table of claim, verdict, evidence IDs, problem), Missing evidence, Novelty versus prior work, and Options. In Options, give **two choices** for every gap:
   - **Add evidence**: the exact experiment or log to add, for example "run `train.py --seed 1..4` and log test RMSE per seed". Do not run it.
   - **Narrow the claim**: replacement wording the current evidence supports, for example "on HousingLite (single seed), SparseMix reached RMSE 2.31 [E0027] vs 2.87 [E0030]".

6. **Stop and ask the author.** Show the summary and the options. Ask, per gap, "add evidence" or "narrow the claim", and whether to go ahead. Do not start writing.

7. When the author answers, record the decisions verbatim in `$WS/evidence/gap_decisions.md`: one line per gap with the choice and any agreed wording, plus the date. If the author chose "narrow the claim", update `inputs/idea.md` (Expected Contribution) and the notes-derived wording to match. If they chose "add evidence", stop the pipeline until the new evidence exists, then rerun c2p-repo-ingest.

## Outputs

`evidence/gap_scan.json`, `evidence/gap_report.md`, and (after the author answers) `evidence/gap_decisions.md`.

## Stop conditions

- Always stop after writing `gap_report.md`, even when there are no gaps. The author must confirm.
- notes.md is missing its novelty claim or target journal.
