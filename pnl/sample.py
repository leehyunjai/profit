"""개발 확인용 샘플 실적 (웹 버전 src/data/sample.ts와 같은 값)."""

from __future__ import annotations

from datetime import datetime, timezone

SAMPLE: dict[str, dict[str, float]] = {
    "plate-hot-domestic": {"salesVolume": 320.5, "revenue": 2950, "operatingProfit": 255, "ordinaryProfit": 205},
    "plate-hot-export": {"salesVolume": 150.2, "revenue": 1380, "operatingProfit": 98, "ordinaryProfit": 76},
    "plate-cold-domestic": {"salesVolume": 210.8, "revenue": 2420, "operatingProfit": 210, "ordinaryProfit": 172},
    "plate-cold-export": {"salesVolume": 95.4, "revenue": 1105, "operatingProfit": 66, "ordinaryProfit": 51},
    "plate-heavy-domestic": {"salesVolume": 180.0, "revenue": 1890, "operatingProfit": 142, "ordinaryProfit": 118},
    "plate-heavy-export": {"salesVolume": 60.3, "revenue": 655, "operatingProfit": -12, "ordinaryProfit": -25},
    "bar-rebar-domestic": {"salesVolume": 410.7, "revenue": 3520, "operatingProfit": 268, "ordinaryProfit": 221},
    "bar-rebar-export": {"salesVolume": 35.1, "revenue": 290, "operatingProfit": 9, "ordinaryProfit": 4},
    "bar-section-domestic": {"salesVolume": 150.6, "revenue": 1720, "operatingProfit": 131, "ordinaryProfit": 104},
    "bar-section-export": {"salesVolume": 48.9, "revenue": 540, "operatingProfit": 27, "ordinaryProfit": 18},
    "bar-special-domestic": {"salesVolume": 72.4, "revenue": 1260, "operatingProfit": 118, "ordinaryProfit": 95},
    "bar-special-export": {"salesVolume": 30.2, "revenue": 545, "operatingProfit": 41, "ordinaryProfit": 33},
}


def sample_records(month: str) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return [
        {"month": month, "categoryId": cid, **values, "checked": False, "updatedAt": now}
        for cid, values in SAMPLE.items()
    ]
