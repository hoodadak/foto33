import streamlit as st
import urllib.parse
import sys
import os
from datetime import datetime, timedelta

st.set_page_config(page_title="기준선 돌파 종목", layout="wide")

st.markdown("""
<style>
.stApp { background-color: #DBFDF9; }
.block-container { padding-top: 1rem !important; }
</style>
""", unsafe_allow_html=True)

# ===================== 헤더 =====================
st.markdown("## 🔍 월봉 기준선 돌파 종목 스캐너")
st.markdown("""
<div style="background:#1e3a5f; color:white; border-radius:8px;
            padding:10px 16px; font-size:13px; margin-bottom:16px; line-height:1.8;">
<b>조건:</b> 최근 12개월 이내 월봉 일목균형표 기준선을 하→위로 돌파한 양봉 종목<br>
&nbsp;&nbsp;• 돌파 양봉 단독 상승률 <b>≥ 50%</b> &nbsp;또는&nbsp; 다음달 양봉과 단순합산 <b>≥ 50%</b><br>
&nbsp;&nbsp;
<span style="background:#fbbf24;color:#000;font-weight:700;padding:1px 7px;border-radius:4px;">A</span> ≥ 100% &nbsp;
<span style="background:#86efac;color:#000;font-weight:700;padding:1px 7px;border-radius:4px;">B</span> ≥ 70% &nbsp;
<span style="background:#93c5fd;color:#000;font-weight:700;padding:1px 7px;border-radius:4px;">C</span> ≥ 50% &nbsp;&nbsp;
<span style="color:#fcd34d;font-weight:700;">⭐ 돌파시 52주 신고가</span>
</div>
""", unsafe_allow_html=True)

ETF_ETN_PREFIXES = (
    "KODEX", "TIGER", "SOL", "ACE", "RISE", "PLUS", "KBSTAR", "HANARO",
    "ARIRANG", "KOSEF", "TIMEFOLIO", "WOORI", "VITA", "FOCUS", "마이다스",
    "삼성 인버스", "신한", "ETN", "ETF"
)

def fetch_52week_high(ticker):
    try:
        import requests
        url = f"https://m.stock.naver.com/api/stock/{ticker}/integration"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
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

