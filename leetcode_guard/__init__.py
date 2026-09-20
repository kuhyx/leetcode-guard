"""Lock the PC until a LeetCode problem is solved.

The gate is a *derived-balance* ledger, not a stored counter. One accepted
LeetCode submission is one credit; one gated day costs two credits on a
Tuesday, Wednesday or Thursday and four on the other days (one and two before
2026-09-21). ``available = sum(credits) - sum(charges)``, always
recomputed, never persisted -- so a single edited number can never buy a day.

Deliberately no re-exports. Every module imports what it needs by full path,
which keeps the import graph flat and lets the test suite replace one module's
``tkinter`` reference without reaching any other.
"""
