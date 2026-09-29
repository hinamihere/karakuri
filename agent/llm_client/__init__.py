"""OpenAI-compatible LLM client with the action-contract schema guard (KARA-10).

Usage::

    from agent.llm_client import LlmClient, LlmConfig, TelemetryContext

    cfg = LlmConfig(base_url="http://localhost:11434/v1", model="llama3")
    client = LlmClient(cfg, on_event=telemetry.append)
    result = client.plan_action(messages, telemetry=TelemetryContext(
        intent="売上をCSVに書き出す",
        window_title="弥生会計 2024 - 仕訳入力",
        tree_snapshot_hash=tree_hash,
    ))
    if isinstance(result, LlmFailure):
        ...  # log already appended; do not dispatch
    else:
        ...  # result is an ActionContract → Mode B dispatches it
"""

from .client import (
    ChatCompletion,
    LlmClient,
    LlmFailure,
    TelemetryContext,
    build_failure_event,
)
from .config import LlmConfig, LlmConfigError, load_llm_config, llm_config_from_document
from .schema_guard import ActionContract, GuardRejection, parse_action_contract, validate_action_contract
from .transport import HttpRequest, HttpResponse, LlmTransportError

__all__ = [
    "ActionContract",
    "ChatCompletion",
    "GuardRejection",
    "HttpRequest",
    "HttpResponse",
    "LlmClient",
    "LlmConfig",
    "LlmConfigError",
    "LlmFailure",
    "LlmTransportError",
    "TelemetryContext",
    "build_failure_event",
    "load_llm_config",
    "llm_config_from_document",
    "parse_action_contract",
    "validate_action_contract",
]
