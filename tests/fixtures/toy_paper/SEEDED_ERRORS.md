# Seeded errors in toy_paper

Evidence comes from `tests/fixtures/toy_repo` (see `toy_repo_truth.json`).

## Numbers (M4)

| tex line text | paper | truth | kind |
|---|---|---|---|
| `GBM & 2.45 & 1.71` | 2.45 | 2.4410 (gbm, HousingLite, test_rmse) | changed digit |
| `The GBM baseline reaches a test RMSE of 5.12 on ConcreteLite` | 5.12 | 5.6017 for GBM; 5.12 is SparseMix | swapped condition |
| `reduces inference latency by 37.5\%` | 37.5% | no latency data in repo | invented number |

`relative reduction of 19.5\%` is correct but derived: (2.8731 - 2.3142) / 2.8731 * 100 = 19.45.
It is `unmatched` until a `derived` row exists, then `derived_ok`.

## Citations (M5)

| key | problem |
|---|---|
| `smith2021quantum` | fabricated: title, authors, journal and DOI do not exist |
| `kingma2015adam` (first use) | real paper (Adam optimizer) cited for a claim about gradient-boosted trees |
| `fedus2022switch` | `\cite` key with no bib entry |
| `srivastava2014dropout` | bib entry never cited |
