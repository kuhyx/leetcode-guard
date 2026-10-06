"""Lock the PC until a LeetCode problem is solved.

The gate is a *derived-balance* ledger, not a stored counter. One accepted
LeetCode submission is one credit; since 2026-10-07 one gated day costs two
credits on a Tuesday, Wednesday or Thursday, three on Monday and Friday and
four on Saturday and Sunday (see ``_daycost``). ``available = sum(credits) -
sum(charges)``, always
recomputed, never persisted -- so a single edited number can never buy a day.

Deliberately no re-exports. Every module imports what it needs by full path,
which keeps the import graph flat and lets the test suite replace one module's
``tkinter`` reference without reaching any other.
"""
