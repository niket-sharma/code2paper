#!/usr/bin/env bash
# Install code2paper: clone PaperOrchestra at a pinned commit into vendor/,
# install Python requirements, and symlink all skills into ~/.claude/skills/.
#
# Usage: scripts/install.sh [--no-pip] [--skills-dir DIR] [--upstream-commit SHA]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UPSTREAM_URL="https://github.com/Ar9av/PaperOrchestra"
UPSTREAM_COMMIT="6a319132932ee031e2d759b0f7f5075cf77bd1cf"   # pinned 2026-11-17, see docs/upstream-notes.md
SKILLS_DIR="${HOME}/.claude/skills"
DO_PIP=1

while [ $# -gt 0 ]; do
  case "$1" in
    --no-pip) DO_PIP=0 ;;
    --skills-dir) SKILLS_DIR="$2"; shift ;;
    --upstream-commit) UPSTREAM_COMMIT="$2"; shift ;;
    -h|--help) sed -n 2,6p "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

VENDOR="$ROOT/vendor/PaperOrchestra"
if [ ! -d "$VENDOR/.git" ]; then
  echo "==> cloning PaperOrchestra into vendor/"
  mkdir -p "$ROOT/vendor"
  git clone --quiet "$UPSTREAM_URL" "$VENDOR"
fi
echo "==> pinning PaperOrchestra at $UPSTREAM_COMMIT"
git -C "$VENDOR" fetch --quiet origin || true
git -C "$VENDOR" checkout --quiet --detach "$UPSTREAM_COMMIT"

if [ "$DO_PIP" = 1 ]; then
  echo "==> installing Python requirements"
  python3 -m pip install --quiet -r "$ROOT/requirements.txt"
  python3 -m pip install --quiet -r "$VENDOR/requirements.txt"
fi

link_skill() {
  local src="$1" name
  name="$(basename "$src")"
  [ -f "$src/SKILL.md" ] || return 0
  local dst="$SKILLS_DIR/$name"
  if [ -L "$dst" ]; then
    rm "$dst"
  elif [ -e "$dst" ]; then
    echo "WARN: $dst exists and is not a symlink; skipping" >&2
    return 0
  fi
  ln -s "$src" "$dst"
  echo "    $name"
}

echo "==> linking skills into $SKILLS_DIR"
mkdir -p "$SKILLS_DIR"
for s in "$VENDOR"/skills/*/ "$ROOT"/skills/*/; do
  link_skill "${s%/}"
done

command -v latexmk >/dev/null 2>&1 || command -v tectonic >/dev/null 2>&1 || \
  echo "WARN: no LaTeX engine found (install TeX Live with latexmk, or tectonic) — needed for c2p-compile-check"

echo "==> done. Next: python3 scripts/init_workspace.py --repo <url|path> --out workspace/"
