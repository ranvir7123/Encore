# Encore web — design spec

**Status:** approved in brainstorm, not yet implemented.
**Date:** 2026-09-01

## 1. Purpose

A deployed page a judge can open cold and, inside 60 seconds, verify the
project's actual claims rather than take them on trust. Two things must land:

1. **The compliance wall is real and cannot be talked out of a decision.**
   The judge should try to break it, in their own browser, against the real
   `wall.py`.
2. **We ran the control that could kill our own headline, and published the
   result.** The judge should see the model lose to random and understand
   exactly why in one glance.

Explicit non-goal: this is not a product dashboard, a merchant console, or a
sales page. It is an evidence surface.

## 2. Verified constraints

Every number below was measured, not assumed (see the conversation that
produced this spec, and BROKELOG entries 9–10).

| Fact | Measured value |
|---|---|
| Pyodide 0.28.3 Python version | 3.13.2 — satisfies `requires-python >=3.13` |
| Pyodide cold load | ~18 s |
| `wall`, `domain`, `simulator`, `policies`, `scheduler`, `audit` deps | **pure stdlib** |
| 100-customer, 30-day simulation in Pyodide | **0.02 s** |
| `scikit-learn` install in Pyodide | **61.7 s**, version 1.7.0 |
| `pydantic` in Pyodide | 2.10.6 |
| Full suite on Pyodide's versions | **61 passed** (pre-baseline suite) |
| `eval.json` on 1.9.0/2.13.5 vs 1.7.0/2.10.6 | **byte-for-byte identical** |

The last row is what licenses the honesty claim: browser-run results and
locally-run results are not merely similar, they are the same bytes.

## 3. Architecture

**Static site. No backend, no server, no database.** A strict two-tier split,
chosen because scikit-learn's 62-second install is unacceptable in a page a
judge opens once.

**Tier A — live, executed in the browser on the real source files.**
Everything that imports only the standard library:
`wall.py`, `domain.py`, `simulator.py`, `policies.py`, `scheduler.py`,
`audit.py`. This covers the compliance wall and four of six policies
(`immediate_x3`, `fixed_t123`, `fixed_spread10`, `random_in_horizon`).

The `.py` files are fetched over HTTP and written into the Pyodide
filesystem, then imported normally. No wheel build, no `micropip`, no
`requires-python` negotiation. The same files are also linked for view-source,
so "this is the code running right now" is checkable, not asserted.

**Tier B — precomputed, generated from `runs/` by a committed script.**
The two ML policies and the day-of-month diagnostic. `scikit-learn` is never
loaded in the browser.

Every Tier B figure renders with a provenance line naming the seeds, customer
count, and the exact command that reproduces it. No number appears without
its origin.

**Progressive enhancement is mandatory.** All Tier B content is server-rendered
HTML that is complete and readable before any JavaScript runs. If Pyodide
fails to load — slow network, blocked CDN, old browser — the page loses the
two interactive panels and nothing else. The static evidence must never
depend on the Python runtime.

## 4. Page structure

1. **Hero.** The surviving claim (2.85x over the industry-standard schedule,
   zero violations in 18 cells) and, directly beneath it, the pull quote
   pointing at the control that beats the model. Same ordering as `README.md`
   — the caveat is never below the fold.
2. **Wall sandbox (Tier A, live).** Controls for the five inputs
   `SequenceState` and `ProposedAction` actually take: original decline,
   retries attempted, last attempt hour, killed flag, proposed hour. Output is
   `decide()`'s real `Decision` — allow/deny plus reason code — with the
   precedence chain shown so a denial explains *which* rule fired first.
   Framed as a challenge: make it approve something illegal.
3. **The cliff (Tier B).** The centrepiece. Retries-per-day-of-month for
   `encore_learned` and `random_in_horizon`, overlaid on the success rate per
   day, for `r1_shifted`. The day-25 step function and the model sitting two
   days to its left.
