"""
pages/supply.py
───────────────
외국인/프로그램/기관 순매수 수급분석 페이지
데이터: 네이버 금융 (모바일 JSON API + PC 스크래핑 병행)
"""

import streamlit as st
import sys, os, re, json
from datetime import timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

st.set_page_config(page_title="수급분석", layout="wide")

with st.sidebar:
    st.markdown("### 📊 메뉴")
    st.page_link("app.py",              label="🏠 주도테마")
    st.page_link("pages/rs_lookup.py",  label="📈 RS Rating 조회")
    st.page_link("pages/supply.py",     label="💰 수급분석")
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
.sname { font-size: 20px; font-weight: 800; }
.smeta { font-size: 14px; color: #94a3b8; margin-top: 3px; }
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

HEADERS_PC = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/",
}
HEADERS_MOBILE = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
    "Referer": "https://m.stock.naver.com/",
}

# ── 종목 기본정보 ─────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_stock_basic(code: str) -> dict:
    """네이버 모바일 JSON API로 종목 기본정보 조회"""
    result = {"name": code, "price": 0, "market": "-", "float_shares": 0, "margin_rate": 40}
    try:
        # 1) 모바일 기본정보 API
        url = f"https://m.stock.naver.com/api/stock/{code}/basic"
        res = requests.get(url, headers=HEADERS_MOBILE, timeout=8)
        if res.status_code == 200:
            data = res.json()
            result["name"]   = data.get("stockName") or data.get("name") or code
            result["price"]  = int(str(data.get("closePrice", "0")).replace(",", "") or 0)
            result["market"] = "KOSDAQ" if data.get("marketType") == "KOSDAQ" else "KOSPI"

        # 2) 유동주식수 / 증거금율 — 네이버 종목분석 페이지
        url2 = f"https://finance.naver.com/item/coinfo.naver?code={code}&target=finsum_more"
        res2 = requests.get(url2, headers=HEADERS_PC, timeout=8)
        if res2.status_code == 200:
            soup = BeautifulSoup(res2.text, "html.parser")
            for table in soup.find_all("table"):
                for tr in table.find_all("tr"):
                    cells = tr.find_all(["th", "td"])
                    for i, cell in enumerate(cells):
                        txt = cell.get_text(strip=True)
                        if "유동주식" in txt and i + 1 < len(cells):
                            val = cells[i+1].get_text(strip=True).replace(",", "")
                            try:
                                result["float_shares"] = int(re.sub(r"[^0-9]", "", val.split("(")[0]))
                            except:
                                pass
                        if "증거금" in txt and i + 1 < len(cells):
                            val = cells[i+1].get_text(strip=True).replace(",", "").replace("%", "")
                            try:
                                result["margin_rate"] = int(re.sub(r"[^0-9]", "", val))
                            except:
                                pass

        # 3) 유동주식 못 가져왔으면 main 페이지 재시도
        if result["float_shares"] == 0:
            url3 = f"https://finance.naver.com/item/main.naver?code={code}"
            res3 = requests.get(url3, headers=HEADERS_PC, timeout=8)
            if res3.status_code == 200:
                soup3 = BeautifulSoup(res3.text, "html.parser")
                text = soup3.get_text()
                # 유동주식수 패턴 검색
                m = re.search(r"유동주식수?\s*[\(（]?주[\)）]?\s*([\d,]+)", text)
                if m:
                    try:
                        result["float_shares"] = int(m.group(1).replace(",", ""))
                    except:
                        pass
                m2 = re.search(r"증거금율?\s*(\d+)\s*%", text)
                if m2:
                    try:
                        result["margin_rate"] = int(m2.group(1))
                    except:
                        pass

    except Exception as e:
        result["error"] = str(e)
    return result


