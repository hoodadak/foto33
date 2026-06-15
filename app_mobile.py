import streamlit as st
import streamlit.components.v1 as components
import urllib.parse
import json
import os
from datetime import datetime, date, timedelta, timezone
from utils import (
    KST, HEADERS, CACHE_TTL, TOP_THEME_COUNT, THEME_SCAN_COUNT, STOCKS_PER_THEME,
    is_market_open_now,
    fetch_trading_top, fetch_top_rising_stock, fetch_theme_list, fetch_theme_detail,
    fetch_limit_up_time, fetch_52week_high, build_theme_ranking_core, load_history
)

# ===================== 기본 설정 =====================
st.set_page_config(page_title="주도테마 모바일", layout="centered")

now = datetime.now(KST)

# ===================== 캐시 래퍼 함수 =====================
@st.cache_data(ttl=CACHE_TTL)
def get_trading_top(market_n=1):
    return fetch_trading_top(market_n)

@st.cache_data(ttl=CACHE_TTL)
def get_top_rising_stock():
    return fetch_top_rising_stock()

@st.cache_data(ttl=CACHE_TTL)
def get_theme_list(page=1):
    return fetch_theme_list(page)

@st.cache_data(ttl=CACHE_TTL)
def get_theme_detail(theme_code, limit=STOCKS_PER_THEME):
    return fetch_theme_detail(theme_code, limit)

@st.cache_data(ttl=CACHE_TTL)
def get_limit_up_time(ticker):
    return fetch_limit_up_time(ticker)

@st.cache_data(ttl=CACHE_TTL)
def get_52week_high(ticker):
    return fetch_52week_high(ticker)

@st.cache_data(ttl=CACHE_TTL)
def build_theme_ranking():
    return build_theme_ranking_core(
        get_trading_top, get_top_rising_stock,
        get_theme_list, get_theme_detail,
        get_limit_up_time, get_52week_high
    )

@st.cache_data(ttl=3600)
def load_history_from_sheet(date_str):
    result, err = load_history(date_str)
    if err:
        st.error(f"과거 데이터 불러오기 실패: {err}")
    return result

# ===================== 모바일 CSS =====================
st.markdown("""
<style>
.stApp { background-color: #DBFDF9; }

/* Streamlit 상단/좌우 여백 완전 제거 */
.block-container { 
    padding-left: 0.5rem !important; 
    padding-right: 0.5rem !important; 
    padding-top: 0rem !important;
    max-width: 100% !important;
    width: 100% !important;
}
[data-testid="stHeader"] { display: none !important; }
[data-testid="stAppViewContainer"] { padding: 0 !important; }
[data-testid="stAppViewContainer"] > section { padding: 0 !important; width: 100% !important; }
[data-testid="stAppViewContainer"] > section > div { 
    padding-left: 0.5rem !important; 
    padding-right: 0.5rem !important;
    max-width: 100% !important;
    width: 100% !important;
}
/* 전체 앱 너비 100% */
.main > div { max-width: 100% !important; width: 100% !important; }

/* 컬럼 가로배치 강제 */
div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 0.2rem !important; }
div[data-testid="column"] { min-width: 0 !important; flex: 1 !important; padding: 0 !important; }

.logo-main { font-size: 20px; font-weight: 800; color: #1e293b; }
.date-text { font-size: 12px; color: #000; font-weight: 500; }
.header-box { display: flex; justify-content: space-between; align-items: center; padding: 2px 2px; }

/* 테마 카드 */
.theme-card-m {
    background-color: #1e3a5f; border-radius: 6px;
    padding: 5px; margin-bottom: 5px;
}
.theme-title-row-m {
    display: flex; justify-content: space-between; align-items: center;
    color: white; font-weight: 800; font-size: 13px; margin-bottom: 4px;
}
.theme-money-m { color: #fbbf24; font-size: 12px; font-weight: 700; }

/* 종목 박스 */
.stock-box-m {
    background-color: white; border-radius: 4px;
    padding: 4px 5px; margin-bottom: 3px;
}
.limit-up-m { background-color: #FFD1DE !important; }

/* 종목 1행: 종목명(좌, flex:1) + 52주신고가+등락률(우, nowrap) */
.stock-row1-m {
    display: flex; justify-content: space-between; align-items: center;
    gap: 4px; overflow: hidden;
}
/* 종목 2행: 현재가(좌) + 거래대금(우) */
.stock-row2-m {
    display: flex; justify-content: space-between; align-items: center;
    margin-top: 1px;
}
.stock-name-m {
    font-weight: 700; font-size: 12px; color: #000000 !important;
    text-decoration: none !important; border-bottom: none !important;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    flex: 1; min-width: 0;
}
.stock-name-m:visited, .stock-name-m:hover, .stock-name-m:active {
    color: #000000 !important; text-decoration: none !important; }
.rate-up { color: #dc2626; font-weight: 700; font-size: 11px; white-space: nowrap; }
.rate-down { color: #2563eb; font-weight: 700; font-size: 11px; white-space: nowrap; }
.stock-price-m { font-size: 11px; color: #000000; font-weight: 600; }
.stock-vol-m { font-size: 11px; font-weight: 600; color: #334155; }

.badge-52w-m { background-color: #16a34a; color: #fff; font-size: 8px; font-weight: 700;
             padding: 1px 2px; border-radius: 2px; margin-left: 1px; }

/* 캔들바 */
.bar-track-m { width: 100%; height: 4px; background-color: #e2e8f0;
             border-radius: 2px; margin-top: 3px; position: relative; }
.bar-center-m { position: absolute; left: 50%; top: -2px; width: 1px; height: 8px;
              background-color: #94a3b8; z-index: 3; }
.bar-up-m { position: absolute; left: 50%; top: 0; height: 100%;
          background-color: #ef4444; border-radius: 0 2px 2px 0; }
.bar-down-m { position: absolute; right: 50%; top: 0; height: 100%;
            background-color: #3b82f6; border-radius: 2px 0 0 2px; }
/* 2열 그리드 */
.grid-2col { width: 100%; }
.grid-row { display: flex; flex-direction: row; gap: 4px; margin-bottom: 0; }
.grid-cell { flex: 1; min-width: 0; }
</style>
""", unsafe_allow_html=True)

