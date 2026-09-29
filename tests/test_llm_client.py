"""KARA-10 done-when: malformed JSON is rejected without executing, a valid
response dispatches, and no secret ever reaches telemetry."""

import json

import pytest

from agent.llm_client import (
    ActionContract,
    LlmClient,
    LlmConfig,
    LlmFailure,
    TelemetryContext,
    build_failure_event,
)
from agent.llm_client.transport import HttpRequest, HttpResponse, LlmTransportError

API_KEY = "sk-test-1234567890abcdef"
MESSAGES = [
    {"role": "system", "content": "Return only the JSON action contract."},
    {"role": "user", "content": "仕訳を入力して"},
]
CONTEXT = TelemetryContext(
    intent="仕訳を入力して",
    window_title="弥生会計 2024 - 仕訳入力",
    tree_snapshot_hash="a" * 64,
)


def envelope(content, *, model="qwen3", finish_reason="stop"):
    """A chat-completions 200 body whose message content is ``content``."""
    return json.dumps(
        {
            "id": "chatcmpl-1",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": finish_reason,
                }
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")


class FakeTransport:
    """Stands in for the network: returns a canned body or raises."""

    def __init__(self, *, status=200, body=None, error=None):
        self.status = status
        self.body = body
        self.error = error
        self.requests = []

    def __call__(self, request: HttpRequest):
        assert isinstance(request, HttpRequest)
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return HttpResponse(status=self.status, body=self.body)


class RecordingDispatcher:
    """The Mode B dispatcher in miniature: records what it was asked to run."""

    def __init__(self):
        self.calls = []

    def dispatch(self, contract: ActionContract) -> None:
        self.calls.append(contract)


def make_client(transport, *, api_key=API_KEY, events=None):
    cfg = LlmConfig(
        base_url="http://localhost:11434/v1", api_key=api_key, model="qwen3"
    )
    on_event = events.append if events is not None else None
    return LlmClient(cfg, transport=transport, on_event=on_event), cfg


def run_step(client, dispatcher, *, telemetry=CONTEXT):
    """One Mode B step: validate, dispatch only on success (§8.4)."""
    result = client.plan_action(MESSAGES, telemetry=telemetry)
    if isinstance(result, ActionContract):
        dispatcher.dispatch(result)
    return result


# --------------------------------------------------------------- happy paths
def test_valid_response_dispatches_exactly_once():
    transport = FakeTransport(
        body=envelope(
            json.dumps(
                {
                    "thought": "借方科目を入力する",
                    "action": "set_value",
                    "target_id": 2,
                    "value": "4100",
                    "is_destructive": True,
                }
            )
        )
    )
    client, _ = make_client(transport)
    dispatcher = RecordingDispatcher()

    result = run_step(client, dispatcher)

    assert isinstance(result, ActionContract)
    assert (result.action, result.target_id, result.value, result.is_destructive) == (
        "set_value",
        2,
        "4100",
        True,
    )
    assert len(dispatcher.calls) == 1
    assert dispatcher.calls[0] is result


def test_request_shape_matches_the_openai_contract():
    transport = FakeTransport(body=envelope('{"action":"wait","target_id":1,"is_destructive":false}'))
    client, cfg = make_client(transport)

    client.plan_action(MESSAGES, telemetry=CONTEXT)

    request = transport.requests[0]
    assert request.url == "http://localhost:11434/v1/chat/completions"
    assert request.headers["Authorization"] == f"Bearer {API_KEY}"
    assert request.headers["Content-Type"] == "application/json"
    assert request.timeout_s == pytest.approx(5000 / 1000.0)

    payload = json.loads(request.body.decode("utf-8"))
    assert payload["model"] == "qwen3"
    assert payload["temperature"] == 0.0
    assert payload["stream"] is False
    assert payload["messages"] == MESSAGES


def test_no_authorization_header_when_api_key_is_empty():
    transport = FakeTransport(body=envelope('{"action":"wait","target_id":1,"is_destructive":false}'))
    client, _ = make_client(transport, api_key="")
    client.plan_action(MESSAGES, telemetry=CONTEXT)
    assert "Authorization" not in transport.requests[0].headers


def test_success_emits_no_telemetry_event():
    # The dispatcher owns the success event — only it knows resolved_target.
    events = []
    transport = FakeTransport(
        body=envelope('{"action":"click","target_id":3,"is_destructive":true}')
    )
    client, _ = make_client(transport, events=events)
    run_step(client, RecordingDispatcher())
    assert events == []


# ------------------------------------------------------------ failure paths
def test_malformed_json_is_rejected_without_executing():
    events = []
    raw = "申し訳ありませんが、うまく表示できません。もう一度お試しください。"
    transport = FakeTransport(body=envelope(raw))
    client, _ = make_client(transport, events=events)
    dispatcher = RecordingDispatcher()

    result = run_step(client, dispatcher)

    assert isinstance(result, LlmFailure)
    assert result.error_category == "llm_malformed_json"
    assert result.llm_output == raw
    assert dispatcher.calls == []  # nothing executed
    assert len(events) == 1
    event = events[0]
    assert event["status"] == "failure"
    assert event["error_category"] == "llm_malformed_json"
    assert event["llm_output"] == raw
    assert event["execution_mode"] == "mode_b"
    assert event["resolved_target"] is None
    assert event["os_error_code"] is None
    assert event["fallback_attempted"] is False


def test_schema_violation_is_rejected_without_executing():
    events = []
    transport = FakeTransport(
        body=envelope(json.dumps({"action": "click", "target_id": "4", "is_destructive": True}))
    )
    client, _ = make_client(transport, events=events)
    dispatcher = RecordingDispatcher()

    result = run_step(client, dispatcher)

    assert isinstance(result, LlmFailure)
    assert result.error_category == "llm_schema_violation"
    assert dispatcher.calls == []
    assert len(events) == 1
    assert events[0]["error_category"] == "llm_schema_violation"


def test_unknown_action_is_rejected_without_executing():
    transport = FakeTransport(
        body=envelope(json.dumps({"action": "format_disk", "target_id": 1, "is_destructive": True}))
    )
    client, _ = make_client(transport)
    dispatcher = RecordingDispatcher()

    result = run_step(client, dispatcher)

    assert result.error_category == "llm_unknown_action"
    assert dispatcher.calls == []


def test_envelope_without_choices_is_malformed_and_logs_the_raw_body():
    events = []
    body = b'{"object":"error","message":"model not found"}'
    transport = FakeTransport(body=body)
    client, _ = make_client(transport, events=events)
    result = client.plan_action(MESSAGES, telemetry=CONTEXT)
    assert result.error_category == "llm_malformed_json"
    assert result.llm_output == body.decode("utf-8")
    assert events[0]["llm_output"] == body.decode("utf-8")


def test_error_payload_with_http_200_is_malformed():
    transport = FakeTransport(body=b'{"error":{"message":"overloaded"}}')
    client, _ = make_client(transport)
    result = client.plan_action(MESSAGES, telemetry=CONTEXT)
    assert result.error_category == "llm_malformed_json"
    assert "overloaded" in result.detail


def test_empty_choices_array_is_malformed():
    transport = FakeTransport(body=b'{"choices": []}')
    client, _ = make_client(transport)
    assert client.plan_action(MESSAGES, telemetry=CONTEXT).error_category == (
        "llm_malformed_json"
    )


def test_non_json_200_body_is_malformed():
    transport = FakeTransport(body=b"<html>502 Bad Gateway</html>")
    client, _ = make_client(transport)
    result = client.plan_action(MESSAGES, telemetry=CONTEXT)
    assert result.error_category == "llm_malformed_json"
    assert result.llm_output == "<html>502 Bad Gateway</html>"


def test_non_utf8_body_is_malformed():
    transport = FakeTransport(body=b"\xff\xfe\x00broken")
    client, _ = make_client(transport)
    result = client.plan_action(MESSAGES, telemetry=CONTEXT)
    assert result.error_category == "llm_malformed_json"
    assert result.llm_output is None


def test_oversized_body_is_malformed():
    transport = FakeTransport(body=b"x" * (1024 * 1024 + 1))
    client, _ = make_client(transport)
    result = client.plan_action(MESSAGES, telemetry=CONTEXT)
    assert result.error_category == "llm_malformed_json"
    assert "exceeds" in result.detail


def test_content_parts_are_flattened_then_guarded():
    body = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": '{"action":"finish",'},
                            {"type": "text", "text": '"target_id":1,"is_destructive":false}'},
                        ],
                    }
                }
            ]
        }
    ).encode("utf-8")
    client, _ = make_client(FakeTransport(body=body))
    result = client.plan_action(MESSAGES, telemetry=CONTEXT)
    assert isinstance(result, ActionContract)
    assert result.action == "finish"


