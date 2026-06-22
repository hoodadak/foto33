import os
import json
import time
import requests
from datetime import datetime
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials

# ===================== 설정 =====================
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
STOCKS_PER_THEME = 5
THEME_SCAN_COUNT = 25
ETF_ETN_PREFIXES = (
    "KODEX", "TIGER", "SOL", "ACE", "RISE", "PLUS", "KBSTAR", "HANARO",
    "ARIRANG", "KOSEF", "TIMEFOLIO", "WOORI", "VITA", "FOCUS", "마이다스",
    "삼성 인버스", "신한", "ETN", "ETF"
)

# ===================== 재시도 로직이 있는 요청 함수 =====================
def safe_get(url, max_retries=3, timeout=15):
    """네트워크 타임아웃/오류 시 최대 max_retries번 재시도"""
    last_err = None
    for attempt in range(max_retries):
        try:
            res = requests.get(url, headers=HEADERS, timeout=timeout)
            return res
        except requests.exceptions.RequestException as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(3)  # 재시도 전 3초 대기
    raise last_err

# ===================== Google Sheets 연결 =====================
def connect_sheet():
    creds_json = os.environ["GOOGLE_CREDENTIALS"]
    creds_dict = json.loads(creds_json)
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    sheet_id = os.environ["SHEET_ID"]
    return gc.open_by_key(sheet_id)

# ===================== 데이터 수집 =====================
def get_trading_top(market_n):
    url = f"https://finance.naver.com/sise/sise_quant.naver?sosok={market_n}"
    res = safe_get(url)
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
        rate_text = tds[4].text.strip().replace("%", "").replace(",", "")
        try:
            rate_num = float(rate_text)
        except ValueError:
            continue
        if "-" in tds[4].text:
            rate_num = -abs(rate_num)
        else:
            rate_num = abs(rate_num)
        amount_text = tds[5].text.strip().replace(",", "")
        try:
            amount_eok = float(amount_text) / 100.0
        except ValueError:
            amount_eok = 0.0
        href = name_tag.get("href", "")
        code = href.split("code=")[-1] if "code=" in href else ""
        results.append({"name": name, "code": code, "rate_num": rate_num, "amount_eok": amount_eok})
    return results

def get_top_rising_stock():
    all_stocks = get_trading_top(0) + get_trading_top(1)
    rising = [s for s in all_stocks if s["rate_num"] > 0]
    rising.sort(key=lambda x: x["amount_eok"], reverse=True)
    return rising[0] if rising else None

def get_theme_list(page=1):
    url = f"https://finance.naver.com/sise/theme.naver?page={page}"
    res = safe_get(url)
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

def get_theme_detail(theme_code):
    url = f"https://finance.naver.com/sise/sise_group_detail.naver?type=theme&no={theme_code}"
    res = safe_get(url)
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
        is_limit_up = "상한가" in tds[3].text
        amount_text = tds[8].text.strip().replace(",", "")
        try:
            amount_eok = float(amount_text) / 100.0
        except ValueError:
            amount_eok = 0.0
        stocks.append({"name": name, "code": code, "price": price, "rate_num": rate_num, "amount_eok": amount_eok, "is_limit_up": is_limit_up})
        if len(stocks) >= STOCKS_PER_THEME:
            break
    return stocks

# ===================== 메인 실행 =====================
def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"[{today}] 데이터 수집 시작")

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
        theme_results.append({
            "name": theme["name"],
            "code": theme["code"],
            "rising_sum": rising_sum,
            "total_sum": total_sum,
            "stocks": detail
        })

    theme_results.sort(key=lambda t: t["total_sum"], reverse=True)
    if selected_theme_code:
        pinned = [t for t in theme_results if t["code"] == selected_theme_code]
        others = [t for t in theme_results if t["code"] != selected_theme_code]
        theme_results = pinned + others

    top10 = theme_results[:10]

    # Google Sheets 저장
    wb = connect_sheet()

    # 날짜별 시트 생성 (없으면 새로 만들기)
    try:
        ws = wb.worksheet(today)
        ws.clear()
    except gspread.exceptions.WorksheetNotFound:
        ws = wb.add_worksheet(title=today, rows=100, cols=20)

    # 헤더 (종목당 4개: 종목명, 등락률, 거래대금, 현재가)
    ws.append_row(["순위", "테마명", "거래대금(억)",
                   "종목1", "등락1", "거래대금1", "현재가1",
                   "종목2", "등락2", "거래대금2", "현재가2",
                   "종목3", "등락3", "거래대금3", "현재가3",
                   "종목4", "등락4", "거래대금4", "현재가4",
                   "종목5", "등락5", "거래대금5", "현재가5"])

    # 데이터 행
    for rank, theme in enumerate(top10, 1):
        row = [rank, theme["name"], f"{theme['total_sum']:,.0f}"]
        for s in theme["stocks"]:
            row += [s["name"], f"{s['rate_num']:.2f}%", f"{s['amount_eok']:,.0f}", s["price"]]
        # 종목이 5개 미만이면 빈칸 채우기
        while len(row) < 23:
            row.append("")
        ws.append_row(row)

    print(f"[{today}] Google Sheets 저장 완료 ({len(top10)}개 테마)")

    # ===================== V2 저장 =====================
    save_v2(wb, today)