# ===================== 자동 새로고침 =====================
if is_market_open_now(now):
    st.markdown(f"<meta http-equiv='refresh' content='{CACHE_TTL}'>", unsafe_allow_html=True)

# ===================== 헤더 + 날짜 + 새로고침 한 줄 =====================
st.markdown("""
<style>
div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
div[data-testid="column"] { min-width: 0 !important; }
</style>
""", unsafe_allow_html=True)

# ===================== 헤더: 주도테마 =====================
st.markdown('<div style="font-size:22px;font-weight:800;color:#1e293b;padding:4px 2px 4px 2px;">주도테마</div>', unsafe_allow_html=True)

# 날짜/새로고침 - 테마박스와 동일한 HTML grid 2열
selected_date_state = st.session_state.get("selected_date", date.today().strftime("%Y-%m-%d"))
st.markdown(f"""
<div style="display:flex; gap:5px; margin-bottom:6px;">
    <div style="flex:1;">
        <input type="date" id="mobile_date" value="{selected_date_state}"
            min="2026-01-01" max="{date.today().strftime('%Y-%m-%d')}"
            style="width:100%; font-size:14px; padding:8px; border-radius:6px;
                   border:1px solid #ccc; background:#1e293b; color:white; box-sizing:border-box;"
            onchange="document.getElementById('date_val').value=this.value; document.getElementById('date_submit').click();">
    </div>
    <div style="flex:1;">
        <button onclick="document.getElementById('refresh_btn_hidden').click();"
            style="width:100%; font-size:14px; padding:8px; border-radius:6px;
                   border:none; background:#1e293b; color:white; cursor:pointer;">
            🔄 새로고침
        </button>
    </div>
</div>
""", unsafe_allow_html=True)

# 히든 입력값 처리
st.markdown('<div style="display:none">', unsafe_allow_html=True)
date_val = st.text_input("날짜값", value=selected_date_state, key="date_val")
st.markdown('</div>', unsafe_allow_html=True)
# 히든 버튼으로 날짜/새로고침 처리
col_h1, col_h2 = st.columns(2)
with col_h1:
    date_submit = st.button("날짜적용", key="date_submit")
with col_h2:
    refresh_hidden = st.button("새로고침실행", key="refresh_btn_hidden")