def test_transport_timeout_yields_llm_timeout_with_null_llm_output():
    events = []
    transport = FakeTransport(
        error=LlmTransportError(
            "llm_timeout", "endpoint did not respond within 5000 ms (config.llm.timeout_ms)"
        )
    )
    client, _ = make_client(transport, events=events)
    dispatcher = RecordingDispatcher()

    result = run_step(client, dispatcher)

    assert result.error_category == "llm_timeout"
    assert result.llm_output is None  # §8.5
    assert dispatcher.calls == []
    assert events[0]["llm_output"] is None
    assert events[0]["error_category"] == "llm_timeout"


def test_http_500_yields_llm_unreachable():
    transport = FakeTransport(status=500, body=b"internal error")
    client, _ = make_client(transport)
    result = client.plan_action(MESSAGES, telemetry=CONTEXT)
    assert result.error_category == "llm_unreachable"
    assert result.llm_output is None
    assert "HTTP 500" in result.detail


def test_http_401_detail_does_not_leak_the_api_key():
    transport = FakeTransport(status=401, body=b'{"error":"invalid api_key=' + API_KEY.encode() + b'"}')
    client, _ = make_client(transport)
    result = client.plan_action(MESSAGES, telemetry=CONTEXT)
    assert result.error_category == "llm_unreachable"
    assert API_KEY not in result.detail
    assert "***" in result.detail


