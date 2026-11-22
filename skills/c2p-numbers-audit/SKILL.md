---
name: c2p-numbers-audit
description: Check that every number in a LaTeX manuscript matches the evidence map (rounding-aware, with derived values), producing numbers_audit.csv and failing on any mismatch. Use as step 4 of code2paper, or when asked to "check the numbers in the paper".
---

# c2p-numbers-audit

Every number in the paper must match a row of `evidence_map.csv`, or be explicitly ignored with a reason.

## Inputs

- The manuscript: `$WS/paper/final/paper.tex` (PaperOrchestra output; `\input` files are followed).
- `$WS/evidence/evidence_map.csv`

## Hard rules

- **Never edit `evidence_map.csv` to make a number pass.** The only change allowed is *adding* a correct `derived` row whose formula recomputes from existing rows. The validator checks this.
- Never mark a number `matched`, `rounding_ok` or `derived_ok` without an evidence ID whose value really matches. The script enforces this for resolutions.

## Steps

1. **Extract.**
   ```bash
   python <skill-dir>/scripts/extract_numbers.py --tex $WS/paper/final/paper.tex --out $WS/audits/numbers.json
   ```
   Default ignore rules: years in citation context, section/figure/table numbering, small integer counts (≤ 10) in prose, and identifiers like `ResNet-50`. Each is kept as `ignored` with its reason.

2. **Match.**
   ```bash
   python <skill-dir>/scripts/match_evidence.py --numbers $WS/audits/numbers.json \
       --evidence-map $WS/evidence/evidence_map.csv --out $WS/audits/numbers_audit.csv \
       --resolutions $WS/audits/number_resolutions.csv
   ```
   (`--resolutions` is optional the first time.) The statuses are:
   - `matched` / `rounding_ok`: the value equals the evidence value rounded to the precision shown.
   - `derived_ok`: it matches a `derived` row.
   - `conflict`: the context names a different row than the value matches (swapped condition), or the context identifies a row whose value differs (changed digit).
   - `unmatched`: no evidence. The note may suggest a derivation.

3. **Resolve what the script could not**, by reading each flagged row's context in the `.tex`:
   - **Correct derived value** (for example "a 19.5% reduction", where the note suggests `(E0027 - E0030) / E0030 * 100`): check that the formula is what the sentence means. If it is, append a `derived` row to `evidence_map.csv` (`kind=derived`, empty `source_file`, `derived_from`, `formula`, `value` at full precision). Then run `validate_evidence_map.py` from c2p-repo-ingest.
   - **Script picked the wrong row of the same value** (`ambiguous` note): add a line to `$WS/audits/number_resolutions.csv` (`tex_file,line,value,status,evidence_id,note`) with the right ID.
   - **Number that is not a quantity claim** (an equation constant, a version number, a page reference): add a resolution with `status=ignored` and a reason in `note`.
   - **Genuine errors** (`conflict`, or an `unmatched` number with no source): do not resolve them. They go to the fix round (in the driver) or into REVIEW.md.

4. Rerun step 2 until only genuine errors remain. Exit code 1 means some remain.

## Outputs

`audits/numbers.json`, `audits/numbers_audit.csv` (`tex_file, line, context, value_in_paper, status, evidence_id, note`), and optionally `audits/number_resolutions.csv`.

## Stop conditions

Finish after step 4. Report the counts per status and list every `conflict` and `unmatched` row with its file:line.
