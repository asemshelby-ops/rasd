"""Scores the engine's answers against the expected answers and writes the Arabic report.

Nothing in this file calls the AI model. benchmark.py does the calls and hands
the answers to render() and render_comparison().
"""

from dataclasses import dataclass

from rasd.cost import MAX_RUN_COST_USD, cost_usd
from rasd.data import NO_NUMBER, Expected, SampleReport
from rasd.incidents import MERGE_WINDOW_MINUTES, group_reports
from rasd.schema import FLAG_REASONS, LOCATION_KINDS, OWNERS, TYPES, URGENCIES
from rasd.understand import Understanding

# The scored fields, in the order they are printed, with their Arabic names.
FIELDS = {
    "type": "النوع",
    "loc_kind": "نوع المكان",
    "loc_number": "رقم المكان",
    "urgency": "الأولوية",
    "owner": "الجهة المسؤولة",
    "needs_confirmation": "الإحالة لتأكيد المشرف",
}
# What the engine understood from the message. The supervisor flag is scored
# too, but it is a decision about these fields, not one of them.
CONTENT_FIELDS = ("type", "loc_kind", "loc_number", "urgency", "owner")
PLACE_FIELDS = ("loc_kind", "loc_number")

# The groups each accuracy is shown for.
LANGUAGE_GROUPS = {
    "الكل": lambda report: True,
    "العربية": lambda report: report.lang.startswith("ar"),
    "الأردو": lambda report: report.lang == "ur",
}

# What happened to a report that is not fully right.
CONFIDENT_MISTAKE = "خطأ واثق"  # wrong, and nobody was asked to check it
CAUGHT_MISTAKE = "أُحيل للمشرف"  # wrong, but the supervisor was asked to check it
NEEDLESS_REFERRAL = "إحالة بلا داعٍ"  # understood correctly, but sent to the supervisor anyway

MAIN_TITLE = "======== القسم الأول: البلاغات الأساسية (كتبها المساعد الآلي) ========"
HOLDOUT_TITLE = "======== القسم الثاني: البلاغات المحجوبة (كتبها مالك المشروع) ========"

RIGHT_TO_LEFT = "‏"  # invisible mark that makes a line display right to left


@dataclass
class Run:
    """One model's answers for one set of reports, and how long they took."""

    model: str
    results: dict[int, Understanding]  # report id -> the engine's answer
    seconds: float
    stopped_at_cost_limit: bool

    @property
    def input_tokens(self) -> int:
        return sum(answer.input_tokens for answer in self.results.values())

    @property
    def output_tokens(self) -> int:
        return sum(answer.output_tokens for answer in self.results.values())

    @property
    def cost(self) -> float:
        """Approximate cost of this run in US dollars."""
        return cost_usd(self.model, self.input_tokens, self.output_tokens)


@dataclass
class Holdout:
    """The owner's own test reports: their expected answers and the run on them."""

    run: Run
    reports: list[SampleReport]
    expected: dict[int, Expected]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score(expected: Expected, actual: Understanding) -> dict[str, bool | None]:
    """Compares one answer with the expected one, field by field.

    True = right, False = wrong, None = this field is not scored for this report
    (its cell in expected.csv is empty).
    """
    location_is_scored = expected.loc_kind is not None
    expected_number = None if expected.loc_number == NO_NUMBER else expected.loc_number
    return {
        "type": actual.type == expected.type,
        "loc_kind": actual.loc_kind == expected.loc_kind if location_is_scored else None,
        "loc_number": actual.loc_number == expected_number if location_is_scored else None,
        "urgency": actual.urgency == expected.urgency if expected.urgency is not None else None,
        "owner": actual.owner == expected.owner,
        "needs_confirmation": (
            actual.needs_confirmation == expected.needs_confirmation
            if expected.needs_confirmation is not None
            else None
        ),
    }


def outcome(marks: dict[str, bool | None], actual: Understanding) -> str | None:
    """What happened to one report: None when it is fully right, otherwise one of the three labels.

    The dangerous one is the confident mistake: something is wrong and the
    report went straight to a worker without the supervisor seeing it.
    """
    if all(mark is not False for mark in marks.values()):
        return None
    if not actual.needs_confirmation:
        return CONFIDENT_MISTAKE
    if any(marks[field] is False for field in CONTENT_FIELDS):
        return CAUGHT_MISTAKE
    return NEEDLESS_REFERRAL


