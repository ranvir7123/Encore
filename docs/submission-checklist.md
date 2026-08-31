# Submission checklist

Short reference for filling out the buildathon submission form. Everything
below traces to a real repo artifact — `README.md`, `BROKELOG.md`, or the
build plan's own self-review — none of it is invented.

## Form fields

- **Track:** AI Revenue Recovery
- **Repo URL:** https://github.com/ranvir7123/Encore
- **Video link:** TODO(user) — paste the unlisted video URL here once
  uploaded (YouTube "Unlisted" or equivalent). Placeholder only; nothing
  has been uploaded yet.
- **Demo script used for the recording:** `docs/demo-script.md`
- **"What broke" essay:** `docs/what-broke-essay.md` (draft — review before
  pasting into the form; it may need trimming to the form's character
  limit)

## TODO(user): in-person round answer

Not filled in — this is a judgment call about what to emphasize live that
only the person presenting can make. Suggested angles, each drawn from
something already true and documented in this repo, not new claims:

- Live-demo the compliance wall's precedence order
  (`tests/test_wall.py`'s 24 tests, all adversarial) and say out loud that
  the ML never gets a vote on legality — `wall.py` is a pure function by
  project rule (`CLAUDE.md`: "wall.py stays pure"), so this is something a
  judge can verify by reading one file, not by trusting a claim.
- Walk through one `BROKELOG.md` entry live — the time-blind-rail one
  (commit `869cdcf`) is the deepest, since it's a controller-directed
  reversal of an earlier approved simplification once the real mechanism
  was traced. It's a good demonstration of the append-only discipline
  actually catching something, not just documenting it after the fact.
- Be ready to explain the `r2_no_signal` ~3x result honestly if asked —
  `README.md`'s limitations section already says it's more likely a
  search-horizon artifact (`LearnedPolicy` searches a 10-day candidate
  window, `FixedSchedule` only tries T+1/T+2/T+3) than genuinely learned
  timing, since `r2_no_signal` deliberately destroys the salary-day signal.
  Leading with that caveat unprompted reads better than waiting to be
  caught on it.

## TODO(user): 6/12-month answer

Not filled in — this is a roadmap commitment only the team can make.
Suggested content, each pulled from a concrete gap already named in the
repo rather than a generic "we'll scale it" answer:

- **Run the horizon-matched baseline.** `README.md`'s limitations section
  names this as "the natural next experiment" that "has not been run" —
  a `FixedSchedule` variant searching the same 10-day window
  `LearnedPolicy` does, to separate a genuine learned-timing win from a
  wider-search-window artifact. This is scoped, cheap, and directly
  answers the biggest open question in the current metrics table.
- **Populate the LLM parser comparison.** `README.md` section 5 already
  has the table shape (`claude-haiku-4-5` / `claude-sonnet-5` rows) and the
  labeled 40-row set (`data/reply_eval.jsonl`) — it's just never been run
  with an `ANTHROPIC_API_KEY` set. `uv run encore parse-eval` exists today
  and explicitly refuses to invent numbers for the LLM rows without a key;
  running it for real, especially against the 6 `dispute` cases the
  keyword parser structurally cannot catch, is the next real evaluation to
  do before touting an LLM-parser win.
- **The global event-queue refactor.** The build plan's own self-review
  (`.superpowers/sdd/encore-build-plan/task-14-brief.md`) names this
  explicitly as a known simplification: sequences are processed per-failure
  rather than through one globally interleaved event queue across
  customers. That was ruled a documented simplification, not a correctness
  issue, for the current policy-comparison eval — but a global queue is the
  natural next step if the simulator needs to model cross-customer
  interaction (e.g. shared rail rate limits, or portfolio-wide kill-switch
  timing) rather than independent per-customer sequences.