def save_v2(wb, today):
    """V2 랭킹 로직으로 계산 후 '주도테마_기록_V2' 시트에 저장"""
    import requests as req
    from bs4 import BeautifulSoup as BS

    print(f"[{today}] V2 데이터 수집 시작")

    # --- 거래대금 상위 50 종목 코드 수집 ---
    def get_top50_codes():
        all_stocks = []
        for market_n in [0, 1]:
            for page in range(1, 4):
                url = f"https://finance.naver.com/sise/sise_quant.naver?sosok={market_n}&page={page}"
                try:
                    res = safe_get(url)
                    res.encoding = "euc-kr"
                    soup = BS(res.text, "html.parser")
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
                        amount_text = tds[5].text.strip().replace(",", "")
                        try:
                            amount_eok = float(amount_text) / 100.0
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

    # --- 뉴스 노출 갯수 ---
    def get_news_counts(theme_names):
        try:
            url = "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258"
            res = safe_get(url)
            res.encoding = "euc-kr"
            soup = BS(res.text, "html.parser")
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

    # --- 미국 연관 점수 (utils에서 직접 재구현) ---
    US_THEME_MAP = {
        "SOXX": ["반도체", "HBM", "시스템반도체", "반도체 장비", "반도체 재료"],
        "NVDA": ["반도체", "HBM", "AI", "GPU", "온디바이스"],
        "AMD":  ["반도체", "AI", "서버"],
        "TSMC": ["반도체", "파운드리"],
        "TSLA": ["2차전지", "전기차", "자율주행", "배터리"],
        "ARKK": ["AI", "로봇", "우주", "바이오"],
        "XLK":  ["IT", "소프트웨어", "클라우드"],
        "XLE":  ["에너지", "정유", "태양광"],
        "XLV":  ["바이오", "제약", "헬스케어"],
        "LMT":  ["방산", "항공우주"],
        "META": ["AI", "메타버스", "광고"],
        "AMZN": ["클라우드", "물류", "AI"],
        "MSFT": ["AI", "클라우드", "소프트웨어"],
        "AAPL": ["스마트폰", "부품", "온디바이스 AI"],
        "IONQ": ["양자컴퓨터"],
        "PLTR": ["AI", "빅데이터", "방산"],
    }

    def get_us_scores(theme_names):
        try:
            import yfinance as yf
            tickers = list(US_THEME_MAP.keys())
            data = yf.download(tickers, period="2d", progress=False, auto_adjust=True)
            if data.empty:
                return {}
            closes = data["Close"]
            us_rates = {}
            for ticker in tickers:
                try:
                    vals = closes[ticker].dropna().values
                    if len(vals) >= 2:
                        us_rates[ticker] = (vals[-1] - vals[-2]) / vals[-2]
                except Exception:
                    pass
            scores = {}
            for name in theme_names:
                score = 0.0
                count = 0
                for ticker, rate in us_rates.items():
                    for kw in US_THEME_MAP.get(ticker, []):
                        if kw in name:
                            score += max(rate, 0)
                            count += 1
                            break
                scores[name] = score / count if count > 0 else 0.0
            max_s = max(scores.values()) if scores else 1
            if max_s > 0:
                scores = {k: v / max_s for k, v in scores.items()}
            return scores
        except Exception:
            return {}

    # --- 데이터 수집 ---
    theme_pool = get_theme_list(1) + get_theme_list(2)
    theme_pool = theme_pool[:THEME_SCAN_COUNT]
    top50_codes = get_top50_codes()

    theme_results = []
    separated_limit_up = []

    for theme in theme_pool:
        detail = get_theme_detail(theme["code"])
        if not detail:
            continue

        limit_up_stocks = [s for s in detail if s.get("is_limit_up")]
        non_limit_up_stocks = [s for s in detail if not s.get("is_limit_up")]

        if limit_up_stocks and non_limit_up_stocks:
            best_non_limit = max(non_limit_up_stocks, key=lambda s: s["rate_num"])
            if best_non_limit.get("code") not in top50_codes:
                for lu in limit_up_stocks:
                    separated_limit_up.append({
                        "name": lu["name"], "code": lu.get("code", ""),
                        "amount_eok": lu["amount_eok"], "rate_num": lu["rate_num"],
                        "original_theme": theme["name"],
                    })
                detail = non_limit_up_stocks

        rising_sum = sum(s["amount_eok"] for s in detail if s["rate_num"] > 0)
        theme_results.append({
            "name": theme["name"], "code": theme["code"],
            "rising_sum": rising_sum,
            "total_sum": sum(s["amount_eok"] for s in detail),
            "stocks": detail,
        })

    if not theme_results:
        print(f"[{today}] V2: 테마 없음, 저장 스킵")
        return

    theme_names = [t["name"] for t in theme_results]
    us_scores = get_us_scores(theme_names)
    news_counts = get_news_counts(theme_names)

    for t in theme_results:
        t["us_score"] = us_scores.get(t["name"], 0.0)
        t["news_count"] = news_counts.get(t["name"], 0)

    # 정렬: 상승 거래대금합 기준
    theme_results.sort(key=lambda t: t["rising_sum"], reverse=True)

    # 미국연관 1위 → 1위
    us_top = max(theme_results, key=lambda t: t["us_score"])
    if theme_results[0]["name"] != us_top["name"]:
        theme_results = [t for t in theme_results if t["name"] != us_top["name"]]
        theme_results.insert(0, us_top)

    # 뉴스노출 1위 → 2위
    news_sorted = sorted(theme_results, key=lambda t: t["news_count"], reverse=True)
    news_top = news_sorted[0]
    if news_top["name"] == theme_results[0]["name"] and len(news_sorted) > 1:
        news_top = news_sorted[1]
    elif news_top["name"] == theme_results[0]["name"]:
        news_top = None

    if news_top and len(theme_results) > 1 and theme_results[1]["name"] != news_top["name"]:
        rest = [t for t in theme_results[1:] if t["name"] != news_top["name"]]
        theme_results = [theme_results[0], news_top] + rest

    top10 = theme_results[:10]
    separated_limit_up.sort(key=lambda s: s["amount_eok"], reverse=True)

    # --- Google Sheets 저장 ---
    sheet_name = "주도테마_기록_V2"
    try:
        ws_v2 = wb.worksheet(sheet_name)
    except Exception:
        ws_v2 = wb.add_worksheet(title=sheet_name, rows=5000, cols=30)

    # 헤더 행 (없으면 추가)
    existing = ws_v2.get_all_values()
    if not existing:
        ws_v2.append_row(["날짜", "순위", "테마명", "상승거래대금(억)", "미국연관점수", "뉴스노출수",
                          "종목1", "등락1", "거래대금1", "현재가1",
                          "종목2", "등락2", "거래대금2", "현재가2",
                          "종목3", "등락3", "거래대금3", "현재가3",
                          "종목4", "등락4", "거래대금4", "현재가4",
                          "종목5", "등락5", "거래대금5", "현재가5"])

    for rank, theme in enumerate(top10, 1):
        row = [
            today, rank, theme["name"],
            f"{theme['rising_sum']:,.0f}",
            f"{theme['us_score']:.3f}",
            theme['news_count'],
        ]
        for s in theme["stocks"][:5]:
            row += [s["name"], f"{s['rate_num']:.2f}%", f"{s['amount_eok']:,.0f}", s.get("price", 0)]
        while len(row) < 26:
            row.append("")
        ws_v2.append_row(row)

    # 개별 상한가 테마 저장 (구분선 + 별도 행)
    if separated_limit_up:
        ws_v2.append_row([today, "개별상한가", "---분리---"] + [""] * 23)
        for i, s in enumerate(separated_limit_up, 1):
            ws_v2.append_row([
                today, f"상한가{i}", s["name"],
                f"{s['amount_eok']:,.0f}", "", "",
                s["name"], f"{s['rate_num']:.2f}%", f"{s['amount_eok']:,.0f}", "",
                f"(원래테마: {s['original_theme']})"
            ])

    print(f"[{today}] V2 Google Sheets 저장 완료 ({len(top10)}개 테마, 개별상한가 {len(separated_limit_up)}개)")


if __name__ == "__main__":
    main()
