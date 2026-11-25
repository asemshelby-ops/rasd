# Rasd — project rules and agreed decisions

Rasd is a hackathon project (Elm hackathon for the Guests of Allah, Jeddah,
22–24 December 2026) by a team of four students. A hotel counter employee at a
Hajj service company sends a pilgrim's report as a voice message; the system
turns it into a report with a type, a room, an owner and a deadline. This code
is the base of a live demo: it must be reliable, simple to explain, and easy
for students to maintain.

## Where the work stands (after the overnight run of 25 to 26 November 2026)

The owner set a six-stage overnight run. **All six stages are done.** Read
these before changing anything:

- `MORNING_REPORT.md` (Arabic): the report to the owner, with what is needed from them.
- `PROGRESS.md`: what each stage did, test counts, measurements, API spending.
- `QUESTIONS.md`: the 81 choices made without the owner, numbered. The owner
  has not yet confirmed them. Treat them as provisional.
- `DEMO.md` (Arabic): demo-day guide. `WHATSAPP_COUNT.md` (Arabic): the counting tool.

What exists (847 tests, `python -m pytest`, no key and no network needed):

- `rasd/`: the rules. The model READS a message (`understand.py`); the team's
  tables DECIDE owner, priority and deadlines (`routing.py`); our code CHECKS
  every quote of the model against the message. Also: number parser, privacy
  (`privacy.py` hides passport, visa and phone numbers before the model),
  ask-back (one question per report), duplicate merging and closing
  (`incidents.py`), case rules, simulated Elm lookup, voice behind one
  interface, mock card reader.
- `app/`: the demo pages (FastAPI, one SQLite file, plain HTML, no build
  step): reporting page, board, supervisor page, lost-card flow, Elm view,
  before-and-after page, operator page (replay switch), scenario card.
- `demo/`: the scene's words and files, the hotspot start helper
  (`python -m demo.run`), the voice-to-board timer, the scene recorder.
- `whatsapp_count/`: a separate, strictly local tool (standard library only).
- `benchmark.py`, `data/` (58 main messages), `measurements/`, `comparison/`.

**Final measurement** (25 November 2026, 12:30 UTC, one run of `python benchmark.py` on
`claude-haiku-5-5`, 58 messages, saved in
`measurements/stage6_final_benchmark.txt`): wrong and not sent to the
supervisor 0 of 58; wrong and sent to the supervisor 1 (report 15); needless
referrals 0; all fields right 57 of 58; spoken room numbers 15 of 15;
non-reports recognised 6 of 6; real reports dropped 0; right question asked 6
of 6; grouping 52 of 52; about $0.029 per run. Earlier runs of the night are in
`PROGRESS.md`. The measurements of 25 November (42 and 35 reports) are kept in
`README.md` and `comparison/` and are not comparable.

**Voice-to-board time**: 2.39 to 3.16 seconds in three runs on one machine,
target under 8. Live speech to text and the upload from a phone were NOT part
of it.

**Not real yet. Say so whenever results are reported:**

- Speech to text has never run: `RASD_OPENAI_KEY` is not set and no real
  recording exists. The two saved voice notes are placeholder tones with their
  words written down. The live transcriber is written and untested.
- Nothing was tried on a real phone, a real hotspot or a real microphone.
- The holdout reports do not exist yet, so there is no holdout result.
- The larger model has not been run with the current prompt.
- The WhatsApp tool was tested only on fake exports.
- The Elm lookup, the notifications and the Elm view are simulated and
  labelled so on screen. Deadlines are trial values.