def scan_kijun_breakout_all(progress_callback=None):
    try:
        from pykrx import stock as krx
    except ImportError:
        return []

    today = datetime.today()
    start = today - timedelta(days=31 * 42)
    start_str = start.strftime("%Y%m%d")
    end_str   = today.strftime("%Y%m%d")

    try:
        kospi  = krx.get_market_ticker_list(today.strftime("%Y%m%d"), market="KOSPI")
        kosdaq = krx.get_market_ticker_list(today.strftime("%Y%m%d"), market="KOSDAQ")
        all_tickers = list(set(kospi + kosdaq))
    except Exception:
        return []

    results = []
    total = len(all_tickers)

    for idx, ticker in enumerate(all_tickers):
        if progress_callback:
            progress_callback(idx + 1, total)
        try:
            name = krx.get_market_ticker_name(ticker)
            if any(name.upper().startswith(p.upper()) or p in name for p in ETF_ETN_PREFIXES):
                continue

            df = krx.get_market_ohlcv(start_str, end_str, ticker, freq="m")
            if df is None or len(df) < 27:
                continue

            df = df.reset_index()
            df.columns = [c.strip() for c in df.columns]

            kijun_list = []
            for i in range(len(df)):
                if i < 25:
                    kijun_list.append(None)
                    continue
                window = df.iloc[i-25:i+1]
                kijun_list.append((window["고가"].max() + window["저가"].min()) / 2)
            df["kijun"] = kijun_list

            closed = df.iloc[:-1].copy()
            n = len(closed)
            if n < 2:
                continue

            scan_start = max(1, n - 12)
            found = None

            for i in range(scan_start, n):
                row      = closed.iloc[i]
                prev_row = closed.iloc[i - 1]

                if row["kijun"] is None or prev_row["kijun"] is None:
                    continue
                kijun = row["kijun"]

                if row["종가"] <= row["시가"]:
                    continue
                if not (prev_row["종가"] < kijun and row["종가"] >= kijun):
                    continue
                if row["시가"] <= 0:
                    continue

                rate1 = (row["종가"] - row["시가"]) / row["시가"] * 100

                if rate1 >= 50:
                    found = {
                        "combined_rate": rate1,
                        "breakout_close": row["종가"],
                        "breakout_date": str(row.get("날짜", row.name))[:7],
                        "two_candle": False,
                    }
                    break
                else:
                    if i + 1 >= n:
                        continue
                    next_row = closed.iloc[i + 1]
                    if next_row["종가"] <= next_row["시가"]:
                        continue
                    if next_row["kijun"] is None or next_row["종가"] < next_row["kijun"]:
                        continue
                    if next_row["시가"] <= 0:
                        continue
                    rate2 = (next_row["종가"] - next_row["시가"]) / next_row["시가"] * 100
                    combined_rate = rate1 + rate2
                    if combined_rate >= 50:
                        found = {
                            "combined_rate": combined_rate,
                            "breakout_close": row["종가"],
                            "breakout_date": str(row.get("날짜", row.name))[:7],
                            "two_candle": True,
                        }
                        break

            if found is None:
                continue

            cr = found["combined_rate"]
            grade = "A" if cr >= 100 else "B" if cr >= 70 else "C"

            high_52w = fetch_52week_high(ticker)
            is_priority = bool(high_52w and found["breakout_close"] >= high_52w * 0.99)
            current_price = int(df["종가"].iloc[-1])

            results.append({
                "ticker": ticker,
                "name": name,
                "grade": grade,
                "combined_rate": round(cr, 1),
                "two_candle": found["two_candle"],
                "breakout_date": found["breakout_date"],
                "breakout_close": int(found["breakout_close"]),
                "current_price": current_price,
                "is_priority": is_priority,
                "high_52w": high_52w,
            })

        except Exception:
            continue

    grade_order = {"A": 0, "B": 1, "C": 2}
    results.sort(key=lambda x: (
        0 if x["is_priority"] else 1,
        grade_order.get(x["grade"], 9),
        -x["combined_rate"]
    ))
    return results

# ===================== 스캔 버튼 =====================
col_btn, col_tip = st.columns([1, 4])
with col_btn:
    run_scan = st.button("🚀 스캔 시작", use_container_width=True, type="primary")
with col_tip:
    st.caption("⏱ 코스피+코스닥 전체 종목(~2,500개) 스캔 · 5~10분 소요 · KRX 로그인 필요(KRX_ID/KRX_PW)")

if "scanner_results" not in st.session_state:
    st.session_state["scanner_results"] = None
if "scanner_done_time" not in st.session_state:
    st.session_state["scanner_done_time"] = None

