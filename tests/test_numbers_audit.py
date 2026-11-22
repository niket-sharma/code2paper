from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from conftest import FIX, run

from c2p.common import read_evidence, write_evidence

PAPER = FIX / "toy_paper" / "paper.tex"


@pytest.fixture
def audit(ingested: dict[str, Path], tmp_path: Path) -> dict[str, Path]:
    nums = tmp_path / "audits" / "numbers.json"
    run("extract_numbers", "--tex", PAPER, "--out", nums)
    return {**ingested, "numbers": nums, "out": tmp_path / "audits" / "numbers_audit.csv"}


def rows_of(path: Path) -> list[dict[str, str]]:
    with open(path) as f:
        return list(csv.DictReader(f))


def test_extract_ignore_rules(audit: dict[str, Path]) -> None:
    nums = json.loads(audit["numbers"].read_text())
    ign = {(n["value"], n["note"]) for n in nums if n["status"] == "ignored"}
    assert ("2017", "year in citation context") in ign
    assert ("3", "section/figure/table numbering") in ign
    assert ("2", "small integer count in prose") in ign
    vals = [n["value"] for n in nums]
    assert "0.8" not in vals  # graphics width stripped
    assert "770" not in vals  # bibliography not scanned
    table = [n for n in nums if n["where"] == "table"]
    assert {(n["row_label"], n["col_label"]) for n in table if n["value"] == "2.45"} == {("GBM", "RMSE")}


def test_three_seeded_errors_reported(audit: dict[str, Path]) -> None:
    p = run("match", "--numbers", audit["numbers"], "--evidence-map", audit["map"], "--out", audit["out"], check=False)
    assert p.returncode == 1
    rows = rows_of(audit["out"])
    flagged = {(r["value_in_paper"], r["status"]) for r in rows if r["status"] in {"conflict", "unmatched"}}
    assert ("2.45", "conflict") in flagged            # changed digit
    assert ("5.12", "conflict") in flagged            # swapped condition
    assert ("37.5%", "unmatched") in flagged          # invented
    assert ("19.5%", "unmatched") in flagged          # correct but derived: needs a derived row
    assert len(flagged) == 4
    ok = {r["value_in_paper"] for r in rows if r["status"] in {"matched", "rounding_ok"}}
    assert {"2.31", "2.87", "0.001", "32", "64", "404", "102", "0.874", "1.60", "2.04", "1.71", "14.2"} <= ok
    swapped = next(r for r in rows if r["value_in_paper"] == "5.12")
    gbm_concrete = next(r for r in read_evidence(audit["map"])
                        if r["metric"] == "test_rmse" and r["condition"] == "model=gbm;dataset=ConcreteLite")
    assert swapped["evidence_id"] == gbm_concrete["evidence_id"]


def test_derived_row_makes_reduction_pass(audit: dict[str, Path]) -> None:
    rows = read_evidence(audit["map"])
    by = {(r["metric"], r["condition"]): r["evidence_id"] for r in rows}
    sp = by[("test_rmse", "model=sparsemix;dataset=HousingLite")]
    lin = by[("test_rmse", "model=linear;dataset=HousingLite")]
    d = {k: "" for k in rows[0]}
    d.update(evidence_id="E0999", value="19.4529", unit="%", metric="test_rmse_reduction", kind="derived",
             condition="sparsemix vs linear;dataset=HousingLite", derived_from=f"{lin};{sp}",
             formula=f"({lin} - {sp}) / {lin} * 100")
    write_evidence(audit["map"], rows + [d])
    run("validate", "--evidence-map", audit["map"], "--repo", audit["repo"])
    run("match", "--numbers", audit["numbers"], "--evidence-map", audit["map"], "--out", audit["out"], check=False)
    red = next(r for r in rows_of(audit["out"]) if r["value_in_paper"] == "19.5%")
    assert red["status"] == "derived_ok" and red["evidence_id"] == "E0999"


def test_resolutions_cannot_fake_a_match(audit: dict[str, Path], tmp_path: Path) -> None:
    rows = read_evidence(audit["map"])
    gbm = next(r for r in rows if r["metric"] == "test_rmse" and r["condition"] == "model=gbm;dataset=HousingLite")
    res = tmp_path / "res.csv"
    res.write_text("tex_file,line,value,status,evidence_id,note\n"
                   f"paper.tex,51,2.45,matched,{gbm['evidence_id']},trust me\n"
                   "paper.tex,39,37.5,ignored,,\n")
    p = run("match", "--numbers", audit["numbers"], "--evidence-map", audit["map"], "--out", audit["out"],
            "--resolutions", res, check=False)
    assert p.returncode == 1
    assert "does not match value 2.45" in p.stdout
    assert "'ignored' needs a reason" in p.stdout
    still = {r["value_in_paper"]: r["status"] for r in rows_of(audit["out"])}
    assert still["2.45"] == "conflict" and still["37.5%"] == "unmatched"


def test_resolution_ignored_with_reason(audit: dict[str, Path], tmp_path: Path) -> None:
    res = tmp_path / "res.csv"
    res.write_text("tex_file,line,value,status,evidence_id,note\npaper.tex,39,37.5,ignored,,author removed claim\n")
    run("match", "--numbers", audit["numbers"], "--evidence-map", audit["map"], "--out", audit["out"],
        "--resolutions", res, check=False)
    r = next(r for r in rows_of(audit["out"]) if r["value_in_paper"] == "37.5%")
    assert r["status"] == "ignored" and "author removed claim" in r["note"]
