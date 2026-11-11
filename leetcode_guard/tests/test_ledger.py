"""Tests for entry construction, signing and serialisation."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import TYPE_CHECKING

import pytest

from leetcode_guard._ledger import (
    BOOTSTRAP,
    CHARGE,
    CREDIT,
    SEEN,
    SOURCE_ESCAPE,
    LedgerEntry,
    entry_payload,
    from_json,
    key_available,
    sign,
    to_json,
    verify,
)
from leetcode_guard._ledger_entries import (
    bootstrap_entry,
    charge_entry,
    credit_entry,
    seen_entry,
)
from leetcode_guard.tests._ledger_fixtures import MONDAY, NOW, SATURDAY, submission

if TYPE_CHECKING:
    from pathlib import Path


def test_a_credit_is_keyed_on_the_submission_id(hmac_key: Path):
    """A credit's id is ac:<submission id>, worth 1, and signed."""
    entry = credit_entry(submission("12345"), day=MONDAY, now=NOW, key_file=hmac_key)

    assert entry.entry_id == "ac:12345"
    assert entry.kind == CREDIT
    assert entry.amount == 1
    assert entry.day == "2026-08-10"
    assert entry.detail["title_slug"] == "two-sum"
    assert verify(entry, key_file=hmac_key)


def test_a_charge_costs_what_the_day_costs(hmac_key: Path):
    """A charge costs 1 on a weekday and 2 on a weekend."""
    weekday = charge_entry(MONDAY, now=NOW, key_file=hmac_key)
    weekend = charge_entry(SATURDAY, now=NOW, key_file=hmac_key)

    assert weekday.amount == 1
    assert weekend.amount == 2
    assert weekday.entry_id == "charge:2026-08-10"
    assert weekday.kind == CHARGE


def test_a_charge_records_why_the_day_was_settled(hmac_key: Path):
    """A charge records its source, e.g. the escape hatch."""
    entry = charge_entry(MONDAY, now=NOW, source=SOURCE_ESCAPE, key_file=hmac_key)

    assert entry.detail["source"] == SOURCE_ESCAPE


def test_seen_and_bootstrap_markers_are_worth_nothing(hmac_key: Path):
    """Seen and bootstrap markers carry amount 0."""
    seen = seen_entry(submission("9"), day=MONDAY, now=NOW, key_file=hmac_key)
    boot = bootstrap_entry(day=MONDAY, now=NOW, seeded=20, key_file=hmac_key)

    assert (seen.kind, seen.amount) == (SEEN, 0)
    assert (boot.kind, boot.amount) == (BOOTSTRAP, 0)
    assert boot.detail["seeded"] == "20"


def test_a_seen_marker_shares_the_credit_id_so_it_blocks_harvesting(hmac_key: Path):
    """Seeding only works because the marker occupies the id a credit would."""
    sub = submission("42")

    assert seen_entry(sub, day=MONDAY, now=NOW, key_file=hmac_key).entry_id == (
        credit_entry(sub, day=MONDAY, now=NOW, key_file=hmac_key).entry_id
    )


def test_the_signature_covers_every_field_that_matters(hmac_key: Path):
    """The signed payload holds exactly the meaningful fields."""
    entry = credit_entry(submission("1"), day=MONDAY, now=NOW, key_file=hmac_key)
    payload = entry_payload(entry)

    assert set(payload) == {
        "entry_id",
        "kind",
        "day",
        "created_at",
        "amount",
        "device",
        "detail",
    }
    assert "signature" not in payload
    assert "verified" not in payload


@pytest.mark.parametrize(
    "mutation",
    [
        {"amount": 5},
        {"day": "2026-01-01"},
        {"kind": "charge"},
        {"device": "phone"},
        {"entry_id": "ac:other"},
    ],
)
def test_any_mutation_breaks_the_signature(hmac_key: Path, mutation: dict):
    """Changing any signed field fails verification."""
    entry = credit_entry(submission("1"), day=MONDAY, now=NOW, key_file=hmac_key)
    tampered = replace(entry, detail=dict(entry.detail), verified=False, **mutation)

    assert not verify(tampered, key_file=hmac_key)


