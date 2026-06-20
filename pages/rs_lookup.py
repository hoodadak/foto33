"""
pages/rs_lookup.py
──────────────────
RS Rating 조회 페이지
- 종목명 또는 종목코드 입력 → 현재 RS + 일별/주별/월별 RS 변화 그래프
- 최대 5개 종목 동시 비교
"""

import streamlit as st
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import timezone, timedelta
KST = timezone(timedelta(hours=9))

try:
    from rs_rating import (
        fetch_rs_ratings, fetch_rs_history, resample_rs_history,
        search_code_by_name, fetch_stock_name,
        rs_rating_label, _detect_market,
    )
    RS_AVAILABLE = True
except ImportError:
    RS_AVAILABLE = False

# ── 페이지 설정 ──────────────────────────────────────────────────────
st.set_page_config(page_title="RS Rating 조회", layout="wide")

with st.sidebar:
    st.markdown("### 📊 메뉴")
    st.page_link("app.py",              label="🏠 주도테마")
    st.page_link("pages/rs_lookup.py",  label="📈 RS Rating 조회")
    st.markdown("---")
    st.caption("RS Rating: 오닐 방식\n52주×0.7 + 13주×0.3")

# ── CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
.stApp { background-color: #ABABAB; }
.rs-badge {
    display: inline-block; padding: 4px 14px; border-radius: 8px;
    font-size: 28px; font-weight: 900; color: white; margin: 4px 0;
}
.rs-meta { font-size: 13px; color: #64748b; margin-top: 2px; }
.stock-header {
    background: #1e3a5f; border-radius: 8px; padding: 12px 16px;
    color: white; margin-bottom: 10px;
}
.section-label {
    font-size: 13px; font-weight: 700; color: #475569;
    background: #e2e8f0; border-radius: 4px;
    padding: 2px 8px; display: inline-block; margin-bottom: 4px;
}
</style>
""", unsafe_allow_html=True)

st.title("📈 RS Rating 조회")
st.caption("오닐(William O'Neil) 방식 — 52주×0.7 + 13주×0.3 복합 수익률 기준 백분위")

if not RS_AVAILABLE:
    st.error("rs_rating.py를 찾을 수 없습니다. 프로젝트 루트에 파일이 있는지 확인하세요.")
    st.stop()

# ── 캐시 ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def cached_rs_history(code: str):
    return fetch_rs_history(code)          # 2년 전체 일별 반환

@st.cache_data(ttl=86400, show_spinner=False)
def cached_current_rs(codes_tuple: tuple):
    return fetch_rs_ratings(list(codes_tuple))

@st.cache_data(ttl=3600, show_spinner=False)
def cached_search(query: str):
    return search_code_by_name(query)

@st.cache_data(ttl=86400, show_spinner=False)
def cached_stock_name(code: str):
    return fetch_stock_name(code)

# ── 상수 ─────────────────────────────────────────────────────────────
COLORS = ["#ef4444", "#3b82f6", "#16a34a", "#f59e0b", "#8b5cf6"]

def rs_badge_color(rs: int) -> str:
    if rs >= 90: return "#dc2626"
    if rs >= 80: return "#ea580c"
    if rs >= 60: return "#65a30d"
    if rs >= 40: return "#94a3b8"
    return "#475569"

# ── 입력 UI ──────────────────────────────────────────────────────────
st.markdown("#### 종목 입력 (최대 5개, 쉼표로 구분)")

col_input, col_btn = st.columns([5, 1])
with col_input:
    user_input = st.text_input(
        "종목 입력",
        placeholder="예: 삼성전자, 005930, 카카오, HLB",
        label_visibility="collapsed",
        key="rs_input",
    )
with col_btn:
    search_clicked = st.button("🔍 조회", use_container_width=True, type="primary")

# ── 입력 파싱 ────────────────────────────────────────────────────────
def parse_input(raw: str) -> list:
    items, seen = [], set()
    for token in raw.replace("，", ",").split(","):
        token = token.strip()
        if not token:
            continue
        if token.isdigit() and len(token) == 6:
            code = token
            if code not in seen:
                items.append({"code": code, "name": cached_stock_name(code)})
                seen.add(code)
        else:
            results = cached_search(token)
            if results:
                best = results[0]
                if best["code"] not in seen:
                    items.append({"code": best["code"], "name": best["name"]})
                    seen.add(best["code"])
            else:
                items.append({"code": None, "name": token})
    return items[:5]

# ── Plotly RS+주가 이중축 그래프 생성 함수 ──────────────────────────
def make_rs_price_fig(df_day, df_week, df_month, stock_name: str, color: str):
    """
    일별 / 주별 / 월별 RS + 주가 이중축 차트 3개를 세로로 쌓아 반환.
    """
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        figs = []
        datasets = [
            ("일별 RS (최근 60거래일)",  df_day.tail(60)  if df_day  is not None else None, "day"),
            ("주별 RS (최근 52주)",       df_week.tail(52) if df_week is not None else None, "week"),
            ("월별 RS (최근 24개월)",     df_month.tail(24) if df_month is not None else None, "month"),
        ]

        fill_rgba = (
            f"rgba({int(color[1:3],16)},"
            f"{int(color[3:5],16)},"
            f"{int(color[5:7],16)},0.13)"
        )

        for title, df, key in datasets:
            if df is None or df.empty:
                continue

            fig = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                row_heights=[0.62, 0.38],
                vertical_spacing=0.04,
            )

            # RS 라인 (상단)
            fig.add_trace(go.Scatter(
                x=df["date"], y=df["rs_score"],
                name="RS", mode="lines",
                line=dict(color=color, width=2.2),
                fill="tozeroy", fillcolor=fill_rgba,
                hovertemplate="RS: %{y}<br>%{x|%Y-%m-%d}<extra></extra>",
            ), row=1, col=1)

            # 기준선 80 / 60
            fig.add_hline(y=80, line_dash="dot", line_color="#dc2626",
                          annotation_text="80", annotation_position="right",
                          annotation_font_size=10, annotation_font_color="#dc2626",
                          row=1, col=1)
            fig.add_hline(y=60, line_dash="dot", line_color="#f59e0b",
                          annotation_text="60", annotation_position="right",
                          annotation_font_size=10, annotation_font_color="#f59e0b",
                          row=1, col=1)

            # 주가 라인 (하단)
            fig.add_trace(go.Scatter(
                x=df["date"], y=df["price"],
                name="주가", mode="lines",
                line=dict(color="#64748b", width=1.4),
                hovertemplate="주가: %{y:,.0f}원<br>%{x|%Y-%m-%d}<extra></extra>",
            ), row=2, col=1)

            fig.update_layout(
                title=dict(text=f"<b>{title}</b>", font=dict(size=13, color="#1e293b"), x=0),
                height=320,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                margin=dict(l=40, r=40, t=36, b=10),
                hovermode="x unified",
            )
            fig.update_yaxes(showgrid=True, gridcolor="#e2e8f0",
                             range=[0, 100], title_text="RS", row=1, col=1)
            fig.update_yaxes(showgrid=True, gridcolor="#e2e8f0",
                             title_text="주가(원)", row=2, col=1)
            fig.update_xaxes(showgrid=True, gridcolor="#e2e8f0")

            figs.append(fig)

        return figs

    except ImportError:
        return []


# ── 전체 비교용 단일 RS 차트 (일/주/월 각각) ─────────────────────────
def make_compare_fig(histories: dict, valid: list, freq: str, title: str, x_tail: int):
    """
    여러 종목 RS를 하나의 차트에 비교.
    histories: {code: df_daily}
    freq: "D" | "W" | "M"
    """
    try:
        import plotly.graph_objects as go

        fig = go.Figure()
        for i, stock in enumerate(valid):
            code = stock["code"]
            df_all = histories.get(code)
            if df_all is None or df_all.empty:
                continue
            df = resample_rs_history(df_all, freq)
            if df is None or df.empty:
                continue
            df = df.tail(x_tail)
            color = COLORS[i % len(COLORS)]
            fig.add_trace(go.Scatter(
                x=df["date"], y=df["rs_score"],
                name=stock["name"], mode="lines",
                line=dict(color=color, width=2.2),
                hovertemplate=f"<b>{stock['name']}</b>  RS: %{{y}}<br>%{{x|%Y-%m-%d}}<extra></extra>",
            ))

        fig.add_hline(y=80, line_dash="dot", line_color="#dc2626",
                      annotation_text="80", annotation_position="right",
                      annotation_font_size=10, annotation_font_color="#dc2626")
        fig.add_hline(y=60, line_dash="dot", line_color="#f59e0b",
                      annotation_text="60", annotation_position="right",
                      annotation_font_size=10, annotation_font_color="#f59e0b")

        fig.update_layout(
            title=dict(text=f"<b>{title}</b>", font=dict(size=13, color="#1e293b"), x=0),
            height=300,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=True, gridcolor="#e2e8f0"),
            yaxis=dict(showgrid=True, gridcolor="#e2e8f0", range=[0, 100], title="RS"),
            legend=dict(orientation="h", y=-0.25),
            margin=dict(l=40, r=40, t=36, b=50),
            hovermode="x unified",
        )
        return fig

    except ImportError:
        return None


# ── 메인 렌더링 ──────────────────────────────────────────────────────
if search_clicked and user_input.strip():
    st.session_state["rs_query"] = user_input.strip()

if "rs_query" in st.session_state and st.session_state["rs_query"]:
    query  = st.session_state["rs_query"]
    parsed = parse_input(query)

    failed = [p["name"] for p in parsed if p["code"] is None]
    valid  = [p for p in parsed if p["code"] is not None]

    if failed:
        st.warning(f"종목을 찾지 못했습니다: {', '.join(failed)}")
    if not valid:
        st.stop()

    codes = [p["code"] for p in valid]

    # 현재 RS 조회
    with st.spinner("RS Rating 계산 중... (최초 조회 시 10~20초)"):
        current_rs_map = cached_current_rs(tuple(sorted(codes)))

    # ── 현재 RS 카드 ─────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 현재 RS Rating")
    card_cols = st.columns(len(valid))
    for i, stock in enumerate(valid):
        code = stock["code"]
        rs   = current_rs_map.get(code)
        with card_cols[i]:
            badge_color = rs_badge_color(rs) if rs else "#94a3b8"
            label       = rs_rating_label(rs) if rs else "데이터 없음"
            market      = _detect_market(code, f"{code}.KS", 0, 0).upper()
            rs_text     = f"RS {rs}" if rs else "RS -"
            st.markdown(f"""
            <div class="stock-header">
                <div style="font-size:15px;font-weight:700;">{stock['name']}</div>
                <div style="font-size:12px;color:#94a3b8;">{code} · {market}</div>
            </div>
            <span class="rs-badge" style="background:{badge_color};">{rs_text}</span>
            <div class="rs-meta">{label}</div>
            """, unsafe_allow_html=True)

    # ── 히스토리 데이터 수집 ────────────────────────────────────────
    st.markdown("---")
    st.markdown("### RS 변화 그래프")
    st.caption("※ 히스토리 RS는 해당 종목 자체의 상대강도 추세 파악용입니다. 절대 등급은 위 '현재 RS Rating' 기준으로 판단하세요.")

    histories = {}   # {code: df_daily(2년)}
    with st.spinner("RS 히스토리 로딩 중... (최초 약 20~40초)"):
        for stock in valid:
            df = cached_rs_history(stock["code"])
            if df is not None and not df.empty:
                histories[stock["code"]] = df

    # ── 탭: 전체비교 / 종목별 ────────────────────────────────────────
    tab_compare, *tab_singles = st.tabs(
        ["📊 전체 비교"] + [p["name"] for p in valid]
    )

    # —— 전체 비교 탭 ——
    with tab_compare:
        if not histories:
            st.warning("히스토리 데이터를 불러오지 못했습니다.")
        else:
            try:
                import plotly.graph_objects as go  # noqa: F401 — import 가능 확인

                st.markdown('<span class="section-label">📅 일별 (최근 60거래일)</span>',
                            unsafe_allow_html=True)
                fig_d = make_compare_fig(histories, valid, "D", "일별 RS 비교", 60)
                if fig_d:
                    st.plotly_chart(fig_d, use_container_width=True)

                st.markdown('<span class="section-label">📆 주별 (최근 52주)</span>',
                            unsafe_allow_html=True)
                fig_w = make_compare_fig(histories, valid, "W", "주별 RS 비교", 52)
                if fig_w:
                    st.plotly_chart(fig_w, use_container_width=True)

                st.markdown('<span class="section-label">🗓️ 월별 (최근 24개월)</span>',
                            unsafe_allow_html=True)
                fig_m = make_compare_fig(histories, valid, "M", "월별 RS 비교", 24)
                if fig_m:
                    st.plotly_chart(fig_m, use_container_width=True)

            except ImportError:
                st.warning("plotly가 설치되어 있지 않습니다. requirements.txt에 `plotly` 추가 후 재배포하세요.")

    # —— 종목별 탭 ——
    for i, (tab, stock) in enumerate(zip(tab_singles, valid)):
        with tab:
            code  = stock["code"]
            rs    = current_rs_map.get(code)
            df_all = histories.get(code)

            if df_all is None or df_all.empty:
                st.warning(f"{stock['name']}: 히스토리 데이터 없음")
                continue

            try:
                import plotly.graph_objects as go  # noqa

                color  = COLORS[i % len(COLORS)]
                df_day   = resample_rs_history(df_all, "D")
                df_week  = resample_rs_history(df_all, "W")
                df_month = resample_rs_history(df_all, "M")

                figs = make_rs_price_fig(df_day, df_week, df_month, stock["name"], color)

                labels = [
                    "📅 일별 (최근 60거래일)",
                    "📆 주별 (최근 52주)",
                    "🗓️ 월별 (최근 24개월)",
                ]
                for label, fig in zip(labels, figs):
                    st.markdown(f'<span class="section-label">{label}</span>',
                                unsafe_allow_html=True)
                    st.plotly_chart(fig, use_container_width=True)

                # 요약 지표
                st.markdown("#### 📋 RS 요약")
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("현재 RS (전체 시장)", f"{rs}" if rs else "-")

                if df_day is not None and not df_day.empty:
                    day60 = df_day.tail(60)
                    m2.metric("60일 RS 최고", f"{int(day60['rs_score'].max())}")
                    m3.metric("60일 RS 최저", f"{int(day60['rs_score'].min())}")
                    trend_60 = "📈 상승" if day60["rs_score"].iloc[-1] > day60["rs_score"].iloc[0] else "📉 하락"
                    m4.metric("60일 추세", trend_60)

                if df_week is not None and not df_week.empty:
                    week13 = df_week.tail(13)
                    trend_13w = "📈 상승" if week13["rs_score"].iloc[-1] > week13["rs_score"].iloc[0] else "📉 하락"
                    m5.metric("13주 추세", trend_13w)

            except ImportError:
                st.warning("plotly가 설치되어 있지 않습니다.")

    # ── 해석 가이드 ──────────────────────────────────────────────────
    with st.expander("📖 RS Rating 해석 가이드 (오닐 기준)"):
        st.markdown("""
| RS Rating | 의미 | 오닐 전략 |
|-----------|------|-----------|
| **90~99** | 🔴 최상위 1~10% | 적극 매수 후보 |
| **80~89** | 🟠 상위 11~20% | 매수 고려 (돌파 시) |
| **60~79** | 🟢 상위 21~40% | 관망 |
| **40~59** | ⬜ 중간권 | 매수 회피 |
| **1~39**  | 🔵 하위권 | 매수 금지 |

**핵심 원칙**
- 오닐은 **RS 80 이상** 종목만 매수 후보로 고려했습니다.
- **신고가 돌파 + RS 상승** 조합이 가장 강한 신호입니다.
- RS가 주가보다 **먼저 신고가**를 찍으면 선행 강세 신호입니다.
- RS 하락 + 주가 횡보 조합은 조기 이탈 신호입니다.

**그래프 구성**
- **상단 RS 라인**: 이 종목 자체의 상대강도 추세 (1~99)
- **하단 주가 라인**: 같은 기간 실제 주가
- **빨간 점선 (RS 80)**: 오닐 매수 기준선
- **노란 점선 (RS 60)**: 관망 기준선
        """)
