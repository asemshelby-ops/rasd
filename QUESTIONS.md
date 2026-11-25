# Decisions made during the overnight run

The owner was asleep. Each entry is a choice the instructions did not cover:
what was chosen, why, and how to change it.

## About the run itself

1. **The first message arrived cut off** at stage 2, item 7. I started stage 1
   and did not invent later stages. The two continuation messages arrived while
   stage 1 was in progress, so nothing was built on a guess.
2. **`PROGRESS.md` and this file are in English**, like the chat and the code
   comments. The team guide (`README.md`) and the morning report are in Arabic.
3. **The speech-to-text key (`RASD_OPENAI_KEY`) is not set** in this
   environment. As instructed, the voice path is built against an interface and
   tested with saved audio or text.

## Stage 1

4. **The sixth risk has the code `danger`** (Arabic label "خطر جسدي مباشر"). The
   people trapped in the elevator (reports 8, 9, 10) and the sparks with a
   burning smell (report 22) now expect "critical".
5. **"Partial" applies only to faults** (`ac`, `water`, `power_elevator`), because
   the instruction speaks of a fault. For any other type it is ignored. Change
   `FAULT_TYPES` in `rasd/routing.py`.
6. **Partial words that are not found in the message do not lower the priority,
   and the report goes to the supervisor.** Lowering on words nobody said would
   be a guess; the default priority is the safe side.
7. **The prompt's own examples of a partial fault are different from yours** (a
   dripping tap, one socket of several). Yours match test reports 29 and 30, and
   the project rule forbids putting test report content in the prompt.
8. **Critical closes in 30 minutes while urgent still closes in 15**, the older
   trial value. It looks odd, but every one of these minutes is a trial value
   and you only gave me the critical ones, so I left the others alone.
9. **Only critical reports have the acknowledge step.**
10. **The hundreds are shown to the model with the usual spelling** ("ستمية"), and
    the prompt says the last letter may also be written "ه". Our own tables keep
    the normalised spelling.
11. **A risk or partial quote may now come from two parts of the message.** In the
    stage 1 measurement, report 22 was sent to the supervisor needlessly in two
    of three runs: the model joined "sparks from the socket" and "a burning
    smell" into one quote, and our check wanted one continuous piece. The check
    now accepts a quote when all its words appear in the message in the same
    order. The room-number quote still has to be one continuous piece.
12. **That fix came after the three measurement runs.** I did not use a fourth
    run (the limit is three per stage). I checked the original symptom instead:
    report 22 sent 8 times, sent to the supervisor 0 times.
13. **The holdout guide already describes the stage 2 columns** (`hotel`, `name`,
    `photo`, `ask`), because stage 1 asked for the real report style in it. It
    is checked again at the end of stage 2.

## Stage 2

