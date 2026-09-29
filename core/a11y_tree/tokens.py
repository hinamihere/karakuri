"""Token counting for the §9.1 200–500 token budget.

Preferred backend is ``tiktoken`` with ``cl100k_base``, which is what
contracts.md §9.1 names ("a standard tokenizer (cl100k_base or equivalent)").
The stdlib fallback is deliberately conservative — it over-estimates — so a tree
accepted by the fallback can never blow the real budget.
"""

from __future__ import annotations

import math
import re
from typing import Optional

BACKEND_TIKTOKEN = "tiktoken:cl100k_base"
BACKEND_APPROX = "approx:v1"

_tokenizer = None
_tokenizer_loaded = False


def _load_tiktoken():
    global _tokenizer, _tokenizer_loaded
    if _tokenizer_loaded:
        return _tokenizer
    _tokenizer_loaded = True
    try:
        import tiktoken  # type: ignore

        _tokenizer = tiktoken.get_encoding("cl100k_base")
    except Exception:  # pragma: no cover - environment without tiktoken
        _tokenizer = None
    return _tokenizer


# CJK ideographs, kana, hangul and full-width forms: GPT-family BPE spends
# roughly one token per character on these, so counting them 1:1 is safe.
_CJK = re.compile(
    "["
    "぀-ヿ"  # hiragana + katakana
    "㐀-䶿"  # CJK ext A
    "一-鿿"  # CJK unified
    "豈-﫿"  # CJK compatibility
    "가-힯"  # hangul syllables
    "　-〿"  # CJK punctuation
    "＀-￯"  # full-width / half-width forms
    "]"
)


def _script_switches(text: str) -> int:
    """Number of CJK<->non-CJK boundaries in ``text``."""
    switches = 0
    previous = None
    for char in text:
        kind = bool(_CJK.match(char))
        if previous is not None and kind != previous:
            switches += 1
        previous = kind
    return switches


def _approx_count(text: str) -> int:
    """Conservative (over-estimating) token count used when tiktoken is absent.

    cl100k_base spends roughly one token per CJK character, while
    punctuation-dense ASCII (the YAML skeleton: ``bounding_rect: {x: 1100, ...}``)
    costs about one token per 1.8 characters. Both coefficients are deliberately
    biased upward — under-counting would let a tree exceed the §9.1 ceiling
    without ``pruner_budget_exceeded`` being logged, over-counting merely prunes
    a little harder.
    """
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    rest = len(text) - cjk
    # Script switches break BPE merges (`name: 借方科目` costs more than the two
    # runs separately), so charge for every CJK/ASCII boundary.
    switches = _script_switches(text)
    return math.ceil(cjk * 1.3 + rest / 1.8 + switches)


def count_tokens(text: str, *, backend: str = "auto") -> tuple[int, str]:
    """Return ``(token_count, backend_used)``.

    ``backend``: ``auto`` (tiktoken if importable, else the approximation),
    ``tiktoken`` (raise if unavailable), or ``approx`` (force the fallback).
    """
    if backend not in ("auto", "tiktoken", "approx"):
        raise ValueError(f"unknown token backend {backend!r}")
    if backend in ("auto", "tiktoken"):
        enc = _load_tiktoken()
        if enc is not None:
            return len(enc.encode(text, disallowed_special=())), BACKEND_TIKTOKEN
        if backend == "tiktoken":
            raise RuntimeError("tiktoken is not available in this environment")
    return _approx_count(text), BACKEND_APPROX


def within_budget(token_count: int, *, low: int = 200, high: int = 500) -> bool:
    """True when the tree sits inside the §9.1 200–500 window.

    The ceiling is contractual; the floor is a target — simple windows are
    expected to land under it (§9.1 "targets the lower end for simple windows").
    """
    return low <= token_count <= high
