from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "src"))

SCRIPTS = {
    "inventory": ROOT / "skills/c2p-repo-ingest/scripts/inventory_repo.py",
    "extract_results": ROOT / "skills/c2p-repo-ingest/scripts/extract_results.py",
    "validate": ROOT / "skills/c2p-repo-ingest/scripts/validate_evidence_map.py",
    "gap_scan": ROOT / "skills/c2p-gap-check/scripts/gap_scan.py",
    "extract_numbers": ROOT / "skills/c2p-numbers-audit/scripts/extract_numbers.py",
    "match": ROOT / "skills/c2p-numbers-audit/scripts/match_evidence.py",
    "extract_citations": ROOT / "skills/c2p-citation-audit/scripts/extract_citations.py",
    "verify": ROOT / "skills/c2p-citation-audit/scripts/verify_existence.py",
    "abstracts": ROOT / "skills/c2p-citation-audit/scripts/fetch_abstracts.py",
    "assemble": ROOT / "skills/c2p-citation-audit/scripts/assemble_audit.py",
    "compile": ROOT / "skills/c2p-compile-check/scripts/compile.py",
    "package": ROOT / "skills/c2p-compile-check/scripts/package_overleaf.py",
    "review": ROOT / "skills/c2p-compile-check/scripts/build_review.py",
    "status": ROOT / "skills/code2paper/scripts/pipeline_status.py",
    "init": ROOT / "scripts/init_workspace.py",
}


def run(name: str, *args: object, check: bool | None = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run([sys.executable, str(SCRIPTS[name]), *map(str, args)], capture_output=True, text=True)
    if check and p.returncode != 0:
        raise AssertionError(f"{name} exited {p.returncode}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}")
    return p


def git_commit_all(repo: Path) -> None:
    for cmd in (["init", "-q"], ["add", "-A"],
                ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "init"]):
        subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def toy_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(FIX / "toy_repo", repo)
    git_commit_all(repo)
    return repo


@pytest.fixture
def ingested(tmp_path: Path, toy_repo: Path) -> dict[str, Path]:
    ev = tmp_path / "evidence"
    run("inventory", "--repo", toy_repo, "--out", ev / "inventory.json")
    run("extract_results", "--repo", toy_repo, "--inventory", ev / "inventory.json",
        "--evidence-map", ev / "evidence_map.csv")
    return {"repo": toy_repo, "evidence": ev, "map": ev / "evidence_map.csv", "inventory": ev / "inventory.json"}
