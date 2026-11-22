"""Train SparseMix and baselines; writes results/results.csv and results/metrics.json."""
import yaml

from model import SparseMix


def main(cfg_path: str = "configs/default.yaml") -> None:
    cfg = yaml.safe_load(open(cfg_path))
    model = SparseMix(in_dim=13, hidden_dim=cfg["model"]["hidden_dim"])
    print(model)


if __name__ == "__main__":
    main()
