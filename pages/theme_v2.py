# ===================== pages/theme_v2.py =====================
# 주도테마 V2 — app.py와 동일한 디자인 + RS Rating + 52주신고가
import streamlit as st
import streamlit.components.v1 as components
import urllib.parse
from datetime import datetime, date, timedelta, timezone

from utils import (
    KST, CACHE_TTL, STOCKS_PER_THEME, is_market_open_now,
    fetch_trading_top, fetch_top_rising_stock, fetch_theme_list, fetch_theme_detail,
    fetch_limit_up_time, fetch_52week_high, fetch_market_top100_codes,
    fetch_us_theme_scores,
)
import requests
from bs4 import BeautifulSoup

try:
    from rs_rating import fetch_rs_ratings_from_history
    RS_AVAILABLE = True
except ImportError:
    RS_AVAILABLE = False

# ===================== 설정 =====================
st.set_page_config(page_title="주도테마 V2", layout="wide")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# ===================== 사이드바 메뉴 =====================
with st.sidebar:
    st.markdown("### 📊 메뉴")
    st.page_link("app.py",                  label="🏠 주도테마")
    st.page_link("pages/theme_v2.py",       label="🏆 주도테마 V2")
    st.page_link("pages/rs_lookup.py",      label="📈 RS Rating 조회")
    st.page_link("pages/supply.py",         label="💰 수급분석")
    st.markdown("---")
    st.caption("V2: 상승거래대금 기반\n미국연관→1위 / 뉴스노출→2위")

# ===================== CSS (app.py 동일) =====================
st.markdown("""
    <style>
    .stApp { background-color: #DBFDF9; }
    .tima-header-box {
        display: flex; justify-content: space-between; align-items: center;
        padding: 5px 15px; font-family: 'Malgun Gothic', sans-serif;
    }
    .logo-main { font-size: 32px; font-weight: 800; color: #1e293b; letter-spacing: -1px; }
    .logo-sub  { font-size: 16px; font-weight: 600; color: #94a3b8; margin-left: 8px; }
    .date-text { font-size: 25px; color: #000000; font-weight: 500; }

    @media (max-width: 768px) {
        [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; overflow-x: auto; }
        [data-testid="column"] { min-width: 0 !important; width: auto !important; }
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
    .candle-bar-up   { position: absolute; left: 50%; top: 0; height: 100%; background-color: #ef4444; border-radius: 0 3px 3px 0; }
    .candle-bar-down { position: absolute; right: 50%; top: 0; height: 100%; background-color: #3b82f6; border-radius: 3px 0 0 3px; }

    .txt-up-red   { color: #dc2626; font-weight: 700; font-size: 15px; }
    .txt-down-blue { color: #2563eb; font-weight: 700; font-size: 15px; }
    .bg-limit-up  { background-color: #FFD1DE !important; border: 1px solid #ffb8cc; }

    /* V2 전용 배지 */
    .v2-rank-badge {
        display: inline-block; font-size: 11px; font-weight: 700;
        padding: 2px 7px; border-radius: 4px; margin-right: 4px;
    }
    .v2-us-badge   { background-color: #1d4ed8; color: #fff; }
    .v2-news-badge { background-color: #7c3aed; color: #fff; }
    .v2-sep-section {
        background-color: #7f1d1d; border-radius: 10px; border: 1px solid #991b1b;
        padding: 14px; margin-bottom: 15px;
    }
    .v2-sep-header { color: #fca5a5; font-weight: 700; font-size: 16px; margin-bottom: 8px; }
    </style>
""", unsafe_allow_html=True)

# ===================== 캐시 래퍼 =====================
@st.cache_data(ttl=CACHE_TTL)
def get_theme_list_c(page=1):      return fetch_theme_list(page)

@st.cache_data(ttl=CACHE_TTL)
def get_theme_detail_c(code):      return fetch_theme_detail(code)

@st.cache_data(ttl=CACHE_TTL)
def get_52week_high_c(ticker):     return fetch_52week_high(ticker)

