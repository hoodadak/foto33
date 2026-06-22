# ===================== pages/theme_v2.py =====================
# 주도테마 V2 - 새로운 랭킹 로직 적용
import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import timedelta, timezone, datetime

KST = timezone(timedelta(hours=9))

# utils.py 공통 함수 임포트
try:
    from utils import (
        HEADERS, ETF_ETN_PREFIXES, THEME_SCAN_COUNT, STOCKS_PER_THEME,
        fetch_us_theme_scores, fetch_theme_list, fetch_theme_detail,
        fetch_limit_up_time, fetch_52week_high, fetch_market_top100_codes,
        fetch_trading_top, fetch_top_rising_stock, is_market_open_now,
    )
except ImportError as e:
    st.error(f"utils.py 임포트 오류: {e}")
    st.stop()

# ===================== V2 전용 함수 =====================

def fetch_news_theme_counts(theme_names):
    """
    네이버 증권 뉴스에서 테마 관련 키워드 노출 갯수(빈도수) 계산
    - 기존: 정규화된 0~1 점수
    - V2: 실제 노출 갯수(정수)를 반환하여 1위 테마 판별에 사용
    """
    try:
        url = "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258"
        res = requests.get(url, headers=HEADERS, timeout=7)
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "html.parser")

        titles = []
        for a in soup.select("dl dd.articleSubject a"):
            titles.append(a.text.strip())
        if not titles:
            for a in soup.select("ul.newsList li a"):
                titles.append(a.text.strip())

        news_text = " ".join(titles)

        theme_counts = {}
        for theme_name in theme_names:
            keywords = [w for w in theme_name.replace("/", " ").replace("·", " ").split() if len(w) >= 2]
            count = sum(news_text.count(kw) for kw in keywords)
            theme_counts[theme_name] = count

        return theme_counts

    except Exception:
        return {name: 0 for name in theme_names}


def fetch_market_top50_codes() -> set:
    """거래대금 상위 50 종목 코드 반환"""
    top50 = set()
    try:
        all_stocks = []
        for market_n in [0, 1]:
            for page in range(1, 4):
                url = f"https://finance.naver.com/sise/sise_quant.naver?sosok={market_n}&page={page}"
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
        all_stocks.sort(key=lambda x: x["amount_eok"], reverse=True)
        top50 = {s["code"] for s in all_stocks[:50]}
    except Exception:
        pass
    return top50


def build_theme_ranking_v2():
    """
    V2 주도테마 랭킹 빌드
    1. 기본정렬: 상승종목 거래대금합 내림차순
    2. 미국연관 점수 1위 테마 → 강제 1위
    3. 뉴스노출 갯수 1위 테마 → 강제 2위 (중복 시 2위는 뉴스 2등)
    4. 상한가 테마 필터: 상한가 제외 최고상승 종목이 거래대금 상위 50 미포함
       → 상한가 종목을 '개별 상한가 테마'로 분리
    5. 👑: 거래대금 1위 테마의 1위 종목(거래대금순) = 뉴스노출 1위 종목 시 표시
    """

    # 데이터 수집
    theme_pool = fetch_theme_list(1) + fetch_theme_list(2)
    theme_pool = theme_pool[:THEME_SCAN_COUNT]
    top50_codes = fetch_market_top50_codes()

    theme_results = []
    separated_limit_up = []  # 개별 상한가 테마로 분리된 종목들

    for theme in theme_pool:
        detail = fetch_theme_detail(theme["code"])
        if not detail:
            continue

        rising_stocks = [s for s in detail if s["rate_num"] > 0]
        rising_sum = sum(s["amount_eok"] for s in rising_stocks)

        limit_up_stocks = [s for s in detail if s.get("is_limit_up")]
        non_limit_up_stocks = [s for s in detail if not s.get("is_limit_up")]

        # 상한가 테마 필터링
        # 상한가가 있고, 상한가 제외 최고상승 종목이 거래대금 상위 50에 없으면
        # → 상한가 종목을 개별테마로 분리
        if limit_up_stocks and non_limit_up_stocks:
            best_non_limit = max(non_limit_up_stocks, key=lambda s: s["rate_num"])
            if best_non_limit.get("code") not in top50_codes:
                # 상한가 종목들을 개별테마로 분리
                for lu_stock in limit_up_stocks:
                    separated_limit_up.append({
                        "name": lu_stock["name"],
                        "code": lu_stock.get("code", ""),
                        "amount_eok": lu_stock["amount_eok"],
                        "rate_num": lu_stock["rate_num"],
                        "original_theme": theme["name"],
                    })
                # 상한가 제외한 종목들만 테마에 남김
                detail = non_limit_up_stocks
                rising_sum = sum(s["amount_eok"] for s in detail if s["rate_num"] > 0)

        theme_results.append({
            "name": theme["name"],
            "code": theme["code"],
            "rising_sum": rising_sum,
            "total_sum": sum(s["amount_eok"] for s in detail),
            "stocks": detail,
            "has_limit_up": any(s.get("is_limit_up") for s in detail),
        })

    if not theme_results:
        return [], []

    theme_names = [t["name"] for t in theme_results]

    # 미국 연관 점수
    us_scores = fetch_us_theme_scores(theme_names)

    # 뉴스 노출 갯수
    news_counts = fetch_news_theme_counts(theme_names)

    for t in theme_results:
        t["us_score"] = us_scores.get(t["name"], 0.0)
        t["news_count"] = news_counts.get(t["name"], 0)

    # 1단계: 상승종목 거래대금합 기준 기본 정렬
    theme_results.sort(key=lambda t: t["rising_sum"], reverse=True)

    # 2단계: 미국연관 1위 → 강제 1위
    us_top = max(theme_results, key=lambda t: t["us_score"])
    if theme_results[0]["name"] != us_top["name"]:
        theme_results = [t for t in theme_results if t["name"] != us_top["name"]]
        theme_results.insert(0, us_top)

    # 3단계: 뉴스노출 갯수 1위 → 강제 2위
    # 뉴스 1위가 미국연관 1위(현재 1위)와 같으면 뉴스 2위를 2위로
    news_sorted = sorted(theme_results, key=lambda t: t["news_count"], reverse=True)
    news_top = news_sorted[0]
    if news_top["name"] == theme_results[0]["name"]:
        # 뉴스 1위 = 미국연관 1위 → 뉴스 2위를 2위로
        if len(news_sorted) > 1:
            news_top = news_sorted[1]
        else:
            news_top = None

    if news_top and len(theme_results) > 1 and theme_results[1]["name"] != news_top["name"]:
        rest = [t for t in theme_results[1:] if t["name"] != news_top["name"]]
        theme_results = [theme_results[0], news_top] + rest

    # 👑 왕관 판별
    # 거래대금 1위 테마의 1위 종목(거래대금순)이 뉴스 노출 1위 종목인지 확인
    # 뉴스 1위 종목: 뉴스 갯수가 가장 많은 테마의 대표 종목(거래대금 1위 종목)
    crown_theme_name = None
    if theme_results:
        # 거래대금 기준 1위 테마 (정렬 후 rising_sum 가장 높은 테마 = 원래 1위)
        orig_top_theme = max(theme_results, key=lambda t: t["rising_sum"])
        if orig_top_theme["stocks"]:
            top_stock_in_theme = max(orig_top_theme["stocks"], key=lambda s: s["amount_eok"])

            # 뉴스 노출 1위 종목: news_counts에서 해당 종목명으로 직접 검색
            # 각 테마의 1위 종목(거래대금) 중 뉴스에서 가장 많이 언급된 종목 찾기
            # 간략하게: 거래대금 1위 테마 종목이 뉴스 1위 테마와 동일 테마인지
            news_count_top_theme = max(theme_results, key=lambda t: t["news_count"])
            if orig_top_theme["name"] == news_count_top_theme["name"]:
                # 거래대금 1위 테마 = 뉴스 노출 1위 테마
                # 해당 테마의 1위 종목이 뉴스 노출 1위 종목
                crown_theme_name = orig_top_theme["name"]

    top10 = theme_results[:10]
    for t in top10:
        t["crown"] = (crown_theme_name is not None and t["name"] == crown_theme_name)

    # 개별 상한가 테마 정렬 (거래대금순)
    separated_limit_up.sort(key=lambda s: s["amount_eok"], reverse=True)

    return top10, separated_limit_up


