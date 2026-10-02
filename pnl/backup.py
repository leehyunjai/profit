"""JSON 백업 (FR-22). 웹 버전과 같은 형식이라 서로 주고받을 수 있다."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .calc import INPUT_KEYS
from .categories import CATEGORY_BY_ID
from .validate import validate_field

APP_ID = "pnl-analysis"
FORMAT_VERSION = 1
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def serialize(data: dict, now: datetime | None = None) -> str:
    exported = (now or datetime.now(timezone.utc)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return json.dumps(
        {"app": APP_ID, "version": FORMAT_VERSION, "exportedAt": exported, "data": data},
        ensure_ascii=False,
        indent=2,
    )


@dataclass
class ImportResult:
    ok: bool
    data: dict = field(default_factory=dict)
    record_count: int = 0
    error: str | None = None


def _reject_constant(name: str) -> float:
    # json 모듈은 기본적으로 NaN·Infinity를 허용하므로 막는다
    raise ValueError(name)


def parse(text: str) -> ImportResult:
    """백업 JSON 검증. 하나라도 잘못되면 전체를 거부한다."""
    try:
        parsed = json.loads(text, parse_constant=_reject_constant)
    except ValueError:
        return ImportResult(False, error="JSON 형식이 올바르지 않습니다.")
    if not isinstance(parsed, dict) or parsed.get("app") != APP_ID or not isinstance(parsed.get("data"), dict):
        return ImportResult(False, error="손익 분석 백업 파일이 아닙니다.")
    if parsed.get("version") != FORMAT_VERSION:
        return ImportResult(False, error=f"지원하지 않는 백업 버전입니다: {parsed.get('version')}")

    data: dict = {}
    count = 0
    for month, month_data in parsed["data"].items():
        if not _MONTH.match(month):
            return ImportResult(False, error=f"월 형식이 올바르지 않습니다: {month}")
        if not isinstance(month_data, dict):
            return ImportResult(False, error=f"{month} 데이터 형식이 올바르지 않습니다.")
        data[month] = {}
        for category_id, raw in month_data.items():
            result = _parse_record(month, category_id, raw)
            if isinstance(result, str):
                return ImportResult(False, error=f"{month} / {category_id}: {result}")
            data[month][category_id] = result
            count += 1
    return ImportResult(True, data=data, record_count=count)


def _parse_record(month: str, category_id: str, raw: object) -> dict | str:
    cat = CATEGORY_BY_ID.get(category_id)
    if cat is None or cat.level != 3:
        return "알 수 없는 항목입니다."
    if not isinstance(raw, dict):
        return "데이터 형식이 올바르지 않습니다."

    values: dict = {}
    for key in INPUT_KEYS:
        value = raw.get(key)
        if value is None:
            values[key] = None
            continue
        # bool은 int의 하위 타입이므로 명시적으로 제외
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return f"{key} 값이 숫자가 아닙니다."
        error = validate_field(key, repr(value) if isinstance(value, float) else str(value)).error
        if error:
            return f"{key} {error}"
        values[key] = value

    for flag in ("checked", "needsReview"):
        if flag in raw and not isinstance(raw[flag], bool):
            return f"{flag} 값이 올바르지 않습니다."
    updated_at = raw.get("updatedAt")
    if updated_at is not None:
        try:
            datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
        except ValueError:
            return "updatedAt 값이 올바르지 않습니다."
        if not isinstance(updated_at, str):
            return "updatedAt 값이 올바르지 않습니다."

    return {
        "month": month,
        "categoryId": category_id,
        **values,
        "checked": raw.get("checked") is True,
        "needsReview": raw.get("needsReview") is True,
        "updatedAt": updated_at,
    }
