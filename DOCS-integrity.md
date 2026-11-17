# leetcode-guard integrity

Ledger entries are HMAC-signed against `/etc/workout-locker/hmac.key`, shared
with the sibling lockers.

* A credit whose signature does not verify is **kept on disk and refused** —
  hand-editing the JSON cannot buy a day.
* A *charge* whose signature does not verify still counts — discarding one
  would refund a day.
* If the key becomes unreadable, this device's own credits keep counting
  (loudly), but credits arriving over sync do not. Otherwise a single `chmod`
  would brick the machine.

**Honest scope:** the key is world-readable, so this is tamper-*evident*, not
tamper-*proof*. It stops casual editing and leaves a record; it does not stop
someone who reads the key.

The gate also refuses to honour an existing charge when the system clock has
moved backwards past a settled day — otherwise setting the date back would be
the cheapest bypass of all.