@st.cache_data(ttl=CACHE_TTL)
def get_top50_codes_c():
    """거래대금 상위 50 종목 코드"""
    all_stocks = []
    for market_n in [0, 1]:
        for page in range(1, 4):
            url = f"https://finance.naver.com/sise/sise_quant.naver?sosok={market_n}&page={page}"
            try:
                res = requests.get(url, headers=HEADERS, timeout=7)
                res.encoding = "euc-kr"
                soup = BeautifulSoup(res.text, "html.parser")
                table = soup.select_one("table.type_2")
                if not table:
                    break
                found = 0
                for tr in table.select("tr"):
                    tds = tr.select("td")
                    if len(tds) < 6:
                        continue
                    name_tag = tds[1].select_one("a")
                    if not name_tag:
                        continue
                    href = name_tag.get("href", "")
                    code = href.split("code=")[-1] if "code=" in href else ""
                    try:
                        amount_eok = float(tds[5].text.strip().replace(",", "")) / 100.0
                    except ValueError:
                        amount_eok = 0.0
                    if code:
                        all_stocks.append({"code": code, "amount_eok": amount_eok})
                        found += 1
                if found == 0:
                    break
            except Exception:
                break
    all_stocks.sort(key=lambda x: x["amount_eok"], reverse=True)
    return {s["code"] for s in all_stocks[:50]}

@st.cache_data(ttl=CACHE_TTL)
def get_news_counts_c(theme_names_tuple):
    """뉴스 노출 갯수 (실제 빈도수)"""
    theme_names = list(theme_names_tuple)
    try:
        url = "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258"
        res = requests.get(url, headers=HEADERS, timeout=7)
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "html.parser")
        titles = [a.text.strip() for a in soup.select("dl dd.articleSubject a")]
        if not titles:
            titles = [a.text.strip() for a in soup.select("ul.newsList li a")]
        news_text = " ".join(titles)
        counts = {}
        for name in theme_names:
            keywords = [w for w in name.replace("/", " ").replace("·", " ").split() if len(w) >= 2]
            counts[name] = sum(news_text.count(kw) for kw in keywords)
        return counts
    except Exception:
        return {name: 0 for name in theme_names}

@st.cache_data(ttl=CACHE_TTL)
def get_market_top10_stocks_c():
    """전체 시장(코스피+코스닥) 거래대금 상위 10 종목명 반환"""
    all_stocks = []
    for market_n in [0, 1]:
        url = f"https://finance.naver.com/sise/sise_quant.naver?sosok={market_n}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=7)
            res.encoding = "euc-kr"
            soup = BeautifulSoup(res.text, "html.parser")
            table = soup.select_one("table.type_2")
            if not table:
                continue
            for tr in table.select("tr"):
                tds = tr.select("td")
                if len(tds) < 6:
                    continue
                name_tag = tds[1].select_one("a")
                if not name_tag:
                    continue
                name = name_tag.text.strip()
                try:
                    amount_eok = float(tds[5].text.strip().replace(",", "")) / 100.0
                except ValueError:
                    amount_eok = 0.0
                all_stocks.append({"name": name, "amount_eok": amount_eok})
        except Exception:
            continue
    all_stocks.sort(key=lambda x: x["amount_eok"], reverse=True)
    return [s["name"] for s in all_stocks[:10]]

@st.cache_data(ttl=CACHE_TTL)
def get_news_counts_by_stock_c(stock_names_tuple):
    """뉴스 노출 갯수 - 종목명 단위"""
    stock_names = list(stock_names_tuple)
    try:
        url = "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258"
        res = requests.get(url, headers=HEADERS, timeout=7)
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "html.parser")
        titles = [a.text.strip() for a in soup.select("dl dd.articleSubject a")]
        if not titles:
            titles = [a.text.strip() for a in soup.select("ul.newsList li a")]
        news_text = " ".join(titles)
        return {name: news_text.count(name) for name in stock_names}
    except Exception:
        return {name: 0 for name in stock_names}

@st.cache_data(ttl=CACHE_TTL)
def get_us_scores_c(theme_names_tuple):
    return fetch_us_theme_scores(list(theme_names_tuple))

@st.cache_data(ttl=86400)
def get_rs_ratings_c(codes_tuple):
    if not RS_AVAILABLE:
        return {}
    return fetch_rs_ratings_from_history(list(codes_tuple))

