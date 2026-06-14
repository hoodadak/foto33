import streamlit as st
import streamlit.components.v1 as components
import urllib.parse
import requests
import json
import os
from datetime import datetime, date, timedelta, timezone

KST = timezone(timedelta(hours=9))
now = datetime.now(KST)
from bs4 import BeautifulSoup

# gspread는 선택적 임포트 (없어도 실시간 기능은 동작)
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

# ===================== 기본 설정 =====================
st.set_page_config(page_title="주도테마", layout="wide")

now = datetime.now()
weekday_list = ['월', '화', '수', '목', '금', '토', '일']
current_date_str = f"{now.strftime('%m-%d')}({weekday_list[now.weekday()]}) {now.strftime('%H:%M')}"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

CACHE_TTL = 180  # 3분
TOP_THEME_COUNT = 10
THEME_SCAN_COUNT = 25
STOCKS_PER_THEME = 5

# ===================== Google Sheets 과거 데이터 조회 =====================
@st.cache_data(ttl=3600)
def load_history_from_sheet(date_str):
    """Google Sheets에서 특정 날짜 데이터 불러오기"""
    if not GSPREAD_AVAILABLE:
        return None
    try:
        creds_json = os.environ.get("GOOGLE_CREDENTIALS", "")
        sheet_id = os.environ.get("SHEET_ID", "")
        if not creds_json or not sheet_id:
            return None
        creds_dict = json.loads(creds_json)
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
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
        # 헤더 제외하고 테마 데이터 파싱
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
                    stocks.append({
                        "name": name,
                        "rate_num": rate_num,
                        "amount_eok": float(vol.replace(",", "")) if vol else 0.0,
                        "price": 0,
                        "is_limit_up": rate_num >= 29.5,
                        "is_52w_high": False,
                        "limit_up_time": None
                    })
            try:
                total_sum = float(row[2].replace(",", "")) if row[2] else 0.0
            except ValueError:
                total_sum = 0.0
            themes.append({
                "name": row[1] if len(row) > 1 else "",
                "code": "",
                "total_sum": total_sum,
                "rising_sum": total_sum,
                "has_limit_up": any(s["is_limit_up"] for s in stocks),
                "has_52w_high": False,
                "is_top_amount": len(themes) == 0,
                "stocks": stocks
            })
        return themes
    except Exception as e:
        st.error(f"과거 데이터 불러오기 실패: {e}")
        return None

# 한국 증시 공휴일(휴장일) 목록 - 필요시 연도별로 추가/수정
KR_MARKET_HOLIDAYS = {
    # 2026년 예시 (실제 거래소 휴장일 캘린더에 맞춰 갱신 필요)
    "2026-01-01",  # 신정
    "2026-02-16", "2026-02-17", "2026-02-18",  # 설날 연휴
    "2026-03-01",  # 삼일절
    "2026-05-05",  # 어린이날
    "2026-05-24",  # 부처님오신날
    "2026-06-06",  # 현충일
    "2026-08-15",  # 광복절
    "2026-09-24", "2026-09-25", "2026-09-26",  # 추석 연휴
    "2026-10-03",  # 개천절
    "2026-10-09",  # 한글날
    "2026-12-25",  # 성탄절
    "2026-12-31",  # 연말 휴장(통상)
}


def is_market_open_now(dt):
    """평일(월~금) 08:00~18:00, 공휴일 제외 시 True"""
    if dt.weekday() >= 5:  # 5=토, 6=일
        return False
    if dt.strftime("%Y-%m-%d") in KR_MARKET_HOLIDAYS:
        return False
    hour_minute = dt.hour + dt.minute / 60
    return 8 <= hour_minute < 18


ETF_ETN_PREFIXES = (
    "KODEX", "TIGER", "SOL", "ACE", "RISE", "PLUS", "KBSTAR", "HANARO",
    "ARIRANG", "KOSEF", "TIMEFOLIO", "WOORI", "VITA", "FOCUS", "마이다스",
    "삼성 인버스", "신한", "ETN", "ETF"
)


