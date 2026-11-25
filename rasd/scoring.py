"""Scores the engine's answers against data/expected.csv and writes the Arabic report.

Nothing in this file calls the AI model. benchmark.py does the calls and hands
the answers to render().
"""

from dataclasses import dataclass

from rasd.cost import MAX_RUN_COST_USD, cost_usd
from rasd.data import NO_NUMBER, Expected, SampleReport
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

# The groups each accuracy is shown for.
LANGUAGE_GROUPS = {
    "الكل": lambda report: True,
    "العربية": lambda report: report.lang.startswith("ar"),
    "الأردو": lambda report: report.lang == "ur",
}

RIGHT_TO_LEFT = "‏"  # invisible mark that makes a line display right to left


@dataclass
class Run:
    """One benchmark run: which model, what it answered, how long it took."""

    model: str
    results: dict[int, Understanding]  # report id -> the engine's answer
    seconds: float
    stopped_at_cost_limit: bool


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


def _accuracy_line(name: str, reports, marks: dict[int, bool | None]) -> str:
    """One line such as: النوع: الكل 33 من 35 (94%) | العربية ... | الأردو ..."""
    parts = []
    for group, belongs in LANGUAGE_GROUPS.items():
        scored = [marks[r.id] for r in reports if belongs(r) and marks[r.id] is not None]
        parts.append(f"{group} {_fraction(sum(scored), len(scored))}")
    return f"{name}: " + " | ".join(parts)


def render(run: Run, reports: list[SampleReport], expected: dict[int, Expected]) -> str:
    """The whole benchmark report as Arabic text."""
    done = [r for r in reports if r.id in run.results]
    scores = {r.id: score(expected[r.id], run.results[r.id]) for r in done}
    arabic = sum(1 for r in done if LANGUAGE_GROUPS["العربية"](r))
    urdu = sum(1 for r in done if LANGUAGE_GROUPS["الأردو"](r))

    lines = [
        "تقرير اختبار الدقة - رصد",
        f"النموذج: {run.model}",
        f"البلاغات: {len(done)} (العربية {arabic}، الأردو {urdu})",
    ]
    if run.stopped_at_cost_limit:
        lines.append(
            f"تنبيه: توقف الاختبار لأن التكلفة تجاوزت الحد ({MAX_RUN_COST_USD:.2f} دولار). "
            f"النتائج لعدد {len(done)} من {len(reports)} بلاغاً فقط."
        )

    lines += ["", "== الدقة حسب الحقل =="]
    for field, name in FIELDS.items():
        lines.append(_accuracy_line(name, done, {rid: s[field] for rid, s in scores.items()}))
    all_right = {rid: all(mark is not False for mark in s.values()) for rid, s in scores.items()}
    lines.append(_accuracy_line("كل الحقول معاً", done, all_right))

    # The room number is the field that breaks the demo, so spoken numbers get their own count.
    lines += ["", "== أرقام الغرف المنطوقة بالكلمات =="]
    spoken = [r for r in done if expected[r.id].room_in_words]
    wrong = [
        r
        for r in spoken
        if (run.results[r.id].loc_kind, run.results[r.id].loc_number) != ("room", expected[r.id].loc_number)
    ]
    caught = [r for r in wrong if run.results[r.id].needs_confirmation]
    lines += [
        f"رقم الغرفة صحيح: {_fraction(len(spoken) - len(wrong), len(spoken))}",
        f"رقم خاطئ ونُبّه المشرف عليه: {len(caught)}",
        f"رقم خاطئ ولم يُنبَّه عليه: {len(wrong) - len(caught)}",
    ]

    wrong_reports = [r for r in done if not all_right[r.id]]
    lines += ["", f"== البلاغات الخاطئة: {len(wrong_reports)} =="]
    for r in wrong_reports:
        actual = run.results[r.id]
        lines.append(f"البلاغ {r.id} ({'الأردو' if r.lang == 'ur' else 'العربية'}): {r.text}")
        for field, name in FIELDS.items():
            if scores[r.id][field] is not False:
                continue
            line = (
                f"  - {name}: المتوقع «{_shown(field, getattr(expected[r.id], field))}»، "
                f"الناتج «{_shown(field, getattr(actual, field))}»"
            )
            if field == "loc_number" and actual.number_words:
                line += f" (قرأه النموذج من: «{actual.number_words}»)"
            if field == "needs_confirmation" and actual.reasons:
                line += " (السبب: " + "، ".join(FLAG_REASONS[reason] for reason in actual.reasons) + ")"
            lines.append(line)

    lines += ["", "== تجميع البلاغات المكررة ==", "لم يُبنَ بعد (الخطوة الثالثة)، فلا توجد له نتيجة."]

    input_tokens = sum(a.input_tokens for a in run.results.values())
    output_tokens = sum(a.output_tokens for a in run.results.values())
    per_report = run.seconds / len(done) if done else 0.0
    lines += [
        "",
        "== التكلفة والزمن ==",
        f"الوحدات النصية (tokens): {input_tokens} داخلة و{output_tokens} خارجة",
        f"التكلفة التقريبية: {cost_usd(run.model, input_tokens, output_tokens):.4f} دولار",
        f"الزمن: {run.seconds:.1f} ثانية ({per_report:.1f} ثانية للبلاغ في المتوسط)",
    ]

    failed = [r for r in done if run.results[r.id].error]
    lines.append(f"بلاغات لم يُجب عنها النموذج: {len(failed)}")
    for r in failed:
        lines.append(f"  - رقم {r.id}: {run.results[r.id].error}")

    return "\n".join(RIGHT_TO_LEFT + line if line else line for line in lines) + "\n"