@dataclass
class Grouping:
    """The incidents the expected table lists, next to the ones the engine made.

    Each incident is a sorted list of report ids.
    """

    expected: list[list[int]]
    produced: list[list[int]]

    @property
    def well_placed(self) -> int:
        """How many reports are in an incident with exactly the right members."""
        return sum(len(incident) for incident in self.produced if incident in self.expected)

    @property
    def repeated(self) -> list[list[int]]:
        """The expected incidents that have more than one report."""
        return [incident for incident in self.expected if len(incident) > 1]

    @property
    def collected(self) -> list[list[int]]:
        """The repeated incidents that the engine put together exactly."""
        return [incident for incident in self.repeated if incident in self.produced]

    @property
    def split(self) -> list[tuple[list[int], list[list[int]]]]:
        """Expected incidents whose reports ended up apart: (the incident, its pieces)."""
        result = []
        for incident in self.expected:
            pieces = [sorted(set(made) & set(incident)) for made in self.produced if set(made) & set(incident)]
            if len(pieces) > 1:
                result.append((incident, pieces))
        return result

    @property
    def mixed(self) -> list[list[int]]:
        """Incidents the engine made out of reports that belong to different incidents."""
        return [made for made in self.produced if not any(set(made) <= set(incident) for incident in self.expected)]


@dataclass
class Tally:
    """One run scored against its expected answers."""

    run: Run
    reports: list[SampleReport]  # every report of the set
    done: list[SampleReport]  # the ones the run got to
    expected: dict[int, Expected]
    scores: dict[int, dict[str, bool | None]]  # report id -> field -> mark
    outcomes: dict[int, str | None]  # report id -> None when fully right, else a label

    def marks(self, field: str) -> dict[int, bool | None]:
        return {report_id: marks[field] for report_id, marks in self.scores.items()}

    @property
    def all_right(self) -> dict[int, bool]:
        return {report_id: label is None for report_id, label in self.outcomes.items()}

    def with_outcome(self, label: str) -> list[SampleReport]:
        return [r for r in self.done if self.outcomes[r.id] == label]

    @property
    def confident_wrong_places(self) -> list[SampleReport]:
        """Confident mistakes where the place itself is wrong: a worker goes to the wrong door."""
        return [
            r
            for r in self.with_outcome(CONFIDENT_MISTAKE)
            if any(self.scores[r.id][field] is False for field in PLACE_FIELDS)
        ]

    @property
    def spoken_rooms(self) -> list[SampleReport]:
        """The reports that say the room number in words."""
        return [r for r in self.done if self.expected[r.id].room_in_words]

    @property
    def wrong_spoken_rooms(self) -> list[SampleReport]:
        def place(report):
            answer = self.run.results[report.id]
            return (answer.loc_kind, answer.loc_number)

        return [r for r in self.spoken_rooms if place(r) != ("room", self.expected[r.id].loc_number)]

    @property
    def grouping(self) -> Grouping | None:
        """None when the incident column is not filled in for every report."""
        wanted = {}
        for r in self.done:
            incident = self.expected[r.id].incident
            if incident is None:
                return None
            wanted.setdefault(incident, []).append(r.id)
        made = group_reports([(r.id, r.sent_at, self.run.results[r.id]) for r in self.done])
        return Grouping(
            expected=[sorted(ids) for ids in wanted.values()],
            produced=[sorted(incident.report_ids) for incident in made],
        )


def tally(run: Run, reports: list[SampleReport], expected: dict[int, Expected]) -> Tally:
    done = [r for r in reports if r.id in run.results]
    scores = {r.id: score(expected[r.id], run.results[r.id]) for r in done}
    outcomes = {r.id: outcome(scores[r.id], run.results[r.id]) for r in done}
    return Tally(run=run, reports=reports, done=done, expected=expected, scores=scores, outcomes=outcomes)


# ---------------------------------------------------------------------------
# Arabic text
# ---------------------------------------------------------------------------


def _shown(field: str, value) -> str:
    """The Arabic text for one value of a field."""
    if field == "needs_confirmation":
        return "نعم" if value else "لا"
    if field == "loc_number":
        return value if value and value != NO_NUMBER else "بلا رقم"
    labels = {"type": TYPES, "loc_kind": LOCATION_KINDS, "urgency": URGENCIES, "owner": OWNERS}[field]
    return labels[value]


def _fraction(right: int, total: int) -> str:
    if total == 0:
        return "لا يوجد"
    return f"{right} من {total} ({round(100 * right / total)}%)"


def _language(report: SampleReport) -> str:
    return "الأردو" if report.lang == "ur" else "العربية"