4. **Live race (Tier A, live).** Pick a regime and a seed; run all four
   stdlib policies — `immediate_x3`, `fixed_t123`, `fixed_spread10`,
   `random_in_horizon` — through the real `Scheduler` and wall, in-browser,
   and show recovered totals. `immediate_x3` recovering ₹0 live is the point,
   not a glitch: the wall denies every one of its attempts, and the denial
   reasons are shown. The judge watches random beat the industry standard on
   their own machine. The two ML policies appear as static reference bars,
   clearly marked precomputed.
5. **Results table (Tier B).** All 18 cells, `random_in_horizon` visually
   emphasised as the row to read first.
6. **The broke-log.** Ten entries as the narrative spine, with 9 and 10
   expanded. Not an appendix.
7. **Reproduce.** The literal commands, and a statement that browser and
   local results are byte-identical.

## 5. Components and data flow

| Path | Responsibility |
|---|---|
| `web/index.html` | Page shell; all Tier B content inlined as static HTML |
| `web/app.js` | Pyodide bootstrap, module mounting, sandbox + race wiring |
| `web/styles.css` | Presentation |
| `web/data/results.json` | 18-cell matrix, generated |
| `web/data/cliff.json` | Day-of-month tried/won per policy, generated |
| `scripts/build_web_data.py` | **The only writer of `web/data/*.json`** |

Data flow is one-directional and has a single source of truth:

```
runs/eval.json ---------.
runs/*_audit.jsonl ------> scripts/build_web_data.py --> web/data/*.json --> index.html
src/encore/*.py ------------------ fetched at runtime -----------------> Pyodide FS
```

`build_web_data.py` is a pure transform over files `encore eval` already
produces. Hand-editing `web/data/*.json` is prohibited; the script is the
only writer, so a stale site is a rebuild away rather than a transcription
bug. `runs/` stays gitignored scratch; the generated JSON is committed,
because the deployed site cannot depend on regenerable local state.

## 6. Error handling

- **Pyodide unavailable** → both live panels replace themselves with a short
  explanation and a link to the local commands. Tier B is untouched.
- **A `.py` fetch 404s** → the sandbox reports which module failed by name
  rather than throwing an opaque error. This is a real deploy risk, since it
  depends on `src/` being published alongside `web/`.
- **Malformed or missing `web/data/*.json`** → the affected section renders a
  "data not built — run `scripts/build_web_data.py`" placeholder, matching
  how `report.py` already degrades on a missing audit log.
- **Live race takes too long** → it cannot; 100 customers is 0.02 s measured.
  Customer count is capped at 500 in the UI so this stays true.

## 7. Testing

- `scripts/build_web_data.py` gets unit tests over a fixture `eval.json` and
  fixture audit lines — it is a pure transform, so it is directly testable
  without running an eval.
- A schema test asserts `web/data/results.json` contains all 18 expected
  `regime/policy` cells with the required keys, so a truncated or half-written
  build fails in CI rather than on the deployed page.
- A test asserts the six policy names the site renders match
  `evaluate.run_matrix`'s actual policy list, so adding or renaming a policy
  cannot silently desync the site from the code.
- The wall sandbox needs no new Python tests: it calls `wall.decide()`, which
  already has 24 adversarial tests. That is the point of it.

## 8. Deployment

Vercel (chosen in brainstorm). Static output, no build step beyond running
`scripts/build_web_data.py`. Both `web/` and `src/encore/*.py` must be
published — the site fetches the latter at runtime.

Requires the user's account; this is one of the steps only they can perform.

## 9. Open questions

- Whether `src/encore/*.py` is fetched from the deploy or from raw GitHub.
  Deploy-local is faster and avoids a cross-origin dependency; GitHub-raw is
  more obviously "the real repo file" to a sceptical judge. Deploy-local is
  the default unless the demo argues otherwise.
- The live race completes in ~0.02 s, which is too fast to read. Default:
  render bars with a short CSS transition and stagger the four policies, so
  the result is legible without faking computation time. The elapsed time is
  displayed honestly next to it.
