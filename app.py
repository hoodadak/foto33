import streamlit as st
import streamlit.components.v1 as components
import urllib.parse
import json
import os
from datetime import datetime, date, timedelta, timezone
from utils import (
    KST, HEADERS, CACHE_TTL, TOP_THEME_COUNT, THEME_SCAN_COUNT, STOCKS_PER_THEME,
    ETF_ETN_PREFIXES, KR_MARKET_HOLIDAYS, is_market_open_now,
    fetch_trading_top, fetch_top_rising_stock, fetch_theme_list, fetch_theme_detail,
    fetch_limit_up_time, fetch_52week_high, build_theme_ranking_core, load_history
)

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

# ===================== 기본 설정 =====================
st.set_page_config(page_title="주도테마", layout="wide")

now = datetime.now(KST)
weekday_list = ['월', '화', '수', '목', '금', '토', '일']
current_date_str = f"{now.strftime('%m-%d')}({weekday_list[now.weekday()]}) {now.strftime('%H:%M')}"

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


# ===================== CSS =====================
st.markdown("""
    <style>
    .stApp { background-color: #DBFDF9; }
    .tima-header-box {
        display: flex; justify-content: space-between; align-items: center;
        padding: 5px 15px; font-family: 'Malgun Gothic', sans-serif;
    }
    .logo-main { font-size: 32px; font-weight: 800; color: #1e293b; letter-spacing: -1px; }
    .logo-sub { font-size: 16px; font-weight: 600; color: #94a3b8; margin-left: 8px; }
    .date-text { font-size: 25px; color: #000000; font-weight: 500; }

    /* Streamlit 컬럼이 모바일에서 세로로 쌓이지 않도록 강제 가로배치 */
    @media (max-width: 768px) {
        [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            overflow-x: auto;
        }
        [data-testid="column"] {
            min-width: 0 !important;
            width: auto !important;
        }
    }

    .tima-search-bar {
        background-color: white; border: 1px solid #e2e8f0; border-radius: 10px;
        padding: 10px 16px; color: #94a3b8; font-size: 14px; margin-bottom: 22px;
    }
    .theme-card-container {
        background-color: #1e3a5f; border-radius: 10px; border: 1px solid #1e293b;
        padding: 14px; margin-bottom: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        position: relative; overflow: visible;
    }
    .theme-card-icons {
        display: inline-flex; gap: 2px; font-size: 1.3em; line-height: 1; vertical-align: middle;
    }
    .theme-card-header {
        display: flex; justify-content: space-between; align-items: center;
        color: white; font-weight: 700; font-size: 20px;
        flex-wrap: wrap; gap: 8px; margin-bottom: 10px;
    }
    .theme-card-title { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .theme-card-money { color: #fbbf24; font-size: 19px; font-weight: 700; }
    .theme-card-news {
        font-size: 13px; color: #475569; margin: 10px 0; padding: 2px 4px;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-bottom: 1px dashed #e2e8f0;
    }

    .stock-item-box {
        background-color: #ffffff; border: 1px solid #d4d4d4; border-radius: 8px;
        padding: 8px 12px; margin-bottom: 7px; position: relative;
    }
    .stock-item-main { display: flex; justify-content: space-between; align-items: center; }
    .stock-item-name { font-weight: 700; font-size: 19px; color: #000000 !important; text-decoration: none !important; border-bottom: none !important; }
    .stock-item-name:visited, .stock-item-name:hover, .stock-item-name:active { color: #000000 !important; text-decoration: none !important; border-bottom: none !important; }
    .stock-item-meta { display: flex; justify-content: space-between; font-size: 11px; color: #94a3b8; margin-top: 2px; flex-wrap: wrap; gap: 4px; }

    .candle-bar-track {
        width: 100%; height: 6px; background-color: #e2e8f0; border-radius: 3px; margin-top: 8px; position: relative;
    }
    .candle-center-line {
        position: absolute; left: 50%; top: -2px; width: 2px; height: 10px; background-color: #94a3b8; z-index: 3;
    }
    .candle-bar-up {
        position: absolute; left: 50%; top: 0; height: 100%; background-color: #ef4444; border-radius: 0 3px 3px 0;
    }
    .candle-bar-down {
        position: absolute; right: 50%; top: 0; height: 100%; background-color: #3b82f6; border-radius: 3px 0 0 3px;
    }

    .txt-up-red { color: #dc2626; font-weight: 700; font-size: 15px; }
    .txt-down-blue { color: #2563eb; font-weight: 700; font-size: 15px; }

    .bg-limit-up { background-color: #FFD1DE !important; border: 1px solid #ffb8cc; }
    </style>
    """, unsafe_allow_html=True)

# ===================== 자동 새로고침 (장 운영시간: 평일 08:00~18:00, 공휴일 제외, 오늘만) =====================
if is_market_open_now(now) and 'selected_date' not in st.session_state:
    st.markdown(
        f"<meta http-equiv='refresh' content='{CACHE_TTL}'>",
        unsafe_allow_html=True
    )

