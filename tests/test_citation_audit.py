from __future__ import annotations

import csv
import json
import shutil
import urllib.request
from pathlib import Path

import pytest
from conftest import FIX, SCRIPTS, run

PAPER = FIX / "toy_paper" / "paper.tex"
CACHE = FIX / "http_cache"


@pytest.fixture
def audits(tmp_path: Path) -> Path:
    a = tmp_path / "audits"
    run("extract_citations", "--tex", PAPER, "--notes", FIX / "toy_notes.md", "--out", a / "citations.json")
    shutil.copytree(CACHE, a / "cache")
    return a


def test_extract_citations_report(audits: Path) -> None:
    data = json.loads((audits / "citations.json").read_text())
    rep = data["report"]
    assert rep["missing_bib_entries"] == ["fedus2022switch"]
    assert rep["uncited_bib_entries"] == ["srivastava2014dropout"]
    assert len(rep["prior_work_not_cited"]) == 2
    assert any("Grinsztajn" in p for p in rep["prior_work_not_cited"])
    adam = [c for c in data["cites"] if c["cite_key"] == "kingma2015adam"]
    assert adam[0]["sentence"].startswith("Gradient boosting with regularised trees")
    assert all("Introduction" not in c["sentence"] for c in data["cites"])


def test_existence_offline_and_no_network(audits: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # in-process run so we can forbid the network outright
    import importlib.util
    import sys

    def boom(*a: object, **k: object) -> None:
        raise AssertionError("network call attempted")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    spec = importlib.util.spec_from_file_location("verify_existence", SCRIPTS["verify"])
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    monkeypatch.setattr(sys, "argv", ["verify", "--citations", str(audits / "citations.json"),
                                      "--cache-dir", str(audits / "cache"), "--out", str(audits / "existence.json")])
    assert mod.main() == 0
    res = json.loads((audits / "existence.json").read_text())
    assert res["network_calls"] == 0
    ex = {k: v["exists"] for k, v in res["results"].items()}
    assert ex["smith2021quantum"] == "no"
    for k in ("he2016deep", "kingma2015adam", "shazeer2017outrageously", "chen2016xgboost", "srivastava2014dropout"):
        assert ex[k] == "yes", (k, res["results"][k]["metadata_match"])


def test_full_citation_audit(audits: Path) -> None:
    run("verify", "--citations", audits / "citations.json", "--cache-dir", audits / "cache",
        "--out", audits / "existence.json", "--offline")
    p = run("abstracts", "--existence", audits / "existence.json", "--cache-dir", audits / "cache",
            "--out", audits / "abstracts.json", "--offline")
    assert "failed or uncached requests: 0" in p.stdout
    run("assemble", "tasks", "--audits", audits)
    tasks = [json.loads(line) for line in (audits / "support_tasks.jsonl").read_text().splitlines()]
    assert all(set(t) == {"task_id", "cited_title", "sentence", "abstract"} for t in tasks)
    assert not any(t["sentence"].startswith("Quantum") for t in tasks)  # failed refs get no task
    shutil.copy(FIX / "toy_paper" / "support.jsonl", audits / "support.jsonl")
    p = run("assemble", "build", "--audits", audits, check=False)
    assert p.returncode == 1
    rows = list(csv.DictReader(open(audits / "citation_audit.csv")))

    def by(key: str, prefix: str) -> dict[str, str]:
        return next(r for r in rows if r["cite_key"] == key and r["sentence"].startswith(prefix))

    fab = next(r for r in rows if r["cite_key"] == "smith2021quantum")
    assert fab["exists"] == "no"
    miscite = by("kingma2015adam", "Gradient boosting")
    assert miscite["exists"] == "yes" and miscite["support"] == "unsupported"
    assert by("kingma2015adam", "We train with Adam")["support"] == "supports"
    assert next(r for r in rows if r["cite_key"] == "fedus2022switch")["metadata_match"] == "cite key has no bib entry"

    # author sign-off survives a rebuild
    for r in rows:
        if r["cite_key"] == "shazeer2017outrageously" and r["support"] == "partial":
            r["author_signoff"] = "ok - checked full text"
    with open(audits / "citation_audit.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    run("assemble", "build", "--audits", audits, check=False)
    rows2 = list(csv.DictReader(open(audits / "citation_audit.csv")))
    assert any(r["author_signoff"] == "ok - checked full text" for r in rows2)
    report = (audits / "citation_report.md").read_text()
    assert "smith2021quantum" in report and "srivastava2014dropout" in report


def test_missing_support_judgment_fails(audits: Path) -> None:
    run("verify", "--citations", audits / "citations.json", "--cache-dir", audits / "cache",
        "--out", audits / "existence.json", "--offline")
    run("abstracts", "--existence", audits / "existence.json", "--cache-dir", audits / "cache",
        "--out", audits / "abstracts.json", "--offline")
    p = run("assemble", "build", "--audits", audits, check=False)
    assert p.returncode == 1 and "no support judgment" in p.stdout
