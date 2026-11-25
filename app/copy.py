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
# The board's layout: a band for critical cases, then three columns.
SECTIONS = {"critical": "حالات حرجة", "now": "الآن", "late": "تجاوزت الموعد", "closed": "مغلقة"}
NO_CRITICAL = "لا حالة حرجة الآن."
COUNT_OPEN = "مفتوحة"
COUNT_CRITICAL = "حرجة"
COUNT_CLOSED_TODAY = "أُغلقت اليوم"
WAITS_FOR_SUPERVISOR = "بانتظار المشرف"
LANGUAGES = {"ar": "العربية", "ur": "الأردية", "en": "الإنجليزية"}
BOARD_NAME_SAVE = "احفظ الاسم"
BOARD_NAME_TITLE = "من يعمل على اللوحة"
BOARD_NAME_NOW = "الاسم المسجَّل الآن"
BOARD_NAME_NONE = "لا اسم بعد. أزرار اللوحة لا تعمل قبل حفظ الاسم."
BOARD_SIZE_TITLE = "حجم الخط على اللوحة"
STILL_WAITING = "ما زالت بانتظار تأكيد المشرف"

# --- the PIN of the operator page and the supervisor page -------------------------------------
PIN_TITLE = "رصد: الرمز السري"
PIN_HELP = "صفحة التشغيل وصفحة المشرف لفريق العرض. اكتب الرمز السري للدخول."
PIN_LABEL = "الرمز السري"
PIN_ENTER = "ادخل"
PIN_WRONG = "الرمز غير صحيح. اكتبه من جديد."
PIN_LOCKED = "خمس محاولات خاطئة. انتظر دقيقة ثم اكتب الرمز من جديد."
PIN_NEEDED = "هذا الطلب يحتاج الرمز السري. افتح صفحة التشغيل واكتب الرمز أولاً."
CASES_COUNT = "عدد الحالات"
LARGER = "كبّر الخط"
SMALLER = "صغّر الخط"
NEW_CASE = "حالة جديدة"
MOVED_TO = "انتقلت إلى"
ACKNOWLEDGE = "استلمتُ الحالة"
CLOSE = "أغلق الحالة"
CONFIRM = "أكّد البلاغ"
YOUR_NAME = "اسمك (يُسجَّل مع كل استلام وإغلاق)"
NAME_NEEDED = "اكتب اسمك في صفحة التشغيل أولاً. الاستلام والإغلاق يُسجَّلان باسم من قام بهما."
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
SHOW_CARD = "صوّر البطاقة التجريبية"
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
CARD_ONLY_FOR_LOST = "البطاقة تُقرأ لحالة حاج تائه مفتوحة فقط."
SOMETHING_WRONG = "لم يتم الطلب. أعد المحاولة، وإن تكرر فأبلغ المشرف."
UNLISTED_HOTEL = "فندق غير مسجّل في القائمة"

# --- the supervisor page: never on the big screen -------------------------------------------------
SUPERVISOR_TITLE = "رصد: بلاغات تنتظر المشرف"
SUPERVISOR_NOTE = "هذه الصفحة للمشرف وحده، ولا تُعرض على الشاشة الكبيرة. أرقام الجوازات والتأشيرات محجوبة فيها."
NOTHING_WAITING = "لا بلاغ ينتظر المشرف الآن."
WHY_WAITING = "سبب الإحالة"
MESSAGE_AS_SENT = "نص الرسالة"
NO_TEXT_KEPT = "لا نص: وصلت صورة فقط، أو لم يُحفظ النص."

PHOTO_TOO_LARGE = "الصورة أكبر من الحد المسموح، فلم تُرسل. صوّر البطاقة من مسافة أبعد قليلاً ثم أعد الإرسال."
AUDIO_TOO_LARGE = "الرسالة الصوتية أكبر من الحد المسموح، فلم تُرسل. سجّل رسالة أقصر من دقيقتين ثم أعد الإرسال."
ATTACH_AUDIO = "أرفق تسجيلاً صوتياً"
MORE_ATTACHMENTS = "مرفقات: تسجيل صوتي أو صورة"
QUESTION_FROM_RASD = "سؤال من رصد"