# ── 외국인 순매수 ─────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def fetch_foreign_trading(code: str, days: int = 3) -> list:
    """네이버 frgn 페이지에서 외국인 순매수(주) 파싱"""
    try:
        url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        res = requests.get(url, headers=HEADERS_PC, timeout=8)
        if res.status_code != 200:
            return []
        soup = BeautifulSoup(res.text, "html.parser")

        def try_int(td):
            try:
                v = td.get_text(strip=True).replace(",","").replace("+","").replace("▲","").replace("▼","-")
                return int(v) if v and v not in ("-","") else 0
            except:
                return 0

        result = []
        for table in soup.find_all("table"):
            rows_found = []
            for tr in table.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) < 4:
                    continue
                date_str = tds[0].get_text(strip=True)
                if not re.match(r"\d{4}\.\d{2}\.\d{2}", date_str):
                    continue
                n = len(tds)
                # 9열: 날짜|종가|전일비|등락률|거래량|기관순매매|외국인순매매|보유주수|보유율
                # 6열: 날짜|종가|전일비|외국인순매매|보유주수|보유율
                if n >= 7:
                    foreign = try_int(tds[6])
                elif n >= 4:
                    foreign = try_int(tds[3])
                else:
                    continue
                rows_found.append({"date": date_str, "foreign": foreign})
                if len(rows_found) >= days:
                    break
            if rows_found:
                result = rows_found
                break
        return result
    except:
        return []


