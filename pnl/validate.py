"""입력 검증 (FR-10)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .fmt import parse_number

MAX_ABS = 999_999_999
NON_NEGATIVE = frozenset({"salesVolume", "revenue"})
#: 입력 가능한 소수 자릿수 = 화면 표시 자릿수
INPUT_DECIMALS = {"salesVolume": 1, "revenue": 0, "operatingProfit": 0, "ordinaryProfit": 0}


@dataclass(frozen=True)
class FieldResult:
    value: float | None
    error: str | None


def validate_field(key: str, raw: str) -> FieldResult:
    value = parse_number(raw)
    if value is None:
        return FieldResult(None, None)
    if math.isnan(value):
        return FieldResult(None, "숫자만 입력할 수 있습니다")
    if value < 0 and key in NON_NEGATIVE:
        return FieldResult(None, "음수는 입력할 수 없습니다")
    if abs(value) > MAX_ABS:
        return FieldResult(None, f"최대 {MAX_ABS:,}까지 입력할 수 있습니다")
    parts = raw.split(".")
    decimals = len(parts[1].strip()) if len(parts) > 1 else 0
    if decimals > INPUT_DECIMALS[key]:
        if INPUT_DECIMALS[key] == 0:
            return FieldResult(None, "정수로 입력하세요")
        return FieldResult(None, f"소수점 {INPUT_DECIMALS[key]}자리까지 입력할 수 있습니다")
    return FieldResult(0 if value == 0 else value, None)


def _draft(key: str, value: float) -> str:
    digits = INPUT_DECIMALS[key]
    text = f"{value:,.{digits}f}"
    # 입력 문자열에서는 불필요한 ".0"을 붙이지 않는다 (1234 → "1,234", 1234.5 → "1,234.5")
    return text[:-2] if digits and text.endswith(".0") else text


def format_draft(key: str, raw: str) -> str:
    """포커스가 빠질 때 쉼표 포맷. 잘못된 값은 그대로 둔다."""
    result = validate_field(key, raw)
    if result.error is not None or result.value is None:
        return raw.strip()
    return _draft(key, result.value)


def to_draft(key: str, value: float | None) -> str:
    return "" if value is None else _draft(key, value)
