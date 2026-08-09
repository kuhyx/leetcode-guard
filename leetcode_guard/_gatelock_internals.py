"""The one place that reaches into gatelock's privates.

Study mode has to stop gatelock's ``RecoveryLoop`` before releasing the X grab
-- leave it running and it re-takes the grab within a tick, which would give the
user a browser that looks focused and swallows every keystroke. gatelock has no
public way to do that:

===========================  =========================================
What is needed               Why the public API cannot supply it
===========================  =========================================
``LockWindow._recovery``     No public stop. ``RecoveryLoop.stop()`` is
                             public and documented state-free, but the
                             *loop itself* is reachable only here.
``LockWindow._detector``     Same. ``_drain`` schedules a full tick
                             independently of ``_verify``, so stopping
                             one without the other undoes the suspend.
``SurfaceSet._surfaces``     ``infos()`` returns dataclasses and
                             ``names()`` returns strings; neither hands
                             back the ``Toplevel`` that must be hidden.
``LockWindow._vt_disabled``  Study mode calls ``restore_vt_switching``
                             directly, and gatelock's ``close()`` skips
                             its own restore when this flag is stale --
                             so it has to be kept truthful.
===========================  =========================================

Concentrating all four here means shipped code has exactly one file to audit,
rather than a suppression scattered across the study modules. The ``scripts/``
harnesses keep their own access on purpose -- ``verify_study_grab.py`` tests
whether the assumptions below actually hold on a real X server, and asking this
module would be marking its own homework.

Everything above is **pinned to gatelock v0.4.0** and covered by
``test_study.py::test_the_private_gatelock_attributes_still_exist``, so a version
bump that renames any of them fails at test time rather than inside a live lock
with the screen already grabbed.

**The right long-term fix is upstream**: ``LockWindow.suspend()`` and
``LockWindow.resume()`` in gatelock itself would serve all four lockers and
delete this module. Until then, this is the seam.
"""

# Every function below reaches a gatelock private on purpose -- that is this
# module's entire job, and the reason shipped code routes through it. Exactly
# the same access the ruff ``SLF001`` exemption in ``pyproject.toml`` already
# covers, declared here too because pylint has no per-file-ignores.
# pylint: disable=protected-access

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterator


class SuspendableLock(Protocol):
    """The slice of ``gatelock.LockWindow`` study mode drives."""

    root: Any

    @property
    def surfaces(self) -> Any:
        """The per-output surface set gatelock owns."""


def stop_recovery(lock: SuspendableLock) -> None:
    """Stop the loop that would otherwise re-take the grab within a tick."""
    lock._recovery.stop()


def start_recovery(lock: SuspendableLock) -> None:
    """Restart it. The loop is what eventually heals a grab we could not take."""
    lock._recovery.start()


def stop_detector(lock: SuspendableLock) -> None:
    """Stop the output-change detector, which can push a tick through alone."""
    lock._detector.stop()


def start_detector(lock: SuspendableLock) -> None:
    """Restart the detector so hotplug is noticed again."""
    lock._detector.start()


def holds_grab(lock: SuspendableLock) -> bool:
    """Whether the lock currently holds the global grab.

    gatelock's own question, asked its way: ``RecoveryLoop.holds_grab`` is
    public and documented for embedders, so this is the one member here that is
    reached through a private *handle* but a public *method*.
    """
    return bool(lock._recovery.holds_grab())


def mark_vt(lock: SuspendableLock, *, disabled: bool) -> None:
    """Keep gatelock's own VT bookkeeping in step with reality.

    Both directions matter, and the second one is easy to forget.
    ``LockWindow._restore_vt`` early-returns when this flag is falsy, so a
    suspend that clears it without a resume that sets it again means
    ``close()`` skips its restore and **the process exits with VT switching
    still disabled** -- Ctrl+Alt+F1..F6 dead after the lock is gone, on a
    screen whose own break-glass text told the user those keys would not work.
    Nothing self-heals it: ``RecoveryLoop._reassert_vt`` re-disables VT without
    touching the flag.
    """
    lock._vt_disabled = disabled


def surface_windows(lock: SuspendableLock) -> Iterator[tuple[Any, Any]]:
    """Yield ``(info, window)`` for every live surface.

    ``infos()`` alone cannot do this: it returns ``SurfaceInfo`` dataclasses,
    and the ``Toplevel`` that actually has to be withdrawn lives in the private
    map beside it. Surfaces missing from that map are skipped rather than
    raising -- a surface we cannot find is one we cannot hide, and the grab
    being released is the part that matters.
    """
    surfaces = lock.surfaces
    for info in surfaces.infos():
        surface = surfaces._surfaces.get(info.output_name)
        if surface is None:
            continue
        yield info, surface.window
