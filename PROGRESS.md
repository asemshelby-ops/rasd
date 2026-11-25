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
| **Total so far** | **0.1694** |

## Stages

| Stage | What | State |
|---|---|---|
| 1 | Priority and number fixes; measure | DONE |
| 2 | Real field style (items 1 to 11); measure | DONE |
| 3 | The demo scene: reporting page, board, lost-card flow, Elm view, before-and-after page | NEXT |
| 4 | Demo safety: voice-to-board time, replay switch, Windows steps, scenario card, risk tests | not started |
| 5 | Local WhatsApp counting tool | not started |
| 6 | Code review, final benchmark, MORNING_REPORT.md | not started |

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
