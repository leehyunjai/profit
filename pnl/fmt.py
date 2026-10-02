"""숫자 표시·입력 파싱 (PRD 3.2).

Python의 기본 반올림(f"{0.25:.1f}" → "0.2")은 사사오입이 아니므로 Decimal ROUND_HALF_UP을 쓴다.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

EMPTY = "-"

#: 지표별 표시 소수 자릿수
DECIMALS: dict[str, int] = {
    "salesVolume": 1,
    "revenue": 0,
    "operatingProfit": 0,
    "ordinaryProfit": 0,
    "operatingMargin": 1,
    "ordinaryMargin": 1,
}


def _round(value: float, digits: int) -> Decimal:
    rounded = Decimal(repr(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    return rounded if rounded != 0 else abs(rounded)  # -0 → 0


def format_number(value: float | None, digits: int) -> str:
    if value is None:
        return EMPTY
    return f"{_round(value, digits):,.{digits}f}"


def format_metric(key: str, value: float | None) -> str:
    return format_number(value, DECIMALS[key])


def is_negative_display(key: str, value: float | None) -> bool:
    """화면에 음수로 보이는지. 반올림해 0이 되는 작은 음수는 음수 색을 쓰지 않는다."""
    return value is not None and value < 0 and format_metric(key, value).startswith("-")


_NUMBER = re.compile(r"^-?(\d+\.?\d*|\.\d+)$")


def parse_number(raw: str) -> float | None:
    """쉼표·앞뒤 공백 허용. 빈 값 → None, 숫자가 아니면 NaN."""
    cleaned = raw.replace(",", "").strip()
    if cleaned == "":
        return None
    if not _NUMBER.match(cleaned):
        return math.nan
    number = float(cleaned)
    return int(number) if number.is_integer() and "." not in cleaned else number


def format_datetime(iso: str) -> str:
    """"2026-10-02 14:30" (로컬 시간)"""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    return dt.strftime("%Y-%m-%d %H:%M")
