"""The understanding function: message text -> report with type, place, owner, deadline and flag.

The message texts and room numbers here are made up for these tests; they are
not the benchmark reports.
"""

import json

import anthropic
import httpx2
import pytest

from rasd.data import load_expected, load_reports
from rasd.numbers import HUNDRED_ENDINGS, TEEN_ENDINGS, hundred_spellings, normalise, teen_spellings
from rasd.routing import ACKNOWLEDGE_MINUTES, DEADLINE_MINUTES
from rasd import routing
from rasd.schema import FLAG_REASONS, LOCATION_KINDS, RISKS, TYPES
from rasd.understand import EFFORT, SYSTEM_PROMPT, Reading, build_report, make_client, understand

MESSAGE = "ما في موية في غرفة تسعمية وسبعة من الصبح"


def reading(**changes) -> Reading:
    """A clear, correct reading of MESSAGE. Tests change one field at a time."""
    fields = dict(
        type="water",
        location_kind="room",
        number_words="تسعمية وسبعة",
        location_number="907",
        risks=[],
        partial_words="",
        confidence="high",
    )
    fields.update(changes)
    return Reading(**fields)


def risk(kind: str, words: str) -> dict:
    """One risk as the model reports it: its kind and the words of the message that state it."""
    return {"kind": kind, "words": words}


# --- build_report: our own rules on top of what the model read -------------


def test_a_clear_reading_becomes_a_report_that_needs_no_confirmation():
    report = build_report(MESSAGE, reading())
    assert (report.type, report.loc_kind, report.loc_number) == ("water", "room", "907")
    assert report.urgency == "urgent"  # the team's default for a water outage
    assert report.risks == ()
    assert report.needs_confirmation is False
    assert report.reasons == ()


def test_owner_comes_from_the_routing_table_not_from_the_model():
    assert build_report(MESSAGE, reading()).owner == "maintenance"
    assert build_report(MESSAGE, reading(type="cleaning")).owner == "housekeeping"


def test_deadline_comes_from_the_routing_table():
    assert build_report(MESSAGE, reading()).deadline_minutes == DEADLINE_MINUTES["urgent"]
    assert build_report(MESSAGE, reading(type="cleaning")).deadline_minutes == DEADLINE_MINUTES["normal"]


# --- priority: the team's tables and the risks the message states -----------
# The model is not asked how urgent a report is. It only says which risks the
# message states, with the words that state them.

RISKY_MESSAGE = "غرفة تسعمية وسبعة تبغى تنظيف وفيها حاجة كبيرة بالعمر وتعبانة وعلاجها ناقص"


def test_the_model_is_never_asked_for_the_priority():
    assert "urgency" not in Reading.model_fields
    assert "priority" not in Reading.model_fields


def test_priority_comes_from_the_teams_table_for_the_type():
    assert build_report(MESSAGE, reading()).urgency == "urgent"
    assert build_report(MESSAGE, reading(type="luggage")).urgency == "medium"
    assert build_report(MESSAGE, reading(type="cleaning")).urgency == "normal"
    assert build_report(MESSAGE, reading(type="health")).urgency == "critical"


def test_a_risk_the_message_states_raises_the_priority_one_level():
    report = build_report(RISKY_MESSAGE, reading(type="cleaning", risks=[risk("elderly", "حاجة كبيرة بالعمر")]))
    assert report.urgency == "medium"
    assert report.risks == ("elderly",)
    assert report.needs_confirmation is False


def test_two_different_risks_raise_the_priority_two_levels():
    stated = [risk("elderly", "حاجة كبيرة بالعمر"), risk("sick", "تعبانة")]
    report = build_report(RISKY_MESSAGE, reading(type="cleaning", risks=stated))
    assert report.urgency == "urgent"
    assert report.risks == ("elderly", "sick")


def test_the_same_kind_of_risk_named_twice_counts_once():
    stated = [risk("sick", "تعبانة"), risk("sick", "حاجة كبيرة بالعمر وتعبانة")]
    report = build_report(RISKY_MESSAGE, reading(type="cleaning", risks=stated))
    assert report.urgency == "medium"
    assert report.risks == ("sick",)


