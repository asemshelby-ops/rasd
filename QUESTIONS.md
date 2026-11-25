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


31. **The corner label is shown in Arabic**: «نموذج أولي: ربط واتساب للأعمال
    بانتظار الموافقة». The owner wrote it in English; every interface is Arabic.
32. **A reporting page belongs to one hotel's counter.** A message that names no
    hotel is taken to be about that hotel. This is how "the same reporting
    hotel" is known when two lost-pilgrim reports are merged.
33. **Lost-pilgrim merge**: same hotel, within 15 minutes of the case's latest
    report (`LOST_PILGRIM_WINDOW_MINUTES`), even when one of the reports is
    waiting for the supervisor, because the pilgrim's own note has no room. Never
    into a closed case, and a report with no hotel never merges. Known cost: two
    different pilgrims lost at the same counter within 15 minutes become one
    case. The case shows its report count, so a supervisor can see it.
34. **The mock card.** The reader refuses any card that is not visibly marked
    SPECIMEN / «نموذج تجريبي». This is the one place a photo is analysed and a
    visa number reaches the model; the card is fictional and its number is
    invented (it starts with 999000). The card photo and the pilgrim photo are
    not stored. The card copies no real card: no emblem, no logo.
35. **The Elm lookup** is one small interface (`ElmDirectory.lookup(name,
    visa_number)`). `SimulatedElm` answers from `data/simulated_elm.json`. It is
    also served on its own address (`/simulated-elm/lookup`), and every answer
    says `simulated`.
36. **Board states**: waiting for the supervisor, with the owner, past its
    time, closed. Critical first in each column. "One tap" to close: the
    supervisor types a name once, the browser remembers it, and each close is
    logged with that name and the time. Closing without a name is refused.
37. **Voice.** There is no speech-to-text key and no real recording. The two
    saved voice notes are placeholder tones with their words in
    `demo/scene/transcripts.json`. The live path (`OpenAITranscriber`) is
    written and has never run. The team must record the two notes.
38. **A hotel glued to a short word was dropped silently** (found while
    building the before-and-after page; `superpowers:systematic-debugging`).
    Cause in one line: the message wrote «بدار المنارة», the model returned the
    bare name «دار المنارة», and our word-for-word check did not find it in the
    message, so the hotel was dropped with no flag. Fix: a name (hotel or
    pilgrim) also counts when a short word (و ف ب ل ك) is glued to its front,
    and the hotel table recognises a known hotel behind such a word. Verified
    with unit tests and by reading the message again with the real model.
