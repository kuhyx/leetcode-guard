"""Work out *why* LeetCode is unreachable, because the answer decides policy.

The bypass this exists to resist: unplug the ethernet, the gate cannot verify a
solve, and it unlocks. So "cannot reach LeetCode" is not one condition, it is
three, and they lead to opposite outcomes:

``REMOTE_OUTAGE``
    Our connection is fine and LeetCode itself is down. Not the user's fault
    and not something they can fix -- unlock, say why, log loudly.

``LOCAL_OFFLINE``
    Nothing at all is reachable. Stay locked, wait, then demand a written
    explanation of what happened to the network.

``LOCAL_TAMPERED``
    Everything *else* is reachable but leetcode.com's name is being answered
    locally -- it does not resolve, or it resolves to loopback/RFC1918.
    Treated as ``LOCAL_OFFLINE``.

``ONLINE``
    LeetCode answered a direct probe, so the poller's failures were transient.
    Keep watching; do **not** unlock.

That third case is what closes the hole. Without it, blackholing one domain in
``/etc/hosts`` -- a single line -- would read as "not our issue" and buy a free
unlock every day.

Honest limits, stated so the README cannot overstate them: a block applied at
the router, or a captive portal answering from a public address, is
indistinguishable here from a real LeetCode outage and will unlock the day.
The DNS checks catch the cheap local blocks -- an ``/etc/hosts`` line, a
Pi-hole rule -- and every verdict is logged loudly. That raises the cost of the
bypass; it does not make it impossible.
"""

from __future__ import annotations

from dataclasses import dataclass
import enum
import ipaddress
import logging
import socket
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

_logger: Final = logging.getLogger(__name__)

ANCHORS: Final[tuple[tuple[str, int], ...]] = (
    ("1.1.1.1", 443),
    ("8.8.8.8", 443),
    ("9.9.9.9", 443),
)
"""Independent, unrelated hosts used to answer "is *anything* reachable?".

Raw IPs on purpose: a hostname would fold a DNS failure into the reachability
answer, and DNS failing while packets flow is exactly the tampering case this
module has to tell apart.
"""

LEETCODE_HOST: Final = "leetcode.com"
ANCHOR_TIMEOUT_SECONDS: Final = 3.0

_LEETCODE_MARKER: Final = "leetcode"
"""What a genuine response from leetcode.com contains.

A captive portal or hijacking resolver answers with HTTP 200 from a perfectly
public IP, so an address-shape test alone would classify it ``REMOTE_OUTAGE``
and unlock. Requiring a positive identity marker before any remote verdict is
what stops hotel wifi being a bypass.
"""


class NetworkVerdict(enum.Enum):
    """Why LeetCode could not be reached."""

    ONLINE = "online"
    """Reachable after all -- the caller's failures were transient.

    Reached when the direct identity probe succeeds. It must NOT unlock: a
    working LeetCode is the one case where the user can simply solve
    something."""

    REMOTE_OUTAGE = "remote-outage"
    LOCAL_OFFLINE = "local-offline"
    LOCAL_TAMPERED = "local-tampered"

    @property
    def is_our_fault(self) -> bool:
        """Whether the user's own machine or network is responsible."""
        return self in {NetworkVerdict.LOCAL_OFFLINE, NetworkVerdict.LOCAL_TAMPERED}


@dataclass(frozen=True)
class NetworkDiagnosis:
    """The verdict plus the evidence behind it."""

    verdict: NetworkVerdict
    reason: str
    anchors_reachable: int
    addresses: tuple[str, ...]

    @property
    def unlocks(self) -> bool:
        """Whether this diagnosis alone justifies opening the gate."""
        return self.verdict is NetworkVerdict.REMOTE_OUTAGE


