# Overnight run: progress

Read this file first when a session resumes. Continue from the first stage that
is not marked DONE. Never redo a finished stage.

Ground rules for the run (from the owner): no questions (choices go in
`QUESTIONS.md`), commit and push after every stage, small model only
(`claude-haiku-5-5`), no larger model, no holdout comparison, never open or
list the report files in `data/holdout` (only `data/holdout/README.md` may be
edited), no real pilgrim data, no new paid services, at most 3 benchmark runs at
each stage marked "measure", and at most 3 US dollars of API usage in total.

## API spending tonight (cap: 3.00 dollars)

| What | Dollars |
|---|---|
| Stage 1: three benchmark runs | 0.0575 |
| Stage 1: two checks of report 22 (6 and 8 single calls) | 0.0081 |
| Stage 2: three benchmark runs | 0.0887 |
| Stage 2: check of seven reports (28 single calls) | 0.0151 |
| Stage 3: before-and-after page read twice (9 calls each) | 0.0090 |
| Stage 3: one call to find the cause of the dropped hotel | 0.0005 |
| Stage 3: live check of the scene, twice (3 calls each) | 0.0028 |
| Stage 4: recording the scene's readings (3 calls) | 0.0016 |
| Stage 4: voice-to-board measurement, three runs (6 calls) | 0.0038 |
| Stage 4: one browser check that ran live by mistake (4 calls) | 0.0019 |
| Stage 6: one final benchmark run | 0.0292 |
| **Total for the night** | **0.2182** |

## Stages

| Stage | What | State |
|---|---|---|
| 1 | Priority and number fixes; measure | DONE |
| 2 | Real field style (items 1 to 11); measure | DONE |
| 3 | The demo scene: reporting page, board, lost-card flow, Elm view, before-and-after page | DONE |
| 4 | Demo safety: voice-to-board time, replay switch, Windows steps, scenario card, risk tests | DONE |
| 5 | Local WhatsApp counting tool | DONE |
| 6 | Code review, final benchmark, MORNING_REPORT.md | DONE |

## Stage notes

(Each finished stage adds: what was done, test count, benchmark lines, next stage.)

### Stage 1: DONE

- Sixth risk `danger`; partial faults go one level down (only when the message
  says so, words checked); critical = acknowledge in 5 minutes and close in 30,
  both trial values; hundreds table in the prompt, generated from
  `rasd/numbers.py`; `data/holdout/README.md` rewritten (report files not opened).
- Expected answers recomputed from the table: reports 8, 9, 10, 22 critical
  (danger), reports 29, 30 medium (partial).
- Tests: 396 passed.
- Measure (3 runs, `python benchmark.py --repeat 3`, saved in
  `measurements/stage1_benchmark.txt`):
  - all fields right in each run: 40 of 42, 41 of 42, 41 of 42
  - confident mistakes in each run: 0, 0, 0
  - reports whose priority changed between runs: 0 of 42
  - reports whose type changed: 0 of 42; place: 1 of 42 (report 15); supervisor
    flag: 2 of 42 (reports 22 and 33)
- After the measure: report 22 was flagged needlessly because the model joins
  two parts of the message into one risk quote. The check now accepts words in
  order; verified with 8 single calls (0 flagged). No fourth benchmark run.
- Next: stage 2.

### Stage 2: DONE

- Hotel as its own field; required fields per type; three new types and
  `not_a_report`; pilgrim's name with a first-letter screen label; photo flag;
  checklists; one-question ask-back whose reply completes the same report;
  passport and visa numbers hidden before the model; closing only through
  `close_incident` with time and name; 10 real-style reports and 6 non-reports.
- New modules: `rasd/privacy.py`, `rasd/askback.py`, `rasd/display.py`.
- Tests: 536 passed.
- Measure (3 runs, saved in `measurements/stage2_benchmark.txt`), 58 messages:
  - all fields right in each run: 54 of 58, 50 of 58, 54 of 58
  - confident mistakes in each run: 1, 1, 1 (report 46, its hotel)
  - non-reports recognised: 6 of 6 each run; real reports dropped: 0
  - right question asked: 6 of 6 each run; needless questions: 0
  - spoken room numbers: 15 of 15 each run
  - priority changed between runs: 0 of 58; type: 0; place: 2; flag: 6
