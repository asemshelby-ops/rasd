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

14. **The hotel list is four invented names** (`HOTELS` in `rasd/routing.py`,
    marked as sample data). They are the tap-buttons of "which hotel?". Replace
    them with the company's hotels.
15. **A hotel is not required when a room is given.** You said a hotel without a
    room is valid for a Nusuk card and that faults need a room or a floor; you
    did not say every report needs a hotel. The 42 older test reports name no
    hotel, and requiring one would send all of them to the supervisor.
16. **What each type needs** (`REQUIRED_BY_TYPE`): faults and cleaning need a room,
    floor or named common area; Nusuk card, no card, forgotten password, luggage
    and gifts need a hotel or place, and also "who": the pilgrim's name or a
    numbered room or floor; a lost pilgrim and a health case need a hotel or
    place. A named common area (a lobby) still counts as a place for a fault.
17. **Codes and priorities of the new types**: `no_nusuk_card` is urgent and
    critical during the Hajj days, like a lost card; `forgot_credentials` is
    medium; `not_a_report` goes to the owner `nobody` and has no priority.
18. **A hotel or a pilgrim's name is kept only when its words are in the message.**
    Otherwise it is dropped, so an invented name can never reach a report.
19. **A photo with no words** is an unclear report: the sender is asked what the
    problem is, and the model is not called.
20. **Checklists for the other types are mine** (yours is used word for word for
    the Nusuk card). They are in `CHECKLISTS` and in the README.
21. **Ask-back asks in this order**: what the problem is, then the room or floor,
    then the hotel, then the pilgrim's name. One question per report, ever. A
    typed reply to "what is the problem?" that is not one of the buttons leaves
    the report with the supervisor; replies are read by plain code, not the model.
22. **What counts as a sensitive number**: a number after a passport or visa word
    (Arabic, English, Urdu); one or two letters followed by 6 to 9 digits; and
    any number of 9 digits or more, which also hides phone numbers. Room numbers
    are never touched. The real values come back from `privacy.redact()` for a
    separate store; the report itself only records that they were given.
23. **A "not a report" answer with low confidence is not trusted**: the message
    goes to the supervisor as unclear. Dropping a real report is the worst case.
24. **Closing an incident twice is an error**, and closing needs a name.
25. **The 10 real-style reports and 6 non-reports are in the main set** (reports
    43 to 58; 58 messages in all). Names, hotels, passport and visa numbers are
    invented.
26. **Two reports with a hotel and no room never merge**: two lost cards in one
    hotel are two pilgrims.
27. **Stage 2 measurement found one confident mistake, three runs out of three**
    (report 46): the hotel "نزل الياسمين" came back as "الياسمين". Cause: the
    prompt tells the model to leave out the word for "hotel", and "نزل" means
    lodging, so the model dropped it; our hotel table only knew full names. The
    table now recognises a hotel by the part of its name no other hotel shares.
28. **Needless referrals rose in stage 2** (1 to 5 per run): with the new hotel
    and name fields the model began to answer "low confidence" for clear
    messages that simply give no hotel or name. The prompt now says an empty
    field is not a reason for low confidence.
29. **Both fixes came after the three measurement runs** and were checked with
    single calls on the affected reports (hotel right 8 of 8; no needless flag
    in 20 of 20), not with a fourth run.
30. **The benchmark prints a multi-line message on one line** and with its
    passport and visa numbers hidden.

## Stage 3

