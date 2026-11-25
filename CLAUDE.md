# Rasd — project rules and agreed decisions

Rasd is a hackathon project (Elm hackathon for the Guests of Allah, Jeddah,
22–24 December 2026) by a team of four students. A hotel counter employee at a
Hajj service company sends a pilgrim's report as a voice message; the system
turns it into a report with a type, a room, an owner and a deadline. This code
is the base of a live demo: it must be reliable, simple to explain, and easy
for students to maintain.

## Overnight run of 25 to 26 November 2026

The owner set a six-stage overnight run. **`PROGRESS.md` says which stages are
done and what comes next; read it first.** `QUESTIONS.md` lists the choices made
without the owner. The notes below this section describe the state before that
run and are updated in its last stage.

## Where the work stands

Phase 1, steps 1 to 3 are done and unit-tested, and the step 4 benchmark covers
everything in its list below. Built: `data/reports.csv` (42 fictional reports),
`data/expected.csv`, `rasd/understand.py` (understanding function and prompt),
`rasd/numbers.py` (dialect number parser), `rasd/routing.py` (the team's owner
and priority tables), `rasd/incidents.py` (duplicate merging),
`rasd/scoring.py`, `rasd/cost.py`, `benchmark.py`, and the holdout folder
`data/holdout/`.

**Priority is no longer judged by the model** (owner's decision, 25 November
2026, after a field review). It comes from tables in `rasd/routing.py`: a
default per type, changed by the journey stage, raised one level for every risk
the message states. See "Agreed design". **This is a team decision based on the
pilgrim's journey. It is not tuning to the test.** The expected answers were
recomputed from the table: each row of `data/expected.csv` lists the risks its
message states, and a unit test checks that the expected priority is exactly
what the table gives for that type and those risks.

Seven reports (36 to 42) were added for the three new types, because the data
tests require every type to be covered. They need the team's dialect review
like the first 35.

**Current measurement** (25 November 2026, `python benchmark.py --repeat 3` on
`claude-haiku-5-5`, 42 reports): all fields right on 41, 39 and 39 of 42;
confident mistakes 0, 0 and 1, never a place; priority right on 41, 41 and 40 of
41; one report (10) changed priority between the runs; spoken room numbers 13,
13 and 14 of 14; grouping 42 of 42 each time; about $0.016 per run.

**Open question for the owner: pilgrims trapped in an elevator.** The one
confident mistake was report 10 (Urdu, pilgrims stuck in an elevator): in one
run Haiku filed them under the risk `alone_or_lost`, which raised urgent to
critical. Cause, found by measuring: that danger has no entry in the team's list
of five risks, and `alone_or_lost` is the nearest one; the quoted words really
are in the message, so our check passes. It happened in 4 of 66 calls on report
10 and in 0 of 24 on the two Arabic wordings (reports 8 and 9). A narrower
wording of that risk in the prompt was tried and made it worse (9 of 12), so it
was not kept. Nothing was changed. The team decides whether trapped pilgrims
should raise the priority.

Other things the owner was told and has not decided:

- Priority follows the type only, so a partial fault (report 29, an AC that
  drips but cools; report 30, some corridor bulbs) is "urgent" like a full
  outage, and sparks with a burning smell (report 22) stay "urgent".
- Haiku misread the dialect word for 600 ("ستمية") in new report 40, in two of
  three runs; our parser disagreed, so it was flagged. A table of hundreds in
  the prompt, like the one for 11 to 19, was proposed and not built.
- Defaults I chose that the team may change in `rasd/routing.py`: the three new
  types are owned by `pilgrim_affairs`; `unclear` is `urgent`; the sample
  deadline for `critical` is 5 minutes; `CURRENT_STAGE` is `makkah`.
- A risk whose quoted words are not found in the message still counts (the
  higher priority is the safe side) and the report goes to the supervisor.
- The guide inside `data/holdout/` predates the priority change and was not
  edited, because the owner said not to open that folder. The current rules for
  writing holdout reports are in the main `README.md`.

**Older measurements** (35 reports, the model still judging priority; kept in
`README.md` and `comparison/` for the record): the one-time comparison gave
Haiku 30 of 35 and `claude-sonnet-5-5` 35 of 35; after the two number fixes
Haiku gave 35, 32 and 35 of 35. They are not comparable with the current
measurement.