# --------------------------------------------------------------- telemetry
def test_failure_event_has_every_required_field():
    failure = LlmFailure(
        error_category="llm_malformed_json", detail="bad", llm_output="{oops"
    )
    event = build_failure_event(failure, CONTEXT)
    assert set(event) == {
        "timestamp",
        "execution_mode",
        "intent",
        "window_title",
        "tree_snapshot_hash",
        "llm_output",
        "resolved_target",
        "status",
        "error_category",
        "os_error_code",
        "fallback_attempted",
    }
    assert event["timestamp"].endswith("Z")
    assert event["intent"] == CONTEXT.intent
    assert event["tree_snapshot_hash"] == "a" * 64


def test_intent_and_window_title_are_truncated():
    ctx = TelemetryContext(intent="i" * 900, window_title="w" * 400, tree_snapshot_hash="b" * 64)
    event = build_failure_event(
        LlmFailure(error_category="llm_timeout", detail="x", llm_output=None), ctx
    )
    assert len(event["intent"]) == 500
    assert len(event["window_title"]) == 200


def test_all_zero_tree_hash_is_refused():
    with pytest.raises(ValueError):
        TelemetryContext(intent="i", window_title="w", tree_snapshot_hash="0" * 64)


def test_event_sink_requires_a_telemetry_context():
    events = []
    client, _ = make_client(FakeTransport(body=b"not json"), events=events)
    with pytest.raises(ValueError):
        client.plan_action(MESSAGES)
    assert events == []


def test_without_a_sink_no_context_is_needed():
    client, _ = make_client(FakeTransport(body=b"not json"))
    assert isinstance(client.plan_action(MESSAGES), LlmFailure)


def test_api_key_never_reaches_an_event_or_a_detail():
    events = []
    transport = FakeTransport(status=403, body=b"forbidden: " + API_KEY.encode())
    client, _ = make_client(transport, events=events)
    failure = client.plan_action(MESSAGES, telemetry=CONTEXT)
    assert len(events) == 1
    blob = json.dumps(events[0], ensure_ascii=False) + failure.detail
    assert API_KEY not in blob
    assert "Bearer sk" not in blob


def test_long_response_is_truncated_to_1000_chars_in_telemetry():
    events = []
    raw = "x" * 5000
    transport = FakeTransport(body=envelope(raw))
    client, _ = make_client(transport, events=events)
    client.plan_action(MESSAGES, telemetry=CONTEXT)
    assert len(events[0]["llm_output"]) == 1000


def test_chat_returns_the_raw_completion_without_the_guard():
    client, _ = make_client(FakeTransport(body=envelope("free-form text")))
    result = client.chat(MESSAGES, telemetry=CONTEXT)
    assert result.content == "free-form text"
    assert result.model == "qwen3"
    assert result.finish_reason == "stop"
