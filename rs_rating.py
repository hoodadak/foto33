# ===================== rs_rating.py =====================
# 윌리엄 오닐 방식 RS Rating 계산 모듈
#
# 알고리즘:
#   1. yfinance로 종목 + 벤치마크 일봉 수집
#   2. 복합 수익률 = 52주 수익률 × 0.7 + 13주 수익률 × 0.3
#   3. (종목 복합 수익률) / (벤치마크 복합 수익률) 으로 상대값 산출
#   4. 전체 종목 중 백분위 → RS Rating 1~99
#
# 사용법:
#   from rs_rating import fetch_rs_ratings
#   rs_map = fetch_rs_ratings(["005930", "000660", ...])
#   # {"005930": 87, "000660": 72, ...}
# =========================================================

import time
from functools import lru_cache

try:
    import yfinance as yf
    import pandas as pd
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


# 벤치마크 티커
KOSPI_TICKER  = "^KS11"   # 코스피 지수
KOSDAQ_TICKER = "^KQ11"   # 코스닥 지수

# 코스닥 종목코드 판별: 코스닥은 A로 시작하거나 숫자 6자리 기준으로
# naver 기준 코스닥 코드는 일반적으로 0으로 시작하지 않는 경우가 많지만
# 실제로는 코드만으로 100% 판별이 어렵기 때문에 yfinance 시도 방식 사용
# → 두 지수 모두 가져와서 종목 수익률과 더 상관도 높은 쪽 자동 선택 (실용적 접근)

PERIOD_LONG  = "1y"   # 52주
PERIOD_SHORT = "3mo"  # 13주
WEIGHT_LONG  = 0.7
WEIGHT_SHORT = 0.3

# yfinance 요청 배치 크기 (한 번에 너무 많으면 timeout 위험)
BATCH_SIZE = 50
REQUEST_DELAY = 0.5   # 배치 간 딜레이(초)


def _to_yf_ticker(code: str) -> str:
    """6자리 종목코드 → yfinance 티커 변환 (예: 005930 → 005930.KS)"""
    code = code.strip()
    # 이미 .KS / .KQ 붙어 있으면 그대로
    if code.endswith(".KS") or code.endswith(".KQ"):
        return code
    # 코스닥 판별 (앞자리 0~2 이외 숫자로 시작하면 코스닥 경향)
    # 완벽하지 않으므로 .KS 붙인 뒤 실패 시 .KQ 로 폴백하는 방식 사용
    return f"{code}.KS"


def _composite_return(prices: "pd.Series") -> float:
    """
    복합 수익률 = 52주 수익률 × 0.7 + 13주 수익률 × 0.3
    prices: 일봉 종가 시리즈 (최소 65 거래일 필요)
    """
    if prices is None or len(prices) < 10:
        return None

    latest = float(prices.iloc[-1])

    # 52주 (약 252 거래일) 전 가격
    idx_52 = max(0, len(prices) - 252)
    price_52 = float(prices.iloc[idx_52])

    # 13주 (약 65 거래일) 전 가격
    idx_13 = max(0, len(prices) - 65)
    price_13 = float(prices.iloc[idx_13])

    ret_52 = (latest - price_52) / price_52 if price_52 > 0 else 0.0
    ret_13 = (latest - price_13) / price_13 if price_13 > 0 else 0.0

    return ret_52 * WEIGHT_LONG + ret_13 * WEIGHT_SHORT


def _fetch_batch_returns(tickers: list) -> dict:
    """
    yfinance로 여러 티커의 복합 수익률 일괄 조회
    반환: {ticker: composite_return}
    """
    if not YFINANCE_AVAILABLE or not tickers:
        return {}

    result = {}
    try:
        raw = yf.download(
            tickers,
            period=PERIOD_LONG,
            progress=False,
            auto_adjust=True,
            threads=True,
        )
        if raw.empty:
            return {}

        closes = raw["Close"] if "Close" in raw.columns else raw

        # 단일 종목이면 Series → DataFrame 변환
        if isinstance(closes, pd.Series):
            closes = closes.to_frame(name=tickers[0])

        for ticker in tickers:
            if ticker not in closes.columns:
                continue
            series = closes[ticker].dropna()
            ret = _composite_return(series)
            if ret is not None:
                result[ticker] = ret

    except Exception:
        pass

    return result


def _fetch_benchmark_returns() -> dict:
    """코스피·코스닥 복합 수익률 반환"""
    bm = _fetch_batch_returns([KOSPI_TICKER, KOSDAQ_TICKER])
    return {
        "kospi":  bm.get(KOSPI_TICKER,  0.0),
        "kosdaq": bm.get(KOSDAQ_TICKER, 0.0),
    }


