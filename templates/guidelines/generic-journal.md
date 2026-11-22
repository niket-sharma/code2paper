# Journal Guidelines (generic research article)

<!-- c2p:limits
page_limit:
word_limit: 9000
abstract_word_limit: 250
class: article
-->

This file is passed to PaperOrchestra as `inputs/conference_guidelines.md`.
It steers the outline toward a journal article rather than a conference paper.

## Submission deadline

None (journal, rolling submission). Use today's date as the literature cutoff
date: papers published after the run date cannot be cited.

## Page limit

No page limit. Main text (excluding references, tables, captions and
statements) should stay under **9000 words**.

## Mandatory sections

The manuscript MUST contain, in this order:

1. Abstract (single paragraph, at most 250 words, no citations)
2. Keywords (4–6)
3. Introduction
4. Related Work (may be merged into the Introduction)
5. Methods — full detail: problem formulation, model, algorithm, implementation
   and evaluation protocol, so that a reader can reproduce the work from the
   paper alone. Use subsections.
6. Nomenclature — required when the paper defines more than about ten symbols
   (place before the Introduction or as an appendix table).
7. Results
8. Discussion — interpretation, limitations, threats to validity.
9. Conclusions — numbered or short paragraph form; no new results.
10. Data availability statement
11. Code availability statement
12. CRediT author contribution statement
13. Declaration of competing interests
14. Declaration of generative AI use in the writing process
15. Acknowledgements and funding
16. References

## Formatting rules

- Single column for review.
- Citations via natbib, author–year or numeric as the class requires.
- Tables use booktabs. Every table and figure is referenced in the text.
- Report variability (standard deviation or confidence interval, with the
  number of runs) wherever the experimental log provides it. Do not invent it.
- Not anonymised: author names and affiliations appear on the title page.

## Review criteria

Soundness, novelty versus the closest prior work, reproducibility (data,
code, hyperparameters, compute), clarity, and whether the claims are limited
to what the evidence supports.
