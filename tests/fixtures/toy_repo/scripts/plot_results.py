"""Plot test RMSE per model -> figures/rmse_bar.png"""
import csv

import matplotlib.pyplot as plt

rows = list(csv.DictReader(open("results/results.csv")))
house = [r for r in rows if r["dataset"] == "HousingLite"]
plt.bar([r["model"] for r in house], [float(r["test_rmse"]) for r in house])
plt.ylabel("Test RMSE")
plt.savefig("figures/rmse_bar.png", dpi=150)