def test_an_unsigned_entry_never_verifies(hmac_key: Path):
    """An entry without a signature never verifies."""
    assert not verify(
        LedgerEntry("ac:1", CREDIT, "2026-08-10", "", 1), key_file=hmac_key
    )


def test_signing_without_a_key_yields_no_signature(missing_key: Path):
    """Signing with a missing key leaves the entry unsigned."""
    entry = sign(LedgerEntry("ac:1", CREDIT, "2026-08-10", "", 1), key_file=missing_key)

    assert entry.signature is None
    assert not entry.verified


def test_key_available_separates_a_broken_key_from_a_forgery(
    hmac_key: Path, missing_key: Path
):
    """The discriminator the whole integrity policy rests on."""
    assert key_available(key_file=hmac_key)
    assert not key_available(key_file=missing_key)


def test_json_round_trip(hmac_key: Path):
    """An entry survives to_json then from_json intact."""
    entry = credit_entry(
        submission("77", "add-two"), day=MONDAY, now=NOW, key_file=hmac_key
    )

    restored = from_json(to_json(entry))

    assert restored is not None
    assert restored.entry_id == entry.entry_id
    assert restored.amount == entry.amount
    assert restored.detail == entry.detail
    assert restored.signature == entry.signature
    assert verify(restored, key_file=hmac_key)


@pytest.mark.parametrize(
    "raw",
    [
        "not-an-object",
        {"kind": "credit", "day": "2026-08-10", "amount": 1},
        {"entry_id": "a", "day": "2026-08-10", "amount": 1},
        {"entry_id": "a", "kind": "credit", "amount": 1},
        {"entry_id": "a", "kind": "credit", "day": "2026-08-10"},
        {"entry_id": "a", "kind": "credit", "day": "2026-08-10", "amount": "one"},
        {"entry_id": "a", "kind": "credit", "day": "2026-08-10", "amount": True},
        {"entry_id": 1, "kind": "credit", "day": "2026-08-10", "amount": 1},
    ],
)
def test_unusable_stored_rows_parse_to_none(raw: object):
    """Malformed stored rows parse to None instead of raising."""
    assert from_json(raw) is None


def test_missing_optional_fields_get_safe_defaults():
    """Absent optional fields default to empty values."""
    entry = from_json(
        {"entry_id": "a", "kind": "credit", "day": "2026-08-10", "amount": 1}
    )

    assert entry is not None
    assert entry.created_at == ""
    assert entry.device == ""
    assert entry.detail == {}
    assert entry.signature is None


def test_a_non_dict_detail_becomes_empty():
    """A non-dict detail parses as an empty dict."""
    entry = from_json(
        {
            "entry_id": "a",
            "kind": "credit",
            "day": "2026-08-10",
            "amount": 1,
            "detail": [],
        }
    )

    assert entry is not None
    assert entry.detail == {}


def test_detail_values_are_coerced_to_strings():
    """Detail values are stored as strings."""
    entry = from_json(
        {
            "entry_id": "a",
            "kind": "credit",
            "day": "2026-08-10",
            "amount": 1,
            "detail": {"count": 3},
        }
    )

    assert entry is not None
    assert entry.detail == {"count": "3"}


def test_a_non_string_signature_is_dropped():
    """A non-string hmac parses as no signature."""
    entry = from_json(
        {"entry_id": "a", "kind": "credit", "day": "2026-08-10", "amount": 1, "hmac": 7}
    )

    assert entry is not None
    assert entry.signature is None


def test_the_day_stamped_on_a_credit_is_the_local_day_passed_in(hmac_key: Path):
    """A credit's day is the day passed in, not derived from now."""
    entry = credit_entry(
        submission("1"), day=date(2026, 12, 31), now=NOW, key_file=hmac_key
    )

    assert entry.day == "2026-12-31"