def test_priority_stops_at_critical_however_many_risks_there_are():
    stated = [risk("elderly", "حاجة كبيرة بالعمر"), risk("sick", "تعبانة"), risk("medication", "علاجها")]
    assert build_report(RISKY_MESSAGE, reading(risks=stated)).urgency == "critical"


def test_risks_are_listed_in_the_order_of_the_schema_whatever_order_the_model_used():
    stated = [risk("medication", "علاجها"), risk("elderly", "حاجة كبيرة بالعمر")]
    report = build_report(RISKY_MESSAGE, reading(type="cleaning", risks=stated))
    assert report.risks == ("elderly", "medication")
    assert report.risk_words == ("حاجة كبيرة بالعمر", "علاجها")


def test_the_deadline_follows_the_priority_after_the_risks_are_counted():
    report = build_report(RISKY_MESSAGE, reading(type="cleaning", risks=[risk("elderly", "حاجة كبيرة بالعمر")]))
    assert report.deadline_minutes == DEADLINE_MINUTES["medium"]


def test_a_risk_whose_words_are_not_in_the_message_still_counts_but_goes_to_the_supervisor():
    # The message says nothing about a sick pilgrim. We keep the higher priority,
    # which is the safe side, and ask a person to look.
    report = build_report(MESSAGE, reading(type="cleaning", risks=[risk("sick", "حاج مريض")]))
    assert report.urgency == "medium"
    assert report.risks == ("sick",)
    assert report.needs_confirmation is True
    assert report.reasons == ("risk_not_confirmed",)


def test_a_risk_quoted_from_two_parts_of_the_message_is_confirmed():
    # The model often joins two pieces of the message into one quote, skipping the words between them.
    message = "في دخان طالع من المطبخ في الدور التاسع، وصوت إنذار"
    stated = [risk("danger", "دخان طالع من المطبخ وصوت إنذار")]
    report = build_report(message, reading(type="power_elevator", location_kind="floor", number_words="التاسع", location_number="9", risks=stated))
    assert report.risks == ("danger",)
    assert report.reasons == ()


def test_partial_words_quoted_from_two_parts_of_the_message_are_confirmed():
    message = "مكيف غرفة تسعمية وسبعة يسرّب موية على السرير بس لسا يبرّد"
    report = build_report(message, reading(type="ac", partial_words="يسرّب موية بس لسا يبرّد"))
    assert report.partial is True
    assert report.reasons == ()


def test_a_risk_with_no_words_goes_to_the_supervisor():
    report = build_report(RISKY_MESSAGE, reading(type="cleaning", risks=[risk("elderly", "")]))
    assert report.reasons == ("risk_not_confirmed",)


def test_one_unconfirmed_risk_among_confirmed_ones_is_enough_to_ask_the_supervisor():
    stated = [risk("elderly", "حاجة كبيرة بالعمر"), risk("time_limit", "الباص بعد ساعة")]
    report = build_report(RISKY_MESSAGE, reading(type="cleaning", risks=stated))
    assert report.urgency == "urgent"
    assert report.reasons == ("risk_not_confirmed",)


# --- a fault the message says is only partial --------------------------------

DRIPPING = "مكيف غرفة تسعمية وسبعة يسرّب موية بس لسا يبرّد"


def test_a_fault_the_message_says_is_partial_goes_one_level_down():
    report = build_report(DRIPPING, reading(type="ac", partial_words="بس لسا يبرّد"))
    assert report.partial is True
    assert report.urgency == "medium"
    assert report.deadline_minutes == DEADLINE_MINUTES["medium"]
    assert report.needs_confirmation is False


def test_a_fault_is_not_partial_when_the_model_quotes_nothing():
    report = build_report(DRIPPING, reading(type="ac"))
    assert report.partial is False
    assert report.urgency == "urgent"


def test_partial_words_that_are_not_in_the_message_do_not_lower_the_priority_and_go_to_the_supervisor():
    # Lowering a priority on words nobody said would be a guess. Keep the default and ask a person.
    report = build_report(DRIPPING, reading(type="ac", partial_words="العطل بسيط"))
    assert report.partial is False
    assert report.urgency == "urgent"
    assert report.reasons == ("partial_not_confirmed",)


