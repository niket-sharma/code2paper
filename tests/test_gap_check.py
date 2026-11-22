from __future__ import annotations

import json
from pathlib import Path

from conftest import FIX, run


def test_unsupported_key_result_flagged(ingested: dict[str, Path], tmp_path: Path) -> None:
    out = tmp_path / "gap_scan.json"
    run("gap_scan", "--notes", FIX / "toy_notes.md", "--evidence-map", ingested["map"],
        "--inventory", ingested["inventory"], "--repo", ingested["repo"], "--out", out)
    scan = json.loads(out.read_text())
    def status(prefix: str) -> str:
        return next(k["status"] for k in scan["key_results"] if k["text"].startswith(prefix))

    assert scan["blocking"] == []
    assert status("SparseMix reaches test RMSE") == "supported_candidate"
    assert status("SparseMix reaches test R2") == "supported_candidate"
    assert status("SparseMix is 3.0x faster") == "not_found"
    checks = {c["check"]: c["status"] for c in scan["evidence_checks"]}
    assert checks["baselines"] == "present"
    assert checks["multiple_seeds"] == "possibly_missing"
    assert checks["error_bars"] == "possibly_missing"
    assert checks["dataset_description"] == "present"
    assert scan["guidelines"] == "elsarticle"


def test_missing_novelty_stops_pipeline(ingested: dict[str, Path], tmp_path: Path) -> None:
    notes = tmp_path / "notes.md"
    notes.write_text((FIX.parent.parent / "templates" / "notes.md").read_text())
    p = run("gap_scan", "--notes", notes, "--evidence-map", ingested["map"], "--inventory", ingested["inventory"],
            "--repo", ingested["repo"], "--out", tmp_path / "g.json", check=False)
    assert p.returncode == 3
    assert "Novelty claim is empty" in p.stdout and "Target journal is empty" in p.stdout
