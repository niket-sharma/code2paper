from __future__ import annotations

import csv
import json
from pathlib import Path

from conftest import FIX, run

from c2p.common import read_evidence, sha256_file, write_evidence


def test_inventory_roles(ingested: dict[str, Path]) -> None:
    inv = json.loads(ingested["inventory"].read_text())
    roles = {f["path"]: f["role"] for f in inv["files"]}
    assert roles["README.md"] == "readme"
    assert roles["results/results.csv"] == "result_table"
    assert roles["results/metrics.json"] == "result_table"
    assert roles["logs/train.log"] == "log"
    assert roles["configs/default.yaml"] == "config"
    assert roles["figures/rmse_bar.png"] == "figure"
    assert roles["src/model.py"] == "core_code"
    assert len(inv["commit"]) == 40
    assert not any(p.startswith(".git/") for p in roles)


def test_all_known_numbers_found(ingested: dict[str, Path]) -> None:
    rows = read_evidence(ingested["map"])
    truth = json.loads((FIX / "toy_repo_truth.json").read_text())["numbers"]
    for t in truth:
        hits = [r for r in rows if r["source_file"] == t["source_file"] and r["value"] == t["value"]
                and r["metric"] == t["metric"] and int(r["line_start"]) == t["line"]]
        assert hits, f"missing {t}"
        r = hits[0]
        for word in t.get("condition_has", []):
            assert word in r["condition"], (t, r["condition"])
        if "unit" in t:
            assert r["unit"] == t["unit"]
        if "kind" in t:
            assert r["kind"] == t["kind"]
    assert all(r["method"] == "parsed" for r in rows)
    assert {r["kind"] for r in rows if r["source_file"] == "configs/default.yaml"} == {"hyperparameter"}


def test_validator_passes(ingested: dict[str, Path]) -> None:
    p = run("validate", "--evidence-map", ingested["map"], "--repo", ingested["repo"])
    assert "0 problem(s)" in p.stdout


def test_ids_stable_and_read_rows_kept(ingested: dict[str, Path]) -> None:
    rows = read_evidence(ingested["map"])
    before = {(r["source_file"], r["metric"], r["condition"], r["line_start"]): r["evidence_id"] for r in rows}
    readme_line = (ingested["repo"] / "README.md").read_text().splitlines()[7]
    rows.append({**rows[0], "evidence_id": "E0900", "value": "2.31", "metric": "test_rmse",
                 "condition": "model=sparsemix;dataset=HousingLite", "kind": "result",
                 "source_file": "README.md", "line_start": "8", "line_end": "8",
                 "file_sha256": sha256_file(ingested["repo"] / "README.md"),
                 "quote": readme_line.strip(), "method": "read"})
    write_evidence(ingested["map"], rows)
    run("extract_results", "--repo", ingested["repo"], "--inventory", ingested["inventory"],
        "--evidence-map", ingested["map"])
    after_rows = read_evidence(ingested["map"])
    after = {(r["source_file"], r["metric"], r["condition"], r["line_start"]): r["evidence_id"] for r in after_rows}
    for k, v in before.items():
        assert after[k] == v
    assert any(r["evidence_id"] == "E0900" and r["method"] == "read" for r in after_rows)
    run("validate", "--evidence-map", ingested["map"], "--repo", ingested["repo"])


def _mutate(path: Path, eid: str, **changes: str) -> None:
    rows = read_evidence(path)
    for r in rows:
        if r["evidence_id"] == eid:
            r.update(changes)
    write_evidence(path, rows)


def test_validator_catches_bad_quote_hash_and_derived(ingested: dict[str, Path]) -> None:
    m = ingested["map"]
    rows = read_evidence(m)
    rmse = {r["condition"]: r for r in rows if r["metric"] == "test_rmse"}
    sp, lin = rmse["model=sparsemix;dataset=HousingLite"], rmse["model=linear;dataset=HousingLite"]
    good = {k: "" for k in rows[0]}
    good.update(evidence_id="E0800", value="19.4529", unit="%", metric="rmse_reduction", kind="derived",
                derived_from=f"{lin['evidence_id']};{sp['evidence_id']}",
                formula=f"({lin['evidence_id']} - {sp['evidence_id']}) / {lin['evidence_id']} * 100")
    bad = {**good, "evidence_id": "E0801", "value": "25.0"}
    write_evidence(m, rows + [good])
    run("validate", "--evidence-map", m, "--repo", ingested["repo"])
    write_evidence(m, rows + [good, bad])
    p = run("validate", "--evidence-map", m, "--repo", ingested["repo"], check=False)
    assert p.returncode == 1 and "E0801" in p.stdout and "E0800" not in p.stdout

    write_evidence(m, rows)
    _mutate(m, sp["evidence_id"], quote="sparsemix,HousingLite,2.9999")
    _mutate(m, lin["evidence_id"], file_sha256="0" * 64)
    _mutate(m, rows[0]["evidence_id"], line_start="999", line_end="999")
    p = run("validate", "--evidence-map", m, "--repo", ingested["repo"], check=False)
    assert p.returncode == 1
    assert f"{sp['evidence_id']}: quote not found" in p.stdout
    assert f"{lin['evidence_id']}: file_sha256 mismatch" in p.stdout
    assert "out of range" in p.stdout


def test_experimental_log_check(ingested: dict[str, Path], tmp_path: Path) -> None:
    rows = read_evidence(ingested["map"])
    by = {(r["metric"], r["condition"]): r["evidence_id"] for r in rows}
    sp = by[("test_rmse", "model=sparsemix;dataset=HousingLite")]
    lin = by[("test_rmse", "model=linear;dataset=HousingLite")]
    lr = by[("lr", "optim")]
    log = tmp_path / "experimental_log.md"
    log.write_text(
        "# Experimental Log\n\n## 1. Experimental Setup\n"
        f"* **Implementation Details:** learning rate 0.001 [{lr}], model `ResNet-50`, an A100 GPU.\n\n"
        "## 2. Raw Numeric Data\n\n| Model | RMSE |\n|---|---|\n"
        f"| SparseMix | 2.31 [{sp}] |\n| Linear | 2.87 [{lin}] |\n\n## 3. Qualitative Observations\n* Training converged.\n"
    )
    run("validate", "--evidence-map", ingested["map"], "--repo", ingested["repo"], "--experimental-log", log)
    text = log.read_text()
    log.write_text(text.replace(f"2.87 [{lin}]", "2.87").replace(f"2.31 [{sp}]", f"2.41 [{sp}]"))
    p = run("validate", "--evidence-map", ingested["map"], "--repo", ingested["repo"],
            "--experimental-log", log, check=False)
    assert p.returncode == 1
    assert "number 2.87 has no evidence ID" in p.stdout
    assert "2.41 does not match" in p.stdout


def test_csv_quotes_are_full_lines(ingested: dict[str, Path]) -> None:
    lines = (ingested["repo"] / "results/results.csv").read_text().splitlines()
    with open(ingested["map"]) as f:
        for r in csv.DictReader(f):
            if r["source_file"] == "results/results.csv":
                assert r["quote"] == lines[int(r["line_start"]) - 1]
