"""UTF-16 handling (contracts.md §3.2 truncation limits, UTF-8 end to end)."""

from __future__ import annotations

import pytest

from core.a11y_tree import (
    MAX_NAME_UTF16_UNITS,
    MAX_VALUE_UTF16_UNITS,
    coerce_text,
    repair_lone_surrogates,
    utf16_len,
    utf16_truncate,
)


def test_utf16_len_counts_code_units_not_code_points():
    assert utf16_len("abc") == 3
    assert utf16_len("保存") == 2
    # U+1F600 GRINNING FACE needs a surrogate pair in UTF-16
    assert utf16_len("😀") == 2
    assert len("😀") == 1


def test_truncate_keeps_whole_characters():
    text = "あいうえおかきくけこ"  # 10 units
    assert utf16_truncate(text, 4) == "あいうえ"
    assert utf16_truncate(text, 10) == text
    assert utf16_truncate(text, 99) == text


def test_truncate_never_splits_a_surrogate_pair():
    text = "😀" * 10  # 20 units
    cut = utf16_truncate(text, 5)  # lands between the pairs of the 3rd emoji
    assert cut == "😀😀"
    # the result must always be encodable as strict UTF-8
    cut.encode("utf-8")


@pytest.mark.parametrize("units", range(0, 24))
def test_every_truncation_point_is_utf8_safe(units):
    text = "a😀い😀b"
    cut = utf16_truncate(text, units)
    cut.encode("utf-8")  # would raise on a split surrogate
    assert utf16_len(cut) <= units


def test_name_limit_is_120_and_value_limit_is_200():
    assert MAX_NAME_UTF16_UNITS == 120
    assert MAX_VALUE_UTF16_UNITS == 200
    long_name = "名" * 300
    assert utf16_len(utf16_truncate(long_name, MAX_NAME_UTF16_UNITS)) == 120
    long_value = "値" * 500
    assert utf16_len(utf16_truncate(long_value, MAX_VALUE_UTF16_UNITS)) == 200


def test_lone_surrogate_is_repaired_so_utf8_encoding_works():
    broken = "abc\ud800def"
    repaired = repair_lone_surrogates(broken)
    assert "�" in repaired
    repaired.encode("utf-8")  # must not raise


def test_coerce_text_accepts_str_bytes_and_none():
    assert coerce_text(None, field="name") == ""
    assert coerce_text("保存", field="name") == "保存"
    assert coerce_text("保存".encode("utf-8"), field="name") == "保存"
    # UTF-16LE with BOM is what a native adapter hands over
    assert coerce_text("保存".encode("utf-16"), field="name") == "保存"
    # BOM-less UTF-16 is indistinguishable from UTF-8 here: fail loudly rather
    # than guess and emit mojibake. CP932 is never accepted at this boundary.
    with pytest.raises(UnicodeDecodeError):
        coerce_text("保存".encode("utf-16-le"), field="name")


def test_coerce_text_rejects_unexpected_types():
    with pytest.raises(TypeError):
        coerce_text(123, field="name")


def test_no_cp932_silently_accepted_at_this_boundary():
    # CP932 bytes for 保存 are invalid UTF-8 -> strict decode fails loudly
    with pytest.raises(UnicodeDecodeError):
        coerce_text("保存".encode("cp932"), field="name")
