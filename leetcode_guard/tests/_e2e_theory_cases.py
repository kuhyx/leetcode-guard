"""Cases d-f of ``scripts/e2e_theory`` and the steps every case shares.

Kept in the package (not ``scripts/``) so the driver imports them without one
script importing another, which mypy reads as one file under two names.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from leetcode_guard.tests._e2e_world import ALGO

if TYPE_CHECKING:
    from leetcode_guard.tests._e2e_world import World

PS_EASY = "ps-one,ps-two,ps-three,ps-four,ps-five"
LEDGER = "home/.local/share/leetcode_guard/ledger.json"


def check(ok: object, why: str) -> None:
    """Fail the case with ``why`` unless ``ok``."""
    if not ok:
        raise AssertionError(why)


def seeded(world: World) -> None:
    """A scratch pool, and a ledger created by the real lock's first run."""
    if not world.display:
        world.start_x()
    code, out = world.role("pool")
    check(code == 0, f"pool: {out}")
    code, log, most = world.lock(seconds=20)
    check(
        code == 0 and most == 0 and "seeded a new ledger" in log,
        f"seed: code={code} windows={most}; {world.x_state()}\n{log[-2000:]}",
    )


def needed(world: World) -> int:
    """Credits today still needs, by the guard's own pricing."""
    _, out = world.role("needed")
    found = re.search(r"needed=(\d+)", out)
    check(found, f"needed: {out}")
    return int(found.group(1)) if found else 0


def _phase_text(world: World) -> str:
    """``theory_phase.json`` as bytes on disk ('' if missing): proves 'kept'."""
    path = world.data / "theory_phase.json"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _one_bad(signed: str) -> str:
    """The signed C2 rows plus one forged copy: the one-bad-row rule (R3)."""
    document = json.loads(signed)
    forged = dict(document["entries"][0], hmac="0" * 64)
    document["entries"].append(forged)
    return json.dumps(document)


def case_d(world: World) -> str:
    """Cannot check: nothing minted, a warning, the last signed phase kept."""
    seeded(world)
    world.role("flip", "prefix-sums/0/180")
    world.role("harvest")
    kept = _phase_text(world)
    check('"theory"' in kept, f"no first phase: {kept}")
    world.role("teach", f"{ALGO}/prefix-sums/60/5")
    ledger = world.tutor / "ledger.json"
    good = ledger.read_text(encoding="utf-8")
    ledger.write_text("{not json", encoding="utf-8")
    _, out = world.role("harvest")
    check("WARNING" in out and not world.entry_ids("theory:"), f"bad C1 minted: {out}")
    ledger.write_text(good, encoding="utf-8")
    state = world.tutor / "module_state.json"
    signed = state.read_text(encoding="utf-8")
    for broken in ("", signed.replace('"hmac": "', '"hmac": "0'), _one_bad(signed)):
        if broken:
            state.write_text(broken, encoding="utf-8")
        else:
            state.unlink()
        _, out = world.role("harvest")
        check(
            "WARNING" in out and not world.entry_ids("theory:"), f"bad C2 minted: {out}"
        )
        check(_phase_text(world) == kept, "the last signed phase was not kept")
    code, log, most = world.lock(seconds=12, until="model.json", shot="held")
    model = world.model() or {}
    check(
        most > 0 and (model.get("screen") or {}).get("phase") == "theory",
        f"held: {model}",
    )
    check("Traceback" not in log, f"raised into the lock: {log[-600:]}")
    (world.data / "theory_phase.json").unlink()
    (world.dir / "model.json").unlink()
    need = len(PS_EASY.split(","))
    code, log, most = world.lock(seconds=30, ac=PS_EASY)
    model = world.model() or {}
    check(
        most > 0 and (model.get("screen") or {}).get("phase") == "none",
        f"none: {model}",
    )
    paid = world.entry_ids("charge:")
    check(code == 0 and paid, f"solves did not pay: {code} {paid} {log[-600:]}")
    return (
        "bad C1, missing C2, forged C2, one bad C2 row: 0 minted, WARNING, C3 bytes kept; "
        "lock held theory; "
        f"no C3: old list, armed, {need} solves paid ({paid[0]})"
    )


