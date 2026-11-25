"""Who owns each type of report, and how long they have to close it.

These are plain tables that the team edits by hand. The AI model does not choose
the owner or the deadline; it only reads the message.
"""

OWNER_BY_TYPE = {
    "nusuk_card": "pilgrim_affairs",
    "luggage": "luggage_team",
    "ac": "maintenance",
    "water": "maintenance",
    "cleaning": "housekeeping",
    "power_elevator": "maintenance",
    "unclear": "supervisor",
}

# SAMPLE VALUES. These minutes are not measured and do not come from a real
# service agreement. Replace them with the company's real targets, and label
# them as sample data wherever they are shown until then.
DEADLINE_MINUTES = {
    "urgent": 15,
    "medium": 60,
    "low": 180,
}
DEADLINES_ARE_SAMPLE_DATA = True