# ── 기관/프로그램 세부 순매수 ─────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def fetch_institutional_detail(code: str, days: int = 3) -> list:
    """기관세부 + 프로그램 순매수(주)
    1차: institutional.naver (기관 세부)
    2차: frgn.naver 기관합계 컬럼 fallback
    """
    def pn(td):
        try:
            v = td.get_text(strip=True).replace(",","").replace("+","").replace("▲","").replace("▼","-")
            return int(v) if v and v not in ("-","") else 0
        except:
            return 0

    # 1차: institutional.naver
    try:
        url = f"https://finance.naver.com/item/institutional.naver?code={code}"
        res = requests.get(url, headers=HEADERS_PC, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            result = []
            for table in soup.find_all("table"):
                for tr in table.find_all("tr"):
                    tds = tr.find_all("td")
                    if len(tds) < 9:
                        continue
                    date_str = tds[0].get_text(strip=True)
                    if not re.match(r"\d{4}\.\d{2}\.\d{2}", date_str):
                        continue
                    result.append({
                        "date":              date_str,
                        "institution_total": pn(tds[1]),
                        "financial":         pn(tds[2]),
                        "insurance":         pn(tds[3]),
                        "trust":             pn(tds[4]),
                        "etf":               pn(tds[5]),
                        "pension":           pn(tds[6]),
                        "private":           pn(tds[7]),
                        "nation":            pn(tds[8]),
                        "other_corp":        pn(tds[9])  if len(tds) > 9  else 0,
                        "program":           pn(tds[10]) if len(tds) > 10 else 0,
                    })
                    if len(result) >= days:
                        break
                if result:
                    return result
    except:
        pass

    # 2차 fallback: frgn.naver 기관합계 컬럼 (index 5)
    try:
        url2 = f"https://finance.naver.com/item/frgn.naver?code={code}"
        res2 = requests.get(url2, headers=HEADERS_PC, timeout=8)
        if res2.status_code == 200:
            soup2 = BeautifulSoup(res2.text, "html.parser")
            result = []
            for table in soup2.find_all("table"):
                for tr in table.find_all("tr"):
                    tds = tr.find_all("td")
                    if len(tds) < 6:
                        continue
                    date_str = tds[0].get_text(strip=True)
                    if not re.match(r"\d{4}\.\d{2}\.\d{2}", date_str):
                        continue
                    # 9열: 날짜|종가|전일비|등락률|거래량|기관순매매|외국인순매매|보유주수|보유율
                    inst_val = pn(tds[5]) if len(tds) >= 6 else 0
                    result.append({
                        "date":              date_str,
                        "institution_total": inst_val,
                        "financial": 0, "insurance": 0, "trust": 0,
                        "etf": 0, "pension": 0, "private": 0,
                        "nation": 0, "other_corp": 0, "program": 0,
                    })
                    if len(result) >= days:
                        break
                if result:
                    return result
    except:
        pass

    return []


@st.cache_data(ttl=3600, show_spinner=False)
def search_by_name(query: str) -> list:
    try:
        url = f"https://ac.finance.naver.com/ac?q={query}&q_enc=UTF-8&target=stock,index"
        res = requests.get(url, headers=HEADERS_PC, timeout=5)
        items = res.json().get("items", [[]])[0]
        return [{"code": it[0].strip(), "name": it[1].strip()}
                for it in items if len(it) >= 2 and len(it[0]) == 6 and it[0].isdigit()][:5]
    except:
        return []


def calc_threshold(float_shares: int, margin_rate: int) -> int:
    """임계값 = 유동주식수 × 증거금율 / 100,000"""
    return int(float_shares * margin_rate / 100000)


def get_grade(net: dict, threshold: int):
    if threshold <= 0:
        return ("❓ 판별불가", "#94a3b8", "유동주식 데이터 없음")
    qualifiers = []
    if net.get("foreign",      0) >= threshold: qualifiers.append("외국인")
    if net.get("institution",  0) >= threshold: qualifiers.append("기관")
    if net.get("program",      0) >= threshold: qualifiers.append("프로그램")
    if qualifiers:
        return ("⭐ 관심종목", "#dc2626", f"{' · '.join(qualifiers)} 순매수 임계값 초과")
    return ("— 해당없음", "#64748b", f"임계값 {threshold:,}주 미달")


def fmt(n: int) -> str:
    if n > 0:   return f'<span class="pos">+{n:,}</span>'
    elif n < 0: return f'<span class="neg">{n:,}</span>'
    else:       return f'<span class="zero">0</span>'


def parse_input(raw: str) -> list:
    items, seen = [], set()
    for token in raw.replace("，", ",").split(","):
        token = token.strip()
        if not token: continue
        if token.isdigit() and len(token) == 6:
            if token not in seen:
                items.append({"code": token, "name": token})
                seen.add(token)
        else:
            r = search_by_name(token)
            if r and r[0]["code"] not in seen:
                items.append(r[0]); seen.add(r[0]["code"])
            elif not r:
                items.append({"code": None, "name": token})
    return items[:5]


# ── 입력 UI ──────────────────────────────────────────────────────────
st.markdown("#### 종목 입력 (최대 5개, 쉼표로 구분)")
ci, cb = st.columns([5, 1])
with ci:
    user_input = st.text_input("종목", placeholder="예: 삼성전자, 000660, HLB",
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
            frgn  = fetch_foreign_trading(code, n_days)
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
        dates_added = set()
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
            dates_added.add(d)
        for ir in inst:
            if ir["date"] not in dates_added:
                merged.append({
                    "date": ir["date"], "foreign": 0,
                    "institution": ir.get("institution_total", 0),
                    "financial":   ir.get("financial", 0),
                    "insurance":   ir.get("insurance", 0),
                    "trust":       ir.get("trust", 0),
                    "etf":         ir.get("etf", 0),
                    "pension":     ir.get("pension", 0),
                    "private":     ir.get("private", 0),
                    "nation":      ir.get("nation", 0),
                    "other_corp":  ir.get("other_corp", 0),
                    "program":     ir.get("program", 0),
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
        float_str = f"{float_shares:,}주" if float_shares > 0 else "조회중"
        st.markdown(f"""
        <div class="stock-header">
            <div class="sname">{name}</div>
            <div class="smeta">
                {code} · {market} · 현재가 {price:,}원 ·
                유동주식 {float_str} · 증거금율 {margin_rate}%
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

        # 디버그 정보 (항상 표시 — 파싱 확인용)
        with st.expander("🔧 파싱 디버그 정보 (확인 후 삭제 예정)"):
            st.write("**외국인 원본:**", frgn)
            st.write("**기관 원본:**", inst)
            st.write("**기본정보:**", basic)
            st.write("**병합결과:**", merged)

        if not merged:
            st.warning("수급 데이터 없음 — 장중 또는 거래일에 다시 시도하세요.")
            # 디버그 정보
            with st.expander("🔧 디버그 정보"):
                st.write(f"외국인 데이터: {frgn}")
                st.write(f"기관 데이터: {inst}")
                st.write(f"기본정보: {basic}")
            continue

        date_ths = "".join(f"<th>{r['date']}</th>" for r in merged)
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
  <th style="text-align:left;">구분</th>{date_ths}<th>{n_days}일 합계</th>
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
임계값(주) = 유동주식수 × 증거금율 / 100,000
```

| 증거금율 | 의미 | 임계값 (유동 1억주 기준) |
|---|---|---|
| 100% | 관리/투기 종목 | 100,000주 |
| 40%  | 일반 종목      | 40,000주  |
| 20%  | 우량주         | 20,000주  |

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
