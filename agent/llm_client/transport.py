"""HTTP transport for the OpenAI-compatible endpoint (contracts.md §5.4, §8.5).

Stdlib only — the project forbids a cloud-mandatory dependency and this must
run on an air-gapped back-office PC. One POST per call, no retries (§8.5: "the
dispatcher does not retry"), no connection reuse, and **redirects are never
followed**: urllib would forward the ``Authorization`` header to the redirect
target, handing the Bearer token to whoever answered. A 3xx is therefore
returned as a response and classified as a non-2xx status by the caller.
"""

from __future__ import annotations

import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Final

#: §8.4 caps the logged response at 1000 chars; reading 1 MiB is already far
#: beyond any action contract, and bounds a hostile endpoint's reach.
MAX_RESPONSE_BYTES: Final[int] = 1024 * 1024


class LlmTransportError(Exception):
    """Socket-level failure, already classified as §2.2's ``llm_*`` category."""

    def __init__(self, error_category: str, detail: str) -> None:
        super().__init__(detail)
        self.error_category = error_category
        self.detail = detail


@dataclass(frozen=True)
class HttpRequest:
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    timeout_s: float = 5.0


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects instead of forwarding the Bearer token cross-origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            f"HTTP {code} redirect refused — Karakuri never follows redirects",
            headers,
            fp,
        )


_OPENER = urllib.request.build_opener(_NoRedirectHandler())


def urllib_transport(request: HttpRequest) -> HttpResponse:
    """Blocking ``POST`` via :mod:`urllib`.

    Raises :class:`LlmTransportError` for timeout (``llm_timeout``) and for a
    connection failure (``llm_unreachable``). Non-2xx statuses — including the
    refused redirect — come back as :class:`HttpResponse`; §8.5 makes every one
    of them ``llm_unreachable``.
    """
    req = urllib.request.Request(
        request.url,
        data=request.body,
        headers=dict(request.headers),
        method="POST",
    )
    try:
        with _OPENER.open(req, timeout=request.timeout_s) as response:
            return HttpResponse(status=response.status, body=response.read(MAX_RESPONSE_BYTES + 1))
    except urllib.error.HTTPError as exc:
        # 3xx from _NoRedirectHandler and every 4xx/5xx land here.
        try:
            body = exc.read(MAX_RESPONSE_BYTES + 1)
        except Exception:  # pragma: no cover - unreadable error body
            body = b""
        finally:
            exc.close()
        return HttpResponse(status=exc.code, body=body)
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise LlmTransportError("llm_timeout", _timeout_detail(request)) from None
        if isinstance(reason, OSError):
            raise LlmTransportError(
                "llm_unreachable", f"connection failed: {reason}"
            ) from None
        raise LlmTransportError(
            "llm_unreachable", f"connection failed: {reason!r}"
        ) from None
    except (TimeoutError, socket.timeout):
        raise LlmTransportError("llm_timeout", _timeout_detail(request)) from None
    except OSError as exc:
        # Connection reset mid-body, TLS failure, network unreachable.
        raise LlmTransportError(
            "llm_unreachable", f"connection failed: {exc}"
        ) from None


def _timeout_detail(request: HttpRequest) -> str:
    return (
        f"endpoint did not respond within {int(request.timeout_s * 1000)} ms "
        "(config.llm.timeout_ms)"
    )