def _detect_market(code: str, yf_ticker: str, kospi_ret: float, kosdaq_ret: float) -> str:
    """
    종목코드로 코스피/코스닥 간단 판별.
    - .KQ 티커가 정상 데이터를 반환한 경우 코스닥으로 간주
    - 코드 앞 두 자리가 0이면 코스피 경향 (삼성전자 005930 등)
    실제로는 종목코드 앞자리가 6자리에 따라 다르지만
    yfinance .KS 실패 여부를 확인하는 대신
    코드 숫자 범위로 근사 판별 (실용적 기준)
    """
    # 코스닥: 앞자리 1~9로 시작하는 경우가 많음 (비절대적)
    # 코스피: 0으로 시작하는 6자리 코드 (005930, 000660 등)
    # 가장 단순하고 실패 없는 방법: 두 벤치마크 모두 사용해 상대값 계산 후
    # 두 값 모두 제공하되 UI에서는 소속 시장 기준으로 선택
    # → 여기서는 코드 앞자리 기준 단순 판별
    if code.startswith("0"):
        return "kospi"
    else:
        return "kosdaq"


def fetch_rs_ratings(codes: list, use_unified_benchmark: bool = False) -> dict:
    """
    주어진 종목코드 리스트의 RS Rating(1~99) 계산

    Parameters
    ----------
    codes : list of str
        6자리 종목코드 목록 (예: ["005930", "000660"])
    use_unified_benchmark : bool
        True면 코스피 단일 벤치마크 사용 (코스피·코스닥 혼합 시)
        False면 종목 소속 시장 벤치마크 자동 선택 (기본값, 오닐 방식)

    Returns
    -------
    dict : {종목코드: RS Rating(int 1~99)}
        데이터 부족 종목은 결과에서 제외됨
    """
    if not YFINANCE_AVAILABLE:
        return {}

    if not codes:
        return {}

    # 1. 벤치마크 수익률 조회
    bm_returns = _fetch_benchmark_returns()
    kospi_ret  = bm_returns["kospi"]
    kosdaq_ret = bm_returns["kosdaq"]

    # 2. 종목 티커 변환
    code_to_ticker = {c: _to_yf_ticker(c) for c in codes}
    all_tickers = list(code_to_ticker.values())

    # 3. 배치별 수익률 조회
    ticker_returns = {}
    for i in range(0, len(all_tickers), BATCH_SIZE):
        batch = all_tickers[i: i + BATCH_SIZE]
        batch_result = _fetch_batch_returns(batch)
        ticker_returns.update(batch_result)

        # .KS 실패한 종목은 .KQ 로 재시도
        failed = [t for t in batch if t not in batch_result]
        if failed:
            kq_tickers = [t.replace(".KS", ".KQ") for t in failed]
            kq_map = dict(zip(kq_tickers, failed))  # .KQ → 원래 .KS 티커
            kq_result = _fetch_batch_returns(kq_tickers)
            for kq_t, ret in kq_result.items():
                orig_t = kq_map[kq_t]
                ticker_returns[orig_t] = ret

        if i + BATCH_SIZE < len(all_tickers):
            time.sleep(REQUEST_DELAY)

    # 4. 상대값 계산: 종목 복합 수익률 / 벤치마크 복합 수익률
    code_relative = {}
    for code, ticker in code_to_ticker.items():
        if ticker not in ticker_returns:
            continue
        stock_ret = ticker_returns[ticker]

        if use_unified_benchmark:
            bm_ret = kospi_ret
        else:
            market = _detect_market(code, ticker, kospi_ret, kosdaq_ret)
            bm_ret = kospi_ret if market == "kospi" else kosdaq_ret

        # 벤치마크가 0이면 종목 수익률 그대로 사용
        if bm_ret == 0:
            relative = stock_ret
        else:
            relative = stock_ret / abs(bm_ret)

        code_relative[code] = relative

    if not code_relative:
        return {}

    # 5. RS Rating 1~99 변환
    # 종목이 5개 미만이면 상대끼리 비교가 무의미 → 절대값 기준 변환
    # 상대값(relative) 의미: 1.0 = 벤치마크와 동일, >1 = 벤치마크 상회
    # 절대값 구간 매핑 (경험적):
    #   relative >= 2.0  → RS 90~99
    #   relative >= 1.3  → RS 80~89
    #   relative >= 1.0  → RS 60~79
    #   relative >= 0.5  → RS 40~59
    #   relative <  0.5  → RS 1~39
    def _relative_to_rs_absolute(rel: float) -> int:
        if rel >= 2.0:
            # 2.0 이상: 80~99 구간 선형 보간 (최대 3.0 기준)
            return max(80, min(99, round(80 + (rel - 2.0) / 1.0 * 19)))
        elif rel >= 1.3:
            return max(70, min(79, round(70 + (rel - 1.3) / 0.7 * 9)))
        elif rel >= 1.0:
            return max(60, min(69, round(60 + (rel - 1.0) / 0.3 * 9)))
        elif rel >= 0.5:
            return max(40, min(59, round(40 + (rel - 0.5) / 0.5 * 19)))
        elif rel >= 0.0:
            return max(20, min(39, round(20 + rel / 0.5 * 19)))
        else:
            # 음수(절대 하락): 1~19
            return max(1, min(19, round(19 + rel * 10)))

    rs_ratings = {}

    if len(code_relative) < 5:
        # 절대값 기준 — 종목 수가 적어 상호 백분위가 의미 없을 때
        for code, rel in code_relative.items():
            rs_ratings[code] = _relative_to_rs_absolute(rel)
    else:
        # 백분위 기준 — 충분한 종목 수일 때 (주도테마 다종목 스캔 등)
        sorted_codes = sorted(code_relative, key=lambda c: code_relative[c])
        n = len(sorted_codes)
        for rank, code in enumerate(sorted_codes):
            rs = max(1, min(99, round(1 + (rank / max(n - 1, 1)) * 98)))
            rs_ratings[code] = rs

    return rs_ratings


