"""
pages/supply.py
─────────────────
외국인/프로그램/기관 순매수 수급분석 페이지

데이터 출처: 네이버 금융 (로그인 불필요)
- 투자자별 매매동향: finance.naver.com/item/frgn.naver
- 기관 세부: finance.naver.com/item/institutional.naver
- 종목 기본정보(유동주식/증거금율): finance.naver.com/item/main.naver

관심종목 기준:
  임계값 = (유동주식 / 100) × (증거금율 / 100)
  외국인/프로그램/기관 중 최소 1곳의 N일 누적 순매수 >= 임계값
"""

import streamlit as st
import sys, os, re
from datetime import timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KST = timezone(timedelta(hours=9))

try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

st.set_page_config(page_title="수급분석", layout="wide")

with st.sidebar:
    st.markdown("### 📊 메뉴")
    st.page_link("app.py",             label="🏠 주도테마")
    st.page_link("pages/rs_lookup.py", label="📈 RS Rating 조회")
    st.page_link("pages/supply.py",  label="💰 수급분석")
    st.markdown("---")
    st.caption("데이터: 네이버 금융")

st.markdown("""
<style>
.stApp { background-color: #ABABAB; }
html, body, [class*="css"] { font-size: 16px !important; }
h1 { font-size: 2rem !important; }
[data-testid="stMetricValue"] { font-size: 22px !important; }
[data-testid="stMetricLabel"] { font-size: 14px !important; }
.stock-header {
    background: #1e3a5f; border-radius: 8px; padding: 14px 18px;
    color: white; margin-bottom: 14px;
}
.stock-header .sname { font-size: 20px; font-weight: 800; }
.stock-header .smeta { font-size: 14px; color: #94a3b8; margin-top: 3px; }
.interest-badge {
    display: inline-block; padding: 6px 18px; border-radius: 8px;
    font-size: 22px; font-weight: 900; color: white; margin: 6px 0 10px 0;
}
.supply-table { width: 100%; border-collapse: collapse; margin-top: 8px; }
.supply-table th {
    background: #1e3a5f; color: white;
    padding: 8px 12px; font-size: 14px; text-align: center;
}
.supply-table td {
    padding: 7px 12px; font-size: 15px; text-align: right;
    border-bottom: 1px solid #cbd5e1; background: white;
}
.supply-table td.label { text-align: left; font-weight: 600; color: #1e293b; }
.pos { color: #dc2626; font-weight: 700; }
.neg { color: #2563eb; font-weight: 700; }
.zero { color: #64748b; }
.hl td { background: #fef9c3 !important; }
</style>
""", unsafe_allow_html=True)

st.title("💰 수급분석")
st.caption("외국인 · 프로그램 · 기관 순매수 동향 및 관심종목 판별")

