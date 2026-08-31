# Encore — project rules

## Broke-log (non-negotiable)
Whenever ANY of these happen, append an entry to BROKELOG.md BEFORE fixing:
- a test fails for a reason you did not predict
- a bug is found in code that was believed done
- a design decision is reversed
- an external API behaves differently than documented

Entry format (append at the bottom):
### <ISO date> — <one-line title>
- **What happened:** <observed behavior, verbatim error if any>
- **Evidence:** <command + output snippet, or failing test name>
- **Root cause:** <fill after diagnosis>
- **Fix:** <commit hash after fixing>
- **Still open:** <anything unresolved, or "nothing">

Never delete or edit past entries. The buildathon essay is assembled from this file.

## Engineering rules
- Money is integer paise everywhere. Floats near money = bug.
- wall.py stays pure: no I/O, no clocks, no randomness. If you need one, pass it in.
- No LLM call on the money path. Parser output goes through pydantic, then the wall.
- All randomness from seeded random.Random instances passed explicitly.
- Every public repo commit message is written for a judge's eyes.
- Run `uv run pytest -q` and `uv run ruff check .` before every commit.

## Verification
Never claim something works without showing the command and its real output.