# ===================== 상단 헤더 + 날짜 선택 + 새로고침 버튼 =====================
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "PC"

is_mobile = (st.session_state.view_mode == "모바일")

if not is_mobile:
    # ── PC 모드: 로고+시계+날짜+버튼 한 줄 ──
    header_col1, header_col2, header_col3, header_col4 = st.columns([5, 1, 0.5, 0.5])
    with header_col1:
        st.markdown("""
            <div class="tima-header-box">
                <div><span class="logo-main">주도테마</span></div>
                <div id="live-clock" class="date-text"></div>
            </div>
            """, unsafe_allow_html=True)
        components.html("""
            <script>
            function updateClock() {
                const weekdays = ['일','월','화','수','목','금','토'];
                const now = new Date();
                const mm = String(now.getMonth()+1).padStart(2,'0');
                const dd = String(now.getDate()).padStart(2,'0');
                const wd = weekdays[now.getDay()];
                const hh = String(now.getHours()).padStart(2,'0');
                const mi = String(now.getMinutes()).padStart(2,'0');
                const ss = String(now.getSeconds()).padStart(2,'0');
                const el = window.parent.document.getElementById('live-clock');
                if (el) el.innerText = mm+'-'+dd+'('+wd+') '+hh+':'+mi+':'+ss;
            }
            updateClock();
            setInterval(updateClock, 1000);
            </script>
        """, height=0)
    with header_col2:
        selected_date = st.date_input(
            "날짜 선택",
            value=date.today(),
            min_value=date(2026, 1, 1),
            max_value=date.today(),
            label_visibility="collapsed"
        )
    with header_col3:
        if st.button("📱 모바일", use_container_width=True):
            st.session_state.view_mode = "모바일"
            st.rerun()
    with header_col4:
        if st.button("🔄 새로고침", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
else:
    # ── 모바일 모드: 로고+시계 1행 / 날짜+버튼 2행 ──
    st.markdown("""
        <div class="tima-header-box">
            <div><span class="logo-main">주도테마</span></div>
            <div id="live-clock" class="date-text" style="font-size:16px;"></div>
        </div>
        """, unsafe_allow_html=True)
    components.html("""
        <script>
        function updateClock() {
            const weekdays = ['일','월','화','수','목','금','토'];
            const now = new Date();
            const mm = String(now.getMonth()+1).padStart(2,'0');
            const dd = String(now.getDate()).padStart(2,'0');
            const wd = weekdays[now.getDay()];
            const hh = String(now.getHours()).padStart(2,'0');
            const mi = String(now.getMinutes()).padStart(2,'0');
            const ss = String(now.getSeconds()).padStart(2,'0');
            const el = window.parent.document.getElementById('live-clock');
            if (el) el.innerText = mm+'-'+dd+'('+wd+') '+hh+':'+mi+':'+ss;
        }
        updateClock();
        setInterval(updateClock, 1000);
        </script>
    """, height=0)

    mob_col1, mob_col2, mob_col3 = st.columns([3, 1, 1])
    with mob_col1:
        selected_date = st.date_input(
            "날짜",
            value=date.today(),
            min_value=date(2026, 1, 1),
            max_value=date.today(),
            label_visibility="collapsed",
            key="mob_date"
        )
    with mob_col2:
        if st.button("🖥️ PC", use_container_width=True, key="mob_pc_btn"):
            st.session_state.view_mode = "PC"
            st.rerun()
    with mob_col3:
        if st.button("🔄", use_container_width=True, key="mob_refresh"):
            st.cache_data.clear()
            st.rerun()

    # 모바일 전용 CSS: 컬럼 가로배치 강제 + 카드/폰트 축소
    st.markdown("""
        <style>
        div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
        div[data-testid="column"] { min-width: 0 !important; flex: 1 !important; }
        .theme-card-container { padding: 6px !important; margin-bottom: 6px !important; }
        .theme-card-header { font-size: 12px !important; gap: 4px !important; }
        .theme-card-money { font-size: 10px !important; padding: 1px 4px !important; }
        .stock-item-box { padding: 5px 6px !important; margin-bottom: 4px !important; }
        .stock-item-name { font-size: 12px !important; }
        .txt-up-red, .txt-down-blue { font-size: 11px !important; }
        .stock-item-meta span { font-size: 10px !important; }
        .candle-bar-track { height: 3px !important; margin-top: 3px !important; }
        </style>
    """, unsafe_allow_html=True)

    if "mob_date" in st.session_state:
        selected_date = st.session_state["mob_date"]

is_today = (selected_date == date.today())
selected_date_str = selected_date.strftime("%Y-%m-%d")

# ===================== 데이터 로드 (오늘=실시간, 과거=Google Sheets) =====================
if is_today:
    if is_market_open_now(now):
        pass  # 자동 새로고침 이미 위에서 처리
    with st.spinner("실시간 테마 데이터를 불러오는 중..."):
        theme_ranking = build_theme_ranking()
else:
    with st.spinner(f"{selected_date_str} 데이터를 불러오는 중..."):
        theme_ranking = load_history_from_sheet(selected_date_str)
    if theme_ranking is None:
        st.warning(f"{selected_date_str} 저장된 데이터가 없습니다. 장이 열린 날짜를 선택해주세요.")
        st.stop()

if not theme_ranking:
    st.warning("테마 데이터를 불러오지 못했습니다. 잠시 후 새로고침 해주세요.")
    st.stop()


def render_theme_card(theme):
    total_sum_str = f"KRX {theme['total_sum']:,.0f}억"

    icons = ""
    if theme.get("is_top_amount"):
        icons += (
            '<span title="거래대금 1위" '
            'style="display:inline-flex; align-items:center; justify-content:center; '
            'width:1.4em; height:1.4em; border-radius:50%; background-color:#dc2626;">'
            '<span style="filter: brightness(0) invert(1); font-size:0.9em;">👍</span>'
            '</span>'
        )
    if theme.get("has_52w_high"):
        icons += '<span title="52주 신고가 발생">⭐</span>'
    if theme.get("has_limit_up"):
        icons += '<span title="상한가 발생" style="color:#dc2626; font-weight:900; font-size:1.1em;">⬆</span>'

    icons_html = f'<span class="theme-card-icons">{icons}</span>' if icons else ""

    card_html = (
        f'<div class="theme-card-container">'
        f'<div class="theme-card-header">'
        f'<div class="theme-card-title">{theme["name"]} {icons_html}</div>'
        f'<span class="theme-card-money">{total_sum_str}</span>'
        f'</div>'
        f'</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)

    for s in theme['stocks']:
        rate_num = s['rate_num']
        is_limit_up = s.get('is_limit_up', False) or rate_num >= 29.5
        rate_str = f"{rate_num:.2f}%"
        if rate_num >= 0:
            color = "txt-up-red"
            bar_class = "candle-bar-up"
            rate_str = f"↑{rate_str}" if is_limit_up else rate_str
        else:
            color = "txt-down-blue"
            bar_class = "candle-bar-down"
        width_pct = min(abs(rate_num) / 30 * 50, 50)

        krx_amount = s['amount_eok']

        data = {
            "rate": rate_str,
            "price": f"{s['price']:,}",
            "time": now.strftime("%H:%M"),
            "vol": f"{krx_amount:,.0f}억(KRX)",
            "bar": bar_class,
            "width": f"width: {width_pct:.0f}%;",
            "color": color,
            "limit": "bg-limit-up" if is_limit_up else ""
        }

        encoded_name = urllib.parse.quote(s['name'])
        news_url = f"https://search.naver.com/search.naver?where=news&query={encoded_name}"

        name_icons = ""
        if s.get("is_52w_high"):
            name_icons += '<span style="background-color:#16a34a; color:#fff; font-size:12px; font-weight:700; padding:1px 6px; border-radius:4px; margin-left:4px;">52주신고가</span>'

        stock_html = (
            f'<div class="stock-item-box {data["limit"]}">'
            f'<div class="stock-item-main">'
            f'<div style="display:flex; align-items:center; gap:0;">'
            f'<a href="{news_url}" target="_blank" class="stock-item-name">{s["name"]}</a>{name_icons}'
            f'</div>'
            f'<span class="{data["color"]}">{data["rate"]}</span>'
            f'</div>'
            f'<div class="stock-item-meta">'
            f'<span style="color:#000000; font-size:19px; font-weight:700;">{data["price"]}원</span>'
            f'<span style="color:#000000; font-size:19px; font-weight:700;">{data["vol"]}</span>'
            f'</div>'
            f'<div class="candle-bar-track">'
            f'<div class="candle-center-line"></div>'
            f'<div class="{data["bar"]}" style="{data["width"]}"></div>'
            f'</div>'
            f'</div>'
        )
        st.markdown(stock_html, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)


# PC: 1행 5개 x 2행 / 모바일: 1행 2개 x 5행
view_mode = st.session_state.get("view_mode", "PC")

row1_themes = theme_ranking[:5]
row2_themes = theme_ranking[5:10]

if view_mode == "PC":
    row1_cols = st.columns(5)
    for theme, col in zip(row1_themes, row1_cols):
        with col:
            render_theme_card(theme)
    row2_cols = st.columns(5)
    for theme, col in zip(row2_themes, row2_cols):
        with col:
            render_theme_card(theme)
else:
    # 모바일: 1행에 2개씩, 총 5행
    for i in range(0, len(theme_ranking), 2):
        mob_cols = st.columns(2)
        for j, col in enumerate(mob_cols):
            idx = i + j
            if idx < len(theme_ranking):
                with col:
                    render_theme_card(theme_ranking[idx])

st.caption(f"네이버 금융 실시간 시세 · {CACHE_TTL//60}분마다 자동 갱신 · 우측 상단 버튼으로 수동 갱신 가능")
