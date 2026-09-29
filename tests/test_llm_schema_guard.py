"""contracts.md §4 — the LLM action contract and its schema guard."""

import json

import pytest

from agent.llm_client import ActionContract, parse_action_contract, validate_action_contract

MALFORMED = "llm_malformed_json"
UNKNOWN = "llm_unknown_action"
SCHEMA = "llm_schema_violation"

VALID = {
    "thought": "借方科目の欄に入力する",
    "action": "set_value",
    "target_id": 2,
    "value": "4100",
    "is_destructive": True,
}


def assert_contract(result, **expected):
    assert isinstance(result, ActionContract), f"expected a contract, got {result!r}"
    for key, value in expected.items():
        assert getattr(result, key) == value, key


# ------------------------------------------------------------------ accepted
def test_full_contract_is_accepted():
    assert_contract(
        validate_action_contract(VALID),
        action="set_value",
        target_id=2,
        value="4100",
        is_destructive=True,
        thought="借方科目の欄に入力する",
    )


def test_required_only_contract_is_accepted_with_defaults():
    result = validate_action_contract(
        {"action": "click", "target_id": 7, "is_destructive": False}
    )
    assert_contract(result, action="click", target_id=7, value=None, thought="")


def test_thought_longer_than_500_chars_is_truncated_not_rejected():
    payload = dict(VALID, thought="あ" * 900)
    result = validate_action_contract(payload)
    assert_contract(result, thought="あ" * 500)


def test_integral_float_target_id_is_accepted_as_json_schema_integer():
    # §4.1 types target_id as integer; JSON Schema counts 4.0 as integer.
    assert_contract(validate_action_contract(dict(VALID, target_id=4.0)), target_id=4)


def test_japanese_value_round_trips():
    payload = dict(VALID, value="令和8年8月1日")
    assert_contract(validate_action_contract(payload), value="令和8年8月1日")


def test_finish_with_null_value_is_accepted():
    assert_contract(
        validate_action_contract(
            {"action": "finish", "target_id": 1, "value": None, "is_destructive": False}
        ),
        action="finish",
    )


def test_wait_without_value_is_accepted():
    assert_contract(
        validate_action_contract(
            {"action": "wait", "target_id": 3, "is_destructive": False}
        ),
        action="wait",
    )


def test_to_dict_uses_contract_key_order():
    assert list(VALID_TO_DICT := validate_action_contract(VALID).to_dict()) == [
        "thought",
        "action",
        "target_id",
        "value",
        "is_destructive",
    ]
    assert VALID_TO_DICT["is_destructive"] is True


# --------------------------------------------------------------- rejections
@pytest.mark.parametrize(
    "raw, category",
    [
        ("this is not json at all", MALFORMED),
        ("{not json", MALFORMED),
        ("", MALFORMED),
        ("[1, 2, 3]", MALFORMED),
        ('"click"', MALFORMED),
        ("null", MALFORMED),
        ("42", MALFORMED),
        ("{}", MALFORMED),
        ('{"target_id": 1, "is_destructive": false}', MALFORMED),
    ],
    ids=[
        "prose",
        "truncated-json",
        "empty",
        "array",
        "string",
        "null",
        "number",
        "empty-object",
        "missing-action",
    ],
)
def test_malformed_json_is_malformed(raw, category):
    result = parse_action_contract(raw)
    assert result.error_category == category
    assert not isinstance(result, ActionContract)


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "destroy", "target_id": 1, "is_destructive": False},
        {"action": "SetValue", "target_id": 1, "is_destructive": False},
        {"action": "", "target_id": 1, "is_destructive": False},
        {"action": 3, "target_id": 1, "is_destructive": False},
        {"action": None, "target_id": 1, "is_destructive": False},
        {"action": ["click"], "target_id": 1, "is_destructive": False},
    ],
)
def test_action_outside_the_enum_is_unknown_action(payload):
    result = validate_action_contract(payload)
    assert result.error_category == UNKNOWN


@pytest.mark.parametrize(
    "payload, missing_rule",
    [
        ({"action": "click", "is_destructive": True}, "target_id"),
        ({"action": "click", "target_id": 1}, "is_destructive"),
        ({"action": "click", "target_id": 1, "is_destructive": True, "value": 42}, "value"),
        ({"action": "click", "target_id": 1, "is_destructive": True, "thought": 5}, "thought"),
        (
            {
                "action": "click",
                "target_id": 1,
                "is_destructive": True,
                "confidence": 0.9,
            },
            "confidence",
        ),
        ({"action": "set_value", "target_id": 1, "is_destructive": True}, "value"),
        ({"action": "select", "target_id": 1, "is_destructive": False}, "value"),
    ],
    ids=[
        "missing-target-id",
        "missing-is-destructive",
        "value-not-string",
        "thought-not-string",
        "extra-key",
        "set-value-without-value",
        "select-without-value",
    ],
)
def test_schema_violations(payload, missing_rule):
    result = validate_action_contract(payload)
    assert result.error_category == SCHEMA
    assert missing_rule in result.detail


@pytest.mark.parametrize("target_id", ['"4"', 0, -1, 1.5, True, False, None, [4]])
def test_bad_target_id(target_id):
    result = validate_action_contract(dict(VALID, target_id=target_id))
    assert result.error_category == SCHEMA
    assert "target_id" in result.detail


def test_missing_is_destructive_is_schema_violation_not_malformed():
    # §2.2 rows two: missing target_id / absent is_destructive → schema violation.
    result = validate_action_contract({"action": "click", "target_id": 4})
    assert result.error_category == SCHEMA


def test_duplicate_keys_are_refused():
    raw = (
        '{"action":"click","target_id":4,'
        '"is_destructive":true,"is_destructive":false}'
    )
    result = parse_action_contract(raw)
    assert result.error_category == SCHEMA
    assert "duplicate" in result.detail


def test_every_rejection_carries_a_contract_rule_reference():
    result = parse_action_contract("nope")
    assert result.rule.startswith("§")
    result = validate_action_contract({"action": "click"})
    assert result.rule.startswith("§")


def test_rejections_never_echo_the_payload():
    secret = "sk-should-not-appear"
    result = parse_action_contract(f"{{bad {secret}")
    assert secret not in result.detail