@st.cache_data(ttl=3600)
def load_history_v2(date_str):
    """주도테마_기록_V2 시트에서 특정 날짜 데이터 불러오기"""
    import json, os
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        return None, "gspread 미설치"
    try:
        creds_json = os.environ.get("GOOGLE_CREDENTIALS", "").strip()
        sheet_id   = os.environ.get("SHEET_ID", "")
        if not creds_json or not sheet_id:
            return None, "환경변수 없음"
        creds_dict = json.loads(creds_json)
        scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        wb = gc.open_by_key(sheet_id)
        try:
            ws = wb.worksheet("주도테마_기록_V2")
        except gspread.exceptions.WorksheetNotFound:
            return None, "주도테마_기록_V2 시트 없음"

        rows = ws.get_all_values()
        if len(rows) < 2:
            return None, "데이터 없음"

        date_rows = [
            r for r in rows[1:]
            if r and r[0] == date_str and len(r) > 2
            and r[1] not in ("개별상한가", "")
            and not (len(r) > 2 and r[2].startswith("---"))
        ]
        if not date_rows:
            return None, f"{date_str} 데이터 없음"

        themes = []
        separated = []
        for row in date_rows:
            if row[1].startswith("상한가"):
                try:
                    rate_num = float(row[7].replace("%","").replace("+","")) if len(row) > 7 else 0.0
                except:
                    rate_num = 0.0
                try:
                    amount_eok = float(row[8].replace(",","")) if len(row) > 8 and row[8] else 0.0
                except:
                    amount_eok = 0.0
                orig = row[10].replace("(원래테마: ","").replace(")","") if len(row) > 10 else ""
                separated.append({
                    "name": row[2], "code": "", "price": 0,
                    "rate_num": rate_num, "amount_eok": amount_eok,
                    "is_limit_up": True, "is_52w_high": False,
                    "rs_rating": None, "original_theme": orig,
                })
                continue

            stocks = []
            for i in range(6, min(6 + 5*4, len(row)), 4):
                name = row[i] if i < len(row) else ""
                if not name:
                    continue
                try:
                    rate_num = float(row[i+1].replace("%","").replace("+","")) if i+1 < len(row) else 0.0
                except:
                    rate_num = 0.0
                try:
                    amount_eok = float(row[i+2].replace(",","")) if i+2 < len(row) and row[i+2] else 0.0
                except:
                    amount_eok = 0.0
                try:
                    price = int(str(row[i+3]).replace(",","")) if i+3 < len(row) and row[i+3] else 0
                except:
                    price = 0
                stocks.append({
                    "name": name, "code": "", "price": price,
                    "rate_num": rate_num, "amount_eok": amount_eok,
                    "is_limit_up": rate_num >= 29.5, "is_52w_high": False,
                    "rs_rating": None,
                })

            try:
                rising_sum = float(row[3].replace(",","")) if row[3] else 0.0
            except:
                rising_sum = 0.0
            try:
                us_score = float(row[4]) if row[4] else 0.0
            except:
                us_score = 0.0
            try:
                news_count = int(row[5]) if row[5] else 0
            except:
                news_count = 0

            rank_num = 0
            try:
                rank_num = int(row[1])
            except:
                pass
            v2_rank_reason = "us" if rank_num == 1 else ("news" if rank_num == 2 else "")

            themes.append({
                "name": row[2], "code": "",
                "rising_sum": rising_sum, "total_sum": rising_sum,
                "us_score": us_score, "news_count": news_count,
                "stocks": stocks,
                "has_limit_up": any(s["is_limit_up"] for s in stocks),
                "has_52w_high": False,
                "is_top_amount": (rank_num == 1),
                "v2_rank_reason": v2_rank_reason,
            })

        return (themes, separated), None
    except Exception as e:
        return None, str(e)