# ===================== 1. 거래상위(거래대금) 종목 수집 =====================
@st.cache_data(ttl=CACHE_TTL)
def get_trading_top(market_n=1):
    """sise_quant.naver 에서 거래대금 상위 종목 수집 (코스피/코스닥)"""
    url = f"https://finance.naver.com/sise/sise_quant.naver?sosok={market_n}"
    res = requests.get(url, headers=HEADERS, timeout=7)
    res.encoding = "euc-kr"
    soup = BeautifulSoup(res.text, "html.parser")

    results = []
    table = soup.select_one("table.type_2")
    if not table:
        return results

    # 테이블 헤더 순서: N | 종목명 | 현재가 | 전일비 | 등락률 | 거래대금(백만) | 시가총액(억)
    for tr in table.select("tr"):
        tds = tr.select("td")
        if len(tds) < 6:
            continue
        name_tag = tds[1].select_one("a")
        if not name_tag:
            continue
        name = name_tag.text.strip()

        # ETF/ETN 제외
        if any(name.upper().startswith(p.upper()) or p in name for p in ETF_ETN_PREFIXES):
            continue

        rate_tag = tds[4].select_one("span")
        rate_text = tds[4].text.strip().replace("%", "").replace(",", "")
        try:
            rate_num = float(rate_text)
        except ValueError:
            continue
        # 상승 여부 (색상 클래스로 판별)
        is_down = False
        if rate_tag and "nv" in (rate_tag.get("class") or []):
            is_down = True
        if "-" in tds[4].text:
            is_down = True
        if is_down:
            rate_num = -abs(rate_num)
        else:
            rate_num = abs(rate_num)

        # 거래대금(백만원) -> 억원
        amount_text = tds[5].text.strip().replace(",", "")
        try:
            amount_eok = float(amount_text) / 100.0
        except ValueError:
            amount_eok = 0.0

        href = name_tag.get("href", "")
        code = ""
        if "code=" in href:
            code = href.split("code=")[-1]

        results.append({
            "name": name,
            "code": code,
            "rate_num": rate_num,
            "amount_eok": amount_eok
        })

    return results


@st.cache_data(ttl=CACHE_TTL)
def get_top_rising_stock():
    """코스피+코스닥 통합, 상승종목 중 거래대금 1위 종목 반환"""
    all_stocks = get_trading_top(0) + get_trading_top(1)
    rising = [s for s in all_stocks if s["rate_num"] > 0]
    rising.sort(key=lambda x: x["amount_eok"], reverse=True)
    return rising[0] if rising else None


# ===================== 2. 테마별 시세 목록 수집 =====================
@st.cache_data(ttl=CACHE_TTL)
def get_theme_list(page=1):
    """theme.naver 에서 테마 목록(이름, 코드, 주도주 목록) 수집

    각 행에는 테마명 외에 "주도주" 컬럼이 있으며, 보통 2개의 종목명
    (상승 주도주 / 하락 주도주)이 링크 형태로 들어있음.
    """
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
        theme_code = ""
        if "no=" in href:
            theme_code = href.split("no=")[-1].split("&")[0]

        # 주도주: 행 내의 모든 종목 링크(item/main.naver?code=...) 중
        # 테마명 링크(sise_group_detail) 이외의 것들을 주도주로 간주
        leading_stocks = []
        for a in tr.select("a"):
            a_href = a.get("href", "")
            if "item/main.naver" in a_href:
                stock_name = a.text.strip()
                if stock_name:
                    leading_stocks.append(stock_name)

        themes.append({"name": theme_name, "code": theme_code, "leading_stocks": leading_stocks})

    return themes


# ===================== 3. 테마 상세(종목 리스트) 수집 =====================
@st.cache_data(ttl=CACHE_TTL)
def get_theme_detail(theme_code, limit=STOCKS_PER_THEME):
    """sise_group_detail.naver?type=theme&no=코드 에서 종목 리스트(이름, 코드, 등락률, 거래대금) 수집

    실제 데이터 행 구조 (총 11개 td, 화면 캡처로 확인됨):
      [0] 종목명(링크)
      [1] 테마 편입 사유(숨김 텍스트)
      [2] 현재가
      [3] 전일비 (상한가/상승/하락 표시 포함)
      [4] 등락률 (예: '+30.00%', '-1.23%')
      [5] 매수호가
      [6] 매도호가
      [7] 거래량 (주식수)
      [8] 거래대금 (당일, 백만원 단위)  <- 사용
      [9] 전일거래량
      [10] (빈 칸)
    """
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
        code = ""
        if "code=" in href:
            code = href.split("code=")[-1]

        price_text = tds[2].text.strip().replace(",", "")
        try:
            price = int(price_text)
        except ValueError:
            price = 0

        # 등락률: "+30.00%", "-1.23%" 형태
        rate_text = tds[4].text.strip().replace("%", "").replace(",", "")
        is_down = "-" in rate_text
        rate_text = rate_text.replace("+", "").replace("-", "")
        try:
            rate_num = float(rate_text)
        except ValueError:
            rate_num = 0.0
        if is_down:
            rate_num = -rate_num

        # 상한가 여부: 전일비 셀에 "상한가" 텍스트 포함
        is_limit_up_flag = "상한가" in tds[3].text

        # 거래대금(백만원) -> 억원 (당일 거래대금 = td[8])
        amount_text = tds[8].text.strip().replace(",", "")
        try:
            amount_eok = float(amount_text) / 100.0
        except ValueError:
            amount_eok = 0.0

        stocks.append({
            "name": name,
            "code": code,
            "price": price,
            "rate_num": rate_num,
            "amount_eok": amount_eok,
            "is_limit_up": is_limit_up_flag
        })

        if len(stocks) >= limit:
            break

    return stocks


