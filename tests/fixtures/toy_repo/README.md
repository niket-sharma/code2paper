# SparseMix

SparseMix is a sparse mixture-of-experts regressor for small tabular datasets.
It routes each sample to 2 of 8 experts.

## Results

On HousingLite, SparseMix reaches a test RMSE of 2.31, versus 2.87 for the
linear baseline. Training takes 14.2 seconds on a laptop CPU.

See `results/results.csv` for all numbers.