@st.cache_data(ttl=CACHE_TTL)
def build_theme_ranking_v2():
    """V2 랭킹 빌드"""
    THEME_SCAN_COUNT = 25
    theme_pool = get_theme_list_c(1) + get_theme_list_c(2)
    theme_pool = theme_pool[:THEME_SCAN_COUNT]
    top50_codes = get_top50_codes_c()

    theme_results = []
    separated_limit_up = []

    for theme in theme_pool:
        detail = get_theme_detail_c(theme["code"])
        if not detail:
            continue

        limit_up_stocks    = [s for s in detail if s.get("is_limit_up")]
        non_limit_up_stocks = [s for s in detail if not s.get("is_limit_up")]

        # 상한가 개별테마 분리
        if limit_up_stocks and non_limit_up_stocks:
            best_non = max(non_limit_up_stocks, key=lambda s: s["rate_num"])
            if best_non.get("code") not in top50_codes:
                for lu in limit_up_stocks:
                    separated_limit_up.append({
                        "name": lu["name"], "code": lu.get("code", ""),
                        "price": lu.get("price", 0), "rate_num": lu["rate_num"],
                        "amount_eok": lu["amount_eok"], "is_limit_up": True,
                        "original_theme": theme["name"],
                    })
                detail = non_limit_up_stocks

        # 52주 신고가
        for s in detail:
            s["is_52w_high"] = False
            if s.get("code"):
                high = get_52week_high_c(s["code"])
                if high and s.get("price", 0) >= high:
                    s["is_52w_high"] = True

        rising_sum = sum(s["amount_eok"] for s in detail if s["rate_num"] > 0)
        total_sum  = sum(s["amount_eok"] for s in detail)

        theme_results.append({
            "name": theme["name"], "code": theme["code"],
            "rising_sum": rising_sum, "total_sum": total_sum,
            "stocks": detail,
            "has_limit_up": any(s.get("is_limit_up") for s in detail),
            "has_52w_high": any(s.get("is_52w_high") for s in detail),
        })

    if not theme_results:
        return [], []

    theme_names_tuple = tuple(t["name"] for t in theme_results)
    us_scores   = get_us_scores_c(theme_names_tuple)
    news_counts = get_news_counts_c(theme_names_tuple)

    for t in theme_results:
        t["us_score"]   = us_scores.get(t["name"], 0.0)
        t["news_count"] = news_counts.get(t["name"], 0)

    # 1단계: 상승거래대금합 기준 정렬
    theme_results.sort(key=lambda t: t["rising_sum"], reverse=True)

    # 2단계: 미국연관 1위 → 강제 1위
    us_top = max(theme_results, key=lambda t: t["us_score"])
    if theme_results[0]["name"] != us_top["name"]:
        theme_results = [t for t in theme_results if t["name"] != us_top["name"]]
        theme_results.insert(0, us_top)
    theme_results[0]["v2_rank_reason"] = "us"

    # 3단계: 뉴스노출 1위 → 강제 2위 (중복시 2등)
    news_sorted = sorted(theme_results, key=lambda t: t["news_count"], reverse=True)
    news_top = news_sorted[0]
    if news_top["name"] == theme_results[0]["name"]:
        news_top = news_sorted[1] if len(news_sorted) > 1 else None
    if news_top:
        if len(theme_results) > 1 and theme_results[1]["name"] != news_top["name"]:
            rest = [t for t in theme_results[1:] if t["name"] != news_top["name"]]
            theme_results = [theme_results[0], news_top] + rest
        theme_results[1]["v2_rank_reason"] = "news"

    # 👑 왕관: 전체 시장 거래대금 상위 10 종목 중 뉴스 노출 1위 종목
    crown_stock_name = None
    market_top10_names = get_market_top10_stocks_c()
    if market_top10_names:
        stock_news = get_news_counts_by_stock_c(tuple(market_top10_names))
        news_top_stock = max(market_top10_names, key=lambda n: stock_news.get(n, 0))
        if stock_news.get(news_top_stock, 0) > 0:
            crown_stock_name = news_top_stock

    top10 = theme_results[:10]

    # is_top_amount 플래그
    if top10:
        top_amt = max(top10, key=lambda t: t["total_sum"])
        for t in top10:
            t["is_top_amount"] = (t["name"] == top_amt["name"])

    # 개별 상한가 52주 신고가 처리
    for s in separated_limit_up:
        s["is_52w_high"] = False
        if s.get("code"):
            high = get_52week_high_c(s["code"])
            if high and s.get("price", 0) >= high:
                s["is_52w_high"] = True
    separated_limit_up.sort(key=lambda s: s["amount_eok"], reverse=True)

    return top10, separated_limit_up, crown_stock_name


# ===================== 뷰 모드 초기화 =====================
now = datetime.now(KST)
weekday_list = ['월', '화', '수', '목', '금', '토', '일']

if "v2_view_mode" not in st.session_state:
    st.session_state.v2_view_mode = "PC"
is_mobile = (st.session_state.v2_view_mode == "모바일")