def _ids(ids) -> str:
    return "، ".join(str(report_id) for report_id in ids)


def _right_and_total(reports, marks: dict[int, bool | None], belongs=LANGUAGE_GROUPS["الكل"]) -> tuple[int, int]:
    """How many of the scored marks are right, among the reports of one language group."""
    scored = [marks[r.id] for r in reports if belongs(r) and marks[r.id] is not None]
    return sum(scored), len(scored)


def _accuracy_line(name: str, reports, marks: dict[int, bool | None]) -> str:
    """One line such as: النوع: الكل 33 من 35 (94%) | العربية ... | الأردو ..."""
    parts = [
        f"{group} {_fraction(*_right_and_total(reports, marks, belongs))}"
        for group, belongs in LANGUAGE_GROUPS.items()
    ]
    return f"{name}: " + " | ".join(parts)


def _right_to_left(lines: list[str]) -> str:
    return "\n".join(RIGHT_TO_LEFT + line if line else line for line in lines) + "\n"


def _stopped_warning(t: Tally) -> list[str]:
    if not t.run.stopped_at_cost_limit:
        return []
    return [
        f"تنبيه: توقف الاختبار لأن التكلفة تجاوزت الحد ({MAX_RUN_COST_USD:.2f} دولار). "
        f"النتائج لعدد {len(t.done)} من {len(t.reports)} بلاغاً فقط."
    ]


def _confident_lines(t: Tally) -> list[str]:
    confident = t.with_outcome(CONFIDENT_MISTAKE)
    lines = [
        "== الأخطاء الواثقة: خطأ لم يُحَل للمشرف ==",
        f"بلاغات فيها خطأ ولم تُحَل للمشرف: {len(confident)} من {len(t.done)}",
    ]
    if confident:
        lines.append(f"  - أرقامها: {_ids(r.id for r in confident)}")
    lines += [
        f"منها بمكان خاطئ (نوعه أو رقمه): {len(t.confident_wrong_places)}",
        f"بلاغات فيها خطأ وأُحيلت للمشرف: {len(t.with_outcome(CAUGHT_MISTAKE))}",
        f"إحالات للمشرف بلا داعٍ (البلاغ مفهوم صحيحاً): {len(t.with_outcome(NEEDLESS_REFERRAL))}",
    ]
    return lines


def _accuracy_lines(t: Tally) -> list[str]:
    lines = ["== الدقة حسب الحقل =="]
    for field, name in FIELDS.items():
        lines.append(_accuracy_line(name, t.done, t.marks(field)))
    lines.append(_accuracy_line("كل الحقول معاً", t.done, t.all_right))
    return lines


def _spoken_room_lines(t: Tally) -> list[str]:
    """The room number is the field that breaks the demo, so spoken numbers get their own count."""
    spoken, wrong = t.spoken_rooms, t.wrong_spoken_rooms
    caught = [r for r in wrong if t.run.results[r.id].needs_confirmation]
    return [
        "== أرقام الغرف المنطوقة بالكلمات ==",
        f"رقم الغرفة صحيح: {_fraction(len(spoken) - len(wrong), len(spoken))}",
        f"رقم خاطئ ونُبّه المشرف عليه: {len(caught)}",
        f"رقم خاطئ ولم يُنبَّه عليه: {len(wrong) - len(caught)}",
    ]


def _wrong_report_lines(t: Tally, show_text: bool) -> list[str]:
    """Every report that is not fully right, with the expected and the actual value of each wrong field.

    show_text=False leaves out the words of the message (for the holdout reports).
    """
    wrong = [r for r in t.done if t.outcomes[r.id] is not None]
    lines = [f"== البلاغات الخاطئة: {len(wrong)} =="]
    for r in wrong:
        actual, wanted = t.run.results[r.id], t.expected[r.id]
        header = f"البلاغ {r.id} ({_language(r)}، {t.outcomes[r.id]}):"
        lines.append(f"{header} {r.text}" if show_text else header)
        for field, name in FIELDS.items():
            if t.scores[r.id][field] is not False:
                continue
            line = f"  - {name}: المتوقع «{_shown(field, getattr(wanted, field))}»، الناتج «{_shown(field, getattr(actual, field))}»"
            if field == "loc_number" and actual.number_words and show_text:
                line += f" (قرأه النموذج من: «{actual.number_words}»)"
            if field == "needs_confirmation" and actual.reasons:
                line += " (السبب: " + "، ".join(FLAG_REASONS[reason] for reason in actual.reasons) + ")"
            lines.append(line)
    return lines