# ===================== Streamlit UI =====================

st.set_page_config(page_title="주도테마 V2", layout="wide")
st.title("🏆 주도테마 V2")
st.caption("상승종목 거래대금 기반 · 미국연관 1위→1등 · 뉴스노출 1위→2등 · 상한가 개별분리")

now = datetime.now(KST)
st.write(f"🕐 기준시각: {now.strftime('%Y-%m-%d %H:%M')} KST")

if not is_market_open_now(now):
    st.warning("⚠️ 현재 장 마감 시간입니다. 마지막 데이터 기준으로 표시됩니다.")

with st.spinner("V2 테마 랭킹 계산 중..."):
    top10, separated = build_theme_ranking_v2()

if not top10:
    st.error("테마 데이터를 불러오지 못했습니다.")
    st.stop()

# ===================== 일반 테마 순위 =====================
st.subheader("📊 주도테마 순위 (V2)")

for rank, theme in enumerate(top10, 1):
    crown = "👑 " if theme.get("crown") else ""
    us_badge = f"🇺🇸 {theme['us_score']:.2f}" if theme.get("us_score", 0) > 0 else ""
    news_badge = f"📰 {theme['news_count']}건" if theme.get("news_count", 0) > 0 else ""
    limit_badge = "🔴" if theme.get("has_limit_up") else ""

    # 강제 순위 표시
    rank_label = f"**{rank}위**"
    if rank == 1:
        rank_label = "**1위 🇺🇸**"
    elif rank == 2:
        rank_label = "**2위 📰**"

    col1, col2 = st.columns([3, 7])
    with col1:
        st.markdown(f"{rank_label} {crown}{limit_badge} **{theme['name']}**")
        st.caption(f"상승거래대금: {theme['rising_sum']:,.0f}억  {us_badge}  {news_badge}")
    with col2:
        if theme["stocks"]:
            cols = st.columns(len(theme["stocks"]))
            for i, s in enumerate(theme["stocks"]):
                with cols[i]:
                    rate_color = "🔴" if s["rate_num"] >= 29.5 else ("📈" if s["rate_num"] > 0 else "📉")
                    st.caption(f"{rate_color} **{s['name']}**")
                    st.caption(f"{s['rate_num']:+.2f}% | {s['amount_eok']:,.0f}억")
    st.divider()

# ===================== 개별 상한가 테마 =====================
if separated:
    st.subheader("🔴 개별 상한가 테마")
    st.caption("상한가 외 최고상승 종목이 거래대금 상위 50 미포함 → 상한가 종목 개별분리")

    for i, s in enumerate(separated, 1):
        st.markdown(
            f"**{i}위** 🔴 **{s['name']}** "
            f"({s['rate_num']:+.2f}% | {s['amount_eok']:,.0f}억) "
            f"_← {s['original_theme']} 에서 분리_"
        )
