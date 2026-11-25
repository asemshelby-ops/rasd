"""The team's tables: who owns each type of report, and how its priority is worked out.

Priority is decided here, by tables the team edits, and not by the AI model:
the type gives a default, the journey stage may change it, and every risk the
message states raises it one level.
"""

import pytest

from rasd.routing import (
    CURRENT_STAGE,
    DEADLINE_MINUTES,
    OWNER_BY_TYPE,
    PRIORITY_BY_TYPE,
    PRIORITY_IN_STAGE,
    priority_for,
)
from rasd.schema import OWNERS, RISKS, STAGES, TYPES, URGENCIES

# --- the levels -------------------------------------------------------------


def test_there_are_four_priority_levels_from_most_to_least_urgent():
    assert list(URGENCIES) == ["critical", "urgent", "medium", "normal"]


def test_every_priority_level_has_a_deadline():
    assert set(DEADLINE_MINUTES) == set(URGENCIES)


def test_a_more_urgent_level_never_has_a_longer_deadline():
    minutes = [DEADLINE_MINUTES[level] for level in URGENCIES]
    assert minutes == sorted(minutes)


# --- the default priority of each type --------------------------------------


def test_every_type_has_an_owner_and_a_default_priority():
    assert set(OWNER_BY_TYPE) == set(TYPES)
    assert set(PRIORITY_BY_TYPE) == set(TYPES)
    assert set(OWNER_BY_TYPE.values()) <= set(OWNERS)
    assert set(PRIORITY_BY_TYPE.values()) <= set(URGENCIES)


@pytest.mark.parametrize(
    "type, priority",
    [
        ("lost_pilgrim", "critical"),
        ("health", "critical"),
        ("nusuk_card", "urgent"),
        ("ac", "urgent"),
        ("water", "urgent"),
        ("power_elevator", "urgent"),
        ("luggage", "medium"),
        ("cleaning", "normal"),
        ("gifts", "normal"),
    ],
)
def test_the_teams_default_priority_for_each_type(type, priority):
    assert priority_for(type, risks=(), stage="makkah") == priority


def test_a_report_nobody_could_classify_is_urgent_because_it_may_be_anything():
    assert priority_for("unclear", risks=(), stage="makkah") == "urgent"


# --- the journey stage ------------------------------------------------------


def test_the_journey_has_four_stages_in_order():
    assert list(STAGES) == ["arrival", "makkah", "hajj", "departure"]


def test_the_stage_in_use_is_one_of_the_four():
    assert CURRENT_STAGE in STAGES


def test_a_lost_nusuk_card_is_critical_during_the_hajj_days():
    assert priority_for("nusuk_card", risks=(), stage="hajj") == "critical"


@pytest.mark.parametrize("stage", ["arrival", "makkah", "departure"])
def test_a_lost_nusuk_card_is_urgent_in_the_other_stages(stage):
    assert priority_for("nusuk_card", risks=(), stage=stage) == "urgent"


def test_the_hajj_days_change_nothing_else():
    for type in TYPES:
        if type != "nusuk_card":
            assert priority_for(type, risks=(), stage="hajj") == PRIORITY_BY_TYPE[type]


def test_the_stage_table_only_names_known_stages_types_and_levels():
    assert set(PRIORITY_IN_STAGE) <= set(STAGES)
    for changes in PRIORITY_IN_STAGE.values():
        assert set(changes) <= set(TYPES)
        assert set(changes.values()) <= set(URGENCIES)


def test_a_stage_that_does_not_exist_is_an_error_not_a_silent_default():
    with pytest.raises(ValueError, match="stage"):
        priority_for("nusuk_card", risks=(), stage="haj")


# --- risks the message states ------------------------------------------------


def test_each_stated_risk_raises_the_priority_one_level():
    assert priority_for("cleaning", risks=(), stage="makkah") == "normal"
    assert priority_for("cleaning", risks=("elderly",), stage="makkah") == "medium"
    assert priority_for("cleaning", risks=("elderly", "sick"), stage="makkah") == "urgent"
    assert priority_for("cleaning", risks=("elderly", "sick", "medication"), stage="makkah") == "critical"


def test_priority_stops_at_critical():
    assert priority_for("cleaning", risks=tuple(RISKS), stage="makkah") == "critical"
    assert priority_for("ac", risks=("elderly", "sick"), stage="makkah") == "critical"
    assert priority_for("health", risks=("sick",), stage="makkah") == "critical"


def test_every_kind_of_risk_counts_the_same():
    assert list(RISKS) == ["elderly", "sick", "medication", "time_limit", "alone_or_lost"]
    for risk in RISKS:
        assert priority_for("luggage", risks=(risk,), stage="makkah") == "urgent"


def test_the_same_risk_named_twice_counts_once():
    assert priority_for("luggage", risks=("medication", "medication"), stage="makkah") == "urgent"


def test_risks_are_added_on_top_of_the_stage_priority():
    assert priority_for("nusuk_card", risks=("time_limit",), stage="makkah") == "critical"
    assert priority_for("nusuk_card", risks=("time_limit",), stage="hajj") == "critical"
    assert priority_for("luggage", risks=("time_limit",), stage="hajj") == "urgent"


def test_a_risk_that_does_not_exist_is_an_error():
    with pytest.raises(ValueError, match="risk"):
        priority_for("luggage", risks=("angry",), stage="makkah")