# ===================== 헤더 =====================
if not is_mobile:
    h1, h2, h3, h4 = st.columns([5, 1, 0.5, 0.5])
    with h1:
        st.markdown("""
            <div class="tima-header-box">
                <div><span class="logo-main">주도테마</span><span class="logo-sub">V2</span></div>
                <div id="live-clock-v2" class="date-text"></div>
            </div>""", unsafe_allow_html=True)
        components.html("""
            <script>
            function updateClockV2() {
                const weekdays = ['일','월','화','수','목','금','토'];
                const now = new Date();
                const mm = String(now.getMonth()+1).padStart(2,'0');
                const dd = String(now.getDate()).padStart(2,'0');
                const wd = weekdays[now.getDay()];
                const hh = String(now.getHours()).padStart(2,'0');
                const mi = String(now.getMinutes()).padStart(2,'0');
                const ss = String(now.getSeconds()).padStart(2,'0');
                const el = window.parent.document.getElementById('live-clock-v2');
                if (el) el.innerText = mm+'-'+dd+'('+wd+') '+hh+':'+mi+':'+ss;
            }
            updateClockV2(); setInterval(updateClockV2, 1000);
            </script>""", height=0)
    with h2:
        selected_date = st.date_input(
            "날짜 선택",
            value=date.today(),
            min_value=date(2026, 1, 1),
            max_value=date.today(),
            label_visibility="collapsed",
            key="v2_date"
        )
    with h3:
        if st.button("📱 모바일", use_container_width=True, key="v2_mob_btn"):
            st.session_state.v2_view_mode = "모바일"
            st.rerun()
    with h4:
        if st.button("🔄 새로고침", use_container_width=True, key="v2_refresh"):
            st.cache_data.clear()
            st.rerun()
else:
    st.markdown("""
        <div class="tima-header-box">
            <div><span class="logo-main">주도테마</span><span class="logo-sub">V2</span></div>
            <div id="live-clock-v2" class="date-text" style="font-size:16px;"></div>
        </div>""", unsafe_allow_html=True)
    components.html("""
        <script>
        function updateClockV2() {
            const weekdays = ['일','월','화','수','목','금','토'];
            const now = new Date();
            const mm = String(now.getMonth()+1).padStart(2,'0');
            const dd = String(now.getDate()).padStart(2,'0');
            const wd = weekdays[now.getDay()];
            const hh = String(now.getHours()).padStart(2,'0');
            const mi = String(now.getMinutes()).padStart(2,'0');
            const ss = String(now.getSeconds()).padStart(2,'0');
            const el = window.parent.document.getElementById('live-clock-v2');
            if (el) el.innerText = mm+'-'+dd+'('+wd+') '+hh+':'+mi+':'+ss;
        }
        updateClockV2(); setInterval(updateClockV2, 1000);
        </script>""", height=0)
    m1, m2, m3 = st.columns([3, 1, 1])
    with m1:
        selected_date = st.date_input(
            "날짜",
            value=date.today(),
            min_value=date(2026, 1, 1),
            max_value=date.today(),
            label_visibility="collapsed",
            key="v2_date"
        )
    with m2:
        if st.button("🖥️ PC", use_container_width=True, key="v2_pc_btn"):
            st.session_state.v2_view_mode = "PC"
            st.rerun()
    with m3:
        if st.button("🔄", use_container_width=True, key="v2_mob_refresh"):
            st.cache_data.clear()
            st.rerun()
    st.markdown("""
        <style>
        div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
        div[data-testid="column"] { min-width: 0 !important; flex: 1 !important; }
        .theme-card-container { padding: 6px !important; margin-bottom: 6px !important; }
        .theme-card-header { font-size: 12px !important; gap: 4px !important; }
        .theme-card-money { font-size: 10px !important; }
        .stock-item-box { padding: 5px 6px !important; margin-bottom: 4px !important; }
        .stock-item-name { font-size: 12px !important; }
        .txt-up-red, .txt-down-blue { font-size: 11px !important; }
        .candle-bar-track { height: 3px !important; margin-top: 3px !important; }
        </style>""", unsafe_allow_html=True)

# ===================== 날짜 확인 =====================
selected_date = st.session_state.get("v2_date", date.today())
is_today = (selected_date == date.today())
selected_date_str = selected_date.strftime("%Y-%m-%d")

# ===================== 자동 새로고침 (오늘 + 장중만) =====================
if is_market_open_now(now) and is_today:
    st.markdown(f"<meta http-equiv='refresh' content='{CACHE_TTL}'>", unsafe_allow_html=True)

# ===================== 데이터 로드 =====================
crown_stock_name = None

if is_today:
    with st.spinner("V2 테마 랭킹 계산 중..."):
        result = build_theme_ranking_v2()
    top10, separated, crown_stock_name = result
