# Demo script v2

The 5-minute submission video, as three clips recorded separately and
stitched in order. Every command below has run on this machine; the
transcripts they are drawn from are in `docs/spike-notes.md` (live takes 1
to 3) and `docs/evidence/`. Hard ceiling **5:00**. Cut narration, never
footage.

## Why it is shaped this way

- Razorpay's bar for this track, verbatim: "Show measured money recovered
  across a batch, with compliant escalation, stopping rules, and an audit
  trail" ([razorpay.com/buildathon](https://razorpay.com/buildathon)). The
  board shows all four in one frame, so it is on screen for about two of the
  five minutes.
- The four scored criteria are Problem taste, Build quality, AI judgment
  (the right tool in the right place, and where you chose not to use one)
  and Failure recovery (what broke and how you got out). Each beat below
  names the one it serves.
- Judges say the demo video "gives the most amount of scope", that
  "presentation and storytelling matters", and they mark down slick pages
  that are "lighter on code"; they want the code running
  ([Devpost, five judges](https://info.devpost.com/blog/hackathon-judging-tips)).
  So: the terminal and a real checkout stay on screen, never slides.
- Pitch in the first seconds, problem then solution then how it works, script
  it, stay under the limit, never below 720p, show the running project
  ([Devpost, six tips](https://info.devpost.com/blog/6-tips-for-making-a-hackathon-demo-video);
  [hackathon.com](https://tips.hackathon.com/article/creating-the-best-demo-video-for-a-hackathon-what-to-know)).
  Record the risky part first and keep a fallback
  ([AngelHack](https://angelhack.com/blog/hackathon-tips-for-winners/)).

| Clip | Beats | Criterion | Target |
|---|---|---|---|
| 1 | title card, the loop with no network, idempotency | Problem taste, Build quality | 1:20 |
| 2 | one real customer on Razorpay test mode | Build quality, the track bar | 2:00 |
| 3 | the wall, the control, what broke, close | AI judgment, Failure recovery | 1:40 |

Record in the order **2, 1, 3**. Clip 2 is the only one that can fail; do it
while you are fresh and links are cheap. The edit puts them back in order 1, 2, 3.

## Recording tool

Windows 11 Snipping Tool plus Clipchamp. Both are preinstalled, and each
clip is under 2:30. `Win+Shift+R`, drag the whole screen, click the
microphone icon in the toolbar and pick your mic **before** Start; mic and
system audio are separate toggles and you only need mic
([Microsoft](https://www.microsoft.com/en-us/windows/learning-center/how-to-use-snipping-tool-on-windows-screenshots-shortcuts-and-screen-recordings)).
Recordings land in `Videos\Screen Recordings`. If your build has no mic
toggle, use OBS Studio instead:

```powershell
winget install --id OBSProject.OBSStudio -e
```

OBS in four clicks: Sources, add Display Capture; Audio Mixer, check the mic
meter moves when you talk; Settings, Output, Recording Quality "High Quality,
Medium File Size", format MP4; Start Recording.

## Pre-flight, 30 minutes before, off camera

1. Fresh code. In `C:\dev\encore`:
   ```powershell
   git pull
   uv sync
   uv run pytest -q
   ```
   The count printed must match the README quickstart (158).
2. `.env` holds the Razorpay **test** keys. Payment Links used on this
   account so far: 17 of 30. Each live take uses 2. That is six takes.
3. Windows: Do Not Disturb on (`Win+N`, the bell). Close mail, Slack, Teams.
   If the terminal looks small at 1080p, set display scale to 125%.
4. Windows Terminal, PowerShell tab, font 18 to 20 pt, a high-contrast scheme
   (One Half Dark or Campbell). Once per session:
   ```powershell
   $env:PYTHONUNBUFFERED = "1"
   ```
   Buffered stdout once hid the link URLs in a redirected run (spike notes).
5. Browser at 125% zoom. Open these tabs, in this order, and leave them:
   1. `docs/video/title-card.html` (open the file from the repo)
   2. GitHub README, scrolled so the four `r1_shifted` rows of the §3 table are in view
   3. GitHub `BROKELOG.md`
   4. GitHub `src/encore/wall.py`
   5. `https://ranvir7123.github.io/Encore/#method` (the cliff chart)
   You will add the board tab and two checkout tabs live.
6. Layout: terminal on the left half (`Win+Left`), browser on the right half
   (`Win+Right`). Both stay visible in every shot so the viewer never loses
   the link between a command and its effect.
7. Sticky note on the monitor edge: contact `9123456789`, card
   `4100 2800 0008 0001`, expiry `12/30`, CVV `123`, Netbanking bank `BOB`.
8. Clean the run files right before each clip. Never between the two dry
   runs in clip 1:
   ```powershell
   Remove-Item runs\agent_ledger_dryrun.txt, runs\agent_audit_dryrun.jsonl, runs\board_dryrun.html -ErrorAction SilentlyContinue
   Remove-Item runs\agent_ledger.txt, runs\agent_audit.jsonl, runs\board.html -ErrorAction SilentlyContinue
   ```
9. Read the whole script aloud once against a timer. Cut words until each
   beat fits its window.

---

## Clip 1: title, then the loop with no network (target 1:20)

### Beat 1, 0:00 to 0:20. Screen: the title card tab.

> UPI AutoPay mandates fail at a rate that would be a P0 outage anywhere
> else. NPCI data reported via Mint put the August 2025 execution failure
> rate at 55 to 90 percent across banks. Twenty million mandates a month get
> revoked, mostly over low balances. And NPCI caps how you may react: one
> execution, three retries, non-peak hours only. Encore is a recovery agent
> for that budget.

Why: Problem taste. Numbers first, sources named, the constraint named. The
constraint is the design, so it sits in the first sentence about the product.

### Beat 2, 0:20 to 1:20. Screen: terminal left, board right.

Type:
```powershell
uv run encore agent --dry-run --batch 50 --speed 0
```
It finishes in about 3 seconds. In the browser, open a new tab at
`file:///C:/dev/encore/runs/board_dryrun.html`. The board refreshes itself
every 3 seconds.

Say, pointing at each card in turn:

> Fifty simulated failures, no network. At risk, recovered, attempts. Every
> card is a sum over audit records, not a counter. Wall denials is the
> compliance gate saying no: thirteen revoked mandates, four customers who
> replied "cancel". Parked is the exception list: what the agent will not
> chase, and why. Nothing here is a guess. Each line is an appended JSON
> record.

Back to the terminal. Press Up, then Enter: the same command, same ledger.

> Same ledger, second run. Attempts zero, duplicates blocked thirty-three.
> Nothing executes twice. That is the idempotency guarantee, on camera.

Do **not** switch to the board for the second run. It is rewritten per run
and now shows Recovered ₹0.00, which reads as failure. Keep the terminal on
screen.

Why: Build quality and the track bar. Batch, stopping rules, audit trail and
idempotency in sixty seconds.

---

## Clip 2: the real rail (target 2:00, ceiling 2:30)

Terminal on screen. Say first:

> Now the same loop with one real customer on Razorpay test mode. Nothing is
> mocked here except the customer's reply.

Type:
```powershell
uv run encore seed-live --n 1 --seed 103
```
It prints one link titled **FAIL THIS ONE** and the operator instructions.
`--seed 103` gives a customer name no earlier take used, so the board and
the Payments API stay unambiguous.

Click the printed URL. In checkout: contact `9123456789`, **Cards**, number
`4100 2800 0008 0001`, expiry `12/30`, CVV `123`, any name, Pay. If a mock
bank page appears, click **Failure**. "Payment failed" shows. Close the tab.

Say while doing it:

> This is the original debit. Razorpay's documented insufficient-funds test
> card. The customer had no money.

Type:
```powershell
uv run encore agent --live 1 --batch 50 --speed 6 --window-s 600
```
First line: `Payments API: 1 mapped failure(s), 0 unmapped, in the last 10 min.`

> The failure was found through Razorpay's Payments API with a reason code,
> and correlated to the customer by the notes the original link carried. No
> webhook. Fifty simulated failures start alongside it.

Open a new browser tab at `file:///C:/dev/encore/runs/board.html`. The live
customer's row is first; its rail reads `razorpay_test_mode`.

Within about 40 seconds the terminal prints:

```
  LINK for cust_XXXX INR 999.00: https://rzp.io/...  (plink_...)  pay by HH:MM:SS
```

> The agent nudged, the policy picked an hour inside the 22:00 to 07:00
> window, the wall allowed it, and it created a real Payment Link. That page
> says PAY THIS ONE. The first one said FAIL THIS ONE. In rehearsal two I
> paid the wrong one, and the agent learned to notice that too. Entry
> fifteen in the broke-log.

Click the link. Contact `9123456789`, **Netbanking**, bank **BOB**, Pay,
mock bank page, **Success**. "Payment successful" shows. Switch to the board
tab. Within 5 to 8 seconds the row reads `recovered`, status `paid`, and the
Recovered card moves by ₹999.

> That row is a real Razorpay payment id. The other fifty are the simulator.
> Same wall, same ledger, same audit log.

Let the terminal print its summary (`at risk`, `recovered`, `attempts`,
`parked:`) and stop the recording there.

Why: Build quality and the track bar's "measured money recovered", with the
real rail proving the integration is not a mock.

**If it goes wrong.** If the LINK line has not appeared after 60 seconds,
keep talking through the board; the batch is working. Do not restart: a
restart with the same ledger executes nothing new, by design. If the take
fails, let the summary print, delete the three run files (pre-flight step
8), use the next `--seed` (104, 105, ...) and go again. `--window-s 600`
limits detection to the last 10 minutes; the Payments API returned newest
first in every listing recorded in `docs/spike-notes.md`, so a retake inside
10 minutes still picks the fresh failure, but waiting 10 minutes removes all
doubt. If two takes fail, show `docs/evidence/board-2026-09-02-live.html`
and the transcript beside it, and say on camera that it is the recorded take
from 2 September.

---

## Clip 3: the wall, the control, what broke, close (target 1:40)

### Beat 4a, 0:00 to 0:25. Screen: terminal, then `wall.py` on GitHub.

Type:
```powershell
uv run pytest tests/test_wall.py -q
```
`24 passed`. Switch to the `wall.py` tab; all 55 lines fit on one screen.

> The wall is a pure function. No I/O, no clock, no randomness, no model, by
> project rule. Killed beats hard-decline beats retry-cap beats cooldown
> beats window; twenty-four adversarial tests pin that order. The policy
> proposes, the wall disposes, and the language model never touches it.

Why: Build quality and AI judgment. Showing the file beats showing test
names; a judge can read 55 lines.

### Beat 4b, 0:25 to 1:05. Screen: the site's cliff chart, then the README table.

Switch to the site tab at `#method`. Hover day 23, then day 25.

> We trained a timing model first. Then we built the control that could kill
> it: same candidate hours, same cooldown, hour drawn at random. On the
> held-out regime the model puts its retries on days 21 to 24, two days
> before payday, and the coin lands past the cliff. Random beat our model by
> 46 percent, so the model does not ship.

Switch to the README tab, the four `r1_shifted` rows.

> Industry standard T+1, 2, 3: fifty-two thousand rupees per thousand
> failures. Our model: one lakh fifty. The random control: two lakh
> eighteen. What ships is random plus the customer's own promise: two lakh
> thirty, four point four times the industry schedule, zero violations in all
> 32 cells. The promise is worth about five percent, and we report the three
> percent noise floor next to it.

Why: AI judgment. The criterion says an LLM forced where a rule works is
marked down; this is the section that shows you refuted your own model on
purpose.

### Beat 5, 1:05 to 1:30. Screen: `BROKELOG.md` on GitHub, scrolling slowly.

> Sixteen entries, append-only, each written before its fix with the commit
> that closed it. The instrument was wrong four times. The platform did not
> match its docs once. Our prediction of a fix was off by ten times. The
> human in the loop broke the live demo twice. And the one AI component had
> never actually run, because its own fallback was hiding the failure. That
> is entry sixteen.

Why: Failure recovery, the field Razorpay reads first.

### Beat 6, 1:30 to 1:40. Screen: the board from clip 2, or the take-3 evidence board.

> The one place a model belongs here is reading the customer, and we
> measured it: keywords 27 of 40, Sonnet 5 40 of 40. Everywhere the money
> moves, it is arithmetic. That is Encore.

Why: the AI-judgment line spoken out loud. It is scored, and the repo earns it.

---

## Edit, upload, submit

1. Clipchamp: New video, import the three MP4s from `Videos\Screen
   Recordings`, place them on the timeline in order 1, 2, 3, trim dead air at
   the clip edges, no transitions, no music. Export 1080p.
2. Watch it once at normal speed. Total under 5:00, voice audible over the
   keyboard, terminal URLs readable.
3. YouTube: upload, visibility **Unlisted**, title "Encore: a recovery agent
   for failed UPI AutoPay debits (Razorpay AI Buildathon)", description with
   the repo URL, the site URL and chapter timestamps (0:00 problem, 0:20 the
   loop, 1:20 real rail, 3:20 wall and control, 4:25 what broke). Open the
   link in an incognito window to confirm it plays.
4. Form: video URL, repo URL `https://github.com/ranvir7123/Encore`, the
   "what it solves" paragraph and the essay from
   `docs/submission-checklist.md`. Fill in the checklist's video-link TODO if
   there is time.
