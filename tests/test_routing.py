"""The team's tables: who owns each type of report, and how its priority is worked out.

Priority is decided here, by tables the team edits, and not by the AI model:
the type gives a default, the journey stage may change it, and every risk the
message states raises it one level.
"""

import pytest

from rasd.routing import (
    ACKNOWLEDGE_MINUTES,
    CURRENT_STAGE,
    DEADLINE_MINUTES,
    DEADLINES_ARE_SAMPLE_DATA,
    FAULT_TYPES,
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


def test_a_critical_report_has_two_steps_acknowledge_in_5_minutes_and_close_in_30():
    assert ACKNOWLEDGE_MINUTES == {"critical": 5}
    assert DEADLINE_MINUTES["critical"] == 30


def test_the_minutes_are_marked_as_trial_values():
    assert DEADLINES_ARE_SAMPLE_DATA is True


def test_a_more_urgent_level_never_waits_longer_for_its_first_answer():
    # The first answer is the acknowledgement where there is one, otherwise the closing.
    first = [ACKNOWLEDGE_MINUTES.get(level, DEADLINE_MINUTES[level]) for level in URGENCIES]
    assert first == sorted(first)


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
        if type not in ("nusuk_card", "no_nusuk_card"):
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
    assert list(RISKS) == ["elderly", "sick", "medication", "time_limit", "alone_or_lost", "danger"]
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


def test_immediate_physical_danger_raises_the_priority_one_level():
    assert priority_for("power_elevator", risks=("danger",), stage="makkah") == "critical"
    assert priority_for("cleaning", risks=("danger",), stage="makkah") == "medium"


# --- a fault the message says is only partial ---------------------------------


def test_the_faults_are_ac_water_and_electricity_or_elevator():
    assert set(FAULT_TYPES) == {"ac", "water", "power_elevator"}


@pytest.mark.parametrize("type", ["ac", "water", "power_elevator"])
def test_a_partial_fault_is_one_level_below_the_default_of_its_type(type):
    assert priority_for(type, risks=(), stage="makkah") == "urgent"
    assert priority_for(type, risks=(), stage="makkah", partial=True) == "medium"


def test_partial_only_applies_to_faults():
    for type in TYPES:
        if type not in FAULT_TYPES:
            assert priority_for(type, risks=(), stage="makkah", partial=True) == PRIORITY_BY_TYPE[type], type


def test_a_stated_risk_still_raises_a_partial_fault():
    assert priority_for("ac", risks=("elderly",), stage="makkah", partial=True) == "urgent"
    assert priority_for("ac", risks=("elderly", "sick"), stage="makkah", partial=True) == "critical"


def test_priority_never_goes_below_normal(monkeypatch):
    monkeypatch.setitem(PRIORITY_BY_TYPE, "water", "normal")
    assert priority_for("water", risks=(), stage="makkah", partial=True) == "normal"


# --- stage 2: the new types ------------------------------------------------------


@pytest.mark.parametrize(
    "type, priority, owner",
    [
        ("no_nusuk_card", "urgent", "pilgrim_affairs"),
        ("forgot_credentials", "medium", "pilgrim_affairs"),
        ("gifts", "normal", "pilgrim_affairs"),
        ("not_a_report", "normal", "nobody"),
    ],
)
def test_priority_and_owner_of_the_types_added_for_real_reports(type, priority, owner):
    assert priority_for(type, risks=(), stage="makkah") == priority
    assert OWNER_BY_TYPE[type] == owner


def test_a_pilgrim_with_no_nusuk_card_is_critical_during_the_hajj_days_like_a_lost_card():
    assert priority_for("no_nusuk_card", risks=(), stage="hajj") == "critical"


# --- hotels ------------------------------------------------------------------------

from rasd.routing import CHECKLISTS, HOTELS, REQUIRED_BY_TYPE, match_hotel, missing_requirements  # noqa: E402


def test_the_hotel_list_is_marked_as_sample_names():
    from rasd import routing

    assert routing.HOTELS_ARE_SAMPLE_DATA is True
    assert len(HOTELS) >= 3


def test_a_known_hotel_is_recognised_with_or_without_the_word_hotel():
    known = HOTELS[0]
    assert match_hotel(known) == known
    assert match_hotel(f"فندق {known}") == known
    assert match_hotel(f"  {known} ") == known


def test_a_known_hotel_is_recognised_in_urdu_letters_and_other_spellings():
    assert match_hotel("برج السکینہ") == "برج السكينة"
    assert match_hotel("برج السكينه") == "برج السكينة"
    assert match_hotel("ہوٹل برج السکینہ") == "برج السكينة"


def test_an_unknown_hotel_is_kept_as_written_without_the_word_hotel():
    assert match_hotel("فندق قصر الغيم") == "قصر الغيم"


def test_no_hotel_is_none():
    assert match_hotel("") is None
    assert match_hotel("  ") is None
    assert match_hotel("فندق") is None


# --- what a report needs before it can go to its owner --------------------------------


def missing(type, hotel=None, loc_kind="none", loc_number=None, name=None):
    return missing_requirements(type, hotel=hotel, loc_kind=loc_kind, loc_number=loc_number, pilgrim_name=name)


def test_every_type_says_what_it_needs():
    assert set(REQUIRED_BY_TYPE) == set(TYPES)


@pytest.mark.parametrize("type", ["ac", "water", "power_elevator", "cleaning"])
def test_a_fault_needs_a_room_or_a_floor_and_a_hotel_alone_is_not_enough(type):
    assert missing(type, hotel="برج السكينة") == ("place",)
    assert missing(type, loc_kind="room", loc_number="907") == ()
    assert missing(type, loc_kind="floor", loc_number="9") == ()
    assert missing(type, loc_kind="elevator", loc_number="2") == ()
    assert missing(type, loc_kind="room") == ("place",)  # a room without its number
    assert missing(type, loc_kind="common_area") == ()


def test_a_nusuk_card_report_with_the_pilgrims_name_and_hotel_needs_no_room():
    assert missing("nusuk_card", hotel="برج السكينة", name="نبيل سعد") == ()


def test_a_nusuk_card_report_needs_to_know_whose_card_it_is():
    assert missing("nusuk_card", hotel="برج السكينة") == ("who",)
    assert missing("nusuk_card", hotel="برج السكينة", loc_kind="room", loc_number="907") == ()


def test_a_report_about_a_person_needs_a_hotel_or_a_place():
    assert missing("nusuk_card", name="نبيل سعد") == ("hotel_or_place",)
    assert missing("lost_pilgrim") == ("hotel_or_place",)
    assert missing("lost_pilgrim", hotel="برج السكينة") == ()
    assert missing("lost_pilgrim", loc_kind="common_area") == ()
    assert missing("health", loc_kind="room", loc_number="907") == ()


@pytest.mark.parametrize("type", ["nusuk_card", "no_nusuk_card", "forgot_credentials", "luggage", "gifts"])
def test_types_about_one_pilgrims_things_need_a_name_or_a_numbered_place(type):
    assert missing(type, hotel="برج السكينة") == ("who",)
    assert missing(type, hotel="برج السكينة", name="نبيل سعد") == ()
    assert missing(type, hotel="برج السكينة", loc_kind="floor", loc_number="7") == ()
    assert missing(type) == ("hotel_or_place", "who")


def test_an_unclear_report_and_a_message_that_is_not_a_report_need_nothing_more():
    assert missing("unclear") == ()
    assert missing("not_a_report") == ()


# --- checklists ----------------------------------------------------------------------


def test_every_type_has_a_checklist_and_only_a_non_report_has_an_empty_one():
    assert set(CHECKLISTS) == set(TYPES)
    for type, items in CHECKLISTS.items():
        assert bool(items) == (type != "not_a_report"), type


def test_the_lost_or_damaged_nusuk_card_checklist_is_the_one_the_team_gave():
    assert list(CHECKLISTS["nusuk_card"]) == [
        "الاسم الكامل كما في الجواز",
        "رقم التأشيرة",
        "رقم الجواز",
        "مكان الفقد",
        "تاريخ الفقد ووقته",
        "الشركة والفندق والغرفة",
    ]


# --- a hotel named by part of its name ---------------------------------------------------


def test_a_known_hotel_is_recognised_by_the_part_of_its_name_that_only_it_has():
    # Staff, and the model, often leave out a first word such as "نزل" or "برج".
    assert match_hotel("الياسمين") == "نزل الياسمين"
    assert match_hotel("فندق الياسمين") == "نزل الياسمين"
    assert match_hotel("السكينة") == "برج السكينة"


def test_a_part_shared_by_two_known_hotels_is_not_guessed(monkeypatch):
    from rasd import routing

    monkeypatch.setattr(routing, "HOTELS", ["برج السكينة", "برج الواحة"])
    assert match_hotel("برج") == "برج"
    assert match_hotel("برج الواحة") == "برج الواحة"
    assert match_hotel("السكينة") == "برج السكينة"


def test_words_that_are_in_no_known_hotel_stay_as_written():
    assert match_hotel("الياسمين الجديد") == "الياسمين الجديد"


# --- a hotel name with a short word glued to its front ("بدار المنارة") ------------------


@pytest.mark.parametrize("written", ["بدار المنارة", "لدار المنارة", "وبدار المنارة", "ببرج السكينة", "في غرفة 533 بنزل الياسمين"])
def test_a_known_hotel_is_recognised_with_a_short_word_glued_to_its_name(written):
    assert match_hotel(written) in HOTELS


def test_a_known_hotel_is_recognised_by_its_own_part_with_a_short_word_glued_to_it():
    assert match_hotel("بالياسمين") == "نزل الياسمين"
    assert match_hotel("للياسمين") == "نزل الياسمين"


def test_a_glued_letter_is_not_taken_off_a_hotel_we_do_not_know():
    assert match_hotel("بيت الضيافة") == "بيت الضيافة"
