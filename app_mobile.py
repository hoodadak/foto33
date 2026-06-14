import streamlit as st
import streamlit.components.v1 as components
import urllib.parse
import requests
import json
import os
from datetime import datetime, date, timedelta, timezone
from bs4 import BeautifulSoup

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

# ===================== 기본 설정 =====================
st.set_page_config(page_title="주도테마 모바일", layout="centered")

KST = timezone(timedelta(hours=9))
now = datetime.now(KST)
weekday_list = ['월', '화', '수', '목', '금', '토', '일']

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
CACHE_TTL = 180
TOP_THEME_COUNT = 10
THEME_SCAN_COUNT = 25
STOCKS_PER_THEME = 5

ETF_ETN_PREFIXES = (
    "KODEX", "TIGER", "SOL", "ACE", "RISE", "PLUS", "KBSTAR", "HANARO",
    "ARIRANG", "KOSEF", "TIMEFOLIO", "WOORI", "VITA", "FOCUS", "마이다스",
    "삼성 인버스", "신한", "ETN", "ETF"
)

KR_MARKET_HOLIDAYS = {
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18",
    "2026-03-01", "2026-05-05", "2026-05-24", "2026-06-06",
    "2026-08-15", "2026-09-24", "2026-09-25", "2026-09-26",
    "2026-10-03", "2026-10-09", "2026-12-25", "2026-12-31",
}

def is_market_open_now(dt):
    if dt.weekday() >= 5:
        return False
    if dt.strftime("%Y-%m-%d") in KR_MARKET_HOLIDAYS:
        return False
    h = dt.hour + dt.minute / 60
    return 8 <= h < 18

# ===================== 데이터 함수 =====================
@st.cache_data(ttl=CACHE_TTL)
def get_trading_top(market_n=1):
    url = f"https://finance.naver.com/sise/sise_quant.naver?sosok={market_n}"
    res = requests.get(url, headers=HEADERS, timeout=7)
    res.encoding = "euc-kr"
    soup = BeautifulSoup(res.text, "html.parser")
    results = []
    table = soup.select_one("table.type_2")
    if not table:
        return results
    for tr in table.select("tr"):
        tds = tr.select("td")
        if len(tds) < 6:
            continue
        name_tag = tds[1].select_one("a")
        if not name_tag:
            continue
        name = name_tag.text.strip()
        if any(name.upper().startswith(p.upper()) or p in name for p in ETF_ETN_PREFIXES):
            continue
        rate_tag = tds[4].select_one("span")
        rate_text = tds[4].text.strip().replace("%", "").replace(",", "")
        try:
            rate_num = float(rate_text)
        except ValueError:
            continue
        is_down = False
        if rate_tag and "nv" in (rate_tag.get("class") or []):
            is_down = True
        if "-" in tds[4].text:
            is_down = True
        rate_num = -abs(rate_num) if is_down else abs(rate_num)
        amount_text = tds[5].text.strip().replace(",", "")
        try:
            amount_eok = float(amount_text) / 100.0
        except ValueError:
            amount_eok = 0.0
        href = name_tag.get("href", "")
        code = href.split("code=")[-1] if "code=" in href else ""
        results.append({"name": name, "code": code, "rate_num": rate_num, "amount_eok": amount_eok})
    return results

@st.cache_data(ttl=CACHE_TTL)
def get_top_rising_stock():
    all_stocks = get_trading_top(0) + get_trading_top(1)
    rising = [s for s in all_stocks if s["rate_num"] > 0]
    rising.sort(key=lambda x: x["amount_eok"], reverse=True)
    return rising[0] if rising else None

@st.cache_data(ttl=CACHE_TTL)
def get_theme_list(page=1):
    url = f"https://finance.naver.com/sise/theme.naver?page={page}"
    res = requests.get(url, headers=HEADERS, timeout=7)
    res.encoding = "euc-kr"
    soup = BeautifulSoup(res.text, "html.parser")
    themes = []
    table = soup.select_one("table.type_1")
    if not table:
        return themes
    for tr in table.select("tr"):
        tds = tr.select("td")
        if len(tds) < 4:
            continue
        link = tr.select_one("td.col_type1 a")
        if not link:
            continue
        theme_name = link.text.strip()
        href = link.get("href", "")
        theme_code = href.split("no=")[-1].split("&")[0] if "no=" in href else ""
        leading_stocks = [a.text.strip() for a in tr.select("a") if "item/main.naver" in a.get("href", "") and a.text.strip()]
        themes.append({"name": theme_name, "code": theme_code, "leading_stocks": leading_stocks})
    return themes

