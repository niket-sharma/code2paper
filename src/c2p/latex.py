"""LaTeX helpers: offset-preserving stripping, \\input expansion, sentences, BibTeX parsing.

Stripping replaces removed spans with spaces (newlines are kept) so character
offsets and line numbers in the stripped text match the original file.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path

from .common import C2PError, read_text


def blank(text: str, start: int, end: int) -> str:
    seg = "".join("\n" if ch == "\n" else " " for ch in text[start:end])
    return text[:start] + seg + text[end:]


def blank_matches(text: str, pattern: re.Pattern[str]) -> str:
    out = list(text)
    for m in pattern.finditer(text):
        for i in range(m.start(), m.end()):
            if out[i] != "\n":
                out[i] = " "
    return "".join(out)


def find_brace_end(text: str, open_idx: int) -> int:
    """Index just past the brace group starting at text[open_idx] == '{'."""
    depth = 0
    i = open_idx
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def strip_comments(text: str) -> str:
    out = []
    for line in text.split("\n"):
        m = re.search(r"(?<!\\)%", line)
        out.append(line if m is None else line[: m.start()] + " " * (len(line) - m.start()))
    return "\n".join(out)


def command_spans(text: str, names: list[str], n_args: int = 1) -> list[tuple[int, int]]:
    """Spans of `\\name*[opt]{arg}...` for each name, including up to n_args brace groups."""
    spans = []
    pat = re.compile(r"\\(" + "|".join(re.escape(n) for n in names) + r")\*?(?![A-Za-z])")
    for m in pat.finditer(text):
        i = m.end()
        args = 0
        while i < len(text):
            j = i
            while j < len(text) and text[j] in " \t":
                j += 1
            if j < len(text) and text[j] == "[":
                k = text.find("]", j)
                i = (k + 1) if k != -1 else len(text)
                continue
            if j < len(text) and text[j] == "{" and args < n_args:
                i = find_brace_end(text, j)
                args += 1
                continue
            break
        spans.append((m.start(), i))
    return spans


def blank_spans(text: str, spans: list[tuple[int, int]]) -> str:
    out = list(text)
    for s, e in spans:
        for i in range(s, e):
            if out[i] != "\n":
                out[i] = " "
    return "".join(out)


def env_spans(text: str, env: str) -> list[tuple[int, int]]:
    pat = re.compile(r"\\begin\{" + re.escape(env) + r"\}.*?\\end\{" + re.escape(env) + r"\}", re.S)
    return [(m.start(), m.end()) for m in pat.finditer(text)]


class LineIndex:
    def __init__(self, text: str) -> None:
        self.starts = [0] + [m.end() for m in re.finditer("\n", text)]

    def line_of(self, offset: int) -> int:
        return bisect_right(self.starts, offset)


# ---------------------------------------------------------------- documents


@dataclass
class TexFile:
    path: Path
    rel: str
    text: str
    stripped: str = ""
    lines: LineIndex = field(init=False)

    def __post_init__(self) -> None:
        self.lines = LineIndex(self.text)


INPUT_RE = re.compile(r"\\(?:input|include|subfile)\{([^}]+)\}")


def load_document(main: Path) -> list[TexFile]:
    """Return main .tex plus every file pulled in by \\input/\\include, in order."""
    root = main.parent
    seen: set[Path] = set()
    files: list[TexFile] = []

    def visit(p: Path) -> None:
        if not p.exists() and p.suffix != ".tex":
            p = p.with_suffix(".tex")
        if not p.exists():
            raise C2PError(f"included file not found: {p}")
        p = p.resolve()
        if p in seen:
            return
        seen.add(p)
        text = read_text(p)
        try:
            rel = str(p.relative_to(root.resolve()))
        except ValueError:
            rel = str(p)
        files.append(TexFile(p, rel, text))
        for m in INPUT_RE.finditer(strip_comments(text)):
            visit(root / m.group(1).strip())

    visit(main)
    return files


def body_start(text: str) -> int:
    m = re.search(r"\\begin\{document\}", text)
    return m.end() if m else 0


NON_PROSE_COMMANDS = [
    "cite", "citep", "citet", "citealp", "citealt", "citeauthor", "citeyear", "citeyearpar",
    "parencite", "textcite", "autocite", "footcite", "nocite", "Cite", "Citep", "Citet",
    "ref", "eqref", "autoref", "cref", "Cref", "pageref", "nameref", "label",
    "includegraphics", "bibliography", "bibliographystyle", "usepackage", "documentclass",
    "vspace", "hspace", "setlength", "addtolength", "graphicspath", "url", "input",
    "include", "newcommand", "renewcommand", "definecolor", "linenumbers",
    "setcounter", "addbibresource", "hypersetup", "multicolumn", "multirow",
]
SECTIONING = ["part", "chapter", "section", "subsection", "subsubsection", "paragraph", "label",
              "maketitle", "tableofcontents", "centering", "includegraphics"]
# commands whose *first* argument is non-prose but later args are prose
FIRST_ARG_ONLY = ["href"]
# \multicolumn{2}{c}{text}: drop first two args, keep text
MULTI_SPEC = re.compile(r"\\multicolumn\{[^}]*\}\{[^}]*\}|\\multirow\{[^}]*\}\{[^}]*\}")
TABULAR_SPEC = re.compile(r"\\begin\{(tabular\*?|tabularx|longtable|array)\}(\{[^}]*\})?(\[[^\]]*\])?(\{(?:[^{}]|\{[^{}]*\})*\})")
LENGTH_RE = re.compile(r"[-+]?\d*\.?\d+\s*\\(?:linewidth|textwidth|columnwidth|textheight|paperwidth)")
DIMEN_RE = re.compile(r"[-+]?\d*\.?\d+\s*(?:pt|cm|mm|in|em|ex|bp)\b")
ENV_NAME_RE = re.compile(r"\\(?:begin|end)\{[^}]*\}(\[[^\]]*\])?")
RULE_RE = re.compile(r"\\(?:cmidrule(?:\([^)]*\))?|cline)\{[^}]*\}|\\\\\[[^\]]*\]")


def strip_for_numbers(tf: TexFile) -> str:
    """Remove everything that is not prose/table/caption content, preserving offsets."""
    t = strip_comments(tf.text)
    t = blank(t, 0, body_start(t)) if "\\begin{document}" in t else t
    for env in ("thebibliography", "filecontents", "verbatim", "lstlisting", "minted", "comment"):
        t = blank_spans(t, env_spans(t, env))
    t = blank_matches(t, MULTI_SPEC)
    t = blank_matches(t, TABULAR_SPEC)
    t = blank_spans(t, command_spans(t, NON_PROSE_COMMANDS, 1))
    t = blank_spans(t, command_spans(t, FIRST_ARG_ONLY, 1))
    t = blank_matches(t, LENGTH_RE)
    t = blank_matches(t, DIMEN_RE)
    t = blank_matches(t, ENV_NAME_RE)
    t = blank_matches(t, RULE_RE)
    return t


def strip_for_sentences(tf: TexFile) -> str:
    """Like strip_for_numbers but keeps \\cite commands (we need their positions)."""
    t = strip_comments(tf.text)
    t = blank(t, 0, body_start(t)) if "\\begin{document}" in t else t
    for env in ("thebibliography", "filecontents", "verbatim", "lstlisting", "comment"):
        t = blank_spans(t, env_spans(t, env))
    t = blank_spans(t, command_spans(t, SECTIONING, 1))
    t = blank_matches(t, ENV_NAME_RE)
    return t


# ---------------------------------------------------------------- sentences

_ABBREV = re.compile(
    r"(?:\bet al|\be\.g|\bi\.e|\bcf|\bvs|\bFig|\bFigs|\bEq|\bEqs|\bSec|\bTab|\bNo|\bResp|\bapprox|\bDr|\bProf|\b[A-Z])\.$"
)


def sentence_bounds(text: str, pos: int) -> tuple[int, int]:
    """Sentence containing offset pos (boundaries: '. ', '? ', '! ' + not abbreviation, blank lines)."""
    start = 0
    for m in re.finditer(r"[.!?](?=\s)|\n\s*\n", text[:pos]):
        if m.group(0).startswith("\n"):
            start = m.end()
            continue
        if _ABBREV.search(text[max(0, m.start() - 8) : m.end()]):
            continue
        start = m.end()
    end = len(text)
    for m in re.finditer(r"[.!?](?=\s|$)|\n\s*\n", text[pos:]):
        if m.group(0).startswith("\n"):
            end = pos + m.start()
            break
        abs_end = pos + m.end()
        if _ABBREV.search(text[max(0, abs_end - 9) : abs_end]):
            continue
        end = abs_end
        break
    return start, end


def clean_prose(s: str) -> str:
    s = re.sub(r"\\(?:emph|textit|textbf|texttt|textsc|mathrm|mathbf|text)\{([^{}]*)\}", r"\1", s)
    s = s.replace("~", " ").replace("\\%", "%").replace("{,}", ",")
    s = re.sub(r"\\[a-zA-Z]+\*?", " ", s)
    s = re.sub(r"[{}$]", "", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- bibtex


@dataclass
class BibEntry:
    key: str
    type: str
    fields: dict[str, str]
    line: int


def _bib_value(text: str, i: int) -> tuple[str, int]:
    while i < len(text) and text[i] in " \t\r\n":
        i += 1
    parts = []
    while i < len(text):
        c = text[i]
        if c == "{":
            end = find_brace_end(text, i)
            parts.append(text[i + 1 : end - 1])
            i = end
        elif c == '"':
            j = i + 1
            depth = 0
            while j < len(text):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                elif text[j] == '"' and depth == 0:
                    break
                j += 1
            parts.append(text[i + 1 : j])
            i = j + 1
        else:
            m = re.match(r"[\w.:-]+", text[i:])
            if not m:
                break
            parts.append(m.group(0))
            i += m.end()
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        if i < len(text) and text[i] == "#":
            i += 1
            continue
        break
    return "".join(parts), i


def parse_bib(text: str) -> list[BibEntry]:
    entries = []
    idx = LineIndex(text)
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", text):
        typ = m.group(1).lower()
        if typ in {"comment", "string", "preamble"}:
            continue
        start_brace = text.index("{", m.start())
        end = find_brace_end(text, start_brace)
        body = text[m.end() : end - 1]
        fields: dict[str, str] = {}
        i = 0
        while i < len(body):
            fm = re.compile(r"\s*([\w-]+)\s*=\s*").match(body, i)
            if not fm:
                nxt = body.find(",", i)
                if nxt == -1:
                    break
                i = nxt + 1
                continue
            val, j = _bib_value(body, fm.end())
            fields[fm.group(1).lower()] = re.sub(r"\s+", " ", val).strip()
            k = body.find(",", j)
            if k == -1:
                break
            i = k + 1
        entries.append(BibEntry(m.group(2), typ, fields, idx.line_of(m.start())))
    return entries


def bib_plain(s: str) -> str:
    """Remove TeX markup from a BibTeX field value."""
    s = re.sub(r"\\[`'^\"~=.uvHtcdb]\{?(\w)\}?", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+\s*", "", s)
    return re.sub(r"\s+", " ", s.replace("{", "").replace("}", "")).strip()


def first_author_last(authors: str) -> str:
    first = re.split(r"\s+and\s+", bib_plain(authors))[0].strip()
    if "," in first:
        return first.split(",")[0].strip()
    return first.split()[-1] if first.split() else ""