if not REQUESTS_OK:
    st.error("requests / beautifulsoup4 패키지가 없습니다.")
    st.stop()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_stock_basic(code):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        res = requests.get(url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(res.text, "html.parser")

        name_tag = soup.select_one("div.wrap_company h2 a")
        name = name_tag.get_text(strip=True) if name_tag else code

        price_tag = soup.select_one("#_nowVal")
        price = int(price_tag.get_text(strip=True).replace(",", "")) if price_tag else 0

        float_shares = 0
        margin_rate = 40

        for dl in soup.select("dl.blind"):
            dts = dl.find_all("dt")
            dds = dl.find_all("dd")
            for dt, dd in zip(dts, dds):
                label = dt.get_text(strip=True)
                val   = dd.get_text(strip=True).replace(",", "").replace("%", "").strip()
                if "유동주식" in label:
                    try:
                        float_shares = int(re.sub(r"[^0-9]", "", val.split("(")[0]))
                    except:
                        pass
                if "증거금" in label:
                    try:
                        margin_rate = int(re.sub(r"[^0-9]", "", val))
                    except:
                        pass

        # 테이블에서도 시도
        if float_shares == 0:
            for table in soup.find_all("table"):
                for tr in table.find_all("tr"):
                    tds = tr.find_all("td")
                    ths = tr.find_all("th")
                    for th, td in zip(ths, tds):
                        label = th.get_text(strip=True)
                        val   = td.get_text(strip=True).replace(",", "")
                        if "유동주식" in label:
                            try:
                                float_shares = int(re.sub(r"[^0-9]", "", val.split("(")[0]))
                            except:
                                pass
                        if "증거금" in label:
                            try:
                                margin_rate = int(re.sub(r"[^0-9]", "", val))
                            except:
                                pass

        market = "KOSDAQ" if soup.select_one("img[alt='코스닥']") else "KOSPI"
        return {"name": name, "price": price, "market": market,
                "float_shares": float_shares, "margin_rate": margin_rate}
    except Exception as e:
        return {"name": code, "price": 0, "market": "-",
                "float_shares": 0, "margin_rate": 40, "error": str(e)}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_investor_trading(code, days=3):
    """외국인 순매수 (주) — naver frgn 페이지"""
    try:
        url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        res = requests.get(url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(res.text, "html.parser")

        result = []
        table = soup.select_one("table.type2")
        if not table:
            return []

        for row in table.find_all("tr"):
            tds = row.find_all("td")
            if len(tds) < 4:
                continue
            date_str = tds[0].get_text(strip=True)
            if not re.match(r"\d{4}\.\d{2}\.\d{2}", date_str):
                continue
            try:
                foreign = int(tds[3].get_text(strip=True).replace(",", "").replace("+", ""))
            except:
                foreign = 0
            result.append({"date": date_str, "foreign": foreign})
            if len(result) >= days:
                break
        return result
    except:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def fetch_institutional_detail(code, days=3):
    """기관세부 + 프로그램 순매수 (주) — naver institutional 페이지"""
    try:
        url = f"https://finance.naver.com/item/institutional.naver?code={code}"
        res = requests.get(url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(res.text, "html.parser")

        result = []
        table = soup.select_one("table.type2")
        if not table:
            return []

        def pn(td):
            try:
                return int(td.get_text(strip=True).replace(",", "").replace("+", ""))
            except:
                return 0

        for row in table.find_all("tr"):
            tds = row.find_all("td")
            if len(tds) < 10:
                continue
            date_str = tds[0].get_text(strip=True)
            if not re.match(r"\d{4}\.\d{2}\.\d{2}", date_str):
                continue
            result.append({
                "date":             date_str,
                "institution_total": pn(tds[1]),
                "financial":        pn(tds[2]),
                "insurance":        pn(tds[3]),
                "trust":            pn(tds[4]),
                "etf":              pn(tds[5]),
                "pension":          pn(tds[6]),
                "private":          pn(tds[7]),
                "nation":           pn(tds[8]),
                "other_corp":       pn(tds[9]),
                "program":          pn(tds[10]) if len(tds) > 10 else 0,
            })
            if len(result) >= days:
                break
        return result
    except:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def search_by_name(query):
    try:
        url = f"https://ac.finance.naver.com/ac?q={query}&q_enc=UTF-8&target=stock,index"
        res = requests.get(url, headers=HEADERS, timeout=5)
        items = res.json().get("items", [[]])[0]
        results = []
        for item in items:
            if len(item) >= 2 and len(item[0]) == 6 and item[0].isdigit():
                results.append({"code": item[0].strip(), "name": item[1].strip()})
        return results[:5]
    except:
        return []


def calc_threshold(float_shares, margin_rate):
    """
    임계값 = 유동주식수 × (증거금율 / 1000) / 100
           = 유동주식수 × 증거금율 / 100000
    증거금 20%  → 유동주식 × 0.2/1000  = 유동주식 × 0.0002
    증거금 100% → 유동주식 × 1.0/1000  = 유동주식 × 0.001
    예) 유동 500만주, 증거금 20% → 5,000,000 × 0.0002 = 1,000주
    """
    return int(float_shares * margin_rate / 100000)


def get_grade(net: dict, threshold: int):
    if threshold <= 0:
        return ("❓ 판별불가", "#94a3b8", "유동주식 데이터 없음")
    qualifiers = []
    if net.get("foreign", 0) >= threshold:
        qualifiers.append("외국인")
    if net.get("institution", 0) >= threshold:
        qualifiers.append("기관")
    if net.get("program", 0) >= threshold:
        qualifiers.append("프로그램")
    if qualifiers:
        return ("⭐ 관심종목", "#dc2626", f"{' · '.join(qualifiers)} 순매수 임계값 초과")
    return ("— 해당없음", "#64748b", f"임계값 {threshold:,}주 미달")


def fmt(n):
    if n > 0:   return f'<span class="pos">+{n:,}</span>'
    elif n < 0: return f'<span class="neg">{n:,}</span>'
    else:       return f'<span class="zero">0</span>'


def parse_input(raw):
    items, seen = [], set()
    for token in raw.replace("，", ",").split(","):
        token = token.strip()
        if not token:
            continue
        if token.isdigit() and len(token) == 6:
            if token not in seen:
                items.append({"code": token, "name": token})
                seen.add(token)
        else:
            r = search_by_name(token)
            if r and r[0]["code"] not in seen:
                items.append(r[0])
                seen.add(r[0]["code"])
            elif not r:
                items.append({"code": None, "name": token})
    return items[:5]


# ── 입력 UI ──────────────────────────────────────────────────────────
st.markdown("#### 종목 입력 (최대 5개, 쉼표로 구분)")
ci, cb = st.columns([5, 1])
with ci:
    user_input = st.text_input("종목", placeholder="예: 삼성전자, 005930, HLB",
                               label_visibility="collapsed", key="supply_input")
with cb:
    clicked = st.button("🔍 조회", use_container_width=True, type="primary")

days_sel = st.radio("조회 기간", ["당일 포함 2일", "당일 포함 3일"],
                    horizontal=True, index=1)
n_days = 2 if "2일" in days_sel else 3

if clicked and user_input.strip():
    st.session_state["supply_query"] = user_input.strip()

if "supply_query" in st.session_state and st.session_state["supply_query"]:
    parsed = parse_input(st.session_state["supply_query"])
    failed = [p["name"] for p in parsed if p["code"] is None]
    valid  = [p for p in parsed if p["code"] is not None]

    if failed:
        st.warning(f"종목을 찾지 못했습니다: {', '.join(failed)}")
    if not valid:
        st.stop()

    for stock in valid:
        code = stock["code"]

        with st.spinner(f"{stock['name']} 수급 데이터 로딩 중..."):
            basic = fetch_stock_basic(code)
            frgn  = fetch_investor_trading(code, n_days)
            inst  = fetch_institutional_detail(code, n_days)

        name         = basic.get("name") or stock["name"]
        price        = basic.get("price", 0)
        market       = basic.get("market", "-")
        float_shares = basic.get("float_shares", 0)
        margin_rate  = basic.get("margin_rate", 40)
        threshold    = calc_threshold(float_shares, margin_rate)

        # 날짜 기준 병합
        inst_map = {r["date"]: r for r in inst}
        merged = []
        for fr in frgn:
            d  = fr["date"]
            ir = inst_map.get(d, {})
            merged.append({
                "date":             d,
                "foreign":          fr["foreign"],
                "institution":      ir.get("institution_total", 0),
                "financial":        ir.get("financial", 0),
                "insurance":        ir.get("insurance", 0),
                "trust":            ir.get("trust", 0),
                "etf":              ir.get("etf", 0),
                "pension":          ir.get("pension", 0),
                "private":          ir.get("private", 0),
                "nation":           ir.get("nation", 0),
                "other_corp":       ir.get("other_corp", 0),
                "program":          ir.get("program", 0),
            })
        # inst에만 있는 날짜 보완
        for ir in inst:
            if not any(m["date"] == ir["date"] for m in merged):
                merged.append({
                    "date": ir["date"], "foreign": 0,
                    "institution": ir.get("institution_total", 0),
                    "financial": ir.get("financial", 0),
                    "insurance": ir.get("insurance", 0),
                    "trust": ir.get("trust", 0),
                    "etf": ir.get("etf", 0),
                    "pension": ir.get("pension", 0),
                    "private": ir.get("private", 0),
                    "nation": ir.get("nation", 0),
                    "other_corp": ir.get("other_corp", 0),
                    "program": ir.get("program", 0),
                })
        merged = sorted(merged, key=lambda x: x["date"], reverse=True)[:n_days]

        net = {
            "foreign":     sum(r["foreign"]     for r in merged),
            "institution": sum(r["institution"] for r in merged),
            "program":     sum(r["program"]     for r in merged),
        }
        grade, gc, gdesc = get_grade(net, threshold)

        # ── 종목 헤더 ────────────────────────────────────────────
        st.markdown("---")
        st.markdown(f"""
        <div class="stock-header">
            <div class="sname">{name}</div>
            <div class="smeta">
                {code} · {market} · 현재가 {price:,}원 ·
                유동주식 {float_shares:,}주 · 증거금율 {margin_rate}%
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── 관심종목 등급 ────────────────────────────────────────
        cg, ct = st.columns([2, 3])
        with cg:
            st.markdown(
                f'<span class="interest-badge" style="background:{gc};">{grade}</span>',
                unsafe_allow_html=True)
            st.caption(gdesc)
        with ct:
            st.markdown(f"""
**임계값**: 유동주식 {float_shares:,} × ({margin_rate}/1000) = **{threshold:,}주**

{n_days}일 누적 | 외국인 **{net['foreign']:+,}주** · 기관 **{net['institution']:+,}주** · 프로그램 **{net['program']:+,}주**
            """)

        # ── 수급 테이블 ──────────────────────────────────────────
        st.markdown("##### 일별 수급 상세 (단위: 주)")

        if not merged:
            st.warning("수급 데이터 없음 — 장중 또는 거래일에 다시 시도하세요.")
            continue

        date_ths = "".join(f"<th>{r['date']}</th>" for r in merged)
        sum_th   = f"<th>{n_days}일 합계</th>"

        rows_def = [
            ("외국인",        "foreign",          True),
            ("기관합계",      "institution",      True),
            ("　금융투자",    "financial",        False),
            ("　보험",        "insurance",        False),
            ("　투신(펀드)",  "trust",            False),
            ("　ETF",         "etf",              False),
            ("　연기금",      "pension",          False),
            ("　사모",        "private",          False),
            ("　국가/지자체", "nation",           False),
            ("　기타법인",    "other_corp",       False),
            ("프로그램",      "program",          True),
        ]

        tbody = ""
        for label, key, is_main in rows_def:
            total = sum(r.get(key, 0) for r in merged)
            hl    = "hl" if (is_main and threshold > 0 and total >= threshold) else ""
            bold  = "font-weight:800;" if is_main else "font-size:14px;color:#475569;"
            cells = "".join(f"<td>{fmt(r.get(key,0))}</td>" for r in merged)
            tbody += (
                f'<tr class="{hl}">'
                f'<td class="label" style="{bold}">{label}</td>'
                f'{cells}'
                f'<td style="{bold}">{fmt(total)}</td>'
                f'</tr>'
            )

        st.markdown(f"""
<table class="supply-table">
<thead><tr>
  <th style="text-align:left;">구분</th>{date_ths}{sum_th}
</tr></thead>
<tbody>{tbody}</tbody>
</table>
<div style="margin-top:6px;font-size:13px;color:#334155;">
  ※ 노란색 행 = {n_days}일 합계가 임계값({threshold:,}주) 이상
</div>
""", unsafe_allow_html=True)

    with st.expander("📖 관심종목 판별 기준 안내"):
        st.markdown("""
**임계값 공식**
```
임계값(주) = 유동주식수 × (증거금율 / 1000)
```
증거금율이 높을수록(위험 종목) 더 강한 매수세가 있어야 관심종목 판정됩니다.

| 증거금율 | 의미 | 임계값 (유동 500만주 기준) |
|---|---|---|
| 100% | 관리/투기 종목 | 5,000주 |
| 40% | 일반 종목 | 2,000주 |
| 20% | 우량주 | 1,000주 |

**기관 세부 항목**

| 항목 | 설명 |
|---|---|
| 금융투자 | 증권사 자기매매 |
| 투신(펀드) | 자산운용사 액티브 펀드 |
| ETF | 패시브 ETF 설정/환매 |
| 연기금 | 국민연금 등 공적연금 |
| 사모 | 사모펀드 |
| 국가/지자체 | 정부·한국은행 등 |
| 프로그램 | 차익·비차익 알고리즘 매매 |
        """)
