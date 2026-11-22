from __future__ import annotations

import importlib.util
import json
import shutil
import zipfile
from pathlib import Path

import pytest
from conftest import FIX, ROOT, SCRIPTS, run


def load(name: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS[name])
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_parse_log() -> None:
    c = load("compile")
    res = c.parse_log((FIX / "latex" / "sample.log").read_text(), 10.0)
    assert res["undefined_refs"] == ["tab:missing"]
    assert res["undefined_cites"] == ["fedus2022switch"]
    assert res["missing_files"] == ["figures/missing_plot.png"]
    assert res["pages"] == 12
    assert len(res["overfull"]) == 1 and res["overfull"][0]["pt"] == 25.71


def test_parse_limits() -> None:
    c = load("compile")
    lim = c.parse_limits(ROOT / "templates" / "guidelines" / "elsarticle.md")
    assert lim["word_limit"] == 8000 and lim["abstract_word_limit"] == 250 and "page_limit" not in lim
    assert lim["class"] == "elsarticle"


def test_compile_report_from_log(tmp_path: Path) -> None:
    out = tmp_path / "audits" / "compile_report.md"
    g = tmp_path / "g.md"
    g.write_text("<!-- c2p:limits\npage_limit: 10\nabstract_word_limit: 20\n-->\n")
    p = run("compile", "--tex", FIX / "toy_paper" / "paper.tex", "--guidelines", g, "--report", out,
            "--log", FIX / "latex" / "sample.log", check=False)
    assert p.returncode == 1
    summary = json.loads(out.with_suffix(".json").read_text())
    assert summary["status"] == "ISSUES"
    assert any("12 pages > limit 10" in o for o in summary["over_limits"])
    assert any("abstract" in o for o in summary["over_limits"])  # toy abstract is ~30 words
    assert 100 < summary["main_text_words"] < 400


@pytest.mark.skipif(bool(shutil.which("latexmk") or shutil.which("tectonic")), reason="engine installed")
def test_no_engine_exit_2(tmp_path: Path) -> None:
    p = run("compile", "--tex", FIX / "toy_paper" / "paper.tex", "--report", tmp_path / "r.md", check=False)
    assert p.returncode == 2


@pytest.mark.skipif(not (shutil.which("latexmk") or shutil.which("tectonic")), reason="no LaTeX engine")
def test_real_compile(tmp_path: Path) -> None:
    paper = tmp_path / "paper"
    shutil.copytree(FIX / "toy_paper", paper)
    (paper / "figures").mkdir()
    shutil.copy(FIX / "toy_repo" / "figures" / "rmse_bar.png", paper / "figures")
    p = run("compile", "--tex", paper / "paper.tex", "--report", tmp_path / "r.md",
            "--pdf-out", tmp_path / "final" / "paper.pdf", check=False)
    summary = json.loads((tmp_path / "r.json").read_text())
    assert summary["status"] in {"OK", "ISSUES"}, p.stdout
    assert summary["undefined_cites"] == ["fedus2022switch"]
    assert (tmp_path / "final" / "paper.pdf").exists()


def make_po_layout(tmp_path: Path) -> Path:
    """Mimic PaperOrchestra's output: paper/final/paper.tex referencing ../figures and refs.bib."""
    paper = tmp_path / "ws" / "paper"
    (paper / "final").mkdir(parents=True)
    (paper / "figures").mkdir()
    shutil.copy(FIX / "toy_repo" / "figures" / "rmse_bar.png", paper / "figures" / "fig_main.png")
    shutil.copy(FIX / "toy_paper" / "refs.bib", paper / "refs.bib")
    (paper / "final" / "sec_extra.tex").write_text("Extra section text.\n")
    (paper / "final" / "paper.tex").write_text(
        "\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\n"
        "\\input{sec_extra}\n"
        "\\includegraphics[width=\\textwidth]{../figures/fig_main.png}\n"
        "\\bibliographystyle{plain}\n\\bibliography{refs}\n\\end{document}\n"
    )
    return paper


def test_package_overleaf_rewrites_paths(tmp_path: Path) -> None:
    paper = make_po_layout(tmp_path)
    out = tmp_path / "ws" / "final" / "overleaf.zip"
    run("package", "--tex", paper / "final" / "paper.tex", "--search", paper, "--out", out)
    z = zipfile.ZipFile(out)
    names = set(z.namelist())
    assert {"paper.tex", "sec_extra.tex", "figures/fig_main.png", "refs.bib"} <= names
    tex = z.read("paper.tex").decode()
    assert "{figures/fig_main.png}" in tex and "../figures" not in tex


def test_package_overleaf_missing_figure(tmp_path: Path) -> None:
    paper = make_po_layout(tmp_path)
    (paper / "figures" / "fig_main.png").unlink()
    p = run("package", "--tex", paper / "final" / "paper.tex", "--out", tmp_path / "ws" / "x.zip", check=False)
    assert p.returncode == 1 and "MISSING figure ../figures/fig_main.png" in p.stdout