# ===================== 스캔 실행 =====================
if run_scan:
    progress_bar = st.progress(0)
    status_text  = st.empty()

    def on_progress(done, total):
        pct = done / total
        progress_bar.progress(pct)
        status_text.text(f"스캔 중... {done:,}/{total:,}  ({pct*100:.1f}%)")

    with st.spinner("월봉 데이터 수집 중..."):
        results = scan_kijun_breakout_all(progress_callback=on_progress)

    st.session_state["scanner_results"] = results
    st.session_state["scanner_done_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    progress_bar.empty()
    status_text.empty()
    st.rerun()

# ===================== 결과 표시 =====================
results   = st.session_state.get("scanner_results")
done_time = st.session_state.get("scanner_done_time")

if results is None:
    st.markdown(
        '<div style="background:#e2e8f0; color:#000000; border-radius:8px; '
        'padding:12px 16px; font-size:14px; font-weight:500;">'
        '🔍 스캔 시작 버튼을 눌러 조건에 맞는 종목을 검색하세요.</div>',
        unsafe_allow_html=True
    )
    st.stop()

if not results:
    st.markdown(
        '<div style="background:#e2e8f0; color:#000000; border-radius:8px; '
        'padding:12px 16px; font-size:14px; font-weight:500;">'
        '⚠️ 조건에 맞는 종목이 없습니다.</div>',
        unsafe_allow_html=True
    )
    st.stop()

if done_time:
    st.caption(f"📅 스캔 완료: {done_time}  ·  총 {len(results)}개 종목 발견")

# ===================== 등급 필터 =====================
grade_filter = st.radio(
    "등급 필터",
    ["전체", "⭐ 우선종목", "A급", "B급", "C급"],
    horizontal=True,
    label_visibility="collapsed"
)

if grade_filter == "A급":
    display = [r for r in results if r["grade"] == "A"]
elif grade_filter == "B급":
    display = [r for r in results if r["grade"] == "B"]
elif grade_filter == "C급":
    display = [r for r in results if r["grade"] == "C"]
elif grade_filter == "⭐ 우선종목":
    display = [r for r in results if r["is_priority"]]
else:
    display = results

st.markdown(f"**{len(display)}개 종목** 표시 중 (전체 {len(results)}개)")
st.divider()

# ===================== 결과 테이블 =====================
hcols = st.columns([0.5, 0.4, 2.2, 0.8, 1.0, 1.0, 1.0, 1.0, 1.0])
for col, label in zip(hcols, ["등급","우선","종목명","코드","합산상승률","돌파월","돌파종가","현재가","비고"]):
    col.markdown(f"<span style='font-size:12px;color:#64748b;font-weight:700;'>{label}</span>",
                 unsafe_allow_html=True)

for r in display:
    grade_color = {"A": "#fbbf24", "B": "#86efac", "C": "#93c5fd"}.get(r["grade"], "#e2e8f0")
    two_tag = "<span style='background:#e2e8f0;color:#475569;font-size:11px;padding:1px 5px;border-radius:3px;'>2봉합산</span>" if r["two_candle"] else ""
    encoded  = urllib.parse.quote(r["name"])
    news_url  = f"https://search.naver.com/search.naver?where=news&query={encoded}"
    chart_url = f"https://finance.naver.com/item/main.naver?code={r['ticker']}"

    rcols = st.columns([0.5, 0.4, 2.2, 0.8, 1.0, 1.0, 1.0, 1.0, 1.0])
    rcols[0].markdown(
        f'<span style="background:{grade_color};color:#000;font-weight:700;'
        f'padding:2px 10px;border-radius:4px;font-size:13px;">{r["grade"]}</span>',
        unsafe_allow_html=True)
    rcols[1].markdown("⭐" if r["is_priority"] else "—")
    rcols[2].markdown(
        f'<a href="{news_url}" target="_blank" '
        f'style="color:#1e293b;font-weight:700;font-size:14px;text-decoration:none;">'
        f'{r["name"]}</a>', unsafe_allow_html=True)
    rcols[3].markdown(
        f'<a href="{chart_url}" target="_blank" '
        f'style="color:#475569;font-size:12px;text-decoration:none;">'
        f'{r["ticker"]}</a>', unsafe_allow_html=True)
    rcols[4].markdown(
        f'<span style="color:#dc2626;font-weight:700;font-size:14px;">'
        f'+{r["combined_rate"]:.1f}%</span>', unsafe_allow_html=True)
    rcols[5].write(r["breakout_date"])
    rcols[6].write(f"{r['breakout_close']:,}원")
    breakout = r["breakout_close"]
    current  = r["current_price"]
    chg = (current - breakout) / breakout * 100 if breakout > 0 else 0
    chg_color = "#dc2626" if chg >= 0 else "#2563eb"
    rcols[7].markdown(
        f'<span style="font-size:14px;">{current:,}원</span>'
        f'<br><span style="font-size:11px;color:{chg_color};">돌파후 {chg:+.1f}%</span>',
        unsafe_allow_html=True)
    rcols[8].markdown(two_tag if two_tag else "—", unsafe_allow_html=True)

st.divider()
st.caption("pykrx 월봉 데이터 기준 · KRX 로그인 필요(환경변수 KRX_ID/KRX_PW) · 투자 참고용")