39. **The "after" side of the before-and-after page is not written by hand.**
    It is Rasd's real reading of the invented group (`python -m
    app.before_after`, nine calls).
40. **Elm view**: the other companies' rows are invented, with fixed times
    left. The mockup screen writes «مثال» beside every number.
41. **Accessibility review of the board** (`design:accessibility-review`).
    All text and border colours pass (lowest text ratio 7.6 to 1). Fixed: the
    whole board was announced to screen readers on every refresh (now only a
    new case or a moved case is announced); keyboard focus was lost, or the
    board froze, while a button had focus (focus now stays on the same button
    across refreshes); the focus ring did not show on the dark top bar; type
    was too small for a hall (all sizes now scale with the screen, and two
    buttons scale them further). Accepted and not changed: the board updates by
    itself with no pause control, because a live board must.
42. **Photos are made smaller on the phone before they are sent** (longest
    side 1600 pixels): a phone photo is too large for a hotspot and for the
    card reader.
43. **The replacement request is filled in and shown, not sent.** The page says
    so. Passport and visa numbers appear only as "held, not shown here".
44. **Live check of the scene**: all six steps passed with the real small model
    (two voice-note readings, the card, the simulated lookup, the notification,
    the close). A reading took 2.3 to 3.1 seconds and the card 1.5 to 1.9
    seconds. The first of two runs was repeated because of a mistake in the
    check script, not in Rasd.
45. **In the scene the place reads «برج السكينة، مرفق عام»**: the model takes
    "at the reception" as a common area. Left as it is.

## Stage 4

46. **The replay switch is the `/operator` page**, with two modes. In replay
    the scene is answered wholly from saved files: the words of the two voice
    notes, the model's reading of them as recorded from the real model on
    25 November 2026 (`python -m demo.record_scene`), and the card reading. No
    network. A case that came from saved files says «من تسجيل محفوظ» on the
    board, and the board shows a banner while replay is on, because nothing
    saved may pass for live.
47. **The operator page and the reporting page work with no script**: plain
    forms. This is the answer to "old phone browser".
48. **Nothing protects `/operator` but the hotspot password.** Clearing the
    board needs a tick box.
49. **Voice-to-board time**: 2.39 to 3.16 seconds in three runs, measured on
    the laptop itself. Live speech-to-text was NOT part of it (no key), nor the
    upload from a phone. About five seconds of the 8-second target are left
    for those two. The board now asks for news every second (it was two).
50. **The pages give a reading 12 seconds and one retry** (the benchmark keeps
    30 seconds and more retries): in front of an audience a stuck call is worse
    than a failed one, and a failed reading goes to the supervisor.
51. **Https on the hotspot** uses a certificate the laptop makes itself
    (`python -m demo.run`). Phones show a warning once. It was checked here
    with a browser on the same machine, not with a real phone on a hotspot.
52. **A saved voice note uses its saved words first** (changed in stage 6
    after the review): it is known by its bytes, so no speech-to-text call is
    made for it, and the placeholder tones play the scene with or without a
    key. The timing tool therefore never measures live speech to text.
53. **Upload limits are my choice**: 4 MB for a photo (after the phone has made
    it smaller), 15 MB for a voice note.
54. **Roles on the scenario card**: the judge plays the counter employee and
    reads the exact Arabic sentence; a teammate plays the pilgrim; a teammate
    plays the supervisor. The owner may cast it differently.
55. **Live-demo risks** are listed in `DEMO.md` with what is automated and what
    must be tried by hand (`engineering:testing-strategy`). Not automatable
    here: a real microphone in a noisy room, real phone browsers, the hotspot,
    live speech-to-text.
56. **An unexpected failure of the reader no longer shows an error page**: the
    message is kept and goes to the supervisor. Found by writing the
    bad-network test first.

## Stage 5

57. **The counting tool is its own folder** (`whatsapp_count/`), standard
    library only. It imports nothing from the rest of the project, because
    `rasd/` loads the AI library.
58. **"Inside the repository" means inside this project's folder.** The hotels
    list and the marked hand-check file are refused there too. What the tool
    writes goes next to the export. `.gitignore` also ignores exports and the
    files made from them, as a second guard.
59. **What "looks like a report" means**: a strong word alone ("خربان", "ضاع",
    "مريض"), or a topic word ("الشنط", "الوجبات") together with a cue that
    something is missing or needed ("ما", "وين", "يحتاج"). The lists are at the
    top of `whatsapp_count/rules.py`. It is a rough net; the hand check
    measures it.
60. **A closing reply is given to the latest open report before it, within 24
    hours** (`--window-hours`). An export does not say which message a reply
    answers. Known limit: "لقيناها" can land on the wrong report.
61. **"Room named" means a room with its number.** A floor is not a room.
62. **"Hotel named"**: by a word such as «فندق» or «برج», or by the team's own
    list of names (`--hotels`).
63. **Dates**: when the file cannot tell day-first from month-first, day first
    is assumed and the report says so. Hijri dates are converted by the
    tabular rule, so a span across a month's end can be a day off.
64. **The hand-check file holds message text**, because the owner must read a
    message to judge it. It has no sender names, long numbers are masked, and
    the tool's own answer is not shown so that it cannot sway the marks. It is
    the only output that is not an aggregate, and it never leaves the folder of
    the export.
65. **Photos are counted and never read.** A caption after a media line is read
    as text.
66. **The tool was tested only on fake exports I wrote** (Android and iPhone
    styles, both digit styles). No real export was available, by design.

## Stage 6

`superpowers:requesting-code-review` ran on the whole project (a separate
reviewer that was told not to open the holdout folder and not to call any API).
It found 3 critical and 13 important issues. What I did with them:

67. **Fixed, critical: one slow reading froze the whole site**, the board and
    the replay switch included. The page handlers are now plain functions, so
    each request runs on its own. A test with a real server and a slow reader
    guards it.
68. **Fixed, critical: with no key, or an engine that could not start, a
    report got an error page and was not saved.** It is now saved and goes to
    the supervisor. The operator's "saved scene" check now really builds the
    replay engine.
69. **Fixed, critical: three privacy holes.** (a) The sending page's hotel is
    taken only from the team's list. (b) A number in an ask-back reply is a
    room only when the reply is the number alone or names the place; passport
    and phone numbers are taken out of the reply first. (c) The redaction now
    also hides numbers written with spaces or dashes, after "جواز السفر" or
    "رقمه", with letters mixed in, and mobile numbers written in groups.
70. **Fixed: a hotel the model gives that is not in the message** now sends the
    report to the supervisor (new reason `hotel_not_confirmed`), like a room
    number that cannot be confirmed. A hotel name that is not in the team's
    list is not written on the board; the board says «فندق غير مسجّل في القائمة».
71. **Fixed: ask-back took "ما اعرف اسمه" as a name.** A reply that says the
    sender does not know, or will answer later, changes nothing.
72. **Fixed: the card step** is accepted only for an open lost-pilgrim case;
    the hidden card button is really hidden; the button says «صوّر البطاقة
    التجريبية».
73. **New: a supervisor page (`/supervisor`)** shows each waiting report with
    why it waits and its words, numbers hidden. Before this a report "sent to
    the supervisor" could not be read by anyone. It is not for the big screen
    and, like `/operator`, has no password.
74. **Fixed: a lost-card report the supervisor confirms** now gets its 24-hour
    clock, counted from the report.
75. **Fixed: two lost pilgrims at one counter** stay two cases when their
    reports give different names or different rooms.
76. **Fixed: the number on the board label is the number the sender was told.**
    The words of a message that is not a report are no longer kept.
77. **Fixed: the sending page on a bad network**: a "send again" button that
    sends the same message, an error with no text still says something, a
    browser without `fetch` falls back to the plain form, and a recording is
    named after what the phone really recorded.
78. **Fixed: messages over 2,000 characters are not sent to the model** (cost
    and time); they go to the supervisor. Failures are now written to the
    console by their kind, never with message text.
79. **Fixed in the WhatsApp tool**: a line with an impossible date is left out
    and counted instead of being glued to the message above (which put a
    sender's name into text); the tool stops when most dates cannot be read;
    Hijri dates with an era mark; "برجع" is no longer a hotel; a bare 3 or
    4 digit number is a room; "ما شاء الله" is no longer a cue; the hand-check
    file cannot hold a spreadsheet formula, masks grouped phone numbers and
    passport-like numbers, and is read back in either encoding and with
    commas or semicolons.
80. **Not fixed, and why.**
    - A waiting case that is past its time stays in the "waiting" column; its
      clock does say «تأخرت». Moving it would hide that it still needs the
      supervisor. The team should decide.
    - On the no-script page a question from Rasd is shown but cannot be
      answered there; the supervisor follows it up.
    - A hotel name misspelt by one letter (as speech-to-text may do) is an
      unlisted hotel: it is not merged with the right one. No fuzzy matching
      was added, because a wrong guess of the hotel is worse.
    - The scene's words still live in three files (`demo/scene.py`,
      `transcripts.json`, `saved_readings.json`). Tests and the operator check
      now catch a mismatch, and the guide names the one place to edit.
    - "لقينا الحاج التايه" is counted as a new report by the WhatsApp tool,
      not as a closing reply.
    - `rasd.db` holds message text and the private numbers unencrypted on the
      laptop (it is never committed). Delete it after the demo.
    - Smaller notes left as they are: `requirements.txt` is not pinned to exact
      versions; `python -m demo.run` is the supported way to start the site.
81. **Final benchmark** (one run, after the fixes): 0 confident mistakes, all
    fields right on 57 of 58, saved in `measurements/stage6_final_benchmark.txt`.

## After the morning report (owner's decisions, 26 November 2026)

The owner decided three open points. They are no longer provisional:

- A late report that waits for the supervisor moves to the overdue column.
- A hotel name with a small transcription error is matched only against the
  company's own hotel list, never corrected silently; the sender is asked with
  one tap: "Did you mean <hotel>?".
- A simple PIN on the operator page and the supervisor page.

Choices I made while building them:

82. **The overdue card still says it waits for the supervisor** and keeps its
    confirm button; it stays on the supervisor page until confirmed.
83. **"Nearly" means at least 0.8 alike** (`NEAR_HOTEL_LIKENESS` in
    `rasd/routing.py`) and near exactly one hotel of the list. Until the sender
    taps, the report waits for the supervisor and the board does not print the
    name as written. "نعم" takes the hotel of the list; "لا" keeps the name as
    written and asks nothing more; any other reply changes nothing.
84. **This question comes before the other ask-back questions**, since a
    report has one question only.
85. **After "نعم" the duplicate check runs again** (owner's decision, 26
    November 2026). If the usual merge rules put the report into another open
    case of that hotel, it moves there with its events and private numbers and
    its own card is removed. The window is counted from when the report was
    sent, not from the tap. The owner then set the rule: any answer that fills
    in the hotel, the room, the floor or the type runs the check again; a reply
    with only a name does not. My one choice left: it runs only for a report
    that is still a case of its own.
86. **The PIN** is read from `RASD_PIN` in `.env`. When it is not set a random
    4-digit PIN is made at every start and printed in the laptop's terminal.
    Five wrong tries shut the door for one minute. It is entered once per
    phone after each start. The board and the sending page need no PIN. The
    value "off" turns it off, for the tests only.
87. **Speech to text**: `python -m demo.check_speech FILE` tries the live
    service on one recording. The request and its errors are tested with the
    network replaced; the live service itself has still never been called.

## Design pass (owner's design brief, 26 November 2026)

The brief was followed as written: the colour tokens, IBM Plex Sans Arabic
only, the sizes, the critical band and three columns, the header with three
counts, the corner replay label, the merge stamp with one pulse, the phone page
as a messaging app. Choices I made where the brief was silent:

88. **The font files are in the project** (`app/static/fonts/`, SIL Open Font
    License, licence file beside them), so the pages look the same with no
    internet. `sans-serif` is listed after it only as the browser's last resort.
89. **The name that signs board actions is written once on the operator
    page** and kept on the laptop, because the name box left the board. One name
    signs for whoever stands at the board until it is changed. A name sent with
    an action still wins. Without a saved name the board's buttons refuse and
    say where to write it.
90. **The board keeps its three action buttons** (acknowledge, confirm, close)
    on each card, small, under the countdowns: the scene closes a case with one
    tap on the board.
91. **The type size is a setting on the operator page** (70% to 200%, 100% is
    the brief's sizes: title 30px, place 22px, countdown 40px, column title
    24px). Cards in the critical band are larger: 40px and 52px.
92. **Open critical cases are always in the band**, also when overdue or
    waiting for the supervisor; a tag on the card says which. A closed critical
    case goes to the closed column.
93. **The language of a report is told from its letters** (`rasd.text.
    language_of`): Arabic, Urdu or English. It is stored per report and only its
    name is shown. A case shows each language once.
94. **The stamp stays on a merged card**; only the pulse (one second, once) is
    the animation. With reduced motion there is no pulse.
95. **Overdue takes no priority colour**, because each colour has one meaning:
    an overdue clock turns dark and says «تأخرت».
96. **The thick priority border is on the start side of every card** (the
    right, in Arabic), with logical CSS. The owner corrected the brief: "left"
    was a mistake.
97. **The label «المدد قيم تجريبية» stays on the board** as a small corner
    label, because unmeasured numbers must be labelled.
98. **Accessibility review of the new screens** (`design:accessibility-review`).
    Every text pair passes: text on background 14.7, on cards 16.6, muted 6.3
    and 7.1, white on critical 6.5, on medium 5.8, on normal 5.8, on green 6.3.
    One limit: white on the urgent colour is 4.2 to 1, which passes only for
    large bold text, so a priority badge is never under 20px bold. The line
    colour is 1.2 to 1 against the background, so it is decoration only: every
    button and field has a dark border. Focus is a 4px dark ring. Nothing on the
    phone page is under 16px (measured in a browser). At 200% zoom the board
    does not scroll sideways. Not checked: a real screen reader.
99. **Screenshots** before and after are in `screenshots/design/`, taken in
    replay mode (no API calls).

**The owner approved 88 to 99 on review**, with three changes, all built: the
border on the start side (96); one critical case spans the band and two or more
share the row equally; on the phone page the record button is the only main
action, the text box is the second option, and the three attachments are
behind one small "+". The owner then decided: the "+" is always closed by
default; when the mock-card step becomes possible one highlighted suggestion
button appears above the text box and opens the camera directly, and it hides
again after the card is read.

