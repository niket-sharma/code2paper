# code2paper review — {{title}}

Generated {{date}} from workspace `{{workspace}}`. Target repo commit `{{commit}}`.

Nothing in `final/` is ready to submit until every box below is ticked by the author.

## Summary

| Check | Result |
|---|---|
| Numbers in paper | {{n_numbers}} checked: {{n_num_ok}} matched, {{n_num_ignored}} ignored, **{{n_num_flagged}} flagged** |
| Citations | {{n_cites}} (sentence, reference) pairs: **{{n_cite_flagged}} need author sign-off**, {{n_cite_signed}} signed off |
| References that failed existence check | {{n_ref_missing}} |
| Compile | {{compile_status}} |
| Page / word limits | {{limits_status}} |

## Flagged numbers

{{numbers_table}}

## Citations needing sign-off

Fill the `author_signoff` column in `audits/citation_audit.csv` (e.g. `ok — checked full text`, `drop`).

{{citations_table}}

## Gap decisions

{{gap_decisions}}

## AI-use disclosure

{{ai_disclosure}}

## Sign-off checklist

- [ ] Every flagged number above is fixed in the paper or explained.
- [ ] Every `partial`, `unsupported`, `no_abstract` and `ambiguous` citation row has an `author_signoff` entry.
- [ ] No reference in `refs.bib` failed the existence check.
- [ ] Gap decisions above are still accurate; narrowed claims read correctly.
- [ ] Author list, affiliations, funding and CRediT statement are correct.
- [ ] Data availability, competing interests and AI-use statements are present and true.
- [ ] `overleaf.zip` compiles on Overleaf without edits.
- [ ] I have read the whole manuscript.

Signed: ____________________  Date: __________