**Larger model.** The owner plans to use the larger model for the demo.
`DEFAULT_MODEL` stays `claude-haiku-5-5` until the holdout comparison has run
(owner's decision). The larger model has not been run with the current prompt.
The comparison on the main reports ran once and is not repeated. The owner
approved one more: `python benchmark.py --compare-holdout claude-sonnet-5-5`,
both models on the holdout reports only. The command is built and tested
offline. It refuses to run while there are no holdout reports, and refuses a
second run. Run it once, when the owner says the holdout files are in.

The owner's teammates will write the holdout reports. None existed on
25 November 2026.

Next: the holdout comparison when the files exist, the owner's answers above,
then step 5 (speech to text) when the owner says so. Do not start Phase 2 until
Phase 1 works and the owner says so.

Confirmed by the owner on 25 November 2026:

- Confidence has two levels, `high` and `low`.
- A room, elevator or floor without its number counts as "location missing" and
  goes to the supervisor.
- A report the system could not understand (API down, refusal, no answer) goes
  to the supervisor as `unclear` and `urgent`.
- No refusal fallback to another model: a refusal becomes a flagged report.
- The number parser covers Arabic only. A number spoken in Urdu words goes to
  the supervisor, for now.
- Merging: the window is 60 minutes, counted from the incident's latest message
  (`MERGE_WINDOW_MINUTES` in `rasd/incidents.py`). A report that needs supervisor
  confirmation never merges and nothing merges into it. A common area never
  merges. An incident is as urgent as its most urgent message.
- A new report about an incident that is already closed opens a new incident
  (`Incident.closed_at`). Nothing closes an incident until Phase 2.
- The benchmark never prints the text of holdout reports; `--compare MODEL`
  replaced `--model`; the benchmark retries up to 6 times when the API says
  slow down (the live system keeps 2).
- The prompt lists the dialect words for 11 to 19, and a room number whose
  exact digits are written in the message is confirmed.
- Priority: the four levels, the per-type table, the journey stage and the five
  risks, as written in "Agreed design".

## How to work

- Build in order, and test each step before the next. Write the failing test first.
- The owner works in checkpoints: finish the step asked for, push, report, stop.
- Push to `main` of `asemshelby-ops/rasd`.
- Chat is in English. The final summary of the whole task must be in Arabic
  only, with no English words in the prose, covering: what works, what does
  not, the accuracy results exactly as printed, how to run it, what is needed
  from the owner.
- Do not edit the test reports or expected answers to make results look better.
  Do not put test report text or its room numbers into the prompt as examples.

## Skills plan (set by the owner on 25 November 2026, for the whole project)

- `superpowers:test-driven-development` for any new logic that decides a
  report's room, type, owner or incident: the failing test first, then the code.
- `superpowers:verification-before-completion` before reporting any result:
  show only output that was actually seen printed.
- If a confident mistake appears, `superpowers:systematic-debugging` to find the
  real cause before changing anything, and explain the cause to the owner in
  one line.
- When Phase 1 is finished, `engineering:testing-strategy` to list what must be
  tested before a live demo in front of judges: noisy rooms, a bad network, an
  old phone browser, two reports at the same second.
- In Phase 2, `frontend-design` for the phone page and the big board (Arabic,
  right to left, readable from the back of a hall, looking like a real
  operations tool), then `design:ux-copy` for every button, status and error
  message, then `design:accessibility-review` on the big board.
- Before the owner hands the code to teammates,
  `superpowers:requesting-code-review`, and fix what it finds.
- If a skill is not available in the session, tell the owner which one and
  continue without it. On 25 November 2026 `frontend-design` was not available;
  the others were. The owner then said: continue Phase 2 without it.

## Hard rules

- **Cost.** The Claude credit is $100 prepaid. Print the approximate API cost
  after every benchmark run. Stop if any single run costs more than $1.
- **Larger-model comparison: run it once only.** It was run on the 35 main
  reports on 25 November 2026. The owner approved exactly one more: both models
  on the holdout set only (`--compare-holdout`), and not before the holdout
  files exist.
- **Holdout.** The folder `data/holdout/` belongs to the owner and teammates,
  who write its reports and expected answers. Do not open the folder: never
  list, open, print, search, copy or edit anything in it, including through git
  (`diff`, `show`, `log -p`), and never load it in unit tests. Only
  `benchmark.py` reads it, when it runs. Report its results separately from the
  main reports. Never use what a holdout run shows to add examples to the
  prompt.
- **Secrets.** Never ask for a key in chat and never commit one. The Claude key
  is read from the environment variable `RASD_CLAUDE_KEY` (set in the cloud
  environment; on laptops it goes in the git-ignored `.env`). Pass it to the
  client explicitly. The OpenAI key is read from `RASD_OPENAI_KEY`; in a cloud
  session it is entered through the secure credential form for
  `api.openai.com`, which does not work for Anthropic's own hosts.
- **Data.** No real pilgrim data, no real names.
- **Numbers.** No invented numbers in any interface. Anything not measured is
  labelled as sample data (the deadline minutes in `rasd/routing.py` are sample).
- **Language.** All interfaces and the benchmark's printed report are in
  Arabic, right to left. Developer error messages stay in simple English,
  because Windows terminals render Arabic badly; the benchmark also saves its
  report to a text file for that reason.
- Write a short run guide in Arabic (`README.md`), kept up to date.

## Agreed design

- **Stack:** Python for everything. Phase 2 uses FastAPI, one SQLite file and
  plain HTML pages, with no build step.
- **Model:** `claude-haiku-5-5` by default (`DEFAULT_MODEL` in
  `rasd/understand.py`). `python benchmark.py --compare MODEL` is the single
  comparison run with one larger current model (`claude-sonnet-5-5` was used):
  both models read the same reports and the accuracy and cost gap is printed
  next to Haiku. Use structured output so the reply always parses.
- **Understanding function** (step 2): input is the report text; output is
  type, location (kind and number), priority, owner, confidence. The model reads
  the message; owner, priority and deadline come from the tables in
  `rasd/routing.py`.
  Reports are flagged "needs supervisor confirmation" when confidence is low,
  the location is missing, or the type is unclear. If the API fails or refuses,
  return a flagged report instead of crashing.
- **Spoken room numbers:** the room is the field that breaks the demo. Staff
  say numbers in dialect words; the engine must convert them to digits. Planned
  safeguard: the model also quotes the exact words it read the number from, and
  our own code re-reads that quote with a small dialect number parser; if the
  two disagree or the quote cannot be checked, the report is flagged. A number
  whose exact digits are written in the message is confirmed without the quote.
  Report room accuracy for the `room_in_words` reports separately.
- **How step 2 calls Claude:** SDK `anthropic` 2.x,
  `client.messages.parse(output_format=Reading)` with `effort` set to `medium`
  and thinking left on its default. Tests use the real SDK with only the network
  replaced (`httpx2.MockTransport`), so they need no key and cost nothing.
  Unit tests use made-up messages and room numbers, never the benchmark's.
- **Priority** (the field and CSV column are named `urgency`): the model is not
  asked for it. Four levels: `critical`, `urgent`, `medium`, `normal`.
  `routing.priority_for` works it out in three steps. (1) The type's default,
  from the team-editable `PRIORITY_BY_TYPE`: lost pilgrim or one who cannot
  communicate, and sick pilgrim or stated health risk, are critical; lost Nusuk
  card, AC or water outage, electricity or elevator fault are urgent; luggage
  is medium; cleaning and gifts not received are normal. (2) The journey stage,
  which the ops room sets by hand (`CURRENT_STAGE`: arrival, makkah, hajj,
  departure): during the Hajj days a lost Nusuk card is critical, because the
  card is needed to enter the holy sites and the transport. (3) Each risk the
  message states explicitly raises it one level, up to critical: elderly, sick,
  medication, a time limit such as a group moving soon, a pilgrim alone or
  lost. The model reports each risk with the words of the message that state
  it, and our code checks those words are in the message. The benchmark always
  scores with `data.EXPECTED_STAGE`, not with the live stage.
- **Duplicate merging** (step 3): same type, same place, within a configurable
  window becomes one incident with a message count. No location or unclear type
  never merges. A closed incident takes no more reports. `add_report` places one
  report as it arrives (for the live system); `group_reports` does a whole list
  (for the benchmark).
- **Benchmark** (step 4): one command. Accuracy per field, Arabic (36) and Urdu
  (6) shown separately, every wrong report listed with expected and actual,
  duplicate-grouping score, measured cost and time. An empty cell in
  `expected.csv` means the field is not scored; `-` means no number expected.
  The report leads with the confident mistakes: reports that are wrong and were
  not sent to the supervisor, with wrong places counted on their own. The owner
  called this the number that matters most for the demo. The main reports and
  the holdout reports are scored in separate sections. `--repeat N` runs N
  times and prints what changed between the runs (priority, type, place, flag).
  Everyday output goes to `results/` (git-ignored); the comparisons that run
  once are kept in `comparison/`.
- **Speech to text** (step 5): Claude takes no audio. Use OpenAI
  `gpt-4o-transcribe` (approved, pay-as-you-go, $0.006 per minute) and keep
  free local Whisper as an offline fallback. The benchmark runs both on the
  same recordings and compares them. Recordings go in `data/audio/`, named by
  report number (`07.m4a`, or `07_a.m4a` for a second speaker). The team will
  record 50 voice messages. No real recordings exist yet, so any synthetic
  audio test only proves the plumbing, not accuracy.

## Phase 2 notes (not started)

- Phone page opened by QR code: record button, text box as fallback.
- After sending, the phone shows the transcript and the extracted room, with a
  one-tap way to correct the room before the report reaches the board.
- Big screen: New, Routed, Escalated, Closed columns, with a countdown each.
- The sender gets a reference number; status updates on the phone on closing.
- A report is closed by uploading a photo from a phone.
- Everything runs on one laptop over a phone hotspot. No WhatsApp dependency.
- Phone browsers only allow microphone recording on a secure connection, so
  plain HTTP over the hotspot will not work for the record button; plan for it.
