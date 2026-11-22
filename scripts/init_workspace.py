#!/usr/bin/env python3
"""Create a code2paper workspace for one paper.

Clones the target repo (URL or local path) into <out>/repo at a pinned commit,
records the commit in workspace.json, copies templates/notes.md, installs the
journal guidelines and LaTeX template into inputs/, and scaffolds the
PaperOrchestra workspace in <out>/paper (its inputs/ is a symlink to <out>/inputs).

Example:
    python scripts/init_workspace.py --repo https://github.com/org/project --out workspace/ \\
        --guidelines elsarticle
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from c2p import __version__  # noqa: E402
from c2p.common import C2PError, git_head, run_main  # noqa: E402

DIRS = ["inputs/figures", "evidence", "paper", "audits", "final"]
PO_DIRS = ["figures", "drafts", "refinement", "final", "cache"]
COPY_IGNORE = shutil.ignore_patterns(".venv", "venv", "node_modules", "__pycache__", "*.pyc", ".mypy_cache")


def is_url(s: str) -> bool:
    return s.startswith(("http://", "https://", "git@", "ssh://", "git://"))


def git(*args: str, cwd: Path | None = None) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        raise C2PError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout.strip()


def clone_repo(src: str, dest: Path, commit: str | None) -> str:
    if is_url(src):
        git("clone", "--quiet", src, str(dest))
    else:
        sp = Path(src).expanduser().resolve()
        if not sp.is_dir():
            raise C2PError(f"repo path not found: {sp}")
        if git_head(sp):
            dirty = subprocess.run(["git", "-C", str(sp), "status", "--porcelain"], capture_output=True, text=True).stdout
            if dirty.strip():
                print("WARN: local repo has uncommitted changes; the workspace gets the committed state only.")
            git("clone", "--quiet", "--no-hardlinks", str(sp), str(dest))
        else:
            print("WARN: local path is not a git repo; copying files. Evidence rows will have no commit hash.")
            shutil.copytree(sp, dest, ignore=COPY_IGNORE)
    if commit:
        git("checkout", "--quiet", "--detach", commit, cwd=dest)
    return git_head(dest)


def pick_template(guidelines: Path | None, explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p
        q = ROOT / "templates" / "latex" / f"{explicit}.tex"
        if q.is_file():
            return q
        raise C2PError(f"template not found: {explicit}")
    if guidelines and guidelines.exists():
        import re

        m = re.search(r"^\s*class:\s*(\S+)", guidelines.read_text(encoding="utf-8"), re.M)
        if m and (ROOT / "templates" / "latex" / f"{m.group(1)}.tex").is_file():
            return ROOT / "templates" / "latex" / f"{m.group(1)}.tex"
    return None


def scaffold_upstream(out: Path, vendor: Path) -> str:
    paper = out / "paper"
    link = paper / "inputs"
    if not link.exists():
        os.symlink(Path("..") / "inputs", link, target_is_directory=True)
    script = vendor / "skills" / "paper-orchestra" / "scripts" / "init_workspace.py"
    if script.is_file():
        p = subprocess.run([sys.executable, str(script), "--out", str(paper), "--force"], capture_output=True, text=True)
        if p.returncode != 0:
            raise C2PError(f"upstream init_workspace.py failed: {p.stderr.strip()}")
        return git_head(vendor)
    print(f"WARN: PaperOrchestra not found at {vendor}; run scripts/install.sh. Creating its directories only.")
    for d in PO_DIRS:
        (paper / d).mkdir(parents=True, exist_ok=True)
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="target repo URL or local path")
    ap.add_argument("--out", required=True, type=Path, help="workspace directory to create")
    ap.add_argument("--commit", help="commit/tag to pin (default: HEAD of default branch)")
    ap.add_argument("--guidelines", default="generic-journal",
                    help="name in templates/guidelines/ or a path (default: generic-journal)")
    ap.add_argument("--template", help="LaTeX template: name in templates/latex/ or a path")
    ap.add_argument("--vendor", type=Path, default=ROOT / "vendor" / "PaperOrchestra")
    ap.add_argument("--force", action="store_true", help="allow a non-empty --out")
    a = ap.parse_args()

    out = a.out.resolve()
    if out.exists() and any(out.iterdir()) and not a.force:
        raise C2PError(f"{out} exists and is not empty (use --force)")
    for d in DIRS:
        (out / d).mkdir(parents=True, exist_ok=True)

    repo_dir = out / "repo"
    if repo_dir.exists() and any(repo_dir.iterdir()):
        print("INFO: repo/ already present; not re-cloning")
        commit = git_head(repo_dir)
    else:
        if repo_dir.exists():
            repo_dir.rmdir()
        commit = clone_repo(a.repo, repo_dir, a.commit)

    notes = out / "notes.md"
    if not notes.exists():
        shutil.copy2(ROOT / "templates" / "notes.md", notes)

    g = Path(a.guidelines)
    if not g.is_file():
        g = ROOT / "templates" / "guidelines" / f"{a.guidelines}.md"
    if not g.is_file():
        raise C2PError(f"guidelines not found: {a.guidelines}")
    gdst = out / "inputs" / "conference_guidelines.md"
    if not gdst.exists():
        shutil.copy2(g, gdst)
    tpl = pick_template(g, a.template)
    tdst = out / "inputs" / "template.tex"
    if tpl and not tdst.exists():
        shutil.copy2(tpl, tdst)

    upstream_commit = scaffold_upstream(out, a.vendor.resolve())
    if not tdst.exists():
        shutil.copy2(ROOT / "templates" / "latex" / "article.tex", tdst)

    meta = {
        "code2paper_version": __version__,
        "created": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "repo_source": a.repo if is_url(a.repo) else str(Path(a.repo).expanduser().resolve()),
        "repo_commit": commit,
        "guidelines": g.name,
        "template": tpl.name if tpl else "upstream fallback",
        "upstream": {"path": str(a.vendor), "commit": upstream_commit},
    }
    (out / "workspace.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"workspace ready: {out}")
    print(f"  repo commit: {commit or '(not a git repo)'}")
    print(f"  next: fill in {notes}, then ask Claude Code: \"Run code2paper on {out}\"")
    return 0


if __name__ == "__main__":
    run_main(main)