@st.cache_data(ttl=CACHE_TTL)
def get_theme_detail(theme_code, limit=STOCKS_PER_THEME):
    url = f"https://finance.naver.com/sise/sise_group_detail.naver?type=theme&no={theme_code}"
    res = requests.get(url, headers=HEADERS, timeout=7)
    res.encoding = "euc-kr"
    soup = BeautifulSoup(res.text, "html.parser")
    stocks = []
    table = soup.select_one("table.type_5")
    if not table:
        return stocks
    for tr in table.select("tr"):
        tds = tr.select("td")
        if len(tds) < 10:
            continue
        name_tag = tds[0].select_one("a")
        if not name_tag:
            continue
        name = name_tag.text.strip()
        href = name_tag.get("href", "")
        code = href.split("code=")[-1] if "code=" in href else ""
        price_text = tds[2].text.strip().replace(",", "")
        try:
            price = int(price_text)
        except ValueError:
            price = 0
        rate_text = tds[4].text.strip().replace("%", "").replace(",", "")
        is_down = "-" in rate_text
        rate_text = rate_text.replace("+", "").replace("-", "")
        try:
            rate_num = float(rate_text)
        except ValueError:
            rate_num = 0.0
        if is_down:
            rate_num = -rate_num
        is_limit_up_flag = "상한가" in tds[3].text
        amount_text = tds[8].text.strip().replace(",", "")
        try:
            amount_eok = float(amount_text) / 100.0
        except ValueError:
            amount_eok = 0.0
        stocks.append({"name": name, "code": code, "price": price, "rate_num": rate_num,
                       "amount_eok": amount_eok, "is_limit_up": is_limit_up_flag})
        if len(stocks) >= limit:
            break
    return stocks

@st.cache_data(ttl=CACHE_TTL)
def get_52week_high(ticker):
    try:
        url = f"https://m.stock.naver.com/api/stock/{ticker}/integration"
        res = requests.get(url, headers=HEADERS, timeout=5)
        data = res.json()
        def search(obj):
            if isinstance(obj, dict):
                if obj.get("code") == "highPriceOf52Weeks":
                    val = obj.get("value", "").replace(",", "")
                    try:
                        return int(val)
                    except ValueError:
                        return None
                for v in obj.values():
                    r = search(v)
                    if r is not None:
                        return r
            elif isinstance(obj, list):
                for item in obj:
                    r = search(item)
                    if r is not None:
                        return r
            return None
        return search(data)
    except Exception:
        return None

@st.cache_data(ttl=CACHE_TTL)
def build_theme_ranking():
    top_stock = get_top_rising_stock()
    theme_pool = get_theme_list(1) + get_theme_list(2)
    theme_pool = theme_pool[:THEME_SCAN_COUNT]
    theme_results = []
    selected_theme_code = None
    for theme in theme_pool:
        detail = get_theme_detail(theme["code"])
        if not detail:
            continue
        if top_stock and selected_theme_code is None:
            for s in detail:
                if s["name"] == top_stock["name"] or s["code"] == top_stock["code"]:
                    selected_theme_code = theme["code"]
                    break
        rising_sum = sum(s["amount_eok"] for s in detail if s["rate_num"] > 0)
        total_sum = sum(s["amount_eok"] for s in detail)
        limit_up_stocks = [s for s in detail if s.get("is_limit_up")]
        other_stocks = [s for s in detail if not s.get("is_limit_up")]
        detail = limit_up_stocks + other_stocks
        theme_results.append({"name": theme["name"], "code": theme["code"],
                               "rising_sum": rising_sum, "total_sum": total_sum,
                               "has_limit_up": len(limit_up_stocks) > 0, "stocks": detail})
    theme_results.sort(key=lambda t: t["rising_sum"], reverse=True)
    if selected_theme_code:
        for i, t in enumerate(theme_results):
            if t["code"] == selected_theme_code:
                top_theme = theme_results.pop(i)
                theme_results.insert(0, top_theme)
                break
    theme_results = theme_results[:TOP_THEME_COUNT]
    leading_stock_to_themes = {}
    for theme in theme_pool:
        for sn in theme.get("leading_stocks", []):
            leading_stock_to_themes.setdefault(sn, set()).add(theme["code"])
    for t in theme_results:
        stocks = t["stocks"]
        if not stocks:
            continue
        top_rate = max(stocks, key=lambda s: s["rate_num"])["name"]
        filtered = []
        for s in stocks:
            owner = leading_stock_to_themes.get(s["name"], set())
            if bool(owner - {t["code"]}) and t["code"] not in owner and s["name"] != top_rate:
                continue
            filtered.append(s)
        for s in filtered:
            s["is_52w_high"] = False
            if s.get("code"):
                high = get_52week_high(s["code"])
                if high and s["price"] >= high:
                    s["is_52w_high"] = True
        t["stocks"] = filtered
        t["total_sum"] = sum(s["amount_eok"] for s in filtered)
        t["has_limit_up"] = any(s.get("is_limit_up") for s in filtered)
        t["has_52w_high"] = any(s.get("is_52w_high") for s in filtered)
    if theme_results:
        top_amt = max(theme_results, key=lambda t: t["total_sum"])
        for t in theme_results:
            t["is_top_amount"] = (t["code"] == top_amt["code"])
    if selected_theme_code:
        pinned = [t for t in theme_results if t["code"] == selected_theme_code]
        others = sorted([t for t in theme_results if t["code"] != selected_theme_code],
                        key=lambda t: t["total_sum"], reverse=True)
        theme_results = pinned + others
    else:
        theme_results.sort(key=lambda t: t["total_sum"], reverse=True)
    return theme_results

