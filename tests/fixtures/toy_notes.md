# Paper notes

## Working title
SparseMix: Sparse Mixtures of Experts for Small Tabular Regression

## Target journal
Computers & Chemical Engineering — Research article
Guidelines: elsarticle

## Novelty claim
SparseMix is the first sparse mixture-of-experts regressor designed for small
tabular datasets. Versus gradient-boosted trees and linear models it lowers test
error at a similar training cost.

## Key results
- SparseMix reaches test RMSE 2.31 on HousingLite versus 2.87 for linear regression (results/results.csv)
- SparseMix reaches test R2 of 0.903 on ConcreteLite (results/metrics.json)
- SparseMix is 3.0x faster at inference than GBM (results/latency.csv)

## Closest prior work
- Shazeer et al. 2017, Outrageously large neural networks — arXiv:1701.06538
- Fedus et al. 2022, Switch Transformers — arXiv:2101.03961
- Chen and Guestrin 2016, XGBoost — doi:10.1145/2939672.2939785
- Grinsztajn et al. 2022, Why do tree-based models still outperform deep learning on tabular data? — arXiv:2207.08815

## Out of scope / limitations
Only two small datasets; single seed.

## Authors, affiliations, funding, AI-use disclosure
A. Author, Example University. No external funding.
AI-use disclosure: Claude Code was used to draft the manuscript from the code repository; the authors checked every number and reference and take responsibility for the content.