def test_partial_is_ignored_for_a_type_that_is_not_a_fault():
    report = build_report(DRIPPING, reading(type="luggage", partial_words="بس لسا يبرّد"))
    assert report.partial is False
    assert report.urgency == "medium"
    assert report.reasons == ()


def test_a_stated_risk_raises_a_partial_fault_again():
    message = DRIPPING + " وفيها حاجة كبيرة بالعمر"
    stated = [risk("elderly", "حاجة كبيرة بالعمر")]
    report = build_report(message, reading(type="ac", partial_words="بس لسا يبرّد", risks=stated))
    assert report.urgency == "urgent"


# --- critical reports: acknowledge first, then close ----------------------------


def test_a_critical_report_must_be_acknowledged_in_5_minutes_and_closed_in_30():
    report = build_report(MESSAGE, reading(type="health"))
    assert report.urgency == "critical"
    assert report.acknowledge_minutes == ACKNOWLEDGE_MINUTES["critical"] == 5
    assert report.deadline_minutes == DEADLINE_MINUTES["critical"] == 30


def test_other_levels_have_no_acknowledge_step():
    for type in ("water", "luggage", "cleaning"):
        assert build_report(MESSAGE, reading(type=type)).acknowledge_minutes is None


def test_a_lost_nusuk_card_is_critical_when_the_stage_is_the_hajj_days():
    lost_card = reading(type="nusuk_card")
    assert build_report(MESSAGE, lost_card, stage="makkah").urgency == "urgent"
    assert build_report(MESSAGE, lost_card, stage="hajj").urgency == "critical"


def test_the_stage_is_the_one_set_in_the_routing_table_unless_another_is_given(monkeypatch):
    lost_card = reading(type="nusuk_card")
    monkeypatch.setattr(routing, "CURRENT_STAGE", "hajj")
    assert build_report(MESSAGE, lost_card).urgency == "critical"
    monkeypatch.setattr(routing, "CURRENT_STAGE", "departure")
    assert build_report(MESSAGE, lost_card).urgency == "urgent"


def test_number_is_stored_in_western_digits():
    report = build_report(MESSAGE, reading(location_number="٩٠٧"))
    assert report.loc_number == "907"
    assert report.needs_confirmation is False


def test_low_confidence_is_flagged():
    report = build_report(MESSAGE, reading(confidence="low"))
    assert report.needs_confirmation is True
    assert report.reasons == ("low_confidence",)


def test_unclear_type_is_flagged_and_goes_to_the_supervisor():
    report = build_report(MESSAGE, reading(type="unclear"))
    assert report.owner == "supervisor"
    assert report.reasons == ("unclear_type",)


def test_no_location_is_flagged():
    report = build_report(
        "المكيف خربان عند الحجاج الجدد",
        reading(type="ac", location_kind="none", number_words="", location_number=""),
    )
    assert report.loc_number is None
    assert report.reasons == ("no_location",)


def test_a_room_without_its_number_counts_as_no_location():
    report = build_report(
        "في غرفة بالدور السابع ما فيها موية",
        reading(number_words="", location_number=""),
    )
    assert report.loc_kind == "room"
    assert report.loc_number is None
    assert report.reasons == ("no_location",)


def test_a_common_area_needs_no_number():
    report = build_report(
        "اللوبي يبغاله تنظيف",
        reading(type="cleaning", location_kind="common_area", number_words="", location_number=""),
    )
    assert report.needs_confirmation is False


def test_a_number_that_disagrees_with_its_own_quote_is_flagged():
    report = build_report(MESSAGE, reading(location_number="970"))
    assert report.loc_number == "970"  # we keep the model's reading, but ask a person
    assert report.reasons == ("number_not_confirmed",)


def test_a_quote_that_is_not_in_the_message_is_flagged():
    report = build_report(MESSAGE, reading(number_words="تسعمية وسبعين", location_number="970"))
    assert report.reasons == ("number_not_confirmed",)