def _grouping_lines(t: Tally) -> list[str]:
    lines = [
        "== تجميع البلاغات المكررة ==",
        f"نافذة الدمج: {MERGE_WINDOW_MINUTES} دقيقة بعد آخر بلاغ عن الحادثة (اجتهاد أولي يعدّله الفريق)",
    ]
    grouping = t.grouping
    if grouping is None:
        return lines + ["لم يُحتسب: العمود incident في جدول الإجابات المتوقعة غير مكتمل."]
    lines += [
        f"عدد الحوادث: المتوقع {len(grouping.expected)}، الناتج {len(grouping.produced)}",
        f"بلاغات في حادثتها الصحيحة: {_fraction(grouping.well_placed, len(t.done))}",
        f"حوادث مكررة جُمعت كاملة: {len(grouping.collected)} من {len(grouping.repeated)}",
        f"حوادث تفرّقت بلاغاتها (تكرار لم يُدمج): {len(grouping.split)}",
    ]
    for incident, pieces in grouping.split:
        lines.append(f"  - المتوقع معاً: {_ids(incident)}. الناتج: " + " | ".join(_ids(piece) for piece in pieces))
    lines.append(f"حوادث دُمجت فيها بلاغات مختلفة خطأً: {len(grouping.mixed)}")
    for made in grouping.mixed:
        lines.append(f"  - دُمجت خطأً: {_ids(made)}")
    return lines


def _set_lines(t: Tally, show_text: bool) -> list[str]:
    """Everything the report says about one set of reports."""
    arabic = sum(1 for r in t.done if LANGUAGE_GROUPS["العربية"](r))
    urdu = sum(1 for r in t.done if LANGUAGE_GROUPS["الأردو"](r))
    lines = [f"البلاغات: {len(t.done)} (العربية {arabic}، الأردو {urdu})"]
    lines += _stopped_warning(t)
    for section in (
        _confident_lines(t),
        _accuracy_lines(t),
        _spoken_room_lines(t),
        _wrong_report_lines(t, show_text),
        _grouping_lines(t),
    ):
        lines += ["", *section]
    return lines


def render(
    run: Run, reports: list[SampleReport], expected: dict[int, Expected], holdout: Holdout | None = None
) -> str:
    """The whole benchmark report of one model as Arabic text.

    The main reports and the owner's holdout reports are scored separately.
    The words of the holdout reports are never printed.
    """
    main = tally(run, reports, expected)
    lines = ["تقرير اختبار الدقة - رصد", f"النموذج: {run.model}", "", MAIN_TITLE]
    lines += _set_lines(main, show_text=True)

    lines += ["", HOLDOUT_TITLE]
    held = None
    if holdout is None:
        lines.append("لا توجد بلاغات محجوبة بعد. توضع في المجلد data/holdout ثم يُعاد تشغيل الاختبار.")
    else:
        held = tally(holdout.run, holdout.reports, holdout.expected)
        lines.append("نصوص هذه البلاغات لا تُطبع هنا حتى تبقى اختباراً مستقلاً. ابحثوا برقم البلاغ في ملفكم.")
        lines += _set_lines(held, show_text=False)

    parts = [main] + ([held] if held else [])
    seconds = sum(t.run.seconds for t in parts)
    count = sum(len(t.done) for t in parts)
    lines += [
        "",
        "== التكلفة والزمن ==",
        f"الوحدات النصية (tokens): {sum(t.run.input_tokens for t in parts)} داخلة "
        f"و{sum(t.run.output_tokens for t in parts)} خارجة",
        f"التكلفة التقريبية: {sum(t.run.cost for t in parts):.4f} دولار",
        f"الزمن: {seconds:.1f} ثانية ({seconds / count if count else 0.0:.1f} ثانية للبلاغ في المتوسط)",
    ]

    failed = [(r, t) for t in parts for r in t.done if t.run.results[r.id].error]
    lines.append(f"بلاغات لم يُجب عنها النموذج: {len(failed)}")
    for r, t in failed:
        origin = " (من المحجوبة)" if t is held else ""
        lines.append(f"  - رقم {r.id}{origin}: {t.run.results[r.id].error}")

    return _right_to_left(lines)


# ---------------------------------------------------------------------------
# Two models side by side
# ---------------------------------------------------------------------------


def _verdict(small_right: int, large_right: int) -> str:
    if large_right > small_right:
        return f"الأكبر أفضل بـ {large_right - small_right}"
    if small_right > large_right:
        return f"الأصغر أفضل بـ {small_right - large_right}"
    return "لا فرق"