else:
    with st.spinner(f"{selected_date_str} V2 데이터 불러오는 중..."):
        hist_result, err = load_history_v2(selected_date_str)
    if err:
        st.warning(f"{selected_date_str} 저장된 V2 데이터가 없습니다: {err}")
        st.stop()
    top10, separated = hist_result

# RS Rating 주입
if RS_AVAILABLE and top10:
    all_codes = list({s["code"] for t in top10 for s in t.get("stocks", []) if s.get("code")})
    if separated:
        all_codes += [s["code"] for s in separated if s.get("code")]
    all_codes = list(set(all_codes))
    if all_codes:
        rs_map = get_rs_ratings_c(tuple(sorted(all_codes)))
        for t in top10:
            for s in t.get("stocks", []):
                s["rs_rating"] = rs_map.get(s.get("code", ""))
        for s in separated:
            s["rs_rating"] = rs_map.get(s.get("code", ""))
else:
    for t in top10:
        for s in t.get("stocks", []):
            s.setdefault("rs_rating", None)
    for s in separated:
        s.setdefault("rs_rating", None)

if not top10:
    st.warning("테마 데이터를 불러오지 못했습니다. 잠시 후 새로고침 해주세요.")
    st.stop()

# ===================== 디버그: 뉴스 노출 현황 =====================
if is_today:
    with st.expander("🔍 거래대금 상위 10 종목 뉴스 노출 현황 (디버그)", expanded=False):
        market_top10 = get_market_top10_stocks_c()
        if market_top10:
            stock_news = get_news_counts_by_stock_c(tuple(market_top10))
            rows_debug = sorted(
                [(name, stock_news.get(name, 0)) for name in market_top10],
                key=lambda x: x[1], reverse=True
            )
            for i, (name, cnt) in enumerate(rows_debug, 1):
                crown = "👑 " if (crown_stock_name and name == crown_stock_name) else ""
                st.write(f"{i}. {crown}**{name}** — 뉴스 {cnt}건")
        else:
            st.write("데이터 없음")


# ===================== 카드 렌더 함수 =====================
def render_stock_item(s, now, crown_stock_name=None):
    rate_num = s["rate_num"]
    is_limit_up = s.get("is_limit_up", False) or rate_num >= 29.5
    rate_str = f"{rate_num:.2f}%"
    if rate_num >= 0:
        color = "txt-up-red"
        bar_class = "candle-bar-up"
        rate_str = f"↑{rate_str}" if is_limit_up else rate_str
    else:
        color = "txt-down-blue"
        bar_class = "candle-bar-down"
    width_pct = min(abs(rate_num) / 30 * 50, 50)
    limit_cls = "bg-limit-up" if is_limit_up else ""

    encoded_name = urllib.parse.quote(s["name"])
    news_url = f"https://search.naver.com/search.naver?where=news&query={encoded_name}"

    name_icons = ""
    # 👑 왕관
    if crown_stock_name and s["name"] == crown_stock_name:
        name_icons += '<span style="font-size:16px; margin-left:2px;">👑</span>'
    # 52주 신고가
    if s.get("is_52w_high"):
        name_icons += '<span style="background-color:#16a34a; color:#fff; font-size:12px; font-weight:700; padding:1px 6px; border-radius:4px; margin-left:4px;">52주신고가</span>'
    # RS Rating
    rs = s.get("rs_rating")
    if rs is not None:
        if rs >= 90:   rs_bg = "#dc2626"
        elif rs >= 80: rs_bg = "#ea580c"
        elif rs >= 60: rs_bg = "#65a30d"
        else:          rs_bg = "#94a3b8"
        name_icons += f'<span style="background-color:{rs_bg}; color:#fff; font-size:11px; font-weight:700; padding:1px 5px; border-radius:4px; margin-left:4px;">RS {rs}</span>'

    stock_html = (
        f'<div class="stock-item-box {limit_cls}">'
        f'<div class="stock-item-main">'
        f'<div style="display:flex; align-items:center; gap:0;">'
        f'<a href="{news_url}" target="_blank" class="stock-item-name">{s["name"]}</a>{name_icons}'
        f'</div>'
        f'<span class="{color}">{rate_str}</span>'
        f'</div>'
        f'<div class="stock-item-meta">'
        f'<span style="color:#000000; font-size:19px; font-weight:700;">{s.get("price",0):,}원</span>'
        f'<span style="color:#000000; font-size:19px; font-weight:700;">{s["amount_eok"]:,.0f}억(KRX)</span>'
        f'</div>'
        f'<div class="candle-bar-track">'
        f'<div class="candle-center-line"></div>'
        f'<div class="{bar_class}" style="width: {width_pct:.0f}%;"></div>'
        f'</div>'
        f'</div>'
    )
    st.markdown(stock_html, unsafe_allow_html=True)