# 히든 버튼 숨기기
st.markdown("""
<style>
button[kind="secondary"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

if date_submit and date_val:
    st.session_state["selected_date"] = date_val
    st.rerun()
if refresh_hidden:
    st.cache_data.clear()
    st.session_state["selected_date"] = date.today().strftime("%Y-%m-%d")
    st.rerun()

try:
    selected_date = date.fromisoformat(selected_date_state)
    if selected_date > date.today():
        selected_date = date.today()
except Exception:
    selected_date = date.today()

# ===================== 데이터 로드 =====================
is_today = (selected_date == date.today())
selected_date_str = selected_date.strftime("%Y-%m-%d")

if is_today:
    with st.spinner("실시간 데이터 로딩중..."):
        theme_ranking = build_theme_ranking()
else:
    with st.spinner(f"{selected_date_str} 데이터 로딩중..."):
        theme_ranking = load_history_from_sheet(selected_date_str)
    if theme_ranking is None:
        st.warning(f"{selected_date_str} 저장된 데이터가 없습니다.")
        st.stop()

if not theme_ranking:
    st.warning("데이터를 불러오지 못했습니다.")
    st.stop()

# 과거 데이터에 누락된 키 기본값 설정
for i, t in enumerate(theme_ranking):
    t.setdefault("is_top_amount", i == 0)
    t.setdefault("has_52w_high", False)
    t.setdefault("has_limit_up", False)
    for s in t.get("stocks", []):
        s.setdefault("is_52w_high", False)
        s.setdefault("is_limit_up", s.get("rate_num", 0) >= 29.5)
        s.setdefault("price", 0)

# ===================== 테마 카드 HTML 생성 함수 =====================
def make_card_html(theme):
    icons = ""
    if theme.get("is_top_amount"):
        icons += '<span style="filter:hue-rotate(140deg) saturate(3);">👍</span>'
    if theme.get("has_52w_high"):
        icons += '⭐'
    if theme.get("has_limit_up"):
        icons += '<span style="color:#dc2626;font-weight:900;">⬆</span>'

    total_sum_str = f"KRX {theme['total_sum']:,.0f}억"
    stocks_html = ""

    for s in theme["stocks"]:
        rate_num = s["rate_num"]
        is_limit_up = s.get("is_limit_up", False) or rate_num >= 29.5
        rate_str = f"{rate_num:.2f}%"
        if rate_num >= 0:
            rate_class = "rate-up"
            rate_str = f"↑{rate_str}" if is_limit_up else rate_str
        else:
            rate_class = "rate-down"
        width_pct = min(abs(rate_num) / 30 * 50, 50)
        bar_dir = "bar-up" if rate_num >= 0 else "bar-down"
        box_class = "stock-box-m limit-up-m" if is_limit_up else "stock-box-m"
        badge_52w = '<span class="badge-52w-m">52주신고가</span>' if s.get("is_52w_high") else ""
        encoded = urllib.parse.quote(s["name"])
        news_url = f"https://search.naver.com/search.naver?where=news&query={encoded}"
        vol_str = f"{s['amount_eok']:,.0f}억"
        price_str = f"{s['price']:,}" if s.get('price') else ""

        stocks_html += (
            f'<div class="{box_class}">'
            f'<div class="stock-row1-m">'
            f'<a href="{news_url}" target="_blank" class="stock-name-m">{s["name"]}</a>'
            f'<span style="display:flex;align-items:center;gap:3px;white-space:nowrap;">'
            f'{badge_52w}'
            f'<span class="{rate_class}">{rate_str}</span>'
            f'</span>'
            f'</div>'
            f'<div class="stock-row2-m">'
            f'<span class="stock-price-m">{price_str}</span>'
            f'<span class="stock-vol-m">{vol_str}</span>'
            f'</div>'
            f'<div class="bar-track-m">'
            f'<div class="bar-center-m"></div>'
            f'<div class="{bar_dir}-m" style="width:{width_pct:.0f}%;"></div>'
            f'</div>'
            f'</div>'
        )

    return (
        f'<div class="theme-card-m">'
        f'<div class="theme-title-row-m">'
        f'<span>{theme["name"]} {icons}</span>'
        f'<span class="theme-money-m">{total_sum_str}</span>'
        f'</div>'
        f'{stocks_html}'
        f'</div>'
    )


# ===================== 전체 그리드 HTML로 렌더링 =====================
grid_html = '<div class="grid-2col">'
for i in range(0, len(theme_ranking), 2):
    grid_html += '<div class="grid-row">'
    grid_html += f'<div class="grid-cell">{make_card_html(theme_ranking[i])}</div>'
    if i + 1 < len(theme_ranking):
        grid_html += f'<div class="grid-cell">{make_card_html(theme_ranking[i+1])}</div>'
    else:
        grid_html += '<div class="grid-cell"></div>'
    grid_html += '</div>'
grid_html += '</div>'

st.markdown(grid_html, unsafe_allow_html=True)
st.caption(f"네이버 금융 실시간 · {CACHE_TTL//60}분 캐시")
