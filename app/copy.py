"""Every Arabic sentence the pages show, in one place.

Rules these follow (design:ux-copy): a button starts with a verb and says what it
does; an error says what happened, why, and what to do next; the same thing has
the same name everywhere (بلاغ = one message that reports a problem, حالة = the
case on the board that one or more reports belong to).
"""

from rasd.schema import FLAG_REASONS, LOCATION_KINDS, OWNERS, TYPES, URGENCIES, location_label  # noqa: F401

# --- labels that say what is not real ---------------------------------------------
PROTOTYPE_LABEL = "نموذج أولي: ربط واتساب للأعمال بانتظار الموافقة"
SIMULATED = "محاكاة"
SIMULATED_DATA_BANNER = "بيانات محاكاة: كل الشركات والحجاج والأرقام في هذه الصفحة مخترعة"
MOCKUP_LABEL = "نموذج شكلي"
SAMPLE_NUMBERS = "الأرقام في هذه الشاشة أمثلة شكلية وليست قياسات"
TRIAL_TIMES = "المدد قيم تجريبية"
FICTIONAL_GROUP = "مجموعة خيالية: الأسماء والرسائل مخترعة"
MOCK_CARD_NOTE = "بطاقة تجريبية مزيفة، ليست بطاقة نسك حقيقية"

# --- the board ----------------------------------------------------------------------
BOARD_TITLE = "رصد: لوحة الحالات"
STATES = {
    "waiting": "بانتظار المشرف",
    "routed": "عند الجهة المسؤولة",
    "late": "تجاوزت الموعد",
    "closed": "مغلقة",
}
NO_CASES = "لا حالات هنا الآن."
CASES_COUNT = "عدد الحالات"
LARGER = "كبّر الخط"
SMALLER = "صغّر الخط"
NEW_CASE = "حالة جديدة"
MOVED_TO = "انتقلت إلى"
ACKNOWLEDGE = "استلمتُ الحالة"
CLOSE = "أغلق الحالة"
CONFIRM = "أكّد البلاغ"
YOUR_NAME = "اسمك (يُسجَّل مع كل استلام وإغلاق)"
NAME_NEEDED = "اكتب اسمك أولاً. الإغلاق يُسجَّل باسم من أغلق."
ALREADY_CLOSED = "هذه الحالة مغلقة من قبل."
NOT_FOUND = "هذه الحالة غير موجودة."
ACKNOWLEDGE_WITHIN = "الاستلام خلال"
CLOSE_WITHIN = "الإغلاق خلال"
LATE_BY = "تأخرت"
ACKNOWLEDGED = "استُلمت"
CLOSED_BY = "أغلقها"
PHOTO_ATTACHED = "معها صورة (لا تُعرض هنا)"
REPLACEMENT = "طلب بدل فاقد"
REPLACEMENT_WITHIN = "باقٍ على المهلة"
OPEN_REQUEST = "افتح الطلب"
REPLACEMENT_TITLE = "طلب بدل فاقد لبطاقة نسك"
REQUEST_NOT_SENT = "طلب معبّأ من البلاغ. لم يُرسل إلى أي جهة: الإرسال غير مربوط في هذا النموذج."
ITEM_PRESENT = "موجود"
ITEM_MISSING = "ناقص"
NUMBER_KEPT = "محفوظ، ولا يُعرض هنا"
BACK_TO_BOARD = "عودة إلى لوحة الحالات"
NOTIFICATIONS = "الإشعارات"
NO_NOTIFICATIONS = "لا إشعارات بعد."
PLACE_UNKNOWN = "المكان غير معروف"
CONNECTION_LOST = "انقطع الاتصال بالخادم. اللوحة تعرض آخر ما وصل، وتُحدَّث وحدها حين يعود الاتصال."

