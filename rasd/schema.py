"""The fixed vocabulary of a report: internal codes and their Arabic labels.

Code uses the short English codes. Screens and printed reports use the Arabic labels.
"""

TYPES = {
    "nusuk_card": "فقدان بطاقة نسك",
    "luggage": "أمتعة لم تصل",
    "ac": "عطل تكييف",
    "water": "انقطاع الماء",
    "cleaning": "نظافة الغرفة",
    "power_elevator": "عطل كهرباء أو مصعد",
    "unclear": "غير واضح",
}

LOCATION_KINDS = {
    "room": "غرفة",
    "elevator": "مصعد",
    "floor": "دور",
    "common_area": "مرفق عام",
    "none": "غير مذكور",
}

URGENCIES = {
    "urgent": "عاجل",
    "medium": "متوسط",
    "low": "عادي",
}

OWNERS = {
    "pilgrim_affairs": "شؤون الحجاج",
    "luggage_team": "فريق الأمتعة",
    "maintenance": "الصيانة",
    "housekeeping": "التدبير الفندقي",
    "supervisor": "مشرف الوردية",
}

CONFIDENCES = {
    "high": "عالية",
    "low": "منخفضة",
}

# Why a report needs the supervisor to confirm it before it is trusted.
FLAG_REASONS = {
    "unclear_type": "نوع البلاغ غير واضح",
    "no_location": "المكان غير مذكور أو رقمه ناقص",
    "number_not_confirmed": "رقم المكان لم يتأكد آلياً",
    "low_confidence": "ثقة النموذج في فهمه منخفضة",
    "not_understood": "تعذّر فهم البلاغ آلياً",
}


def location_label(kind: str, number: str | None) -> str:
    """Arabic text for a location, for example 'غرفة 412' or 'غير مذكور'."""
    label = LOCATION_KINDS[kind]
    return f"{label} {number}" if number else label
