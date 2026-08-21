# Session prompt: take pylint from 8.53 to 10.00

Paste everything below the line into a fresh Claude Code session started in
`~/leetcode-guard`.

---

Take this repo's pylint score from **8.53/10 to a clean 10.00/10**, without
weakening the linter.

## Why

The pre-commit pylint hook runs with `--fail-under=8.0`, so at 8.53 the repo
passes its gate while carrying ~1100 findings — and it is close enough to the
floor that a single ordinary change can push it under. (It measured 8.64 on
2026-08-21 and dropped to 8.53 the same day purely from the import lines
added by the crdt-sync v0.9.0 migration.) The same job was done in
`~/utils/crdt-sync` on 2026-08-21 (8.58 -> 10.00).

Measured on this machine, 2026-08-21, with
`~/.cache/pre-commit/repo01lfw04p/py_env-python3/bin/pylint --rcfile=pyproject.toml leetcode_guard scripts`:

| category | count |
|---|---|
| missing-function-docstring | 457 |
| protected-access | 344 |
| use-implicit-booleaness-not-comparison-to-zero | 73 |
| unused-argument | 56 |
| import-outside-toplevel | 44 |
| use-implicit-booleaness-not-comparison | 38 |
| invalid-name | 34 |
| duplicate-code | 16 |

Locality: **466 of the docstring findings and 328 of the protected-access
findings are in `leetcode_guard/tests/`.** Only 16 protected-access are in
`scripts/` and 8 in `leetcode_guard/` proper. Tests are ~93% of the work.

Re-measure before you start and again at the end.

## Scope

**In scope**
1. Every pylint finding under `leetcode_guard/` and `scripts/`.

**Out of scope — do not touch**
- `--fail-under` in `.pre-commit-config.yaml`. Do NOT raise it to hide a
  shortfall, and do NOT lower it. Leave it at 8.0.
- `pyproject.toml`'s pylint `disable` list.
- The `crdt-sync` pin, in `pyproject.toml`, `requirements.txt`, or the
  pylint hook's `additional_dependencies`. All three are on
  `crdt-sync-v0.9.0` deliberately; the hook pins it separately so the gate
  lints against the API the code imports. Changing any of them is a
  different task.

## The rule that decides the approach

**Fix the underlying issue; do not suppress it.** The repo blocks `noqa` and
`type: ignore` outright via a pre-commit hook. Inline `# pylint: disable=` is
permitted ONLY for a genuine false positive, and then it must be scoped to
the narrowest unit, placed on the line that actually triggers it (verify —
a `disable-next` one line off silently does nothing and pylint reports
`useless-suppression`), and carry a comment saying why the check is wrong
there.

Ask before adding any suppression that is not clearly a false positive.

## The 344 protected-access findings need a decision, not a script

This is the largest category after docstrings and the least mechanical. For
each cluster, work out which case applies:

- **The private member IS the unit under test** (no public accessor exists).
  A scoped disable with a reason is legitimate. In crdt-sync this covered
  `_timeout_seconds`, where reading the private attribute is the entire
  assertion.
- **A public accessor exists** and the test simply reached past it. Fix the
  test.
- **No accessor exists but should.** Adding one is a source change with
  blast radius — surface it rather than doing it unilaterally.

Do not blanket-disable `protected-access` for the whole tests tree without
asking. 328 findings is enough that the right answer may well be a
tests-scoped disable, but that is the user's call, and it should be made
once with the reasoning visible — not assumed.

## What worked in crdt-sync (copy this for the 457 docstrings)

Script the first draft, then review every one:

1. Parse each test file with `ast`; find every `ClassDef`/`FunctionDef`
   named `test_*`/`Test*` with no docstring.
2. Derive prose from the identifier — the names are already sentences.
3. **Insert at the anchor, not the first body statement.** A decorated first
   statement (`@staticmethod`, `@pytest.mark...`) means inserting at its
   `lineno` puts the docstring BETWEEN decorator and `def` — a syntax error.
   Anchor to `min(lineno, *[d.lineno for d in decorator_list])`.
4. Back the test tree up (`cp -a`), `ast.parse` every touched file, and run
   the suite immediately.

Then improve the ones where the assertion says more than the name does.

## Also expect

- `use-implicit-booleaness-*` (111): `assert not x` for `== {}` / `== []` /
  `== 0` / `== ""`. Check each — the explicit form sometimes asserts type.
- `unused-argument` (56): prefix with `_` when the argument exists only to
  match a real signature (stubs, fixtures).
- `import-outside-toplevel` (44): often deliberate, to avoid a cycle or a
  slow import. Where it is, that is a legitimate scoped disable with the
  reason stated.
- `invalid-name` (34): check whether the name is imposed by an external API
  (e.g. `do_GET` on a `BaseHTTPRequestHandler`) before renaming anything.
- `duplicate-code` (16): near-copy helpers across test modules; merge into
  `conftest.py`, and watch that coverage holds.

## Gates

- `python -m pytest -q` — currently **717 passing at 100% branch coverage**.
  Both numbers must hold.
- `pre-commit run --files <changed>` — must pass, including the noqa blocker.
- `ruff format` will reformat what you touch; re-run the suite afterwards.

## Done means

1. `pylint --rcfile=pyproject.toml leetcode_guard scripts` reports
   **10.00/10**.
2. `--fail-under` still 8.0, `disable` list unchanged, crdt-sync pins
   untouched.
3. 717 tests still passing at 100% branch coverage.
4. Every suppression listed in the final report with its justification —
   especially whatever you concluded about the 344 protected-access findings.
   If 10.00 was not reachable on terms the user would accept, say so and
   report the real number.
