"""Drop the 100% coverage threshold for a ``-k``/``-m`` subset run.

``[tool.coverage.report] fail_under = 100`` is the full suite's gate. A subset
(the runner's done_check: ``pytest -q -k '<expr>' leetcode_guard/tests``) can
never cover the whole package, so the threshold failed every clause whose tests
all passed. Coverage is still measured and reported; only the total stops
deciding the exit code. File or node-id arguments are left alone: a run of the
changed tests may want the gate on purpose.

Registered with ``-p`` in ``addopts``, like ``_gatelock_fixtures``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def relax_for_subset(config: pytest.Config) -> None:
    """Unset pytest-cov's ``cov_fail_under`` when tests were selected by expression.

    pytest-cov copies ``fail_under`` into its own options when it starts (before
    any ``pytest_configure``) and reads them at the end of the run, so the
    registered ``_cov`` plugin is the one place the value can be changed.
    """
    if not (config.option.keyword or config.option.markexpr):
        return
    cov = config.pluginmanager.getplugin("_cov")
    if cov is not None:
        cov.options.cov_fail_under = None


def pytest_configure(config: pytest.Config) -> None:
    """Pytest hook: apply :func:`relax_for_subset` once the options are parsed."""
    relax_for_subset(config)