# --- the operator page: the replay switch -------------------------------------------------------
OPERATOR_TITLE = "رصد: تشغيل العرض"
MODE_LIVE = "الوضع الآن: مباشر"
MODE_REPLAY = "الوضع الآن: إعادة من ملفات محفوظة"
MODE_LIVE_HELP = "الرسائل تُقرأ بالنموذج مباشرة. إن تعطّلت الشبكة أو تأخر الرد، حوّل إلى الإعادة."
MODE_REPLAY_HELP = "المشهد يُعرض من ملفات محفوظة على هذا الحاسوب، ولا يحتاج إنترنت."
SWITCH_TO_REPLAY = "حوّل إلى الإعادة"
SWITCH_TO_LIVE = "ارجع إلى المباشر"
UNKNOWN_MODE = "وضع غير معروف. الوضعان: مباشر، أو إعادة."
REPLAY_MODE_ON = "وضع الإعادة يعمل: المشهد يُعرض من ملفات محفوظة"
FROM_SAVED = "من تسجيل محفوظ"
SCENE_STEPS = "خطوات المشهد من الملفات المحفوظة"
SCENE_STEPS_HELP = "كل زر يرسل الملف المحفوظ كأنه وصل الآن. اضغطها بالترتيب."
STEP_COUNTER = "1. أرسل رسالة موظف الاستقبال"
STEP_PILGRIM = "2. أرسل رسالة الحاج"
STEP_CARD = "3. اقرأ البطاقة التجريبية"
NO_CASE_FOR_CARD = "لا توجد حالة حاج تائه مفتوحة. أرسل رسالة موظف الاستقبال أولاً."
CLEAR_DEMO = "امسح حالات العرض"
CLEAR_HELP = "يمسح كل ما على اللوحة قبل عرض جديد. لا يمكن التراجع."
CLEAR_YES = "نعم، امسح كل الحالات"
CLEAR_NEEDS_YES = "لم يُمسح شيء. ضع علامة التأكيد أولاً ثم اضغط «امسح حالات العرض»."
CLEARED = "مُسحت حالات العرض. اللوحة فارغة."
LAST_VOICE_TOOK = "آخر رسالة صوتية، من وصولها إلى تسجيل الحالة"
LAST_VOICE_PARTS = "تحويل الصوت إلى نص {heard} ث، ثم القراءة والتسجيل {read} ث"
SECONDS = "ثانية"
NO_VOICE_YET = "لم تصل رسالة صوتية بعد."
CHECKS_TITLE = "فحص قبل العرض"
CHECK_CLAUDE_KEY_OK = "مفتاح Claude موجود."
CHECK_CLAUDE_KEY_MISSING = "مفتاح Claude غير موجود، فالقراءة المباشرة لن تعمل. استعمل وضع الإعادة."
CHECK_SPEECH_KEY_OK = "مفتاح تحويل الصوت موجود."
CHECK_SPEECH_KEY_MISSING = "مفتاح تحويل الصوت غير موجود، فالرسائل الصوتية المباشرة لن تُحوَّل. الرسائل المحفوظة تعمل."
CHECK_SCENE_OK = "ملفات المشهد المحفوظة موجودة."
CHECK_SCENE_MISSING = "ملفات المشهد المحفوظة ناقصة، فوضع الإعادة لن يعمل."

# --- the printable scenario card ------------------------------------------------------------------
CARD_TITLE = "بطاقة المشهد"
CARD_FOR_JUDGE = "ما يقوله المحكّم"
CARD_FOR_OPERATOR = "ما يقوله المشغّل"
CARD_IF_LIVE_FAILS = "إن تعطّل المباشر"
PRINT = "اطبع البطاقة"

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
