"""Common helpers: evidence-map schema, hashing, number handling, safe formulas."""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import operator
import re
import subprocess
import sys
from collections.abc import Iterable
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

EVIDENCE_COLUMNS = [
    "evidence_id",
    "value",
    "unit",
    "metric",
    "condition",
    "kind",
    "source_file",
    "line_start",
    "line_end",
    "commit",
    "file_sha256",
    "quote",
    "method",
    "derived_from",
    "formula",
]
KINDS = {"result", "hyperparameter", "dataset_stat", "derived"}
METHODS = {"parsed", "read"}
EVIDENCE_ID_RE = re.compile(r"^E\d{4,}$")

# A plain decimal number (no thousands separators). Used for evidence values.
NUMBER_RE = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


class C2PError(Exception):
    """Raised for user-facing failures; scripts turn this into exit code 1."""


# ---------------------------------------------------------------- filesystem


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head(repo: Path) -> str:
    """Full commit hash of repo HEAD, or '' if repo is not a git checkout."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return out.stdout.strip()


def find_workspace(path: Path) -> Path | None:
    """Walk up from path to the directory holding `workspace.json`."""
    p = path.resolve()
    for cand in [p, *p.parents]:
        if (cand / "workspace.json").is_file():
            return cand
    return None


def guard_output(path: Path, workspace: Path | None = None) -> Path:
    """Refuse to write outside the workspace (rule 7).

    If `workspace` is not given it is discovered from the output path. When no
    workspace marker exists at all (e.g. ad-hoc use in tests), the write is
    allowed as long as the path is not inside the code2paper repo's vendor/.
    """
    path = path.resolve()
    ws = workspace.resolve() if workspace else find_workspace(path.parent)
    if ws is not None and not path.is_relative_to(ws):
        raise C2PError(f"refusing to write outside workspace {ws}: {path}")
    if "vendor" in path.parts and (Path(__file__).resolve().parents[2] / "vendor") in path.parents:
        raise C2PError(f"refusing to write under vendor/: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: Any) -> None:
    guard_output(path)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- evidence map


def read_evidence(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in EVIDENCE_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise C2PError(f"{path}: missing columns {missing}")
        return [{k: (v or "") for k, v in row.items() if k in EVIDENCE_COLUMNS} for row in reader]


def write_evidence(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    write_csv(path, EVIDENCE_COLUMNS, rows)


def write_csv(path: Path, columns: list[str], rows: Iterable[dict[str, Any]]) -> None:
    guard_output(path)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: "" if r.get(c) is None else r.get(c) for c in columns})


def read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return [{k: (v or "") for k, v in row.items()} for row in csv.DictReader(f)]


def next_evidence_id(existing: Iterable[str]) -> int:
    nums = [int(e[1:]) for e in existing if EVIDENCE_ID_RE.match(e)]
    return (max(nums) + 1) if nums else 1


def format_evidence_id(n: int) -> str:
    return f"E{n:04d}"


def parse_derived_from(s: str) -> list[str]:
    return [t for t in re.split(r"[\s,;\[\]\"']+", s) if t]


# ---------------------------------------------------------------- numbers


def to_decimal(s: str) -> Decimal | None:
    s = s.strip().replace(",", "").replace("{,}", "")
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def shown_decimals(s: str) -> int:
    """Number of digits after the decimal point as written (scientific -> exponent aware)."""
    d = to_decimal(s)
    if d is None:
        return 0
    exp = d.as_tuple().exponent
    return max(0, -exp) if isinstance(exp, int) else 0


def rounds_to(evidence_value: Decimal, paper_value: str) -> str | None:
    """Return 'exact', 'rounding' or None.

    A paper value matches when it equals the evidence value rounded to the
    precision shown in the paper (half-up or half-even both accepted).
    """
    p = to_decimal(paper_value)
    if p is None:
        return None
    if evidence_value == p:
        return "exact"
    q = Decimal(1).scaleb(p.as_tuple().exponent)  # type: ignore[arg-type]
    for mode in (ROUND_HALF_UP, ROUND_HALF_EVEN):
        try:
            if evidence_value.quantize(q, rounding=mode) == p:
                return "rounding"
        except InvalidOperation:
            return None
    return None


# ---------------------------------------------------------------- formulas

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_UNOPS = {ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"abs": abs, "min": min, "max": max, "mean": lambda *a: sum(a) / len(a)}


def eval_formula(formula: str, values: dict[str, Decimal]) -> Decimal:
    """Evaluate an arithmetic formula over evidence IDs, e.g. `(E0012 - E0015) / E0015 * 100`."""
    tree = ast.parse(formula, mode="eval")

    def ev(node: ast.AST) -> Decimal:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Decimal(str(node.value))
        if isinstance(node, ast.Name):
            if node.id not in values:
                raise C2PError(f"formula references unknown id {node.id}")
            return values[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return Decimal(_BINOPS[type(node.op)](ev(node.left), ev(node.right)))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNOPS:
            return Decimal(_UNOPS[type(node.op)](ev(node.operand)))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _FUNCS
            and not node.keywords
        ):
            return Decimal(_FUNCS[node.func.id](*[ev(a) for a in node.args]))
        raise C2PError(f"unsupported expression in formula: {ast.dump(node)}")

    return ev(tree)


def formula_ids(formula: str) -> set[str]:
    return {n.id for n in ast.walk(ast.parse(formula, mode="eval")) if isinstance(n, ast.Name)} - set(
        _FUNCS
    )


# ---------------------------------------------------------------- CLI helper


def run_main(main_fn) -> None:  # type: ignore[no-untyped-def]
    """Run a script main(), mapping C2PError to exit 1 with a clean message."""
    try:
        code = main_fn()
    except C2PError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(code or 0)