**Larger model.** The owner plans to use the larger model for the demo.
`DEFAULT_MODEL` stays `claude-haiku-5-5` until the holdout comparison has run
(owner's decision). The comparison on the main reports ran once and is not
repeated. The owner approved one more: `python benchmark.py --compare-holdout
claude-sonnet-5-5`, both models on the holdout reports only. It refuses to run
while there are no holdout reports, and refuses a second run. Run it once, when
the owner says the holdout files are in.

Next, when the owner says so: their answers to `MORNING_REPORT.md`, the holdout
comparison when the files exist, real voice recordings and the speech-to-text
key, then a rehearsal on the real laptop and phones.

Confirmed by the owner on 25 November 2026 (before the run):

- Confidence has two levels, `high` and `low`.
- A room, elevator or floor without its number counts as "location missing" and
  goes to the supervisor.
- A report the system could not understand (API down, refusal, no answer) goes
  to the supervisor as `unclear` and `urgent`.
- No refusal fallback to another model: a refusal becomes a flagged report.
- The number parser covers Arabic only. A number spoken in Urdu words goes to
  the supervisor, for now.
- Merging: the window is 60 minutes, counted from the incident's latest message.
  A report that needs supervisor confirmation never merges and nothing merges
  into it. A common area never merges. An incident is as urgent as its most
  urgent message. A new report about a closed incident opens a new one.
- The benchmark never prints the text of holdout reports; `--compare MODEL`
  replaced `--model`; the benchmark retries up to 6 times when the API says
  slow down.
- The prompt lists the dialect words for 11 to 19, and a room number whose
  exact digits are written in the message is confirmed.
- Priority comes from the team's tables, not from the model. **This is a team
  decision based on the pilgrim's journey. It is not tuning to the test.**

Set by the owner in the overnight instructions (25 November 2026):

- A sixth risk, immediate physical danger (`danger`). A partial fault is one
  level below its default, only when the message says so.
- Critical: acknowledge in 5 minutes, close in 30 (trial values). New types
  are owned by pilgrim affairs; `unclear` is urgent; the stage is Makkah days.
- The hotel is its own field. Types: gifts or distributions, no Nusuk card at
  all, forgot app password or passport number, and "not a report".
- The big screen shows only the first letter of a name and the report number,
  never a photo. Passport and visa numbers never reach the model, a log or the
  big screen.
- Ask-back: at most one short Arabic question per report; the reply completes
  the same report.
- A chat reply such as "found it" never closes anything. A case closes only
  through Rasd's close action, with a time stamp and who closed it.
- Lost pilgrim: two reports from the same hotel within 15 minutes are one case.
- No real pilgrim data and no real Nusuk card, ever. Simulated parts are
  labelled on screen.

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
  `routing.priority_for` works it out in four steps. (1) The type's default,
  from the team-editable `PRIORITY_BY_TYPE`. (2) The journey stage, which the
  ops room sets by hand (`CURRENT_STAGE`): during the Hajj days a lost Nusuk
  card is critical. (3) A fault the message says is partial goes one level
  down. (4) Each risk the message states explicitly raises it one level, up to
  critical: elderly, sick, medication, a time limit, a pilgrim alone or lost,
  immediate physical danger. The model reports each risk with the words of the
  message that state it, and our code checks those words are in the message.
  The benchmark always scores with `data.EXPECTED_STAGE`, not the live stage.
- **Checks on what the model returns**: a room number is re-read by our parser;
  a hotel or a name must be in the message (a short word glued to its front is
  allowed: "بدار المنارة"); a mismatch sends the report to the supervisor.
- **Duplicate merging** (step 3): same type, same hotel and place, within a
  configurable window becomes one incident with a message count. A lost pilgrim
  has no room: same hotel within 15 minutes, unless the reports give different
  names or rooms. No location or unclear type
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

## The demo pages (built in the overnight run)

- Run for phones on a hotspot: `python -m demo.run` (https with a certificate
  made on the laptop, because phone browsers record only on a secure
  connection). Plain run: `python -m uvicorn app.main:app`.
- Page handlers are plain `def` functions on purpose: each request runs on its
  own thread, so a slow reading never blocks the board or the replay switch.
  Do not make them `async` again.
- What the big screen may show is decided in one place, `Store.board` in
  `app/store.py`: no full name, no number, no words of a message, no photo, no
  hotel name that is not in the team's list. The supervisor page
  (`/supervisor`) is the only page that shows message text.
- Every Arabic sentence of the pages is in `app/copy.py`.
- The scene's words have one source, `demo/scene.py`. After changing them run
  `python -m demo.make_scene_assets`, `python -m demo.record_scene` (three
  paid calls) and the tests.
- `/operator` and `/supervisor` have no password: the hotspot password is the
  only protection.
- `whatsapp_count/` must stay standard-library only and import nothing from
  the project. Two tests fail if it loads a network library.

Not built: correcting the room on the phone before the report reaches the
board, status updates back to the sender, closing by uploading a photo, a QR
code for the phone page, a button for the journey stage.
