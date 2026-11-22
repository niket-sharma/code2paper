#!/usr/bin/env python3
"""Zip the manuscript for Overleaf: main .tex, \\input files, .bib, figures and local class/style files.

Figure or input paths that point outside the main file's directory (e.g.
`../figures/x.png`, as PaperOrchestra writes them) are copied into the zip
under `figures/` and the .tex copies are rewritten to match, so the zip builds
without edits. Fails if any referenced file is missing.

Example:
    python package_overleaf.py --tex workspace/paper/final/paper.tex \\
        --search workspace/inputs --out workspace/final/overleaf.zip
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from c2p.common import C2PError, guard_output, run_main  # noqa: E402
from c2p.latex import load_document, strip_comments  # noqa: E402

GRAPHIC_EXT = ["", ".pdf", ".png", ".jpg", ".jpeg", ".eps"]
GRAPHICS_RE = re.compile(r"(\\includegraphics\*?(?:\[[^\]]*\])?\{)([^}]+)(\})")
INPUT_RE = re.compile(r"(\\(?:input|include)\{)([^}]+)(\})")


def resolve(base: Path, name: str, dirs: list[Path], exts: list[str]) -> Path | None:
    for d in [base, *dirs]:
        for ext in exts:
            p = (d / (name + ext)) if ext and not name.endswith(ext) else d / name
            if p.is_file():
                return p.resolve()
    return None


def package(tex: Path, out: Path, search: list[Path]) -> list[str]:
    root = tex.parent.resolve()
    files = load_document(tex)
    graphicspaths = [root]
    for tf in files:
        for m in re.finditer(r"\\graphicspath\{((?:\{[^}]*\})+)\}", strip_comments(tf.text)):
            graphicspaths += [(root / g).resolve() for g in re.findall(r"\{([^}]*)\}", m.group(1))]

    members: dict[str, Path | str] = {}
    missing: list[str] = []

    def arcname_for(p: Path, default_dir: str) -> str:
        try:
            return p.relative_to(root).as_posix()
        except ValueError:
            return f"{default_dir}/{p.name}"

    for tf in files:
        text = tf.text

        def fix_graphic(m: re.Match[str]) -> str:
            name = m.group(2).strip()
            p = resolve(root, name, graphicspaths[1:] + search, GRAPHIC_EXT)
            if p is None:
                missing.append(f"figure {name} (from {tf.rel})")  # noqa: B023 - closure runs inside this loop iteration
                return m.group(0)
            arc = arcname_for(p, "figures")
            members[arc] = p
            # inside the project dir the original reference still works; outside, point at the copy
            return m.group(1) + (name if p.is_relative_to(root) else arc) + m.group(3)

        text = GRAPHICS_RE.sub(fix_graphic, text)

        def fix_input(m: re.Match[str]) -> str:
            name = m.group(2).strip()
            p = resolve(root, name, search, ["", ".tex"])
            if p is None:
                missing.append(f"input {name}")
                return m.group(0)
            arc = arcname_for(p, "sections")
            return m.group(1) + arc + m.group(3)

        text = INPUT_RE.sub(fix_input, text)
        members[arcname_for(tf.path, "sections")] = text

        for m in re.finditer(r"\\(?:bibliography|addbibresource)\{([^}]+)\}", strip_comments(text)):
            for name in m.group(1).split(","):
                name = name.strip()
                p = resolve(root, name, search + [root.parent], [".bib", ""])
                if p is None:
                    missing.append(f"bibliography {name}")
                else:
                    members[Path(name).name if name.endswith(".bib") else f"{Path(name).name}.bib"] = p
        nc = strip_comments(text)
        for _kind, ext, pat in (("class", ".cls", r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}"),
                               ("style", ".sty", r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}"),
                               ("bst", ".bst", r"\\bibliographystyle\{([^}]+)\}")):
            for m in re.finditer(pat, nc):
                for name in m.group(1).split(","):
                    p = resolve(root, name.strip(), search, [ext])
                    if p is not None:  # system classes/styles are not bundled
                        members[p.name] = p
    if missing:
        return missing
    guard_output(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, src in sorted(members.items()):
            if isinstance(src, str):
                z.writestr(arc, src)
            else:
                z.write(src, arc)
    print(f"{len(members)} files -> {out}")
    for arc in sorted(members):
        print(f"  {arc}")
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tex", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--search", type=Path, action="append", default=[],
                    help="extra directories to look for figures, .bib, .cls, .bst (repeatable)")
    a = ap.parse_args()
    if not a.tex.exists():
        raise C2PError(f"not found: {a.tex}")
    missing = package(a.tex, a.out, [s.resolve() for s in a.search])
    for m in missing:
        print(f"MISSING {m}")
    return 1 if missing else 0


if __name__ == "__main__":
    run_main(main)
