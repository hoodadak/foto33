import streamlit as st
import urllib.parse
import sys
import os

# utils.py가 상위 폴더에 있으므로 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import scan_kijun_breakout_all, ETF_ETN_PREFIXES

# ===================== 페이지 설정 =====================
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
&nbsp;&nbsp;• 돌파 양봉 단독 상승률 <b>≥ 50%</b> &nbsp;또는&nbsp;
  다음달 양봉과 단순합산 <b>≥ 50%</b><br>
&nbsp;&nbsp;
<span style="background:#fbbf24; color:#000; font-weight:700;
             padding:1px 7px; border-radius:4px;">A</span> ≥ 100% &nbsp;
<span style="background:#86efac; color:#000; font-weight:700;
             padding:1px 7px; border-radius:4px;">B</span> ≥ 70% &nbsp;
<span style="background:#93c5fd; color:#000; font-weight:700;
             padding:1px 7px; border-radius:4px;">C</span> ≥ 50% &nbsp;&nbsp;
<span style="color:#fcd34d; font-weight:700;">⭐ 돌파시 52주 신고가</span>
</div>
""", unsafe_allow_html=True)

# ===================== 스캔 버튼 =====================
col_btn, col_tip = st.columns([1, 4])
with col_btn:
    run_scan = st.button("🚀 스캔 시작", use_container_width=True, type="primary")
with col_tip:
    st.caption("⏱ 코스피+코스닥 전체 종목(~2,500개) 스캔 · 5~10분 소요 · KRX 로그인 필요(KRX_ID/KRX_PW)")

# ===================== 세션 상태 초기화 =====================
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
    from datetime import datetime
    from utils import KST
    st.session_state["scanner_done_time"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    progress_bar.empty()
    status_text.empty()
    st.rerun()

# ===================== 결과 표시 =====================
results = st.session_state.get("scanner_results")
done_time = st.session_state.get("scanner_done_time")

if results is None:
    st.info("'스캔 시작' 버튼을 눌러 조건에 맞는 종목을 검색하세요.")
    st.stop()

if not results:
    st.warning("조건에 맞는 종목이 없습니다.")
    st.stop()

# 스캔 완료 시각 표시
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
# 헤더
hcols = st.columns([0.5, 0.4, 2.2, 0.8, 1.0, 1.0, 1.0, 1.0, 1.0])
for col, label in zip(hcols, ["등급", "우선", "종목명", "코드",
                                "합산상승률", "돌파월", "돌파종가", "현재가", "비고"]):
    col.markdown(f"<span style='font-size:12px; color:#64748b; font-weight:700;'>{label}</span>",
                 unsafe_allow_html=True)

for r in display:
    grade_color = {"A": "#fbbf24", "B": "#86efac", "C": "#93c5fd"}.get(r["grade"], "#e2e8f0")
    priority_tag = "⭐" if r["is_priority"] else ""
    two_tag = "<span style='background:#e2e8f0; color:#475569; font-size:11px; " \
              "padding:1px 5px; border-radius:3px;'>2봉합산</span>" if r["two_candle"] else ""

    encoded = urllib.parse.quote(r["name"])
    news_url  = f"https://search.naver.com/search.naver?where=news&query={encoded}"
    chart_url = f"https://finance.naver.com/item/main.naver?code={r['ticker']}"

    rcols = st.columns([0.5, 0.4, 2.2, 0.8, 1.0, 1.0, 1.0, 1.0, 1.0])

    # 등급 뱃지
    rcols[0].markdown(
        f'<span style="background:{grade_color}; color:#000; font-weight:700; '
        f'padding:2px 10px; border-radius:4px; font-size:13px;">{r["grade"]}</span>',
        unsafe_allow_html=True
    )

    # 우선종목
    rcols[1].markdown(priority_tag or "—")

    # 종목명 (네이버 뉴스 링크)
    rcols[2].markdown(
        f'<a href="{news_url}" target="_blank" '
        f'style="color:#1e293b; font-weight:700; font-size:14px; text-decoration:none;">'
        f'{r["name"]}</a>',
        unsafe_allow_html=True
    )

    # 종목코드 (차트 링크)
    rcols[3].markdown(
        f'<a href="{chart_url}" target="_blank" '
        f'style="color:#475569; font-size:12px; text-decoration:none;">'
        f'{r["ticker"]}</a>',
        unsafe_allow_html=True
    )

    # 합산 상승률
    rcols[4].markdown(
        f'<span style="color:#dc2626; font-weight:700; font-size:14px;">'
        f'+{r["combined_rate"]:.1f}%</span>',
        unsafe_allow_html=True
    )

    # 돌파월
    rcols[5].write(r["breakout_date"])

    # 돌파 종가
    rcols[6].write(f"{r['breakout_close']:,}원")

    # 현재가
    current = r["current_price"]
    breakout = r["breakout_close"]
    if breakout > 0:
        chg = (current - breakout) / breakout * 100
        chg_color = "#dc2626" if chg >= 0 else "#2563eb"
        chg_str = f"<br><span style='font-size:11px; color:{chg_color};'>" \
                  f"돌파후 {chg:+.1f}%</span>"
    else:
        chg_str = ""
    rcols[7].markdown(
        f'<span style="font-size:14px;">{current:,}원</span>{chg_str}',
        unsafe_allow_html=True
    )

    # 비고
    rcols[8].markdown(two_tag if two_tag else "—", unsafe_allow_html=True)

st.divider()
st.caption("pykrx 월봉 데이터 기준 · KRX 로그인 필요(환경변수 KRX_ID/KRX_PW) · 투자 참고용")