# ===================== 3-1. 상한가 종목의 체결시각(상한가 도달 시각) 조회 =====================
@st.cache_data(ttl=CACHE_TTL)
def get_limit_up_time(ticker):
    """종목 상세페이지에서 현재가 옆 체결시각을 가져옴 (상한가 도달 추정 시각)"""
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "html.parser")

        time_tag = soup.select_one("#time")
        if time_tag:
            return time_tag.text.strip()  # 예: "15:30"
    except Exception:
        pass
    return None


# ===================== 3-2. 52주 최고가 조회 (52주 신고가 판별용) =====================
@st.cache_data(ttl=CACHE_TTL)
def get_52week_high(ticker):
    """네이버 모바일 증권 API에서 52주 최고가를 가져옴"""
    try:
        url = f"https://m.stock.naver.com/api/stock/{ticker}/integration"
        res = requests.get(url, headers=HEADERS, timeout=5)
        data = res.json()

        # totalInfos 등 여러 섹션에 code/key/value 형태의 항목들이 있음
        def search(obj):
            if isinstance(obj, dict):
                if obj.get("code") == "highPriceOf52Weeks":
                    val = obj.get("value", "").replace(",", "")
                    try:
                        return int(val)
                    except ValueError:
                        return None
                for v in obj.values():
                    result = search(v)
                    if result is not None:
                        return result
            elif isinstance(obj, list):
                for item in obj:
                    result = search(item)
                    if result is not None:
                        return result
            return None

        return search(data)
    except Exception:
        return None


