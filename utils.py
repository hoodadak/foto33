# ===================== utils.py - 공통 함수 모음 =====================
import requests
import json
import os
from bs4 import BeautifulSoup
from datetime import timedelta, timezone, datetime

KST = timezone(timedelta(hours=9))

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

# ===================== 미국 연관 테마 매핑 =====================
# 미국 ETF/종목 → 한국 연관 테마 키워드
US_THEME_MAP = {
    "SOXX":  ["반도체", "HBM", "시스템반도체", "반도체 장비", "반도체 재료"],
    "NVDA":  ["반도체", "HBM", "AI", "GPU", "온디바이스"],
    "AMD":   ["반도체", "AI", "서버"],
    "TSMC":  ["반도체", "파운드리"],
    "TSLA":  ["2차전지", "전기차", "자율주행", "배터리"],
    "ARKK":  ["AI", "로봇", "우주", "바이오"],
    "XLK":   ["IT", "소프트웨어", "클라우드"],
    "XLE":   ["에너지", "정유", "태양광"],
    "XLV":   ["바이오", "제약", "헬스케어"],
    "LMT":   ["방산", "항공우주"],
    "META":  ["AI", "메타버스", "광고"],
    "AMZN":  ["클라우드", "물류", "AI"],
    "MSFT":  ["AI", "클라우드", "소프트웨어"],
    "AAPL":  ["스마트폰", "부품", "온디바이스 AI"],
    "IONQ":  ["양자컴퓨터"],
    "PLTR":  ["AI", "빅데이터", "방산"],
}


def fetch_us_theme_scores(theme_names):
    """
    yfinance로 미국 주요 종목/ETF 전일 등락률 조회 후
    각 한국 테마별 미국 연관 점수 계산 (0~1)
    """
    try:
        import yfinance as yf
    except ImportError:
        return {}

    try:
        tickers = list(US_THEME_MAP.keys())
        data = yf.download(tickers, period="2d", progress=False, auto_adjust=True)
        if data.empty:
            return {}

        # 전일 종가 기준 등락률 계산
        closes = data["Close"]
        us_rates = {}
        for ticker in tickers:
            try:
                vals = closes[ticker].dropna().values
                if len(vals) >= 2:
                    rate = (vals[-1] - vals[-2]) / vals[-2]
                    us_rates[ticker] = rate
            except Exception:
                pass

        # 테마별 연관 점수 계산
        theme_scores = {}
        for theme_name in theme_names:
            score = 0.0
            count = 0
            for ticker, rate in us_rates.items():
                keywords = US_THEME_MAP.get(ticker, [])
                for kw in keywords:
                    if kw in theme_name:
                        score += max(rate, 0)  # 상승분만 반영
                        count += 1
                        break
            theme_scores[theme_name] = score / count if count > 0 else 0.0

        # 0~1 정규화
        max_score = max(theme_scores.values()) if theme_scores else 1
        if max_score > 0:
            theme_scores = {k: v / max_score for k, v in theme_scores.items()}

        return theme_scores

    except Exception:
        return {}


def fetch_news_theme_scores(theme_names):
    """
    네이버 증권 뉴스에서 테마 관련 키워드 빈도로 이슈 연관도 점수 계산 (0~1)
    """
    try:
        url = "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258"
        res = requests.get(url, headers=HEADERS, timeout=7)
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "html.parser")

        # 뉴스 제목 수집
        titles = []
        for a in soup.select("dl dd.articleSubject a"):
            titles.append(a.text.strip())
        if not titles:
            for a in soup.select("ul.newsList li a"):
                titles.append(a.text.strip())

        news_text = " ".join(titles)

        # 테마명 키워드 빈도 계산
        theme_scores = {}
        for theme_name in theme_names:
            # 테마명에서 핵심 키워드 추출 (2글자 이상 단어)
            keywords = [w for w in theme_name.replace("/", " ").replace("·", " ").split() if len(w) >= 2]
            score = sum(news_text.count(kw) for kw in keywords)
            theme_scores[theme_name] = float(score)

        # 0~1 정규화
        max_score = max(theme_scores.values()) if theme_scores else 1
        if max_score > 0:
            theme_scores = {k: v / max_score for k, v in theme_scores.items()}

        return theme_scores

    except Exception:
        return {}

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


def fetch_trading_top(market_n=1):
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


def fetch_top_rising_stock():
    all_stocks = fetch_trading_top(0) + fetch_trading_top(1)
    rising = [s for s in all_stocks if s["rate_num"] > 0]
    rising.sort(key=lambda x: x["amount_eok"], reverse=True)
    return rising[0] if rising else None


