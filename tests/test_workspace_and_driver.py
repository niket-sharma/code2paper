from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path

from conftest import FIX, ROOT, run


def fake_vendor(tmp_path: Path) -> Path:
    """Stand-in for PaperOrchestra's init_workspace.py (same CLI: --out, --force)."""
    v = tmp_path / "vendor" / "PaperOrchestra"
    s = v / "skills" / "paper-orchestra" / "scripts"
    s.mkdir(parents=True)
    (s / "init_workspace.py").write_text(
        "import argparse, os\n"
        "p = argparse.ArgumentParser(); p.add_argument('--out'); p.add_argument('--force', action='store_true')\n"
        "a = p.parse_args()\n"
        "for d in ['inputs', 'inputs/figures', 'figures', 'drafts', 'refinement', 'final', 'cache']:\n"
        "    os.makedirs(os.path.join(a.out, d), exist_ok=True)\n"
        "t = os.path.join(a.out, 'inputs', 'template.tex')\n"
        "open(t, 'a').close()\n"
    )
    return v


def test_init_workspace_local_repo(tmp_path: Path, toy_repo: Path) -> None:
    ws = tmp_path / "ws"
    run("init", "--repo", toy_repo, "--out", ws, "--guidelines", "elsarticle", "--vendor", fake_vendor(tmp_path))
    meta = json.loads((ws / "workspace.json").read_text())
    head = subprocess.run(["git", "-C", str(toy_repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert meta["repo_commit"] == head
    assert (ws / "repo" / "results" / "results.csv").exists()
    assert (ws / "notes.md").read_text().startswith("# Paper notes")
    assert (ws / "paper" / "inputs").is_symlink()
    assert (ws / "paper" / "inputs" / "conference_guidelines.md").exists()
    assert "elsarticle" in (ws / "inputs" / "template.tex").read_text()
    for d in ("evidence", "audits", "final", "inputs/figures", "paper/final", "paper/drafts"):
        assert (ws / d).is_dir(), d
    p = run("init", "--repo", toy_repo, "--out", ws, check=False)
    assert p.returncode == 1 and "not empty" in p.stderr


def test_init_without_vendor_uses_own_template(tmp_path: Path, toy_repo: Path) -> None:
    ws = tmp_path / "ws"
    p = run("init", "--repo", toy_repo, "--out", ws, "--vendor", tmp_path / "nope")
    assert "PaperOrchestra not found" in p.stdout
    assert "\\documentclass[11pt]{article}" in (ws / "inputs" / "template.tex").read_text()


def test_pipeline_status_and_review(tmp_path: Path, toy_repo: Path) -> None:
    ws = tmp_path / "ws"
    run("init", "--repo", toy_repo, "--out", ws, "--vendor", fake_vendor(tmp_path))
    st = json.loads(run("status", "--workspace", ws, "--json").stdout)
    assert st["next"]["step"] == "1"
    shutil.copy(FIX / "toy_notes.md", ws / "notes.md")
    (ws / "audits" / "numbers_audit.csv").write_text(
        "tex_file,line,context,value_in_paper,status,evidence_id,note\n"
        "paper.tex,51,ctx,2.45,conflict,E0033,context points to E0033\n"
        "paper.tex,49,ctx,2.31,rounding_ok,E0027,\n"
    )
    with open(ws / "audits" / "citation_audit.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cite_key", "sentence", "tex_line", "doi", "exists", "metadata_match", "abstract_source",
                    "support", "rationale", "author_signoff"])
        w.writerow(["smith2021quantum", "s", "27", "", "no", "x", "none", "no_abstract", "failed", ""])
        w.writerow(["he2016deep", "s", "22", "", "yes", "x", "s2", "supports", "ok", ""])
    (ws / "evidence" / "gap_decisions.md").write_text("- latency claim: narrow the claim (removed). 2026-11-17\n")
    run("review", "--workspace", ws)
    review = (ws / "final" / "REVIEW.md").read_text()
    assert "**1 flagged**" in review
    assert "smith2021quantum" in review and "latency claim" in review
    assert "Claude Code was used to draft" in review
    assert "{{" not in review


def test_every_script_has_help() -> None:
    import sys

    from conftest import SCRIPTS

    for name, path in SCRIPTS.items():
        p = subprocess.run([sys.executable, str(path), "--help"], capture_output=True, text=True)
        assert p.returncode == 0 and "usage" in p.stdout.lower(), name


def test_skill_frontmatter() -> None:
    for skill in (ROOT / "skills").iterdir():
        text = (skill / "SKILL.md").read_text()
        assert text.startswith("---\nname: " + skill.name + "\ndescription: "), skill.name