# ===================== 4. 테마 선정 로직 =====================
@st.cache_data(ttl=CACHE_TTL)
def build_theme_ranking():
    # 거래대금 1위 상승종목
    top_stock = get_top_rising_stock()

    # 스캔할 테마 목록 수집 (1~2페이지)
    theme_pool = get_theme_list(1) + get_theme_list(2)
    theme_pool = theme_pool[:THEME_SCAN_COUNT]

    # 테마 상세는 테마당 1회만 호출 (결과 재사용)
    theme_results = []
    selected_theme_code = None

    for theme in theme_pool:
        detail = get_theme_detail(theme["code"])
        if not detail:
            continue

        # top_stock이 이 테마에 포함되는지 확인 (아직 선정 안 됐을 때만)
        if top_stock and selected_theme_code is None:
            for st_item in detail:
                if st_item["name"] == top_stock["name"] or st_item["code"] == top_stock["code"]:
                    selected_theme_code = theme["code"]
                    break

        rising_sum = sum(s["amount_eok"] for s in detail if s["rate_num"] > 0)
        total_sum = sum(s["amount_eok"] for s in detail)

        # 상한가 종목들의 도달 시각 조회 (상한가 종목만 추가 호출)
        for s in detail:
            if s.get("is_limit_up") and s.get("code"):
                s["limit_up_time"] = get_limit_up_time(s["code"])
            else:
                s["limit_up_time"] = None

        # 상한가 종목을 도달 시각 오름차순(빠른 순)으로 맨 앞에 배치, 나머지는 기존 순서 유지
        limit_up_stocks = [s for s in detail if s.get("is_limit_up")]
        other_stocks = [s for s in detail if not s.get("is_limit_up")]
        limit_up_stocks.sort(key=lambda s: s.get("limit_up_time") or "99:99")
        detail = limit_up_stocks + other_stocks

        theme_results.append({
            "name": theme["name"],
            "code": theme["code"],
            "rising_sum": rising_sum,
            "total_sum": total_sum,
            "has_limit_up": len(limit_up_stocks) > 0,
            "stocks": detail
        })

    # rising_sum 내림차순 정렬
    theme_results.sort(key=lambda t: t["rising_sum"], reverse=True)

    # 1위 테마를 맨 앞으로 이동
    if selected_theme_code:
        for i, t in enumerate(theme_results):
            if t["code"] == selected_theme_code:
                top_theme = theme_results.pop(i)
                theme_results.insert(0, top_theme)
                break

    theme_results = theme_results[:TOP_THEME_COUNT]

    # ===== 대표주(주도주) 중복 필터링 =====
    # 전체 테마 풀에서 "종목명 -> 그 종목이 주도주인 테마 코드 집합" 맵 구축
    leading_stock_to_themes = {}
    for theme in theme_pool:
        for stock_name in theme.get("leading_stocks", []):
            leading_stock_to_themes.setdefault(stock_name, set()).add(theme["code"])

    for t in theme_results:
        stocks = t["stocks"]
        if not stocks:
            continue

        # 현재 테마(t) 내 등락률 1위 종목명 확인
        top_rate_stock_name = max(stocks, key=lambda s: s["rate_num"])["name"]

        filtered = []
        for s in stocks:
            owner_themes = leading_stock_to_themes.get(s["name"], set())
            # 이 종목이 "다른 테마"의 주도주이고, 현재 테마(t)의 주도주는 아니며,
            # 현재 테마 내 등락률 1위도 아니라면 제외
            is_leading_elsewhere = bool(owner_themes - {t["code"]})
            is_leading_here = t["code"] in owner_themes
            if is_leading_elsewhere and not is_leading_here and s["name"] != top_rate_stock_name:
                continue
            filtered.append(s)

        t["stocks"] = filtered

        # 52주 신고가 여부 (현재가 >= 52주 최고가)
        for s in filtered:
            s["is_52w_high"] = False
            if s.get("code"):
                high = get_52week_high(s["code"])
                if high and s["price"] >= high:
                    s["is_52w_high"] = True

        # 통계 재계산
        t["rising_sum"] = sum(s["amount_eok"] for s in filtered if s["rate_num"] > 0)
        t["total_sum"] = sum(s["amount_eok"] for s in filtered)
        t["has_limit_up"] = any(s.get("is_limit_up") for s in filtered)
        t["has_52w_high"] = any(s.get("is_52w_high") for s in filtered)

    # 거래대금(total_sum) 1위 테마 표시
    if theme_results:
        top_amount_theme = max(theme_results, key=lambda t: t["total_sum"])
        for t in theme_results:
            t["is_top_amount"] = (t["code"] == top_amount_theme["code"])

    # 최종 순서: total_sum(거래대금) 내림차순. 단, selected_theme_code(1위 테마)는 맨 앞 고정
    if selected_theme_code:
        pinned = [t for t in theme_results if t["code"] == selected_theme_code]
        others = [t for t in theme_results if t["code"] != selected_theme_code]
        others.sort(key=lambda t: t["total_sum"], reverse=True)
        theme_results = pinned + others
    else:
        theme_results.sort(key=lambda t: t["total_sum"], reverse=True)

    return theme_results


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
        background-color: #334155; border-radius: 10px; border: 1px solid #1e293b;
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
    .theme-card-money { background-color: #475569; padding: 2px 8px; border-radius: 5px; font-size: 19px; font-weight: 500; }
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
    .stock-item-meta { display: flex; justify-content: flex-end; font-size: 11px; color: #94a3b8; margin-top: 2px; flex-wrap: wrap; gap: 4px; }

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

# PC: 로고+시계+버튼 한 줄 / 모바일: 로고+시계 1행, 버튼 2행
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
    if st.button("📱 모바일" if st.session_state.view_mode == "PC" else "🖥️ PC", use_container_width=True):
        st.session_state.view_mode = "모바일" if st.session_state.view_mode == "PC" else "PC"
        st.rerun()
with header_col4:
    if st.button("🔄 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# 모바일 모드일 때만 2행에 컨트롤 추가 표시 (HTML로 가로 강제 배치)
if st.session_state.view_mode == "모바일":
    mob_col1, mob_col2, mob_col3 = st.columns([3, 1, 1])
    with mob_col1:
        mob_date = st.date_input(
            "날짜",
            value=date.today(),
            min_value=date(2026, 1, 1),
            max_value=date.today(),
            label_visibility="collapsed",
            key="mob_date"
        )
        selected_date = mob_date
    with mob_col2:
        if st.button("🖥️ PC", use_container_width=True, key="mob_pc_btn"):
            st.session_state.view_mode = "PC"
            st.rerun()
    with mob_col3:
        if st.button("🔄", use_container_width=True, key="mob_refresh"):
            st.cache_data.clear()
            st.rerun()
    # 컬럼 강제 가로배치 CSS (모바일 전용)
    st.markdown("""
        <style>
        section[data-testid="stSidebar"] { display: none; }
        div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
        div[data-testid="column"] { min-width: 0 !important; }
        </style>
    """, unsafe_allow_html=True)

# 모바일 모드에선 mob_date 값을 사용
if st.session_state.view_mode == "모바일" and "mob_date" in st.session_state:
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