def _side_by_side(name: str, small: tuple[int, int], large: tuple[int, int]) -> str:
    """One line such as: النوع: الأصغر 34 من 35 (97%) | الأكبر 35 من 35 (100%) | الأكبر أفضل بـ 1"""
    return f"{name}: الأصغر {_fraction(*small)} | الأكبر {_fraction(*large)} | {_verdict(small[0], large[0])}"


def render_comparison(small: Run, large: Run, reports: list[SampleReport], expected: dict[int, Expected]) -> str:
    """The accuracy and cost gap between two models that read the same reports, as Arabic text."""
    a, b = tally(small, reports, expected), tally(large, reports, expected)
    lines = [
        "======== المقارنة بين النموذجين (البلاغات الأساسية) ========",
        f"الأصغر: {small.model}",
        f"الأكبر: {large.model}",
        "النموذجان قرآ البلاغات نفسها بالتعليمات نفسها.",
    ]
    for name, t in (("الأصغر", a), ("الأكبر", b)):
        if len(t.done) < len(reports):
            lines.append(
                f"تنبيه: النموذج {name} لم يُكمل البلاغات ({len(t.done)} من {len(reports)}) "
                "لأن التكلفة تجاوزت الحد، فالمقارنة غير متكافئة."
            )

    lines += [
        "",
        "== الأخطاء الواثقة: خطأ لم يُحَل للمشرف ==",
        f"بلاغات فيها خطأ ولم تُحَل للمشرف: الأصغر {len(a.with_outcome(CONFIDENT_MISTAKE))} "
        f"| الأكبر {len(b.with_outcome(CONFIDENT_MISTAKE))}",
        f"منها بمكان خاطئ (نوعه أو رقمه): الأصغر {len(a.confident_wrong_places)} "
        f"| الأكبر {len(b.confident_wrong_places)}",
        f"بلاغات فيها خطأ وأُحيلت للمشرف: الأصغر {len(a.with_outcome(CAUGHT_MISTAKE))} "
        f"| الأكبر {len(b.with_outcome(CAUGHT_MISTAKE))}",
        f"إحالات للمشرف بلا داعٍ (البلاغ مفهوم صحيحاً): الأصغر {len(a.with_outcome(NEEDLESS_REFERRAL))} "
        f"| الأكبر {len(b.with_outcome(NEEDLESS_REFERRAL))}",
        "",
        "== الدقة حسب الحقل ==",
    ]
    for field, name in FIELDS.items():
        lines.append(
            _side_by_side(name, _right_and_total(a.done, a.marks(field)), _right_and_total(b.done, b.marks(field)))
        )
    for group, belongs in LANGUAGE_GROUPS.items():
        name = "كل الحقول معاً" if group == "الكل" else f"كل الحقول معاً ({group})"
        lines.append(
            _side_by_side(
                name, _right_and_total(a.done, a.all_right, belongs), _right_and_total(b.done, b.all_right, belongs)
            )
        )

    lines += ["", "== أرقام الغرف المنطوقة وتجميع المكررات =="]
    lines.append(
        _side_by_side(
            "رقم الغرفة المنطوق بالكلمات",
            (len(a.spoken_rooms) - len(a.wrong_spoken_rooms), len(a.spoken_rooms)),
            (len(b.spoken_rooms) - len(b.wrong_spoken_rooms), len(b.spoken_rooms)),
        )
    )
    if a.grouping is None or b.grouping is None:
        lines.append("بلاغات في حادثتها الصحيحة: لم يُحتسب (العمود incident غير مكتمل).")
    else:
        lines.append(
            _side_by_side(
                "بلاغات في حادثتها الصحيحة",
                (a.grouping.well_placed, len(a.done)),
                (b.grouping.well_placed, len(b.done)),
            )
        )

    cost_line = f"التكلفة التقريبية: الأصغر {small.cost:.4f} دولار | الأكبر {large.cost:.4f} دولار"
    if small.cost > 0:
        cost_line += f" | الأكبر أغلى بنحو {round(large.cost / small.cost)} مرة"
    lines += [
        "",
        "== التكلفة والزمن ==",
        cost_line,
        f"الزمن للبلاغ: الأصغر {_per_report(a):.1f} ثانية | الأكبر {_per_report(b):.1f} ثانية",
    ]
    return _right_to_left(lines)


def _per_report(t: Tally) -> float:
    return t.run.seconds / len(t.done) if t.done else 0.0
