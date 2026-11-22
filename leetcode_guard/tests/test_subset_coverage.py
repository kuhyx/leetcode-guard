"""A ``-k``/``-m`` subset is judged by its tests, not by the 100% gate.

The runner's done_check runs ``pytest -q -k '<expr>' leetcode_guard/tests``.
A subset can never cover the whole package, so ``fail_under = 100`` made every
such clause exit 1 with its tests passing (2026-11-22). The full suite, with no
selection, keeps the gate.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from leetcode_guard.tests._subset_coverage import relax_for_subset


def _config(*, keyword: str = "", markexpr: str = "", cov: object = None):
    plugins = {"_cov": cov} if cov is not None else {}
    return SimpleNamespace(
        option=SimpleNamespace(keyword=keyword, markexpr=markexpr),
        pluginmanager=SimpleNamespace(getplugin=plugins.get),
    )


@pytest.mark.parametrize(("keyword", "markexpr"), [("some and expr", ""), ("", "slow")])
def test_a_selected_subset_drops_the_coverage_threshold(keyword: str, markexpr: str):
    """``-k`` or ``-m``: report coverage, but never fail on the total."""
    cov = SimpleNamespace(options=SimpleNamespace(cov_fail_under=100))

    relax_for_subset(_config(keyword=keyword, markexpr=markexpr, cov=cov))

    assert cov.options.cov_fail_under is None


def test_the_full_suite_keeps_the_threshold():
    """No selection: the 100% branch gate stands."""
    cov = SimpleNamespace(options=SimpleNamespace(cov_fail_under=100))

    relax_for_subset(_config(cov=cov))

    assert cov.options.cov_fail_under == 100


def test_no_coverage_plugin_is_a_no_op():
    """``--no-cov`` or ``-p no:cov``: nothing to relax, nothing raised."""
    relax_for_subset(_config(keyword="some and expr"))