@st.cache_data(ttl=3600)
def load_history_from_sheet(date_str):
    if not GSPREAD_AVAILABLE:
        return None
    try:
        creds_json = os.environ.get("GOOGLE_CREDENTIALS", "")
        sheet_id = os.environ.get("SHEET_ID", "")
        if not creds_json or not sheet_id:
            return None
        creds_dict = json.loads(creds_json)
        scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        wb = gc.open_by_key(sheet_id)
        try:
            ws = wb.worksheet(date_str)
        except gspread.exceptions.WorksheetNotFound:
            return None
        rows = ws.get_all_values()
        if len(rows) < 2:
            return None
        themes = []
        for row in rows[1:]:
            if not row or not row[0]:
                continue
            stocks = []
            for i in range(3, min(18, len(row)), 3):
                name = row[i] if i < len(row) else ""
                rate = row[i+1] if i+1 < len(row) else ""
                vol = row[i+2] if i+2 < len(row) else ""
                if name:
                    try:
                        rate_num = float(rate.replace("%", "").replace("+", ""))
                    except ValueError:
                        rate_num = 0.0
                    stocks.append({"name": name, "rate_num": rate_num,
                                   "amount_eok": float(vol.replace(",", "")) if vol else 0.0,
                                   "price": 0, "is_limit_up": rate_num >= 29.5,
                                   "is_52w_high": False, "limit_up_time": None})
            try:
                total_sum = float(row[2].replace(",", "")) if row[2] else 0.0
            except ValueError:
                total_sum = 0.0
            themes.append({"name": row[1] if len(row) > 1 else "", "code": "",
                           "total_sum": total_sum, "rising_sum": total_sum,
                           "has_limit_up": any(s["is_limit_up"] for s in stocks),
                           "has_52w_high": False, "is_top_amount": len(themes) == 0,
                           "stocks": stocks})
        return themes
    except Exception as e:
        st.error(f"과거 데이터 불러오기 실패: {e}")
        return None