def tcp_reachable(
    host: str, port: int, *, timeout: float = ANCHOR_TIMEOUT_SECONDS
) -> bool:
    """Whether a TCP connection to ``host:port`` completes."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError as exc:
        # An unreachable anchor is expected input, not a fault -- but the
        # no-silent-failures rule wants every swallowed exception visible, and
        # this one genuinely helps when diagnosing a misclassification.
        _logger.warning("anchor %s:%d unreachable: %s", host, port, exc)
        return False


def resolve_host(host: str) -> tuple[str, ...]:
    """Every address ``host`` resolves to, or an empty tuple."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        _logger.warning("cannot resolve %s: %s", host, exc)
        return ()
    return tuple(sorted({str(info[4][0]) for info in infos}))


def _is_blackholed(addresses: Sequence[str]) -> bool:
    """Whether the addresses look like a local redirect rather than the site.

    Loopback, unspecified and RFC1918 all mean the name is being answered
    locally -- an ``/etc/hosts`` entry, a Pi-hole rule, a dnsmasq override.
    """
    for text in addresses:
        try:
            address = ipaddress.ip_address(text)
        except ValueError:
            _logger.warning(
                "ignoring unparsable address %r for %s", text, LEETCODE_HOST
            )
            continue
        if address.is_loopback or address.is_unspecified or address.is_private:
            return True
    return False


def classify(
    *,
    connect: Callable[[str, int], bool] | None = None,
    resolve: Callable[[str], tuple[str, ...]] | None = None,
    identity_ok: Callable[[], bool] | None = None,
) -> NetworkDiagnosis:
    """Decide which of the three failure modes applies.

    Args:
        connect: TCP reachability probe. Injected for tests.
        resolve: DNS lookup. Injected for tests.
        identity_ok: Whether a control fetch of leetcode.com looks like
            LeetCode. Only consulted when a remote verdict is otherwise on the
            table, so the common paths cost nothing.

    Returns:
        The diagnosis. Never raises.
    """
    probe = connect if connect is not None else _default_connect
    lookup = resolve if resolve is not None else resolve_host

    reachable = sum(1 for host, port in ANCHORS if probe(host, port))
    if reachable == 0:
        return NetworkDiagnosis(
            verdict=NetworkVerdict.LOCAL_OFFLINE,
            reason=(
                "This machine has no working internet connection -- none of "
                f"{len(ANCHORS)} independent hosts responded."
            ),
            anchors_reachable=0,
            addresses=(),
        )

    addresses = lookup(LEETCODE_HOST)
    if not addresses:
        return _tampered(
            f"The internet is reachable but {LEETCODE_HOST} does not resolve at "
            "all, which is what a local DNS block looks like.",
            reachable,
            addresses,
        )
    if _is_blackholed(addresses):
        return _tampered(
            f"{LEETCODE_HOST} resolves to {', '.join(addresses)}, which is not "
            "LeetCode -- the name is being answered locally.",
            reachable,
            addresses,
        )

    if identity_ok is not None and identity_ok():
        # LeetCode just answered us. Whatever the poller tripped over has
        # cleared, so the honest verdict is "fine again" -- NOT an outage.
        # Returning REMOTE_OUTAGE here would hand out a free day every time a
        # transient blip lasted longer than the blind threshold, which is a
        # bypass rather than a kindness.
        return NetworkDiagnosis(
            verdict=NetworkVerdict.ONLINE,
            reason="LeetCode answered a direct probe -- the earlier failures "
            "were transient.",
            anchors_reachable=reachable,
            addresses=addresses,
        )

    return NetworkDiagnosis(
        verdict=NetworkVerdict.REMOTE_OUTAGE,
        reason=(
            "Your connection is fine and leetcode.com resolves normally, so "
            "LeetCode itself is unreachable. This is not something you can fix."
        ),
        anchors_reachable=reachable,
        addresses=addresses,
    )


def _tampered(
    reason: str, reachable: int, addresses: tuple[str, ...]
) -> NetworkDiagnosis:
    """Build a tampering verdict, logging it at ERROR."""
    _logger.error("leetcode-guard: %s", reason)
    return NetworkDiagnosis(
        verdict=NetworkVerdict.LOCAL_TAMPERED,
        reason=reason,
        anchors_reachable=reachable,
        addresses=addresses,
    )


def _default_connect(host: str, port: int) -> bool:
    """Default reachability probe."""
    return tcp_reachable(host, port)
