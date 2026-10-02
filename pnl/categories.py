"""고정 카테고리 마스터 (PRD 2장, 5.1)."""

from __future__ import annotations

from dataclasses import dataclass

ROOT_ID = "total"


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    parent_id: str | None
    level: int  # 0: 전사, 1: 사업부, 2: 품목, 3: 내수/수출 (입력 항목)
    order: int


_SALES_TYPES = (("domestic", "내수"), ("export", "수출"))

_DIVISIONS = (
    ("plate", "판재", (("plate-hot", "열연"), ("plate-cold", "냉연"), ("plate-heavy", "후판"))),
    ("bar", "봉형강", (("bar-rebar", "철근"), ("bar-section", "형강"), ("bar-special", "특수강"))),
)


def _build() -> list[Category]:
    cats = [Category(ROOT_ID, "전사", None, 0, 0)]
    for d, (div_id, div_name, products) in enumerate(_DIVISIONS):
        cats.append(Category(div_id, div_name, ROOT_ID, 1, d))
        for p, (prod_id, prod_name) in enumerate(products):
            cats.append(Category(prod_id, prod_name, div_id, 2, p))
            for t, (suffix, type_name) in enumerate(_SALES_TYPES):
                cats.append(Category(f"{prod_id}-{suffix}", type_name, prod_id, 3, t))
    return cats


CATEGORIES: tuple[Category, ...] = tuple(_build())
CATEGORY_BY_ID: dict[str, Category] = {c.id: c for c in CATEGORIES}
LEAF_IDS: tuple[str, ...] = tuple(c.id for c in CATEGORIES if c.level == 3)


def children(parent_id: str) -> list[Category]:
    return sorted((c for c in CATEGORIES if c.parent_id == parent_id), key=lambda c: c.order)


def flatten(root_id: str = ROOT_ID) -> list[Category]:
    """화면 표시 순서(깊이 우선)."""
    root = CATEGORY_BY_ID.get(root_id)
    if root is None:
        return []
    out = [root]
    for child in children(root_id):
        out.extend(flatten(child.id))
    return out


def path(category_id: str) -> list[str]:
    """["전사", "판재", "열연", "내수"]"""
    names: list[str] = []
    current = CATEGORY_BY_ID.get(category_id)
    while current is not None:
        names.insert(0, current.name)
        current = CATEGORY_BY_ID.get(current.parent_id) if current.parent_id else None
    return names


def path_label(category_id: str) -> str:
    """"판재 > 열연 > 내수" (전사 제외). 전사는 "전사"."""
    parts = path(category_id)
    return " > ".join(parts[1:]) if len(parts) > 1 else parts[0]


def leaf_ids_under(category_id: str) -> list[str]:
    cat = CATEGORY_BY_ID.get(category_id)
    if cat is None:
        return []
    if cat.level == 3:
        return [category_id]
    return [leaf for child in children(category_id) for leaf in leaf_ids_under(child.id)]


def ancestor_ids(category_id: str) -> list[str]:
    ids: list[str] = []
    cat = CATEGORY_BY_ID.get(category_id)
    parent = cat.parent_id if cat else None
    while parent:
        ids.append(parent)
        parent = CATEGORY_BY_ID[parent].parent_id
    return ids
