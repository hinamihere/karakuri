"""End-to-end over a real socket: auth, URL, timeout, non-2xx, redirects.

Everything here runs against a local ``http.server`` bound to 127.0.0.1 on an
ephemeral port — no external endpoint, no cloud dependency (AGENTS.md).
"""

import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent.llm_client import ActionContract, LlmClient, LlmConfig, LlmFailure, TelemetryContext

API_KEY = "sk-local-abcdef123456"
CONTEXT = TelemetryContext(
    intent="売上をCSVに書き出す",
    window_title="弥生会計 2024 - 売上",
    tree_snapshot_hash="c" * 64,
)
MESSAGES = [{"role": "user", "content": "仕訳を入力して"}]


@dataclass
class Reply:
    status: int = 200
    body: bytes = b""
    delay: float = 0.0
    headers: dict = field(default_factory=dict)


def contract_json(action="click", target_id=4, is_destructive=True):
    return json.dumps(
        {"action": action, "target_id": target_id, "is_destructive": is_destructive}
    ).encode("utf-8")


def envelope_bytes(content) -> bytes:
    if isinstance(content, (bytes, bytearray)):
        content = content.decode("utf-8")
    return json.dumps(
        {
            "model": "qwen3",
            "choices": [
                {"message": {"role": "assistant", "content": content}}
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")


class _Recorder(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, reply):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.reply = reply
        self.requests = []

    def handle_error(self, request, client_address):  # client aborts on timeouts
        pass


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        self.server.requests.append(
            {
                "method": "POST",
                "path": self.path,
                "headers": {k.lower(): v for k, v in self.headers.items()},
                "body": body,
            }
        )
        reply = self.server.reply(self.path) if callable(self.server.reply) else self.server.reply
        if reply.delay:
            time.sleep(reply.delay)
        try:
            self.send_response(reply.status)
            self.send_header("Content-Type", "application/json")
            for key, value in reply.headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(reply.body)))
            self.end_headers()
            self.wfile.write(reply.body)
        except OSError:  # peer timed out and hung up
            pass

    def do_GET(self):  # noqa: N802
        self.server.requests.append(
            {"method": "GET", "path": self.path, "headers": {}, "body": b""}
        )
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


@contextmanager
def running_server(reply):
    server = _Recorder(reply)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def make_client(base_url, *, api_key=API_KEY, timeout_ms=5000, events=None):
    cfg = LlmConfig(base_url=base_url, api_key=api_key, model="qwen3", timeout_ms=timeout_ms)
    return LlmClient(cfg, on_event=(events.append if events is not None else None))


def test_post_goes_to_chat_completions_with_bearer_auth():
    reply = Reply(body=envelope_bytes(contract_json()))
    with running_server(reply) as (base_url, server):
        client = make_client(f"{base_url}/v1")
        result = client.plan_action(MESSAGES, telemetry=CONTEXT)

    assert isinstance(result, ActionContract)
    assert result.target_id == 4
    assert len(server.requests) == 1
    request = server.requests[0]
    assert request["method"] == "POST"
    assert request["path"] == "/v1/chat/completions"
    assert request["headers"]["authorization"] == f"Bearer {API_KEY}"
    assert request["headers"]["content-type"] == "application/json"
    payload = json.loads(request["body"].decode("utf-8"))
    assert payload["model"] == "qwen3"
    assert payload["temperature"] == 0.0
    assert payload["stream"] is False
    assert API_KEY not in json.dumps(payload)  # the key never rides in the body


def test_no_authorization_header_without_an_api_key():
    reply = Reply(body=envelope_bytes(contract_json(action="wait", target_id=1, is_destructive=False)))
    with running_server(reply) as (base_url, server):
        make_client(base_url, api_key="").plan_action(MESSAGES, telemetry=CONTEXT)
    assert "authorization" not in server.requests[0]["headers"]


def test_non_2xx_is_llm_unreachable_and_logs_no_output():
    events = []
    with running_server(Reply(status=503, body=b"upstream down")) as (base_url, _):
        result = make_client(base_url, events=events).plan_action(MESSAGES, telemetry=CONTEXT)
    assert isinstance(result, LlmFailure)
    assert result.error_category == "llm_unreachable"
    assert result.llm_output is None
    assert "HTTP 503" in result.detail
    assert len(events) == 1
    assert events[0]["llm_output"] is None


def test_endpoint_timeout_is_llm_timeout():
    events = []
    reply = Reply(body=envelope_bytes(contract_json()), delay=3.0)
    started = time.monotonic()
    with running_server(reply) as (base_url, _):
        result = make_client(base_url, timeout_ms=1000, events=events).plan_action(
            MESSAGES, telemetry=CONTEXT
        )
    elapsed = time.monotonic() - started
    assert result.error_category == "llm_timeout"
    assert result.llm_output is None  # §8.5
    assert elapsed < 2.5, f"timeout did not bound the request: {elapsed:.2f}s"
    assert events[0]["error_category"] == "llm_timeout"


def test_redirects_are_not_followed_and_the_token_is_not_forwarded():
    with running_server(Reply()) as (victim_base, victim):
        reply = Reply(status=302, headers={"Location": f"{victim_base}/steal"})
        with running_server(reply) as (base_url, _):
            result = make_client(base_url).plan_action(MESSAGES, telemetry=CONTEXT)

    assert isinstance(result, LlmFailure)
    assert result.error_category == "llm_unreachable"  # 3xx is a non-2xx status
    assert "302" in result.detail
    assert victim.requests == [], "the redirect target must never be contacted"
    assert API_KEY not in result.detail


def test_malformed_content_over_a_real_socket_is_rejected_without_dispatch():
    events = []
    reply = Reply(body=envelope_bytes("申し訳ありません。うまく処理できませんでした。"))
    with running_server(reply) as (base_url, _):
        client = make_client(base_url, events=events)
        result = client.plan_action(MESSAGES, telemetry=CONTEXT)

    assert result.error_category == "llm_malformed_json"
    assert result.llm_output == "申し訳ありません。うまく処理できませんでした。"
    assert len(events) == 1
    assert events[0]["error_category"] == "llm_malformed_json"


def test_timeout_reaches_the_client_before_the_server_finishes_replying():
    """The socket timeout, not the server, decides when the step fails."""
    reply = Reply(body=envelope_bytes(contract_json()), delay=2.0)
    with running_server(reply) as (base_url, server):
        client = make_client(base_url, timeout_ms=1000)
        started = time.monotonic()
        client.plan_action(MESSAGES, telemetry=CONTEXT)
        elapsed = time.monotonic() - started
        assert elapsed < 1.9
        assert len(server.requests) == 1  # the request did reach the server