def render_theme_card_v2(theme, now, crown_stock_name=None):
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

    # V2 강제순위 배지
    rank_badge = ""
    reason = theme.get("v2_rank_reason", "")
    if reason == "us":
        rank_badge = '<span class="v2-rank-badge v2-us-badge">🇺🇸 미국연관 1위</span>'
    elif reason == "news":
        rank_badge = '<span class="v2-rank-badge v2-news-badge">📰 뉴스노출 1위</span>'

    # 뉴스/US 점수 표시
    sub_info = []
    if theme.get("us_score", 0) > 0:
        sub_info.append(f'<span style="color:#93c5fd; font-size:12px;">🇺🇸 {theme["us_score"]:.2f}</span>')
    if theme.get("news_count", 0) > 0:
        sub_info.append(f'<span style="color:#c4b5fd; font-size:12px;">📰 {theme["news_count"]}건</span>')
    sub_html = " &nbsp;".join(sub_info)

    card_html = (
        f'<div class="theme-card-container">'
        f'<div class="theme-card-header">'
        f'<div class="theme-card-title">{rank_badge}{theme["name"]} {icons_html}</div>'
        f'<span class="theme-card-money">{total_sum_str}</span>'
        f'</div>'
        + (f'<div style="margin-bottom:6px;">{sub_html}</div>' if sub_html else "")
        + f'</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)

    for s in theme["stocks"]:
        render_stock_item(s, now, crown_stock_name)

    st.markdown("<br>", unsafe_allow_html=True)


# ===================== 레이아웃 렌더링 =====================
row1 = top10[:5]
row2 = top10[5:10]
view_mode = st.session_state.get("v2_view_mode", "PC")

if view_mode == "PC":
    cols1 = st.columns(5)
    for theme, col in zip(row1, cols1):
        with col:
            render_theme_card_v2(theme, now, crown_stock_name)
    cols2 = st.columns(5)
    for theme, col in zip(row2, cols2):
        with col:
            render_theme_card_v2(theme, now, crown_stock_name)
else:
    for i in range(0, len(top10), 2):
        mob_cols = st.columns(2)
        for j, col in enumerate(mob_cols):
            idx = i + j
            if idx < len(top10):
                with col:
                    render_theme_card_v2(top10[idx], now, crown_stock_name)

# ===================== 개별 상한가 테마 섹션 =====================
if separated:
    st.markdown("---")
    st.markdown("""
        <div style="background-color:#7f1d1d; border-radius:10px; padding:10px 14px; margin-bottom:12px;">
            <span style="color:#fca5a5; font-weight:700; font-size:18px;">🔴 개별 상한가 테마</span>
            <span style="color:#fca5a5; font-size:13px; margin-left:8px;">
                상한가 外 최고상승 종목이 거래대금 상위 50 미포함 → 상한가 종목 개별분리
            </span>
        </div>
    """, unsafe_allow_html=True)

    if view_mode == "PC":
        sep_cols = st.columns(min(5, len(separated)))
        for i, s in enumerate(separated):
            col_idx = i % len(sep_cols)
            with sep_cols[col_idx]:
                st.markdown(
                    f'<div style="background-color:#1e3a5f; border-radius:8px; padding:8px 10px; margin-bottom:8px;">'
                    f'<div style="color:#fca5a5; font-size:12px; margin-bottom:4px;">← {s["original_theme"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
                render_stock_item(s, now, crown_stock_name)
    else:
        for s in separated:
            st.markdown(
                f'<div style="color:#fca5a5; font-size:11px; margin-bottom:2px;">← {s["original_theme"]}</div>',
                unsafe_allow_html=True
            )
            render_stock_item(s, now, crown_stock_name)

if is_today:
    st.caption(f"V2 랭킹: 상승거래대금 기반 · {CACHE_TTL//60}분마다 자동갱신 · 🇺🇸미국연관 강제1위 · 📰뉴스노출 강제2위")
else:
    st.caption(f"📅 {selected_date_str} 저장 데이터 · V2 랭킹: 🇺🇸미국연관 강제1위 · 📰뉴스노출 강제2위")
