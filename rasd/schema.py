"""The fixed vocabulary of a report: internal codes and their Arabic labels.

Code uses the short English codes. Screens and printed reports use the Arabic labels.
"""

TYPES = {
    "lost_pilgrim": "حاج تائه أو لا يستطيع التواصل",
    "health": "حالة صحية",
    "nusuk_card": "بطاقة نسك مفقودة أو تالفة",
    "no_nusuk_card": "حاج بلا بطاقة نسك",
    "forgot_credentials": "نسي كلمة المرور أو رقم الجواز",
    "luggage": "أمتعة لم تصل",
    "ac": "عطل تكييف",
    "water": "انقطاع الماء",
    "cleaning": "نظافة الغرفة",
    "power_elevator": "عطل كهرباء أو مصعد",
    "gifts": "هدايا أو توزيعات لم تُستلم",
    "unclear": "غير واضح",
    "not_a_report": "ليست بلاغاً",
}

LOCATION_KINDS = {
    "room": "غرفة",
    "elevator": "مصعد",
    "floor": "دور",
    "common_area": "مرفق عام",
    "none": "غير مذكور",
}

# The priority levels, the most urgent first. Code calls this field "urgency".
URGENCIES = {
    "critical": "حرج",
    "urgent": "عاجل",
    "medium": "متوسط",
    "normal": "عادي",
}

# Risks that a message may state in words. Each one raises the priority one level.
RISKS = {
    "elderly": "حاج كبير في السن",
    "sick": "حاج مريض",
    "medication": "دواء",
    "time_limit": "موعد قريب",
    "alone_or_lost": "حاج وحده أو تائه",
    "danger": "خطر جسدي مباشر",
}

# The stages of the pilgrim's journey. The operations room sets the current one by hand.
STAGES = {
    "arrival": "الوصول",
    "makkah": "أيام مكة",
    "hajj": "أيام الحج",
    "departure": "المغادرة",
}

OWNERS = {
    "pilgrim_affairs": "شؤون الحجاج",
    "luggage_team": "فريق الأمتعة",
    "maintenance": "الصيانة",
    "housekeeping": "التدبير الفندقي",
    "supervisor": "مشرف الوردية",
    "nobody": "لا أحد (ليست بلاغاً)",
}

CONFIDENCES = {
    "high": "عالية",
    "low": "منخفضة",
}

# Why a report needs the supervisor to confirm it before it is trusted.
FLAG_REASONS = {
    "unclear_type": "نوع البلاغ غير واضح",
    "no_location": "المكان غير مذكور أو رقمه ناقص",
    "no_pilgrim": "لا يُعرف لمن البلاغ: لا اسم ولا غرفة",
    "number_not_confirmed": "رقم المكان لم يتأكد آلياً",
    "hotel_not_confirmed": "فندق قرأه النموذج وليس في الرسالة",
    "hotel_near_match": "اسم الفندق قريب من فندق في القائمة ولم يؤكده المرسل",
    "risk_not_confirmed": "خطر قرأه النموذج ولم يتأكد آلياً",
    "partial_not_confirmed": "عطل جزئي قرأه النموذج ولم يتأكد آلياً",
    "low_confidence": "ثقة النموذج في فهمه منخفضة",
    "not_understood": "تعذّر فهم البلاغ آلياً",
}


def location_label(kind: str, number: str | None) -> str:
    """Arabic text for a location, for example 'غرفة 412' or 'غير مذكور'."""
    label = LOCATION_KINDS[kind]
    return f"{label} {number}" if number else label