- After the measure: hotel recognised by the distinctive part of its name;
  confidence rule clarified. Checked with 28 single calls, no fourth run.
- Next: stage 3.

### Stage 3: DONE

- Pages (`app/`): chat-style reporting page with the prototype label; board
  with four states, critical first, countdowns, acknowledge / confirm / close
  with a name and a time; lost-card flow with a pre-filled replacement request
  and a 24-hour clock; Elm view with a fixed simulated-data banner; one static
  mockup screen; before-and-after page.
- Scene rules (`rasd/`): lost-pilgrim merge (same hotel, 15 minutes),
  reporting hotel, replacement request, simulated Elm lookup, voice behind one
  interface, mock card reader that refuses unmarked cards.
- Scene files (`demo/scene/`): mock card, two PLACEHOLDER voice notes (tones)
  with their words. No speech-to-text key, no real recordings.
- Found and fixed: a hotel glued to a short word («بدار المنارة») was dropped
  silently (QUESTIONS.md 38).
- Skills: `design:ux-copy` for the wording (`app/copy.py`),
  `design:accessibility-review` on the board (QUESTIONS.md 41),
  `superpowers:systematic-debugging` for the dropped hotel. `frontend-design`
  is not available in this session; the owner said to continue without it.
- Tests: 658 passed.
- Live check with the real small model: the whole scene passed (two voice
  notes merged into one critical case "بلاغان، حالة واحدة", card read,
  simulated lookup, notification, close logged). No benchmark run in this
  stage (it is not a "measure" stage).
- Next: stage 4.

### Stage 4: DONE

- Voice-to-board time (`python -m demo.measure_time`, saved in
  `measurements/stage4_voice_to_board.txt`), three runs with the real small
  model: 2.99, 2.39 and 3.16 seconds; target under 8. Live speech-to-text was
  not part of it (no key); the report says so.
- Replay switch: `/operator`, plain forms, works from a phone. Replay mode
  answers the scene from saved files with no network; saved cases are labelled
  on the board.
- Hotspot: `python -m demo.run` serves https with a certificate made on the
  laptop and prints the addresses. Windows steps in Arabic in `DEMO.md`.
- Scenario card: `/scenario-card`, one printed A4 sheet, exact sentences.
- Risks (`engineering:testing-strategy`): listed in `DEMO.md`; automated in
  `tests/test_demo_safety.py` and `tests/test_demo_tools.py` (same-second
  reports, twelve phones at once, restart, failed reading, failed card reader,
  noise, double tap, upload limits, no-script form).
- Tests: 705 passed.
- Next: stage 5.

### Stage 5: DONE

- `whatsapp_count/`: reads a WhatsApp text export (Android and iPhone lines,
  both digit styles, 12 and 24 hour time, day-first, month-first, year-first
  and Hijri dates, a .zip from an iPhone), flags report-like messages by word
  rules, checks hotel and room, pairs closing replies, prints aggregates in
  Arabic, and has a hand-check mode with an agreement rate.
- Strictly local: two tests fail if a network library or the AI library is
  imported (one runs the tool and looks at what was loaded, one reads every
  import in its source). It refuses a file inside the repository.
- Guide in Arabic: `WHATSAPP_COUNT.md` (WhatsApp export steps and Windows).
- No API calls in this stage.
- Tests: 783 passed.
- Next: stage 6.

### Stage 6: DONE

- Code review of the whole project (`superpowers:requesting-code-review`):
  3 critical and 13 important findings. Fixed and tested: see QUESTIONS.md 67
  to 79. Not fixed, with reasons: QUESTIONS.md 80.
- Tests: 847 passed.
- Final benchmark, one run (`measurements/stage6_final_benchmark.txt`), 58
  messages:
  - wrong and not sent to the supervisor (confident mistakes): 0 of 58
  - wrong and sent to the supervisor: 1 (report 15, place kind)
  - needless referrals: 0
  - all fields right: 57 of 58
  - spoken room numbers: 15 of 15; non-reports recognised: 6 of 6; real
    reports dropped: 0; right question asked: 6 of 6
  - duplicate grouping: 52 of 52 reports in their right incident
  - cost: 0.0292 dollars
- `MORNING_REPORT.md` written (Arabic). `CLAUDE.md` brought up to date.
- All six stages are done. Nothing is left to continue.
