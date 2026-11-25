"""Who owns each type of report, how urgent it is, and how long there is to close it.

These are plain tables that the team edits by hand. The AI model does not choose
the owner, the priority or the deadline. It only reads the message.

How the priority of a report is worked out (priority_for, at the bottom):
  1. the type gives the default            PRIORITY_BY_TYPE
  2. the journey stage may change it       PRIORITY_IN_STAGE
  3. every risk the message states in words raises it one level, up to critical

The priority table is the team's decision, made after a field review. It follows
what a problem means for the pilgrim at each point of the journey. It was not
fitted to the test reports.
"""

from rasd.schema import RISKS, STAGES, URGENCIES

OWNER_BY_TYPE = {
    "lost_pilgrim": "pilgrim_affairs",
    "health": "pilgrim_affairs",
    "nusuk_card": "pilgrim_affairs",
    "luggage": "luggage_team",
    "ac": "maintenance",
    "water": "maintenance",
    "cleaning": "housekeeping",
    "power_elevator": "maintenance",
    "gifts": "pilgrim_affairs",
    "unclear": "supervisor",
}

# The default priority of each type of report.
PRIORITY_BY_TYPE = {
    "lost_pilgrim": "critical",
    "health": "critical",
    "nusuk_card": "urgent",
    "ac": "urgent",
    "water": "urgent",
    "power_elevator": "urgent",
    "luggage": "medium",
    "cleaning": "normal",
    "gifts": "normal",
    "unclear": "urgent",  # nobody knows what it is yet, so it may be anything
}

# The stage of the journey the pilgrims are in now. The operations room changes
# it by hand: arrival, makkah, hajj or departure. (In Phase 2 this becomes a
# control on the board.)
CURRENT_STAGE = "makkah"

# What a stage changes. During the Hajj days the Nusuk card is needed to enter
# the holy sites and the transport, so losing it is critical.
PRIORITY_IN_STAGE = {
    "hajj": {"nusuk_card": "critical"},
}

# SAMPLE VALUES. These minutes are not measured and do not come from a real
# service agreement. Replace them with the company's real targets, and label
# them as sample data wherever they are shown until then.
DEADLINE_MINUTES = {
    "critical": 5,
    "urgent": 15,
    "medium": 60,
    "normal": 180,
}
DEADLINES_ARE_SAMPLE_DATA = True


def priority_for(type: str, risks, stage: str) -> str:
    """The priority of a report: a code from schema.URGENCIES.

    type is a code from schema.TYPES, risks are codes from schema.RISKS (the
    risks the message states), stage is a code from schema.STAGES.
    """
    if stage not in STAGES:
        raise ValueError(f"'{stage}' is not a journey stage. Allowed: {', '.join(STAGES)}")
    unknown = [risk for risk in risks if risk not in RISKS]
    if unknown:
        raise ValueError(f"'{unknown[0]}' is not a known risk. Allowed: {', '.join(RISKS)}")

    levels = list(URGENCIES)  # the most urgent first
    default = PRIORITY_IN_STAGE.get(stage, {}).get(type, PRIORITY_BY_TYPE[type])
    steps_up = len(set(risks))
    return levels[max(levels.index(default) - steps_up, 0)]