def test_a_quote_we_cannot_read_is_flagged():
    message = "غرفة نمبر نو سو سات میں پانی نہیں ہے"
    report = build_report(message, reading(number_words="نو سو سات"))
    assert report.reasons == ("number_not_confirmed",)


def test_a_number_written_in_digits_in_the_message_is_confirmed_even_when_the_quote_is_not_a_copy():
    # The model spelled the digits out as words instead of copying them from the message.
    report = build_report("غرفة ٩٠٧ ما فيها موية من الصبح", reading(number_words="تسعة صفر سبعة"))
    assert report.loc_number == "907"
    assert report.needs_confirmation is False
    assert report.reasons == ()


def test_a_number_written_in_digits_in_the_message_is_confirmed_with_an_empty_quote():
    report = build_report("غرفة 907 ما فيها موية من الصبح", reading(number_words=""))
    assert report.reasons == ()


def test_digits_that_are_only_part_of_a_longer_number_do_not_confirm_it():
    report = build_report("غرفة 1907 ما فيها موية من الصبح", reading(number_words=""))
    assert report.loc_number == "907"
    assert report.reasons == ("number_not_confirmed",)


def test_other_digits_in_the_message_do_not_confirm_a_different_number():
    report = build_report("3 شنط ناقصة من غرفة 355", reading(type="luggage", number_words="", location_number="907"))
    assert report.reasons == ("number_not_confirmed",)


def test_a_number_that_is_not_digits_is_flagged():
    report = build_report(MESSAGE, reading(location_number="تسعمية وسبعة"))
    assert report.reasons == ("number_not_confirmed",)


def test_an_elevator_named_by_an_ordinal_word_is_confirmed():
    report = build_report(
        "المصعد السابع واقف",
        reading(type="power_elevator", location_kind="elevator", number_words="السابع", location_number="7"),
    )
    assert (report.loc_kind, report.loc_number) == ("elevator", "7")
    assert report.needs_confirmation is False


def test_several_reasons_are_all_listed():
    report = build_report(MESSAGE, reading(type="unclear", confidence="low"))
    assert set(report.reasons) == {"unclear_type", "low_confidence"}


def test_every_reason_has_an_arabic_label():
    report = build_report(MESSAGE, reading(type="unclear", confidence="low", location_number="970"))
    assert all(reason in FLAG_REASONS for reason in report.reasons)


# --- understand: the call to the model ------------------------------------
# These tests use the real Anthropic client. Only the network is replaced: each
# test supplies the HTTP answer that the API would have sent.


def client_answering(handler) -> anthropic.Anthropic:
    """A real client whose HTTP requests are answered by handler(request) instead of the internet."""
    return anthropic.Anthropic(
        api_key="test-key",
        max_retries=0,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )


def api_message(content, stop_reason="end_turn", input_tokens=900, output_tokens=120) -> httpx2.Response:
    """The JSON the Messages API sends back."""
    return httpx2.Response(
        200,
        json={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-5-5",
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        },
    )


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


GOOD_ANSWER = text_block(reading().model_dump_json())


def test_understand_sends_the_message_the_prompt_and_the_schema_to_the_chosen_model():
    sent = []

    def handler(request):
        sent.append(request)
        return api_message([GOOD_ANSWER])

    understand(MESSAGE, client_answering(handler), model="some-model")

    body = json.loads(sent[0].content)
    assert body["model"] == "some-model"
    assert body["system"] == SYSTEM_PROMPT
    assert body["messages"] == [{"role": "user", "content": MESSAGE}]
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["output_config"]["effort"] == EFFORT
    assert set(body["output_config"]["format"]["schema"]["properties"]) == set(Reading.model_fields)


def test_understand_sends_the_key_it_was_given():
    sent = []

    def handler(request):
        sent.append(request)
        return api_message([GOOD_ANSWER])

    understand(MESSAGE, client_answering(handler))
    assert "test-key" in sent[0].headers.get("authorization", "") + sent[0].headers.get("x-api-key", "")


