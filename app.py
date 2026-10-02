"""손익 분석 — Streamlit 버전.

실행: streamlit run app.py
데이터 파일: 환경 변수 PNL_DATA_FILE (기본 data/pnl_data.json)
"""

from __future__ import annotations

import html
import math
import os
import time
from datetime import date
from pathlib import Path

import streamlit as st

from pnl import backup, excel
from pnl.calc import INPUT_KEYS, compute_all, to_metrics
from pnl.categories import CATEGORY_BY_ID, LEAF_IDS, ancestor_ids, flatten, leaf_ids_under, path_label
from pnl.fmt import format_datetime, format_metric, is_negative_display
from pnl.sample import sample_records
from pnl.storage import Store
from pnl.validate import format_draft, to_draft, validate_field

APP_DIR = Path(__file__).parent
DATA_FILE = Path(os.environ.get("PNL_DATA_FILE", APP_DIR / "data" / "pnl_data.json"))
UNDO_SECONDS = 5
ROWS = flatten()
COLLAPSIBLE = [c.id for c in ROWS if c.level < 3]
LABELS = {key: (name, unit) for key, name, unit in excel.COLUMNS}

st.set_page_config(page_title="손익 분석", page_icon="📊", layout="wide")


def store() -> Store:
    return Store(DATA_FILE)


