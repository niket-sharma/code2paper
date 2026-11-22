#!/usr/bin/env python3
"""Walk a target repository and write inventory.json (file type, size, sha256, role guess).

Reads only; never executes anything in the target repo.

Example:
    python inventory_repo.py --repo workspace/repo --out workspace/evidence/inventory.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from c2p.common import C2PError, git_head, run_main, sha256_file, write_json  # noqa: E402

SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "env", ".env", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".idea", ".vscode", "site-packages",
    ".ipynb_checkpoints", "dist", "build", ".eggs", "wandb", "mlruns",
}
CODE_EXT = {".py", ".r", ".jl", ".m", ".c", ".cc", ".cpp", ".h", ".hpp", ".rs", ".go", ".java",
            ".js", ".ts", ".f90", ".sh", ".scala", ".cu"}
CONFIG_EXT = {".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf"}
TABLE_EXT = {".csv", ".tsv"}
FIGURE_EXT = {".png", ".jpg", ".jpeg", ".pdf", ".svg", ".eps", ".gif"}
LOG_EXT = {".log", ".out", ".err"}
TEXT_EXT = CODE_EXT | CONFIG_EXT | TABLE_EXT | LOG_EXT | {".md", ".rst", ".txt", ".json",
                                                         ".jsonl", ".ipynb", ".tex", ".bib"}
PROJECT_CONFIG_NAMES = {"pyproject.toml", "setup.cfg", "tox.ini", "environment.yml",
                        "requirements.txt", "package.json"}


def is_binary(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return b"\0" in f.read(4096)
    except OSError:
        return True


def guess_role(rel: Path, ext: str, binary: bool) -> str:
    name = rel.name.lower()
    parts = [p.lower() for p in rel.parts[:-1]]
    if name.startswith("readme"):
        return "readme"
    if ext in FIGURE_EXT:
        return "figure"
    if ext == ".ipynb":
        return "notebook"
    if name.startswith("test_") or name.endswith("_test.py") or "tests" in parts or "test" in parts:
        return "test"
    if ext in TABLE_EXT:
        return "result_table"
    if ext in LOG_EXT or "logs" in parts or "log" in parts:
        return "log"
    if ext in {".json", ".jsonl"}:
        if any(k in name for k in ("metric", "result", "eval", "score", "summary")) or any(
            p in ("results", "outputs", "metrics", "eval") for p in parts
        ):
            return "result_table"
        return "config" if any(p in ("configs", "config", "conf") for p in parts) else "other"
    if ext in CONFIG_EXT:
        return "other" if name in PROJECT_CONFIG_NAMES else "config"
    if ext == ".txt" and any(p in ("results", "outputs") for p in parts):
        return "log"
    if ext in CODE_EXT:
        return "core_code"
    if binary:
        return "other"
    return "other"


def inventory(repo: Path, max_bytes: int) -> dict:
    files = []
    skipped = []
    for p in sorted(repo.rglob("*")):
        rel = p.relative_to(repo)
        if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in rel.parts[:-1]):
            continue
        if p.is_dir() or p.is_symlink():
            continue
        if rel.parts[0] in SKIP_DIRS:
            continue
        size = p.stat().st_size
        ext = p.suffix.lower()
        binary = ext not in TEXT_EXT and is_binary(p)
        role = guess_role(rel, ext, binary)
        if binary and size > max_bytes and role != "figure":
            skipped.append({"path": str(rel), "size": size, "reason": "binary over size limit"})
            continue
        if not binary and size > max_bytes * 10:
            skipped.append({"path": str(rel), "size": size, "reason": "text file over size limit"})
            continue
        files.append(
            {
                "path": rel.as_posix(),
                "ext": ext,
                "size": size,
                "binary": binary,
                "role": role,
                "sha256": sha256_file(p),
            }
        )
    roles: dict[str, int] = {}
    for f in files:
        roles[f["role"]] = roles.get(f["role"], 0) + 1
    return {
        "repo": str(repo),
        "commit": git_head(repo),
        "n_files": len(files),
        "roles": roles,
        "files": files,
        "skipped": skipped,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, type=Path, help="target repository root")
    ap.add_argument("--out", required=True, type=Path, help="path to write inventory.json")
    ap.add_argument("--max-bytes", type=int, default=5_000_000, help="skip binaries larger than this")
    a = ap.parse_args()
    if not a.repo.is_dir():
        raise C2PError(f"repo not found: {a.repo}")
    inv = inventory(a.repo.resolve(), a.max_bytes)
    write_json(a.out, inv)
    print(f"inventory: {inv['n_files']} files, roles={inv['roles']}, skipped={len(inv['skipped'])}")
    return 0


if __name__ == "__main__":
    run_main(main)
