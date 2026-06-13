import os
import json
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

def get_theme_detail(theme_code):
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

    # 헤더
    ws.append_row(["순위", "테마명", "거래대금(억)", "종목1", "등락1", "거래대금1",
                   "종목2", "등락2", "거래대금2", "종목3", "등락3", "거래대금3",
                   "종목4", "등락4", "거래대금4", "종목5", "등락5", "거래대금5"])

    # 데이터 행
    for rank, theme in enumerate(top10, 1):
        row = [rank, theme["name"], f"{theme['total_sum']:,.0f}"]
        for s in theme["stocks"]:
            row += [s["name"], f"{s['rate_num']:.2f}%", f"{s['amount_eok']:,.0f}"]
        # 종목이 5개 미만이면 빈칸 채우기
        while len(row) < 18:
            row.append("")
        ws.append_row(row)

    print(f"[{today}] Google Sheets 저장 완료 ({len(top10)}개 테마)")

if __name__ == "__main__":
    main()