def case_e(world: World) -> str:
    """Every Easy problem of the unit solved: THEORY of the next unit, C3 rewritten."""
    seeded(world)
    world.role("flip", "prefix-sums/0/240", "prefix-sums/1/120")
    world.role("harvest")
    before = (world.phase_file() or {}).get("detail") or {}
    check(before.get("phase") == "solve", f"not in SOLVE first: {before}")
    _, out = world.role("harvest", ac=PS_EASY)
    check("credited 5" in out, f"solves: {out}")
    detail = (world.phase_file() or {}).get("detail") or {}
    check(
        detail.get("unit") == "stack-queue"
        and detail.get("phase") == "theory"
        and detail.get("teachable") == [[ALGO, "stack-queue"]],
        f"C3 after the unit's last solve (same harvest): {json.dumps(detail)}",
    )
    return (
        "5/5 prefix-sums Easy credited in one harvest -> "
        f"C3 {detail.get('unit')} theory {detail.get('teachable')}"
    )


def case_f(world: World) -> str:
    """Deleting the ledger re-mints only today's; deleting C3/C2 mints nothing."""
    seeded(world)
    world.role("flip", "prefix-sums/0/3000")
    world.role("harvest")
    world.role("began", "3000")
    world.role("teach", f"{ALGO}/prefix-sums/60/1500", f"{ALGO}/prefix-sums/24/5")
    world.role("harvest")
    first = world.entry_ids("theory:")
    check(len(first) == 2, f"today's 24 min: {first}")
    (world.data / "ledger.json").unlink()
    _, out = world.role("harvest")
    check(
        "not seeded" in out and not world.entry_ids(""),
        f"unseeded harvest wrote: {out}",
    )
    seeded(world)
    world.role("harvest")
    again = world.entry_ids("theory:")
    check(again == first, f"re-minted {again}, before {first}")
    need = needed(world)
    for name in ("theory_phase.json", "../tutor/module_state.json"):
        (world.data / name).unlink()
        world.role("harvest")
        check(world.entry_ids("theory:") == first, f"rm {name} minted")
        check(
            not world.entry_ids("charge:") and needed(world) == need, f"rm {name} paid"
        )
    return (
        "rm ledger -> unseeded harvest writes nothing; "
        f"reseed re-mints {again} only (yesterday's 60 min never); "
        f"rm C3 / C2: 0 minted, still needs {need}"
    )


def case_h(world: World) -> str:
    """The turn that finished the unit pays though C2 is stamped 1 s before its end."""
    seeded(world)
    world.role("flip", "prefix-sums/0/180")
    world.role("harvest")
    world.role("began", "40")
    world.role("teach", f"{ALGO}/prefix-sums/6/30")
    world.role("teach", f"{ALGO}/prefix-sums/6/10")
    world.role("flip", f"prefix-sums/1/{10 + 1 / 60}")
    _, out = world.role("harvest")
    minted = world.entry_ids("theory:")
    check('"solve"' in _phase_text(world), f"not SOLVE: {_phase_text(world)}")
    check(len(minted) == 1, f"last turn not paid: {minted} {out[-600:]}")
    return f"THEORY->SOLVE, C2 at 1 s before the last turn ended: minted {minted}"


def case_i(world: World) -> str:
    """R2: minutes taught before THEORY(u) began never pay; later ones do."""
    seeded(world)
    world.role("flip", "prefix-sums/0/600", "prefix-sums/1/500")
    world.role("harvest")
    morning = [f"{ALGO}/stack-queue/12/{240 - 12 * i}" for i in range(10)]
    world.role("teach", *morning)
    _, out = world.role("harvest", ac=PS_EASY)
    detail = (world.phase_file() or {}).get("detail") or {}
    check(
        (detail.get("unit"), detail.get("phase")) == ("stack-queue", "theory"),
        f"no THEORY(stack-queue): {detail} {out[-400:]}",
    )
    early = world.entry_ids("theory:")
    check(not early, f"morning minutes paid: {early}")
    world.role("teach", f"{ALGO}/stack-queue/12/0")
    world.role("harvest")
    later = world.entry_ids("theory:")
    check(len(later) == 1, f"a lesson after THEORY began did not pay: {later}")
    return f"120 morning min before THEORY(stack-queue): 0 minted; 12 after: {later}"