# ===================== 모바일 CSS =====================
st.markdown("""
<style>
.stApp { background-color: #DBFDF9; }
.logo-main { font-size: 28px; font-weight: 800; color: #1e293b; }
.date-text { font-size: 16px; color: #000; font-weight: 500; }
.header-box { display: flex; justify-content: space-between; align-items: center; padding: 8px 4px; }

.theme-card-m {
    background-color: #334155; border-radius: 10px;
    padding: 10px; margin-bottom: 12px;
}
.theme-title-row-m {
    display: flex; justify-content: space-between; align-items: center;
    color: white; font-weight: 700; font-size: 16px; margin-bottom: 8px;
}
.theme-money-m { background-color: #475569; padding: 2px 6px; border-radius: 5px; font-size: 13px; }
.stock-box-m {
    background-color: white; border-radius: 8px;
    padding: 8px 10px; margin-bottom: 6px;
}
.limit-up-m { background-color: #FFD1DE !important; }
.stock-row-m { display: flex; justify-content: space-between; align-items: center; }
.stock-name-m { font-weight: 700; font-size: 15px; color: #000; text-decoration: none; }
.rate-up { color: #dc2626; font-weight: 700; font-size: 15px; }
.rate-down { color: #2563eb; font-weight: 700; font-size: 15px; }
.stock-vol-m { font-size: 13px; font-weight: 700; color: #000; text-align: right; margin-top: 2px; }
.badge-52w-m { background-color: #16a34a; color: #fff; font-size: 11px; font-weight: 700;
             padding: 1px 5px; border-radius: 4px; margin-left: 4px; }
.bar-track-m { width: 100%; height: 5px; background-color: #e2e8f0;
             border-radius: 3px; margin-top: 6px; position: relative; }
.bar-center-m { position: absolute; left: 50%; top: -2px; width: 2px; height: 9px;
              background-color: #94a3b8; z-index: 3; }
.bar-up-m { position: absolute; left: 50%; top: 0; height: 100%;
          background-color: #ef4444; border-radius: 0 3px 3px 0; }
.bar-down-m { position: absolute; right: 50%; top: 0; height: 100%;
            background-color: #3b82f6; border-radius: 3px 0 0 3px; }
</style>
""", unsafe_allow_html=True)

# ===================== 자동 새로고침 =====================
if is_market_open_now(now):
    st.markdown(f"<meta http-equiv='refresh' content='{CACHE_TTL}'>", unsafe_allow_html=True)

# ===================== 헤더 =====================
st.markdown("""
    <div class="header-box">
        <span class="logo-main">주도테마</span>
        <span id="mob-clock" class="date-text"></span>
    </div>
""", unsafe_allow_html=True)
components.html("""
    <script>
    function tick() {
        const w = ['일','월','화','수','목','금','토'];
        const n = new Date();
        const mm = String(n.getMonth()+1).padStart(2,'0');
        const dd = String(n.getDate()).padStart(2,'0');
        const wd = w[n.getDay()];
        const hh = String(n.getHours()).padStart(2,'0');
        const mi = String(n.getMinutes()).padStart(2,'0');
        const ss = String(n.getSeconds()).padStart(2,'0');
        const el = window.parent.document.getElementById('mob-clock');
        if(el) el.innerText = mm+'-'+dd+'('+wd+') '+hh+':'+mi+':'+ss;
    }
    tick(); setInterval(tick, 1000);
    </script>
""", height=0)

# 날짜 선택 + 새로고침
c1, c2 = st.columns([3, 1])
with c1:
    selected_date = st.date_input("날짜", value=date.today(),
                                   min_value=date(2026, 1, 1), max_value=date.today(),
                                   label_visibility="collapsed")
with c2:
    if st.button("🔄 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

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

# ===================== 테마 카드 렌더링 =====================
for theme in theme_ranking:
    icons = ""
    if theme.get("is_top_amount"):
        icons += '<span style="filter:hue-rotate(140deg) saturate(3);">👍</span>'
    if theme.get("has_52w_high"):
        icons += '⭐'
    if theme.get("has_limit_up"):
        icons += '<span style="color:#dc2626;font-weight:900;">⬆</span>'

    total_sum_str = f"KRX {theme['total_sum']:,.0f}억"

    # 테마 헤더
    st.markdown(
        f'<div class="theme-card-m">'
        f'<div class="theme-title-row-m">'
        f'<span>{theme["name"]} {icons}</span>'
        f'<span class="theme-money-m">{total_sum_str}</span>'
        f'</div>',
        unsafe_allow_html=True
    )

    # 종목 카드
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
        vol_str = f"{s['amount_eok']:,.0f}억(KRX)"

        st.markdown(
            f'<div class="{box_class}">'
            f'<div class="stock-row-m">'
            f'<span><a href="{news_url}" target="_blank" class="stock-name-m">{s["name"]}</a>{badge_52w}</span>'
            f'<span class="{rate_class}">{rate_str}</span>'
            f'</div>'
            f'<div class="stock-vol-m">{vol_str}</div>'
            f'<div class="bar-track-m">'
            f'<div class="bar-center-m"></div>'
            f'<div class="{bar_dir}-m" style="width:{width_pct:.0f}%;"></div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    st.markdown('</div>', unsafe_allow_html=True)

st.caption(f"네이버 금융 실시간 · {CACHE_TTL//60}분 캐시")