def test_understand_returns_the_report_with_the_tokens_it_used():
    client = client_answering(lambda request: api_message([GOOD_ANSWER], input_tokens=900, output_tokens=120))
    report = understand(MESSAGE, client)
    assert (report.type, report.loc_number, report.owner) == ("water", "907", "maintenance")
    assert (report.input_tokens, report.output_tokens) == (900, 120)
    assert report.error is None


def test_understand_reads_the_answer_when_the_model_thinks_first():
    thinking = {"type": "thinking", "thinking": "", "signature": "abc"}
    client = client_answering(lambda request: api_message([thinking, GOOD_ANSWER]))
    assert understand(MESSAGE, client).loc_number == "907"


def test_understand_uses_the_stage_it_is_given():
    lost_card = text_block(reading(type="nusuk_card").model_dump_json())
    client = client_answering(lambda request: api_message([lost_card]))
    assert understand(MESSAGE, client, stage="hajj").urgency == "critical"
    assert understand(MESSAGE, client, stage="arrival").urgency == "urgent"


def test_understand_returns_the_risks_the_model_reported():
    answer = text_block(reading(type="cleaning", risks=[risk("elderly", "حاجة كبيرة بالعمر")]).model_dump_json())
    report = understand(RISKY_MESSAGE, client_answering(lambda request: api_message([answer])))
    assert (report.risks, report.urgency) == (("elderly",), "medium")


def assert_sent_to_supervisor(report):
    assert report.type == "unclear"
    assert report.urgency == "urgent"
    assert report.risks == ()
    assert report.loc_kind == "none"
    assert report.owner == "supervisor"
    assert report.needs_confirmation is True
    assert report.reasons == ("not_understood",)
    assert report.error


def test_a_network_failure_gives_a_flagged_report_instead_of_a_crash():
    def handler(request):
        raise httpx2.ConnectError("no internet", request=request)

    assert_sent_to_supervisor(understand(MESSAGE, client_answering(handler)))


