"""월별 실적 저장소 (JSON 파일).

웹 버전의 localStorage 대신 서버의 JSON 파일에 저장한다. 형식은 웹 버전과 같다:
``month → categoryId → record`` (record 키는 camelCase).

- 모든 변경은 잠금 안에서 파일을 새로 읽고(read-modify-write) 원자적으로 교체 저장한다.
  여러 브라우저 탭·세션이 동시에 저장해도 서로의 변경을 덮어쓰지 않는다.
- 값·체크·재검토 표시가 모두 없는 항목은 저장하지 않는다.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path

from .calc import INPUT_KEYS, empty_values
from .categories import CATEGORY_BY_ID

Record = dict
Data = dict[str, dict[str, Record]]

_LOCKS: dict[Path, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(path.resolve(), threading.Lock())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _assert_leaf(category_id: str) -> None:
    cat = CATEGORY_BY_ID.get(category_id)
    if cat is None or cat.level != 3:
        raise ValueError(f"입력 가능한 항목이 아닙니다: {category_id}")


def _empty_record(month: str, category_id: str) -> Record:
    return {"month": month, "categoryId": category_id, **empty_values(), "checked": False, "updatedAt": None}


def _is_blank(record: Record) -> bool:
    return all(record.get(k) is None for k in INPUT_KEYS) and not record.get("checked") and not record.get("needsReview")


def values_equal(a: Record, b: Record) -> bool:
    return all(a.get(k) == b.get(k) for k in INPUT_KEYS)


class Store:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self._lock = _lock_for(self.path)

    # ---------- 읽기 ----------
    def load(self) -> Data:
        """파일 전체. 없거나 손상되면 빈 데이터."""
        try:
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def month(self, month: str) -> dict[str, Record]:
        return self.load().get(month, {})

    # ---------- 쓰기 ----------
    def _write(self, data: Data) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".pnl-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _update_month(
        self,
        month: str,
        category_ids: Iterable[str],
        updater: Callable[[Record | None, str], Record | None],
    ) -> None:
        ids = list(category_ids)
        for cid in ids:
            _assert_leaf(cid)
        with self._lock:
            data = self.load()
            month_data = dict(data.get(month, {}))
            for cid in ids:
                nxt = updater(month_data.get(cid), cid)
                if nxt is None or _is_blank(nxt):
                    month_data.pop(cid, None)
                else:
                    month_data[cid] = nxt
            data[month] = month_data
            self._write(data)

    def save_values(self, month: str, category_id: str, values: dict) -> bool:
        """값 저장 (FR-09, FR-11, FR-20). 값이 그대로면 아무것도 바꾸지 않는다.

        값이 바뀌면 updatedAt 갱신, 검토 완료 상태였다면 체크 해제 + 재검토 필요.
        Returns: 값이 바뀌었는지
        """
        _assert_leaf(category_id)
        changed = False

        def update(current: Record | None, cid: str) -> Record | None:
            nonlocal changed
            cur = current or _empty_record(month, cid)
            if values_equal(cur, values):
                return current
            changed = True
            return {
                **cur,
                **{k: values.get(k) for k in INPUT_KEYS},
                "checked": False,
                "needsReview": bool(cur.get("checked") or cur.get("needsReview")),
                "updatedAt": _now_iso(),
            }

        self._update_month(month, [category_id], update)
        return changed

    def set_checked(self, month: str, category_ids: Iterable[str], checked: bool) -> None:
        """검토 완료 상태 변경 (FR-17). 체크하면 재검토 필요 표시가 사라진다."""

        def update(current: Record | None, cid: str) -> Record:
            cur = current or _empty_record(month, cid)
            return {**cur, "checked": checked, "needsReview": False if checked else bool(cur.get("needsReview"))}

        self._update_month(month, category_ids, update)

    def reset_records(self, month: str, category_ids: Iterable[str]) -> list[Record]:
        """실적 초기화 (FR-12). 실행 취소용 삭제 전 스냅샷을 반환한다."""
        ids = list(category_ids)
        for cid in ids:
            _assert_leaf(cid)
        with self._lock:
            data = self.load()
            month_data = dict(data.get(month, {}))
            snapshot = [copy.deepcopy(month_data[cid]) for cid in ids if cid in month_data]
            if snapshot:
                for cid in ids:
                    month_data.pop(cid, None)
                data[month] = month_data
                self._write(data)
        return snapshot

    def restore_records(self, records: Iterable[Record]) -> None:
        """삭제 실행 취소 (FR-15): 스냅샷을 그대로 되돌린다."""
        by_month: dict[str, dict[str, Record]] = {}
        for r in records:
            by_month.setdefault(r["month"], {})[r["categoryId"]] = r
        for month, by_id in by_month.items():
            self._update_month(month, by_id.keys(), lambda _cur, cid, by_id=by_id: copy.deepcopy(by_id[cid]))

    def replace_month(self, month: str, records: Iterable[Record]) -> None:
        recs = list(records)
        for r in recs:
            _assert_leaf(r["categoryId"])
        with self._lock:
            data = self.load()
            data[month] = {r["categoryId"]: {**r, "month": month} for r in recs}
            self._write(data)

    def replace_all(self, data: Data) -> None:
        """전체 교체 (JSON 가져오기). 검증은 호출 전에 끝나 있어야 한다."""
        with self._lock:
            self._write(data)