# ---------------------------------------------------------------- 상태
def init_state() -> None:
    today = date.today()
    defaults = {
        "sel_year": today.year,
        "sel_month": today.month,
        "collapsed": set(),
        "undo": None,  # {"records": [...], "at": float, "msg": str}
        "flash": [],  # [(kind, message)]
        "edit_sid": 0,
        "uploader_n": 0,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def current_month() -> str:
    return f"{st.session_state.sel_year}-{st.session_state.sel_month:02d}"


def flash(kind: str, message: str) -> None:
    st.session_state.flash.append((kind, message))


# ---------------------------------------------------------------- 콜백
def shift_month(delta: int) -> None:
    index = st.session_state.sel_year * 12 + (st.session_state.sel_month - 1) + delta
    st.session_state.sel_year, st.session_state.sel_month = index // 12, index % 12 + 1


def toggle_collapse(category_id: str) -> None:
    st.session_state.collapsed ^= {category_id}


def set_all_collapsed(collapsed: bool) -> None:
    st.session_state.collapsed = set(COLLAPSIBLE) if collapsed else set()


def toggle_check(month: str, category_id: str, state: str) -> None:
    store().set_checked(month, leaf_ids_under(category_id), state != "checked")


def load_sample(month: str) -> None:
    store().replace_month(month, sample_records(month))
    flash("success", f"{excel.month_label(month)} 샘플 데이터를 넣었습니다.")


def format_draft_cb(widget_key: str, metric: str) -> None:
    st.session_state[widget_key] = format_draft(metric, st.session_state[widget_key])


# ---------------------------------------------------------------- 다이얼로그
@st.dialog("실적 수정")
def edit_dialog(month: str, category_id: str) -> None:
    record = store().month(month).get(category_id) or {}
    sid = st.session_state.edit_sid
    keys = {k: f"draft-{sid}-{k}" for k in INPUT_KEYS}
    for k in INPUT_KEYS:
        st.session_state.setdefault(keys[k], to_draft(k, record.get(k)))

    st.markdown(
        f"<div class='dlg-path'>{excel.month_label(month)} · <b>{html.escape(path_label(category_id))}</b></div>",
        unsafe_allow_html=True,
    )
    results = {}
    grid = st.columns(2)
    for i, k in enumerate(INPUT_KEYS):
        name, unit = LABELS[k]
        with grid[i % 2]:
            st.text_input(f"{name}({unit})", key=keys[k], placeholder="-", on_change=format_draft_cb, args=(keys[k], k))
            results[k] = validate_field(k, st.session_state[keys[k]])
            if results[k].error:
                st.markdown(f"<div class='field-error' role='alert'>{results[k].error}</div>", unsafe_allow_html=True)

    has_error = any(r.error for r in results.values())
    values = {k: results[k].value for k in INPUT_KEYS}
    preview = to_metrics(values)
    st.markdown(
        "<div class='dlg-preview' aria-live='polite'>"
        f"이익률 <b data-testid='preview-op'>{format_metric('operatingMargin', preview['operatingMargin'])}</b>% · "
        f"경상이익률 <b data-testid='preview-ord'>{format_metric('ordinaryMargin', preview['ordinaryMargin'])}</b>%"
        "<span class='hint'>입력 후 Enter 또는 다른 칸을 누르면 반영됩니다</span></div>",
        unsafe_allow_html=True,
    )
    cancel_col, save_col = st.columns(2)
    if cancel_col.button("취소", key="dlg-cancel-edit", use_container_width=True):
        st.rerun()
    if save_col.button("저장", key="dlg-save-edit", type="primary", disabled=has_error, use_container_width=True):
        store().save_values(month, category_id, values)
        # 삭제 후 다시 입력한 값이 실행 취소로 덮어써지지 않도록 닫는다
        st.session_state.undo = None
        st.rerun()


def open_edit(month: str, category_id: str) -> None:
    st.session_state.edit_sid += 1  # 매번 새 입력값으로 시작
    edit_dialog(month, category_id)


@st.dialog("실적 삭제")
def delete_dialog(month: str, category_ids: list[str], message: str) -> None:
    st.markdown(f"<div class='dlg-message'>{message}</div>", unsafe_allow_html=True)
    cancel_col, delete_col = st.columns(2)
    if cancel_col.button("취소", key="dlg-cancel-delete", use_container_width=True):
        st.rerun()
    with delete_col.container(key="danger"):
        confirmed = st.button("삭제", key="dlg-confirm-delete", type="primary", use_container_width=True)
    if confirmed:
        snapshot = store().reset_records(month, category_ids)
        if snapshot:
            # 새 삭제가 이전 실행 취소를 대체한다 (이전 삭제는 확정)
            st.session_state.undo = {
                "records": snapshot,
                "at": time.time(),
                "msg": f"{excel.month_label(month)} {len(snapshot)}개 항목 실적을 삭제했습니다.",
            }
        st.rerun()


@st.dialog("데이터 가져오기")
def import_dialog(result: backup.ImportResult, filename: str) -> None:
    st.markdown(
        f"<div class='dlg-message'>현재 저장된 모든 데이터를 \"{html.escape(filename)}\"의 "
        f"<b>{result.record_count}개 항목</b>으로 대체합니다. 계속하시겠습니까?</div>",
        unsafe_allow_html=True,
    )
    cancel_col, ok_col = st.columns(2)
    if cancel_col.button("취소", key="dlg-cancel-import", use_container_width=True):
        st.session_state.uploader_n += 1
        st.rerun()
    if ok_col.button("가져오기", key="dlg-confirm-import", type="primary", use_container_width=True):
        store().replace_all(result.data)
        st.session_state.uploader_n += 1
        flash("success", f"{result.record_count}개 항목을 가져왔습니다.")
        st.rerun()


# ---------------------------------------------------------------- 화면 조각
def check_state(category_id: str, checked: set[str]) -> str:
    leaves = leaf_ids_under(category_id)
    count = sum(leaf in checked for leaf in leaves)
    return "unchecked" if count == 0 else "checked" if count == len(leaves) else "mixed"


def value_class(key: str, value: float | None) -> str:
    if value is None:
        return "empty"
    text = format_metric(key, value)
    # 열 폭을 넘는 긴 숫자는 글자를 줄여 잘리지 않게 한다 (style.css .long·.xlong)
    size = "xlong" if len(text) >= 15 else "long" if len(text) >= 12 else ""
    return f"{'neg' if is_negative_display(key, value) else ''} {size}".strip()


def render_header(month: str, metrics: dict) -> None:
    with st.container(key="app-header"):
        title_col, nav_col, data_col = st.columns([4, 3.2, 1.2], vertical_alignment="center")
        title_col.markdown(
            "<div class='brand'><div class='logo'>📊</div><div><h1>손익 분석</h1>"
            "<p>월별 손익 실적 관리</p></div></div>",
            unsafe_allow_html=True,
        )
        with nav_col.container(key="month-nav"):
            prev_col, year_col, month_col, next_col = st.columns([0.6, 1.4, 1.1, 0.6], vertical_alignment="center")
            prev_col.button("◀", key="prev-month", help="이전 월", on_click=shift_month, args=(-1,))
            year = st.session_state.sel_year
            year_col.selectbox("연도", range(year - 5, year + 6), key="sel_year", format_func=lambda y: f"{y}년", label_visibility="collapsed")
            month_col.selectbox("월", range(1, 13), key="sel_month", format_func=lambda m: f"{m}월", label_visibility="collapsed")
            next_col.button("▶", key="next-month", help="다음 월", on_click=shift_month, args=(1,))
        with data_col.popover("데이터", icon=":material/download:", use_container_width=True):
            st.download_button(
                "엑셀 내보내기",
                data=excel.to_xlsx(month, metrics),
                file_name=f"손익분석_{month}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                icon=":material/table_view:",
                use_container_width=True,
            )
            st.download_button(
                "JSON 내보내기",
                data=backup.serialize(store().load()),
                file_name=f"손익분석_백업_{date.today():%Y%m%d}.json",
                mime="application/json",
                icon=":material/data_object:",
                use_container_width=True,
            )
            st.file_uploader("JSON 가져오기", type=["json"], key=f"uploader-{st.session_state.uploader_n}")
            st.divider()
            st.button("샘플 데이터 넣기", icon=":material/database:", on_click=load_sample, args=(month,), use_container_width=True)


def render_summary(metrics: dict) -> None:
    total, plate, bar = metrics["total"], metrics["plate"], metrics["bar"]

    def card(key: str, label: str, unit: str, detail: str) -> str:
        display = format_metric(key, total[key])
        # 자릿수가 많으면 카드 너비(cqw)에 맞춰 글자를 줄인다 (단위 줄바꿈 방지)
        size = f"min(28px, calc((100cqw - 3rem) / {len(display) * 0.62:.2f}))"
        return (
            f"<div class='card'><div class='card-label'>전사 {label}</div>"
            f"<div class='card-value'><span class='{value_class(key, total[key])}' style='font-size:{size}'>{display}</span>"
            f"<span class='unit'>{unit}</span></div><div class='card-detail'>{detail}</div></div>"
        )

    vol, rev = "salesVolume", "revenue"
    cards = [
        card(vol, "판매량", "천톤", f"판재 {format_metric(vol, plate[vol])} · 봉형강 {format_metric(vol, bar[vol])}"),
        card(rev, "매출", "억원", f"판재 {format_metric(rev, plate[rev])} · 봉형강 {format_metric(rev, bar[rev])}"),
        card("operatingProfit", "영업이익", "억원", f"이익률 {format_metric('operatingMargin', total['operatingMargin'])}%"),
        card("ordinaryProfit", "경상이익", "억원", f"경상이익률 {format_metric('ordinaryMargin', total['ordinaryMargin'])}%"),
    ]
    st.markdown(f"<section class='cards' aria-label='전사 실적 요약'>{''.join(cards)}</section>", unsafe_allow_html=True)


def render_toolbar(month: str, checked: set[str]) -> None:
    with st.container(key="toolbar"):
        progress_col, expand_col, collapse_col, delete_col = st.columns([5, 1.25, 1.1, 1.25], vertical_alignment="center")
        n = len(checked)
        with progress_col:
            st.markdown(
                f"<div class='progress' data-testid='review-progress'>검토 완료 <b>{n}</b> / {len(LEAF_IDS)}"
                f"<div class='bar' role='progressbar' aria-label='검토 진행률' aria-valuemin='0' "
                f"aria-valuemax='{len(LEAF_IDS)}' aria-valuenow='{n}'><div style='width:{n / len(LEAF_IDS) * 100:.1f}%'></div></div></div>",
                unsafe_allow_html=True,
            )
        expand_col.button("전체 펼치기", icon=":material/unfold_more:", on_click=set_all_collapsed, args=(False,), type="tertiary")
        collapse_col.button("전체 접기", icon=":material/unfold_less:", on_click=set_all_collapsed, args=(True,), type="tertiary")
        if delete_col.button("선택 삭제", icon=":material/delete:", key="bulk-delete", disabled=n == 0, help="체크한 항목 삭제"):
            ids = [leaf for leaf in LEAF_IDS if leaf in checked]
            delete_dialog(month, ids, f"{excel.month_label(month)} 선택한 <b>{len(ids)}개 항목</b> 실적을 삭제하시겠습니까?")


COL_WIDTHS = [0.42, 2.5, 8.4, 1.3]


def render_table(month: str, records: dict, metrics: dict, checked: set[str]) -> None:
    collapsed: set[str] = st.session_state.collapsed
    with st.container(key="pnl-table"):
        with st.container(key="row-header"):
            cols = st.columns(COL_WIDTHS, vertical_alignment="center")
            cols[1].markdown("<div class='th'>구분</div>", unsafe_allow_html=True)
            heads = "".join(f"<span>{name}<small>({unit})</small></span>" for _, name, unit in excel.COLUMNS)
            cols[2].markdown(f"<div class='nums th'>{heads}</div>", unsafe_allow_html=True)
            cols[3].markdown("<div class='th center'>관리</div>", unsafe_allow_html=True)

        for cat in ROWS:
            if any(a in collapsed for a in ancestor_ids(cat.id)):
                continue
            render_row(month, cat.id, records.get(cat.id), metrics[cat.id], checked, collapsed)


def render_row(month, category_id, record, m, checked, collapsed) -> None:
    cat = CATEGORY_BY_ID[category_id]
    is_leaf = cat.level == 3
    label = path_label(category_id)
    state = check_state(category_id, checked)

    with st.container(key=f"row-l{cat.level}-{category_id}"):
        check_col, name_col, nums_col, action_col = st.columns(COL_WIDTHS, vertical_alignment="center")
        # 체크 상태가 바뀌면 key가 바뀌어 위젯이 새 값으로 다시 만들어진다
        check_col.checkbox(
            f"{label} 선택",
            value=state == "checked",
            key=f"chk-{month}-{category_id}-{state}",
            label_visibility="collapsed",
            on_change=toggle_check,
            args=(month, category_id, state),
        )

        if is_leaf:
            title = f"최종 수정: {format_datetime(record['updatedAt'])}" if record and record.get("updatedAt") else ""
            badges = ""
            if record and record.get("checked"):
                badges += "<span class='badge badge-reviewed'>✔ 검토 완료</span>"
            if record and record.get("needsReview"):
                badges += "<span class='badge badge-review'>재검토 필요</span>"
            name_col.markdown(
                f"<div class='name' title='{html.escape(title)}'>{cat.name}{badges}</div>", unsafe_allow_html=True
            )
        else:
            is_collapsed = category_id in collapsed
            name_col.button(
                f"{'▶' if is_collapsed else '▼'} {cat.name}",
                key=f"toggle-{category_id}",
                type="tertiary",
                help=("펼치기" if is_collapsed else "접기") + " · 자동 집계 (읽기 전용)",
                on_click=toggle_collapse,
                args=(category_id,),
            )

        cells = "".join(
            f"<span class='{value_class(key, m[key])}'>{format_metric(key, m[key])}</span>" for key, _, _ in excel.COLUMNS
        )
        nums_col.markdown(f"<div class='nums' data-row='{category_id}'>{cells}</div>", unsafe_allow_html=True)

        if is_leaf:
            has_values = bool(record) and any(record.get(k) is not None for k in INPUT_KEYS)
            if action_col.button("수정", key=f"edit-{category_id}", type="tertiary", help=f"{label} 수정"):
                open_edit(month, category_id)
            if action_col.button(
                "삭제",
                key=f"delete-{category_id}",
                type="tertiary",
                disabled=not has_values,
                help=f"{label} 삭제" if has_values else "삭제할 실적이 없습니다",
            ):
                delete_dialog(
                    month,
                    [category_id],
                    f"{excel.month_label(month)} <b>{html.escape(label)}</b> 실적을 삭제하시겠습니까?",
                )
        elif state != "unchecked":
            leaves = leaf_ids_under(category_id)
            done = sum(leaf in checked for leaf in leaves)
            action_col.markdown(
                f"<div class='center'><span class='badge {'badge-reviewed' if state == 'checked' else 'badge-partial'}'>"
                f"검토 {done}/{len(leaves)}</span></div>",
                unsafe_allow_html=True,
            )


@st.fragment(run_every=0.5)
def undo_banner() -> None:
    undo = st.session_state.undo
    if not undo:
        return
    left = UNDO_SECONDS - (time.time() - undo["at"])
    if left <= 0:
        st.session_state.undo = None
        return
    with st.container(key="undo-banner"):
        msg_col, btn_col = st.columns([4, 1.6], vertical_alignment="center")
        msg_col.markdown(f"<div role='status'>✅ {undo['msg']}</div>", unsafe_allow_html=True)
        if btn_col.button(f"실행 취소 ({math.ceil(left)}초)", key="undo-btn", type="tertiary"):
            store().restore_records(undo["records"])
            st.session_state.undo = None
            st.rerun(scope="app")


# ---------------------------------------------------------------- 메인
def main() -> None:
    init_state()
    st.markdown(f"<style>{(APP_DIR / 'style.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

    month = current_month()
    records = store().month(month)
    metrics = compute_all(records)
    checked = {cid for cid, r in records.items() if r.get("checked")}

    render_header(month, metrics)

    # 가져오기: 파일을 고르면 검증 → 확인 다이얼로그
    uploaded = st.session_state.get(f"uploader-{st.session_state.uploader_n}")
    if uploaded is not None:
        result = backup.parse(uploaded.getvalue().decode("utf-8", errors="replace"))
        if result.ok:
            import_dialog(result, uploaded.name)
        else:
            st.session_state.uploader_n += 1
            flash("error", f"가져오기 실패: {result.error}")

    for kind, message in st.session_state.flash:
        if kind == "error":
            st.error(message, icon=":material/error:")
        else:
            st.toast(message, icon="✅")
    st.session_state.flash = []

    st.markdown(
        f"<div class='page-title'><h2>{excel.month_label(month)} 실적</h2>"
        "<span>단위: 판매량 천톤 · 매출·이익 억원 · 이익률 %</span></div>",
        unsafe_allow_html=True,
    )
    render_summary(metrics)
    with st.container(key="pnl-section"):
        render_toolbar(month, checked)
        render_table(month, records, metrics, checked)
    st.caption("내수·수출 행의 ‘수정’으로 값을 입력합니다. 상위 행은 자동 집계되며 이익률은 집계된 매출 대비로 다시 계산됩니다.")

    if st.session_state.undo:
        undo_banner()


main()