def test_a_rejected_key_gives_a_flagged_report_that_names_the_key():
    error = {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
    report = understand(MESSAGE, client_answering(lambda request: httpx2.Response(401, json=error)))
    assert_sent_to_supervisor(report)
    assert "RASD_CLAUDE_KEY" in report.error


def test_an_overloaded_api_gives_a_flagged_report():
    error = {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}
    report = understand(MESSAGE, client_answering(lambda request: httpx2.Response(529, json=error)))
    assert_sent_to_supervisor(report)
    assert "529" in report.error


def test_a_refusal_in_plain_words_gives_a_flagged_report():
    client = client_answering(lambda request: api_message([text_block("I cannot help with that.")], "refusal"))
    assert_sent_to_supervisor(understand(MESSAGE, client))


def test_a_refusal_with_no_text_gives_a_flagged_report_and_counts_its_tokens():
    client = client_answering(lambda request: api_message([], "refusal", input_tokens=900, output_tokens=5))
    report = understand(MESSAGE, client)
    assert_sent_to_supervisor(report)
    assert "refused" in report.error
    assert (report.input_tokens, report.output_tokens) == (900, 5)


def test_an_answer_cut_off_in_the_middle_gives_a_flagged_report():
    half = text_block(reading().model_dump_json()[:40])
    assert_sent_to_supervisor(understand(MESSAGE, client_answering(lambda request: api_message([half], "max_tokens"))))


def test_a_reply_that_ran_out_of_tokens_while_thinking_gives_a_flagged_report():
    thinking = {"type": "thinking", "thinking": "", "signature": "abc"}
    client = client_answering(lambda request: api_message([thinking], "max_tokens"))
    assert_sent_to_supervisor(understand(MESSAGE, client))


def test_an_empty_message_is_flagged_without_calling_the_model():
    def handler(request):
        raise AssertionError("the model must not be called for an empty message")

    assert_sent_to_supervisor(understand("   ", client_answering(handler)))


# --- the prompt -----------------------------------------------------------


def test_the_model_can_only_answer_with_codes_from_the_schema():
    properties = Reading.model_json_schema()["properties"]
    assert properties["type"]["enum"] == list(TYPES)
    assert properties["location_kind"]["enum"] == list(LOCATION_KINDS)
    assert Reading.model_json_schema()["$defs"]["Risk"]["properties"]["kind"]["enum"] == list(RISKS)


def test_the_prompt_explains_every_code():
    for code in [*TYPES, *LOCATION_KINDS, *RISKS]:
        assert f"\n- {code}: " in SYSTEM_PROMPT, f"the prompt has no line that explains '{code}'"


def prompt_line_for(number: int) -> str:
    """The line of the prompt's dialect table for one number, for example the line of 12."""
    lines = [line for line in SYSTEM_PROMPT.splitlines() if line.startswith(f"- {number}:")]
    assert len(lines) == 1, f"the prompt should have exactly one line that starts with '- {number}:'"
    return lines[0]


def test_the_prompt_lists_every_dialect_word_our_parser_knows_for_11_to_19():
    for number, spellings in teen_spellings().items():
        listed = prompt_line_for(number).split(":", 1)[1].replace("،", " ").split()
        assert listed == spellings


def test_the_prompt_lists_the_palestinian_word_for_twelve():
    # The first real benchmark run showed the small model reading this word as another number.
    assert "طنعش" in prompt_line_for(12)


def test_the_prompt_says_the_ending_of_these_words_can_change():
    for ending in TEEN_ENDINGS:
        assert ending in SYSTEM_PROMPT


def test_the_prompt_lists_every_dialect_word_our_parser_knows_for_the_hundreds():
    for number, spellings in hundred_spellings().items():
        listed = prompt_line_for(number).split(":", 1)[1].replace("،", " ").split()
        assert listed == spellings


def test_the_prompt_lists_the_word_for_six_hundred():
    # A new report showed the small model reading this word as five hundred.
    assert "ستمية" in prompt_line_for(600)


def test_the_prompt_says_the_ending_of_the_hundreds_can_change():
    for ending in HUNDRED_ENDINGS[1:]:
        assert ending in normalise(SYSTEM_PROMPT)


def test_the_prompt_asks_for_the_words_that_say_a_fault_is_partial():
    assert "partial_words" in SYSTEM_PROMPT
    assert "partial_words" in Reading.model_fields


def test_the_prompt_does_not_contain_benchmark_room_numbers():
    prompt = normalise(SYSTEM_PROMPT).split()
    numbers = {e.loc_number for e in load_expected().values() if e.loc_number}
    for report in load_reports():
        numbers.update(word for word in normalise(report.text).split() if word.isdigit())
    leaked = {n for n in numbers if len(n) >= 3 and n in prompt}
    assert not leaked, f"benchmark room numbers used in the prompt: {leaked}"


def test_the_prompt_does_not_quote_benchmark_reports():
    prompt = f" {normalise(SYSTEM_PROMPT)} "
    for report in load_reports():
        words = normalise(report.text).split()
        for i in range(len(words) - 2):
            phrase = " ".join(words[i : i + 3])
            assert f" {phrase} " not in prompt, f"report {report.id} is quoted in the prompt: {phrase}"


# --- the key --------------------------------------------------------------


def test_the_client_gets_the_key_from_the_environment_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("RASD_CLAUDE_KEY", "key-from-the-environment")
    client = make_client(env_file=tmp_path / "no-such-file")
    assert client.api_key == "key-from-the-environment"


def test_the_client_gets_the_key_from_the_env_file_on_a_laptop(monkeypatch, tmp_path):
    monkeypatch.delenv("RASD_CLAUDE_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("RASD_CLAUDE_KEY=key-from-the-file\n", encoding="utf-8")
    assert make_client(env_file=env_file).api_key == "key-from-the-file"
    monkeypatch.delenv("RASD_CLAUDE_KEY", raising=False)  # load_dotenv wrote it into the environment


def test_a_missing_key_is_reported_by_name(monkeypatch, tmp_path):
    monkeypatch.delenv("RASD_CLAUDE_KEY", raising=False)
    with pytest.raises(RuntimeError, match="RASD_CLAUDE_KEY"):
        make_client(env_file=tmp_path / "no-such-file")