def fetch_theme_list(page=1):
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
        leading_stocks = [
            a.text.strip() for a in tr.select("a")
            if "item/main.naver" in a.get("href", "") and a.text.strip()
        ]
        themes.append({"name": theme_name, "code": theme_code, "leading_stocks": leading_stocks})
    return themes


def fetch_theme_detail(theme_code, limit=STOCKS_PER_THEME):
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
        try:
            price = int(tds[2].text.strip().replace(",", ""))
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
        try:
            amount_eok = float(tds[8].text.strip().replace(",", "")) / 100.0
        except ValueError:
            amount_eok = 0.0
        try:
            volume = int(tds[7].text.strip().replace(",", ""))
        except ValueError:
            volume = 0
        try:
            prev_volume = int(tds[9].text.strip().replace(",", ""))
        except ValueError:
            prev_volume = 0
        stocks.append({
            "name": name, "code": code, "price": price,
            "rate_num": rate_num, "amount_eok": amount_eok,
            "is_limit_up": is_limit_up_flag,
            "volume": volume, "prev_volume": prev_volume
        })
        if len(stocks) >= limit:
            break
    return stocks


def fetch_limit_up_time(ticker):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "html.parser")
        time_tag = soup.select_one("#time")
        if time_tag:
            return time_tag.text.strip()
    except Exception:
        pass
    return None


def fetch_52week_high(ticker):
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


def build_theme_ranking_core(
    get_trading_top_fn, get_top_rising_stock_fn,
    get_theme_list_fn, get_theme_detail_fn,
    get_limit_up_time_fn, get_52week_high_fn
):
    """
    주도테마 랭킹 계산 핵심 로직.
    각 fn 인자는 캐시가 적용된 함수 (app.py 또는 app_mobile.py에서 주입).
    """
    top_stock = get_top_rising_stock_fn()
    theme_pool = get_theme_list_fn(1) + get_theme_list_fn(2)
    theme_pool = theme_pool[:THEME_SCAN_COUNT]

    theme_results = []
    selected_theme_code = None

    for theme in theme_pool:
        detail = get_theme_detail_fn(theme["code"])
        if not detail:
            continue

        if top_stock and selected_theme_code is None:
            for st_item in detail:
                if st_item["name"] == top_stock["name"] or st_item["code"] == top_stock["code"]:
                    selected_theme_code = theme["code"]
                    break

        rising_sum = sum(s["amount_eok"] for s in detail if s["rate_num"] > 0)
        total_sum = sum(s["amount_eok"] for s in detail)
        rising_count = sum(1 for s in detail if s["rate_num"] > 0)
        total_count = len(detail)
        rising_ratio = rising_count / total_count if total_count > 0 else 0

        vol_ratios = []
        for s in detail:
            if s.get("prev_volume", 0) > 0:
                vol_ratios.append(s["volume"] / s["prev_volume"])
        avg_vol_ratio = sum(vol_ratios) / len(vol_ratios) if vol_ratios else 1.0

        limit_up_count = sum(1 for s in detail if s.get("is_limit_up"))
        limit_up_stocks = [s for s in detail if s.get("is_limit_up")]
        other_stocks = [s for s in detail if not s.get("is_limit_up")]
        for s in limit_up_stocks:
            s["limit_up_time"] = get_limit_up_time_fn(s["code"]) if s.get("code") else None
        limit_up_stocks.sort(key=lambda s: s.get("limit_up_time") or "99:99")
        detail = limit_up_stocks + other_stocks

        theme_results.append({
            "name": theme["name"], "code": theme["code"],
            "rising_sum": rising_sum, "total_sum": total_sum,
            "rising_ratio": rising_ratio, "avg_vol_ratio": avg_vol_ratio,
            "limit_up_count": limit_up_count, "has_limit_up": limit_up_count > 0,
            "stocks": detail
        })

    theme_names = [t["name"] for t in theme_results]

    # 미국 연관 테마 점수 (yfinance)
    us_scores = fetch_us_theme_scores(theme_names)

    # 뉴스/이슈 연관도 점수 (네이버 증권 뉴스)
    news_scores = fetch_news_theme_scores(theme_names)

    # 복합 점수 계산
    max_rising_sum = max((t["rising_sum"] for t in theme_results), default=1) or 1
    max_vol_ratio = max((t["avg_vol_ratio"] for t in theme_results), default=1) or 1
    max_limit_up = max((t["limit_up_count"] for t in theme_results), default=1) or 1

    for t in theme_results:
        name = t["name"]
        t["us_score"] = us_scores.get(name, 0.0)
        t["news_score"] = news_scores.get(name, 0.0)
        t["score"] = (
            (t["rising_sum"] / max_rising_sum) * 0.20   # 상승종목 거래대금 합산 20%
            + t["rising_ratio"] * 0.20                   # 상승종목 비율 20%
            + (t["avg_vol_ratio"] / max_vol_ratio) * 0.15  # 거래량 급증 15%
            + (t["limit_up_count"] / max_limit_up) * 0.15  # 상한가 종목 수 15%
            + t["us_score"] * 0.15                       # 미국 연관 테마 15%
            + t["news_score"] * 0.15                     # 뉴스/이슈 연관도 15%
        )

    theme_results.sort(key=lambda t: t["score"], reverse=True)

    if selected_theme_code:
        for i, t in enumerate(theme_results):
            if t["code"] == selected_theme_code:
                theme_results.insert(0, theme_results.pop(i))
                break

    theme_results = theme_results[:TOP_THEME_COUNT]

    # 주도주 중복 필터링
    leading_stock_to_themes = {}
    for theme in theme_pool:
        for stock_name in theme.get("leading_stocks", []):
            leading_stock_to_themes.setdefault(stock_name, set()).add(theme["code"])

    for t in theme_results:
        stocks = t["stocks"]
        if not stocks:
            continue
        top_rate_name = max(stocks, key=lambda s: s["rate_num"])["name"]
        filtered = []
        for s in stocks:
            owner_themes = leading_stock_to_themes.get(s["name"], set())
            is_elsewhere = bool(owner_themes - {t["code"]})
            is_here = t["code"] in owner_themes
            if is_elsewhere and not is_here and s["name"] != top_rate_name:
                continue
            filtered.append(s)

        # 52주 신고가 여부
        for s in filtered:
            s["is_52w_high"] = False
            if s.get("code"):
                high = get_52week_high_fn(s["code"])
                if high and s["price"] >= high:
                    s["is_52w_high"] = True

        t["stocks"] = filtered
        t["total_sum"] = sum(s["amount_eok"] for s in filtered)
        t["has_limit_up"] = any(s.get("is_limit_up") for s in filtered)
        t["has_52w_high"] = any(s.get("is_52w_high") for s in filtered)

    # 거래대금 1위 테마 표시
    if theme_results:
        top_amt = max(theme_results, key=lambda t: t["total_sum"])
        for t in theme_results:
            t["is_top_amount"] = (t["code"] == top_amt["code"])

    return theme_results