def rs_rating_label(rs: int) -> str:
    """RS Rating을 등급 레이블로 변환"""
    if rs >= 90:
        return "🔥 최상위"
    elif rs >= 80:
        return "⭐ 상위"
    elif rs >= 60:
        return "✅ 양호"
    elif rs >= 40:
        return "➖ 보통"
    else:
        return "🔻 하위"


# =====================================================================
# RS Rating 히스토리 (일별 RS 변화) — RS 조회 페이지용
# =====================================================================

def fetch_stock_name(code: str) -> str:
    """
    네이버 증권 API로 종목명 조회.
    실패 시 코드 그대로 반환.
    """
    try:
        import requests
        url = f"https://m.stock.naver.com/api/stock/{code}/basic"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        data = res.json()
        return data.get("stockName") or data.get("name") or code
    except Exception:
        return code


def search_code_by_name(query: str) -> list:
    """
    네이버 증권 검색으로 종목명 → 종목코드 변환.
    반환: [{"code": "005930", "name": "삼성전자", "market": "KOSPI"}, ...]
    """
    try:
        import requests
        url = f"https://ac.finance.naver.com/ac?q={query}&q_enc=UTF-8&target=stock,index"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        data = res.json()
        results = []
        for item in data.get("items", [[]])[0]:
            # item: [코드, 이름, 시장구분코드, 시장명, ...]
            if len(item) >= 4:
                code = item[0].strip()
                name = item[1].strip()
                market = item[3].strip() if len(item) > 3 else ""
                if len(code) == 6 and code.isdigit():
                    results.append({"code": code, "name": name, "market": market})
        return results[:10]
    except Exception:
        return []


