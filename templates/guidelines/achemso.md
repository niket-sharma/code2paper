# Journal Guidelines (ACS journals, achemso class — article)

<!-- c2p:limits
page_limit:
word_limit: 7000
abstract_word_limit: 200
class: achemso
-->

This file is passed to PaperOrchestra as `inputs/conference_guidelines.md`.
Check the target ACS journal's author guidelines and adjust the limits above.

## Submission deadline

None (journal, rolling submission). Use today's date as the literature cutoff.

## Page limit

No page limit; main text under **7000 words** unless the journal says otherwise.

## Mandatory sections

The manuscript MUST contain, in this order:

1. Title, authors, affiliations, `\email` for the corresponding author
2. Abstract (at most 200 words; no citations)
3. Keywords (if the journal uses them)
4. Introduction
5. Methods (ACS journals often call this "Computational Methods" or
   "Experimental Section") — full detail with subsections.
6. Nomenclature / list of symbols when equations are heavy (may go in the
   Supporting Information)
7. Results and Discussion (ACS commonly combines these)
8. Conclusions
9. Associated Content — Supporting Information description
10. Author Information — corresponding author, ORCID, author contributions
11. Notes — competing financial interests statement
12. Data and Software Availability
13. Acknowledgments (funding)
14. Disclosure of AI use (where text or figures were produced with AI tools)
15. References (`achemso` numeric style, superscript or bracketed per journal)

## Formatting rules

- `\documentclass[journal=XXXXXX,manuscript=article]{achemso}`.
- Use `\begin{acknowledgement}`, `\begin{suppinfo}` environments.
- Bibliography via `achemso` style; DOIs included.
- Tables use booktabs; TOC graphic required by most ACS journals (not generated).

## Review criteria

Significance to the journal's readers, novelty, rigor and reproducibility,
clarity. Claims must match the evidence.