def load_history(date_str):
    """Google Sheets에서 특정 날짜 데이터 불러오기"""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        return None, "gspread 미설치"
    try:
        creds_json = os.environ.get("GOOGLE_CREDENTIALS", "")
        sheet_id = os.environ.get("SHEET_ID", "")
        if not creds_json:
            return None, "GOOGLE_CREDENTIALS 없음 (길이:0)"
        if not sheet_id:
            return None, "SHEET_ID 없음"
        # 앞뒤 공백/줄바꿈 제거
        creds_json = creds_json.strip()
        if not creds_json.startswith("{"):
            return None, f"JSON 형식 오류: 첫글자='{creds_json[:10]}'"
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
            return None, f"{date_str} 시트 없음"
        rows = ws.get_all_values()
        if len(rows) < 2:
            return None, f"{date_str} 시트 데이터 없음"
        themes = []
        for row in rows[1:]:
            if not row or not row[0]:
                continue
            stocks = []
            for i in range(3, min(23, len(row)), 4):
                name = row[i] if i < len(row) else ""
                rate = row[i+1] if i+1 < len(row) else ""
                vol = row[i+2] if i+2 < len(row) else ""
                price = row[i+3] if i+3 < len(row) else "0"
                if name:
                    try:
                        rate_num = float(rate.replace("%", "").replace("+", ""))
                    except ValueError:
                        rate_num = 0.0
                    try:
                        price_int = int(str(price).replace(",", ""))
                    except ValueError:
                        price_int = 0
                    stocks.append({
                        "name": name, "rate_num": rate_num,
                        "amount_eok": float(vol.replace(",", "")) if vol else 0.0,
                        "price": price_int,
                        "is_limit_up": rate_num >= 29.5,
                        "is_52w_high": False, "limit_up_time": None
                    })
            try:
                total_sum = float(row[2].replace(",", "")) if row[2] else 0.0
            except ValueError:
                total_sum = 0.0
            themes.append({
                "name": row[1] if len(row) > 1 else "", "code": "",
                "total_sum": total_sum, "rising_sum": total_sum,
                "has_limit_up": any(s["is_limit_up"] for s in stocks),
                "has_52w_high": False, "is_top_amount": len(themes) == 0,
                "stocks": stocks
            })
        return themes, None
    except Exception as e:
        return None, str(e)
