# Rasd — project rules and agreed decisions

Rasd is a hackathon project (Elm hackathon for the Guests of Allah, Jeddah,
22–24 December 2026) by a team of four students. A hotel counter employee at a
Hajj service company sends a pilgrim's report as a voice message; the system
turns it into a report with a type, a room, an owner and a deadline. This code
is the base of a live demo: it must be reliable, simple to explain, and easy
for students to maintain.

## Where the work stands

Phase 1, steps 1 to 3 are done and unit-tested, and the step 4 benchmark covers
everything in its list below. Built: `data/reports.csv` (35 fictional reports),
`data/expected.csv`, `rasd/understand.py` (understanding function and prompt),
`rasd/numbers.py` (dialect number parser), `rasd/incidents.py` (duplicate
merging), `rasd/scoring.py`, `rasd/cost.py`, `benchmark.py`, and the empty
holdout folder `data/holdout/`.

**Measured on 25 November 2026** with the real key (full reports in
`comparison/`, and the table in `README.md`):

- `claude-haiku-5-5`: all fields right on 30 of 35; 1 confident mistake (an
  urgency, not a place); 0 wrong places that were not sent to the supervisor;
  spoken room numbers 11 of 13; grouping 32 of 35; about $0.009 per run.
- `claude-sonnet-5-5`: 35 of 35 on everything; about $0.13 per run.
- Haiku varies between runs: three runs the same day gave 32, 30 and 30 of 35.
- Haiku reads the Palestinian word for twelve ("طنعش") as another number
  (reports 2 and 14). Our parser reads it correctly, so both were flagged.
- Haiku does not copy Arabic-Indic digits as written into `number_words`
  (report 21), so that correct report is flagged needlessly.

**The larger-model comparison has been run (once, 25 November 2026). Do not run
it again** unless the owner says so in the chat. `benchmark.py --compare`
refuses while `comparison/answers.json` exists.

**The prompt has not been tuned** since the first real run: the owner has not
asked for it. Two fixes were proposed and are waiting for the owner's decision:
a table of dialect words for 11 to 19 in the prompt, and accepting a number
whose digits appear in the message even when the quote does not match.

The owner has not written the holdout reports yet, so they have no results, and
the larger model was not measured on them.

Next: the owner's decisions above, then step 5 (speech to text) when the owner
says so. Do not start Phase 2 until Phase 1 works and the owner says so.

Confirmed by the owner on 25 November 2026:

- Confidence has two levels, `high` and `low`.
- A room, elevator or floor without its number counts as "location missing" and
  goes to the supervisor.
- A report the system could not understand (API down, refusal, no answer) goes
  to the supervisor as `unclear` and `urgent`.
- No refusal fallback to another model: a refusal becomes a flagged report.

Choices that the owner has not confirmed yet:

- The number parser covers Arabic only. A number spoken in Urdu words cannot be
  re-read, so that report is flagged.
- Merging window: 60 minutes, counted from the incident's latest message
  (`MERGE_WINDOW_MINUTES` in `rasd/incidents.py`).
- A report that needs supervisor confirmation for any reason never merges, and
  nothing merges into it. A common area never merges (we do not know which one).
- An incident is as urgent as its most urgent message.
- The benchmark never prints the text of holdout reports, only their numbers
  with expected and actual values.
- The benchmark's `--model` option was replaced by `--compare MODEL`, which runs
  both models on the same reports and saves the record in `comparison/`.
- The benchmark waits and retries up to 6 times when the API says slow down
  (the live system keeps 2).

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

## Hard rules

- **Cost.** The Claude credit is $100 prepaid. Print the approximate API cost
  after every benchmark run. Stop if any single run costs more than $1.
- **Larger-model comparison: run it once only.** It was run on 25 November 2026.
- **Holdout.** `data/holdout/reports.csv` and `data/holdout/expected.csv` are
  written by the owner. Never open, print, search or copy them, including
  through git (`diff`, `show`, `log -p`), and never load them in unit tests.
  Only `benchmark.py` reads them, when it runs. Report their results
  separately from the 35 main reports. Never use what a holdout run shows to
  add examples to the prompt.
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
  type, location (kind and number), urgency, owner, confidence. The model reads
  the message; owner and deadline come from the tables in `rasd/routing.py`.
  Reports are flagged "needs supervisor confirmation" when confidence is low,
  the location is missing, or the type is unclear. If the API fails or refuses,
  return a flagged report instead of crashing.
- **Spoken room numbers:** the room is the field that breaks the demo. Staff
  say numbers in dialect words; the engine must convert them to digits. Planned
  safeguard: the model also quotes the exact words it read the number from, and
  our own code re-reads that quote with a small dialect number parser; if the
  two disagree or the quote cannot be checked, the report is flagged. Report
  room accuracy for the `room_in_words` reports separately.
- **How step 2 calls Claude:** SDK `anthropic` 2.x,
  `client.messages.parse(output_format=Reading)` with `effort` set to `medium`
  and thinking left on its default. Tests use the real SDK with only the network
  replaced (`httpx2.MockTransport`), so they need no key and cost nothing.
  Unit tests use made-up messages and room numbers, never the benchmark's.
- **Urgency rule:** written in `README.md`; it is a first judgement that the
  team may change.
- **Duplicate merging** (step 3): same type, same place, within a configurable
  window becomes one incident with a message count. No location or unclear type
  never merges.
- **Benchmark** (step 4): one command. Accuracy per field, Arabic (30) and Urdu
  (5) shown separately, every wrong report listed with expected and actual,
  duplicate-grouping score, measured cost and time. An empty cell in
  `expected.csv` means the field is not scored; `-` means no number expected.
  The report leads with the confident mistakes: reports that are wrong and were
  not sent to the supervisor, with wrong places counted on their own. The owner
  called this the number that matters most for the demo. The main reports and
  the holdout reports are scored in separate sections. Everyday output goes to
  `results/` (git-ignored); the one-time comparison is kept in `comparison/`.
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
