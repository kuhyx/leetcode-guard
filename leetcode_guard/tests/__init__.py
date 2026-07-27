"""Test suite for :mod:`leetcode_guard`.

A package rather than a bare directory so the shared, non-test helpers
(``_gatelock_fixtures``, ``_net_fixtures``, ``_ledger_fixtures``,
``_guard_factories``) are importable by absolute path from the test modules --
relative imports are banned repo-wide.
"""
