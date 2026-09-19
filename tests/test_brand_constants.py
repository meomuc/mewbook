# SPDX-License-Identifier: AGPL-3.0-or-later
"""The product name and publisher live in smartdoc/__init__.py only (S0-07, decision D9: co-branding is deferred
but must stay possible without touching the widgets)."""
from __future__ import annotations

import ast
from pathlib import Path

from smartdoc import APP_DISPLAY_NAME, APP_NAME

_SRC = Path(__file__).resolve().parents[1] / "src" / "smartdoc"
_NAMES = {APP_NAME, APP_DISPLAY_NAME, APP_DISPLAY_NAME.upper()}


def _string_constants(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            yield node


def test_no_module_hard_codes_the_product_name_as_a_string():
    offenders = [
        f"{path.relative_to(_SRC)}:{node.lineno}"
        for path in _SRC.rglob("*.py")
        if path.name != "__init__.py" or path.parent != _SRC
        for node in _string_constants(path)
        if node.value.strip() in _NAMES
    ]
    assert offenders == [], f"use the APP_NAME / APP_DISPLAY_NAME constants instead: {offenders}"
