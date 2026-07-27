"""Test for the ``python -m leetcode_guard`` entry point.

Importing the module is safe: under an import its ``__name__`` is
``leetcode_guard.__main__``, so the ``if __name__ == "__main__"`` guard does not
fire and nothing is executed.
"""

from __future__ import annotations

import importlib


def test_entry_point_module_imports_and_exposes_main():
    module = importlib.import_module("leetcode_guard.__main__")

    assert module.main.__module__ == "leetcode_guard._cli"
