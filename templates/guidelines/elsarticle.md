# Journal Guidelines (Elsevier, elsarticle class — research article)

<!-- c2p:limits
page_limit:
word_limit: 8000
abstract_word_limit: 250
highlights: 3-5 bullets, max 85 characters each
class: elsarticle
-->

This file is passed to PaperOrchestra as `inputs/conference_guidelines.md`.
Check the specific journal's Guide for Authors and adjust the limits above.

## Submission deadline

None (journal, rolling submission). Use today's date as the literature cutoff.

## Page limit

No page limit. Main text should stay under **8000 words** unless the journal
says otherwise.

## Mandatory sections

The manuscript MUST contain, in this order:

1. Title, authors, affiliations (`\author`, `\affiliation` in the `frontmatter`)
2. Abstract (at most 250 words, no citations, no undefined abbreviations)
3. Highlights (3–5 bullets, each at most 85 characters including spaces)
4. Keywords (1–7)
5. Nomenclature (required when the paper is equation-heavy; a two-column
   symbol/description table)
6. Introduction
7. Methods (or "Materials and methods") — full detail, with subsections for
   problem formulation, model, algorithm, data and evaluation protocol.
8. Results
9. Discussion
10. Conclusions
11. CRediT authorship contribution statement
12. Declaration of competing interest
13. Declaration of generative AI and AI-assisted technologies in the writing process
14. Data availability
15. Acknowledgements (funding sources go here)
16. References (`elsarticle-num` or `elsarticle-harv` style)
17. Appendices (optional)

## Formatting rules

- `\documentclass[preprint,12pt]{elsarticle}`; review layout single column.
- Use `\begin{frontmatter} ... \end{frontmatter}` for title, authors, abstract,
  highlights and keywords.
- Bibliography style `elsarticle-num` unless the journal is author–year.
- Tables use booktabs; figures as PDF or 300 dpi PNG.
- The AI-use declaration must state the tool, the purpose, and that the
  authors reviewed and take responsibility for the content.

## Review criteria

Novelty versus the closest prior work, technical soundness, reproducibility,
and clarity. Claims must be limited to what the results support.