def fetch_rs_history(code: str) -> "pd.DataFrame | None":
    """
    단일 종목의 일별 RS 히스토리 계산 (최대 2년치 전체 반환).

    슬라이딩 윈도우 방식:
      각 날짜 t를 "오늘"로 보고 그 시점까지의 데이터로
      52주×0.7 + 13주×0.3 복합 수익률 → 벤치마크 대비 상대값 계산.

    rs_score(1~99):
      전체 2년 기간 내 최소-최대 정규화.
      절대 백분위가 아닌 해당 종목 자체의 상대강도 추세 파악용.

    반환: DataFrame(columns=["date", "rs_score", "rs_raw", "price"])
    """
    if not YFINANCE_AVAILABLE:
        return None

    try:
        import yfinance as yf
        import pandas as pd

        ticker_ks = f"{code}.KS"
        ticker_kq = f"{code}.KQ"

        # 히스토리 계산용 여유분 포함 3년치 다운로드
        raw = yf.download(ticker_ks, period="3y", progress=False, auto_adjust=True)
        if raw.empty or len(raw) < 65:
            raw = yf.download(ticker_kq, period="3y", progress=False, auto_adjust=True)
        if raw.empty or len(raw) < 65:
            return None

        closes = raw["Close"].dropna()
        if isinstance(closes, pd.DataFrame):
            closes = closes.iloc[:, 0]

        # 벤치마크 3년치
        market    = _detect_market(code, ticker_ks, 0, 0)
        bm_ticker = KOSPI_TICKER if market == "kospi" else KOSDAQ_TICKER
        bm_raw    = yf.download(bm_ticker, period="3y", progress=False, auto_adjust=True)
        if bm_raw.empty:
            return None
        bm_closes = bm_raw["Close"].dropna()
        if isinstance(bm_closes, pd.DataFrame):
            bm_closes = bm_closes.iloc[:, 0]

        # 공통 날짜 인덱스 정렬
        common_idx = closes.index.intersection(bm_closes.index)
        closes    = closes.loc[common_idx]
        bm_closes = bm_closes.loc[common_idx]

        if len(closes) < 65:
            return None

        total = len(closes)
        # 슬라이딩 시작점: 최소 252일(52주) 확보 후부터 RS 계산
        # → 최근 2년치(약 504 거래일)만 결과로 반환
        start_calc = max(252, total - 504)

        results = []
        for i in range(start_calc, total):
            # ── 핵심 수정: 각 시점에서 정확히 최근 252일/65일 기준으로 수익률 계산 ──
            # 전체 누적 슬라이스가 아닌, 해당 시점 기준 고정 윈도우 사용
            price_now   = float(closes.iloc[i])
            bm_now      = float(bm_closes.iloc[i])

            # 52주(252 거래일) 전 가격
            idx_52 = max(0, i - 252)
            price_52  = float(closes.iloc[idx_52])
            bm_52     = float(bm_closes.iloc[idx_52])

            # 13주(65 거래일) 전 가격
            idx_13 = max(0, i - 65)
            price_13  = float(closes.iloc[idx_13])
            bm_13     = float(bm_closes.iloc[idx_13])

            # 복합 수익률 = 52주×0.7 + 13주×0.3
            stock_ret = ((price_now - price_52) / price_52 * 0.7 +
                         (price_now - price_13) / price_13 * 0.3) if price_52 > 0 and price_13 > 0 else None
            bm_ret    = ((bm_now - bm_52) / bm_52 * 0.7 +
                         (bm_now - bm_13) / bm_13 * 0.3) if bm_52 > 0 and bm_13 > 0 else None

            if stock_ret is None or bm_ret is None:
                continue

            rel = stock_ret / abs(bm_ret) if bm_ret != 0 else stock_ret

            results.append({
                "date":   closes.index[i],
                "rs_raw": rel,
                "price":  float(closes.iloc[i]),
            })

        if not results:
            return None

        df = pd.DataFrame(results)

        # rs_raw → 절대값 기준 RS 변환
        # (전체 기간 min-max 정규화 대신 벤치마크 대비 절대 구간 사용)
        # relative 의미: 1.0 = 벤치마크와 동일, 2.0 = 벤치마크의 2배
        def _to_rs(rel: float) -> int:
            if rel >= 2.0:
                return max(80, min(99, round(80 + (rel - 2.0) / 1.0 * 19)))
            elif rel >= 1.3:
                return max(70, min(79, round(70 + (rel - 1.3) / 0.7 * 9)))
            elif rel >= 1.0:
                return max(60, min(69, round(60 + (rel - 1.0) / 0.3 * 9)))
            elif rel >= 0.5:
                return max(40, min(59, round(40 + (rel - 0.5) / 0.5 * 19)))
            elif rel >= 0.0:
                return max(20, min(39, round(20 + rel / 0.5 * 19)))
            else:
                return max(1, min(19, round(19 + rel * 10)))

        df["rs_score"] = df["rs_raw"].apply(_to_rs)

        df = df.reset_index(drop=True)
        return df[["date", "rs_score", "rs_raw", "price"]]

    except Exception:
        return None


def resample_rs_history(df: "pd.DataFrame", freq: str) -> "pd.DataFrame":
    """
    일별 RS 히스토리 DataFrame을 주별/월별로 리샘플링.

    Parameters
    ----------
    df   : fetch_rs_history() 반환값
    freq : "D" (일별 그대로) | "W" (주별 마지막 거래일) | "M" (월별 마지막 거래일)

    반환: DataFrame(columns=["date", "rs_score", "price"])
          - rs_score : 해당 기간 마지막 거래일 값
          - price    : 해당 기간 마지막 종가
    """
    try:
        import pandas as pd

        if df is None or df.empty:
            return df

        tmp = df.copy()
        tmp["date"] = pd.to_datetime(tmp["date"])
        tmp = tmp.set_index("date")

        if freq == "D":
            result = tmp[["rs_score", "price"]].copy()
        else:
            # 주별: W-FRI (금요일 마감), 월별: ME (월말)
            rule = "W-FRI" if freq == "W" else "ME"
            result = tmp[["rs_score", "price"]].resample(rule).last().dropna()

        result = result.reset_index()
        result.columns = ["date", "rs_score", "price"]
        return result

    except Exception:
        return df