# --- the reporting page -----------------------------------------------------------------
REPORT_TITLE = "رصد: إرسال بلاغ"
SENDING_FROM = "ترسل من فندق"
WRITE_HERE = "اكتب البلاغ هنا"
SEND = "أرسل البلاغ"
RECORD = "سجّل رسالة صوتية"
STOP_AND_SEND = "أوقف وأرسل"
ATTACH_PHOTO = "أرفق صورة الحاج"
PHOTO_NOTE = "الصورة للتعرّف على الحاج فقط، ولا تُعرض على اللوحة."
SHOW_CARD = "صوّر بطاقة نسك"
SENDING = "جارٍ الإرسال…"
EMPTY_MESSAGE = "اكتب البلاغ أو سجّله قبل الإرسال."
NOT_A_REPORT = "هذه الرسالة ليست بلاغاً، فلم تُسجَّل."
SENT_TO_SUPERVISOR = "أُرسل إلى المشرف ليتأكد منه."
HEARD = "سمعنا"
MIC_BLOCKED = "تعذّر تشغيل الميكروفون، لأن المتصفح يمنعه على هذا الاتصال. اكتب البلاغ نصاً، أو أرسل ملفاً صوتياً."
VOICE_FAILED = "لم يُحوَّل الصوت إلى نص، لأن خدمة التحويل غير مفعّلة. اكتب البلاغ نصاً ثم أرسله."
SEND_FAILED = "لم يصل البلاغ، لأن الاتصال بالخادم منقطع. تأكد من الشبكة ثم اضغط «أعد الإرسال»."
RESEND = "أعد الإرسال"
ALREADY_ANSWERED = "سبق الرد على سؤال هذا البلاغ. إن بقي شيء ناقص فالمشرف يتابعه."
CARD_REFUSED = "لم تُقرأ البطاقة. رصد يقرأ في هذا النموذج البطاقة التجريبية فقط. صوّر البطاقة التجريبية وأعد الإرسال."
NOT_IN_LOOKUP = "لم يُعثر على الحاج في بحث «علم» (محاكاة). تأكد من البطاقة، أو أبلغ المشرف."
CASE_CLOSED = "أُغلقت الحالة."

# --- the Elm view and the before-and-after page ---------------------------------------------
ELM_TITLE = "متابعة بدل فاقد بطاقات نسك خلال 24 ساعة"
OUR_COMPANY = "شركة العرض"
BEFORE_TITLE = "قبل: مجموعة واتساب واحدة لكل شيء"
AFTER_TITLE = "بعد: البلاغات نفسها على لوحة رصد"
NOT_REPORTS_NOTE = "رسائل ليست بلاغات، فلم تصل إلى اللوحة"
FOUND_IT_NOTE = "«لقيناها 👍» لم تُغلق شيئاً. الحالة تُغلق من رصد فقط، ويُسجَّل الوقت ومن أغلق."


def count_text(reports: int) -> str:
    """How many reports one case holds: "بلاغان، حالة واحدة"."""
    if reports == 1:
        return "بلاغ واحد"
    if reports == 2:
        return "بلاغان، حالة واحدة"
    if reports <= 10:
        return f"{reports} بلاغات، حالة واحدة"
    return f"{reports} بلاغاً، حالة واحدة"


def place_text(hotel: str | None, loc_kind: str, loc_number: str | None) -> str:
    """Where a case is: "برج السكينة، غرفة 907"."""
    inside = location_label(loc_kind, loc_number) if loc_kind != "none" else ""
    return "، ".join(part for part in (hotel, inside) if part) or PLACE_UNKNOWN


def received(label: str, type: str, place: str, owner: str, urgency: str) -> str:
    return f"وصل {label}. {TYPES[type]}، {place}. إلى: {OWNERS[owner]}. الأولوية: {URGENCIES[urgency]}."


def merged(case_id: int, reports: int) -> str:
    return f"أُضيف بلاغك إلى الحالة {case_id}: {count_text(reports)}."


def identified(company: str, hotel: str, room: str, supervisor: str) -> str:
    return f"عُرف الحاج ببحث «علم» ({SIMULATED}): شركة {company}، فندق {hotel}، غرفة {room}. المشرف: {supervisor}."


def notification(supervisor: str, company: str, at_hotel: str | None, case_id: int) -> str:
    where = f"عند استقبال فندق {at_hotel}" if at_hotel else "عند أحد مكاتب الاستقبال"
    return f"إشعار ({SIMULATED}) إلى {supervisor}، مشرف شركة {company}: حاج من شركتكم تائه {where}. الحالة {case_id}."
