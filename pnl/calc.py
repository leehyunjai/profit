"""집계·비율 계산 (PRD 3.1).

- 합산 지표는 하위 합 (미입력은 0 취급, 모두 미입력이면 None)
- 비율 지표는 하위 비율을 합치지 않고 집계된 이익 ÷ 집계된 매출 × 100으로 재계산
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .categories import ROOT_ID, children

INPUT_KEYS: tuple[str, ...] = ("salesVolume", "revenue", "operatingProfit", "ordinaryProfit")
RATIO_KEYS: tuple[str, ...] = ("operatingMargin", "ordinaryMargin")

Values = dict[str, float | None]


def empty_values() -> Values:
    return {key: None for key in INPUT_KEYS}


def sum_values(values: Iterable[float | None]) -> float | None:
    entered = [v for v in values if v is not None]
    if not entered:
        return None
    # 부동소수점 누적 오차 제거 (0.1 + 0.2 → 0.3)
    return round(sum(entered), 6)


def ratio(profit: float | None, revenue: float | None) -> float | None:
    if revenue is None or revenue == 0 or profit is None:
        return None
    return profit / revenue * 100


def to_metrics(values: Mapping[str, float | None]) -> dict[str, float | None]:
    metrics = {key: values.get(key) for key in INPUT_KEYS}
    metrics["operatingMargin"] = ratio(metrics["operatingProfit"], metrics["revenue"])
    metrics["ordinaryMargin"] = ratio(metrics["ordinaryProfit"], metrics["revenue"])
    return metrics


def compute_all(leaf_values: Mapping[str, Mapping[str, float | None]], root_id: str = ROOT_ID) -> dict[str, dict]:
    """모든 카테고리의 지표. leaf_values: L3 id → 입력 값 (없으면 미입력)."""
    result: dict[str, dict] = {}

    def visit(category_id: str) -> Values:
        kids = children(category_id)
        if not kids:
            values = {key: leaf_values.get(category_id, {}).get(key) for key in INPUT_KEYS}
        else:
            child_values = [visit(child.id) for child in kids]
            values = {key: sum_values(cv[key] for cv in child_values) for key in INPUT_KEYS}
        result[category_id] = to_metrics(values)
        return values

    visit(root_id)
    return result
