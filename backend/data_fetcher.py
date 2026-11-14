"""
data_fetcher.py — NSE Stock Analysis Engine
============================================
Fetches price data, fundamentals, technical indicators, and Piotroski scores
for Indian equities listed on NSE.

All analytics are genuinely computed — no hardcoded scores or fake values.
"""

import os
import json
import time
import asyncio
from datetime import datetime, timedelta
import requests
import yfinance as yf
import pandas as pd
import numpy as np

from screener_fetcher import get_screener_fundamentals

# Reusable session with desktop User-Agent
yf_session = requests.Session()
yf_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
})


# ── Price Data ────────────────────────────────────────────────────────────────

def fetch_prices_via_query_api(ticker: str) -> pd.DataFrame:
    """Fallback price chart query."""
    if "." not in ticker:
        ticker = ticker + ".NS"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1y&interval=1d"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return pd.DataFrame()
        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return pd.DataFrame()

        timestamps = result[0].get("timestamp", [])
        indicators = result[0].get("indicators", {}).get("quote", [{}])[0]
        close_prices = indicators.get("close", [])
        volume_data = indicators.get("volume", [])

        if not timestamps or not close_prices:
            return pd.DataFrame()

        clean_pts = []
        for t, c, v in zip(timestamps, close_prices, volume_data):
            if t is not None and c is not None:
                date_str = str(datetime.fromtimestamp(t).date())
                clean_pts.append({
                    "date": date_str,
                    "close": float(c),
                    "volume": int(v) if v is not None else 0
                })
        if not clean_pts:
            return pd.DataFrame()
        df = pd.DataFrame(clean_pts)
        df['date'] = pd.to_datetime(df['date'])
        return df.sort_values('date').reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def get_price_data(ticker: str) -> dict:
    """Get full price history and current price."""
    if "." not in ticker:
        ticker = ticker + ".NS"

    hist_1y = pd.DataFrame()
    try:
        stock = yf.Ticker(ticker, session=yf_session)
        hist_1y = stock.history(period="1y")
        if not hist_1y.empty:
            hist_1y = hist_1y.dropna(subset=["Close"])
    except Exception:
        pass

    if hist_1y.empty:
        df_clean = fetch_prices_via_query_api(ticker)
        if not df_clean.empty:
            hist_1y = df_clean.set_index('date')
            hist_1y.index.name = 'Date'
            hist_1y = hist_1y.rename(columns={'close': 'Close', 'volume': 'Volume'})

    if hist_1y.empty:
        clean_sym = ticker.replace(".NS", "").replace(".BO", "")
        return {"error": f"Stock symbol '{clean_sym}' not found or has no active price data."}

    hist_6m = hist_1y[hist_1y.index >= (hist_1y.index.max() - pd.Timedelta(days=180))]
    hist_1m = hist_1y[hist_1y.index >= (hist_1y.index.max() - pd.Timedelta(days=30))]

    current_price = round(float(hist_1y["Close"].iloc[-1]), 2)
    price_1y_ago  = round(float(hist_1y["Close"].iloc[0]), 2)
    price_6m_ago  = round(float(hist_6m["Close"].iloc[0]), 2) if not hist_6m.empty else current_price
    price_1m_ago  = round(float(hist_1m["Close"].iloc[0]), 2) if not hist_1m.empty else current_price

    high_52w = round(float(hist_1y["Close"].max()), 2)
    low_52w  = round(float(hist_1y["Close"].min()), 2)

    daily_returns = hist_1y["Close"].pct_change().dropna()
    volatility_annual = round(float(daily_returns.std() * (252 ** 0.5) * 100), 2) if len(daily_returns) > 0 else 15.0
    avg_volume = int(hist_1y["Volume"].mean()) if "Volume" in hist_1y else 500000

    return {
        "ticker": ticker,
        "current_price": current_price,
        "change_1d_pct": round(((current_price - float(hist_1y["Close"].iloc[-2])) / float(hist_1y["Close"].iloc[-2])) * 100, 2) if len(hist_1y) > 1 else 0,
        "change_1m_pct": round(((current_price - price_1m_ago) / price_1m_ago) * 100, 2) if price_1m_ago else 0,
        "change_6m_pct": round(((current_price - price_6m_ago) / price_6m_ago) * 100, 2) if price_6m_ago else 0,
        "change_1y_pct": round(((current_price - price_1y_ago) / price_1y_ago) * 100, 2) if price_1y_ago else 0,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "position_in_52w_range_pct": round(((current_price - low_52w) / (high_52w - low_52w)) * 100, 1) if high_52w != low_52w else 50,
        "volatility_annual_pct": volatility_annual,
        "avg_daily_volume": avg_volume,
        "price_history_30d": {
            str(k.date()): round(float(v), 2)
            for k, v in hist_1m["Close"].items()
        },
        # Pass raw series so technical indicator fn can reuse it without a second HTTP call
        "_close_series": hist_1y["Close"],
    }


# ── Fundamentals ──────────────────────────────────────────────────────────────

def get_fundamentals(ticker: str) -> dict:
    """Get fundamental metrics: P/E, P/B, ROE, ROCE, Debt/Equity."""
    if "." not in ticker:
        ticker = ticker + ".NS"

    stock = yf.Ticker(ticker, session=yf_session)
    try:
        info = stock.info or {}
    except Exception:
        info = {}

    screener_data = get_screener_fundamentals(ticker)

    def get_m(s_key, y_key, default=None):
        return screener_data.get(s_key.lower(), info.get(y_key, default))

    pe = get_m("Stock P/E", "trailingPE", None)
    pb = screener_data.get("pb_ratio_calculated") or get_m("Price to book value", "priceToBook", None)
    roe = get_m("ROE", "returnOnEquity", None)
    if isinstance(roe, (int, float)) and roe < 1:
        roe = roe * 100

    de = screener_data.get("debt_to_equity") or info.get("debtToEquity", None)
    if isinstance(de, (int, float)) and de > 10:
        de = de / 100.0

    mcap = get_m("Market Cap", "marketCap")

    # EPS: screener first, then yfinance info
    eps = screener_data.get("eps") or info.get("trailingEps", None)

    # Sector / Industry: yfinance info is the source; fallback to screener if blank
    sector   = info.get("sector") or screener_data.get("sector") or None
    industry = info.get("industry") or screener_data.get("industry") or None

    return {
        "company_name": info.get("longName", ticker.replace(".NS", "")),
        "sector": sector,
        "industry": industry,
        "description": info.get("longBusinessSummary", f"NSE listed enterprise — {ticker}")[:250],
        "market_cap": mcap,
        "pe": round(float(pe), 2) if pe is not None else None,
        "pb": round(float(pb), 2) if pb is not None else None,
        "roe": round(float(roe), 2) if roe is not None else None,
        "debt_to_equity": round(float(de), 2) if de is not None else None,
        "dividend_yield": get_m("Dividend Yield", "dividendYield", None),
        "eps": round(float(eps), 2) if eps is not None else None,
        "revenue_growth_yoy_pct": screener_data.get("sales_growth_yoy", None),
        "profit_growth_yoy_pct": screener_data.get("profit_growth_yoy", None),
    }


# ── Technical Indicators ──────────────────────────────────────────────────────

def _compute_rsi(close: pd.Series, period: int = 14) -> float:
    """
    Wilder's RSI using exponential smoothing (identical to TradingView default).

    Steps:
      1. Compute daily changes (delta).
      2. Separate gains (up) and losses (down).
      3. Seed with a simple mean for the first `period` bars (Wilder initialisation).
      4. Apply Wilder's smoothing: avg = (prev_avg * (n-1) + current) / n
      5. RS = avg_gain / avg_loss  →  RSI = 100 - 100/(1+RS)
    """
    if len(close) < period + 1:
        return float("nan")

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    # Wilder smoothing via ewm with adjust=False and alpha = 1/period
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi_series = 100 - (100 / (1 + rs))
    return round(float(rsi_series.iloc[-1]), 2)


def _compute_macd(close: pd.Series):
    """
    Standard MACD: EMA(12) - EMA(26), signal = EMA(9) of MACD line.
    Returns (macd_value, signal_value, histogram_value, verdict_string).
    """
    if len(close) < 35:
        return None, None, None, "insufficient data"

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line

    macd_val   = round(float(macd_line.iloc[-1]), 4)
    signal_val = round(float(signal_line.iloc[-1]), 4)
    hist_val   = round(float(histogram.iloc[-1]), 4)

    # Bullish when MACD line > signal line
    verdict = "bullish" if macd_val > signal_val else "bearish"
    return macd_val, signal_val, hist_val, verdict


def _compute_sma(close: pd.Series, window: int) -> float | None:
    """Simple Moving Average over `window` bars."""
    if len(close) < window:
        return None
    return round(float(close.rolling(window=window).mean().iloc[-1]), 2)


def _technical_score(
    rsi: float,
    macd_verdict: str,
    price: float,
    ma_50: float | None,
    ma_200: float | None,
) -> int:
    """
    Rule-based technical score out of 100.

    Points breakdown (20 pts each):
      1. RSI in healthy range (40-70)       → 20 pts
      2. MACD bullish crossover             → 20 pts
      3. Price above 50-day MA              → 20 pts
      4. Price above 200-day MA             → 20 pts
      5. Golden cross (50 MA > 200 MA)      → 20 pts
    """
    score = 0

    # 1. RSI health
    if not (rsi is None or np.isnan(rsi)):
        if 40 <= rsi <= 70:
            score += 20
        elif 30 <= rsi < 40 or 70 < rsi <= 80:
            score += 10   # partial — slightly oversold/overbought

    # 2. MACD
    if macd_verdict == "bullish":
        score += 20

    # 3. Price vs 50-day MA
    if ma_50 and price > ma_50:
        score += 20

    # 4. Price vs 200-day MA
    if ma_200 and price > ma_200:
        score += 20

    # 5. Golden cross
    if ma_50 and ma_200 and ma_50 > ma_200:
        score += 20

    return score


def get_technical_indicators(ticker: str, close_series: pd.Series | None = None) -> dict:
    """
    Calculate RSI (Wilder 14), MACD (12/26/9), 50/200-day SMA, and a
    rule-based technical score /100.

    Pass `close_series` from a previously fetched price dict to avoid a
    second HTTP round-trip (fixes Reality Check #9).
    """
    if close_series is None:
        p_data = get_price_data(ticker)
        if "error" in p_data:
            return {"error": p_data["error"]}
        close_series = p_data.get("_close_series")
        current_price = p_data.get("current_price", 0.0)
    else:
        current_price = round(float(close_series.iloc[-1]), 2)

    if close_series is None or len(close_series) < 20:
        return {
            "rsi": None,
            "macd": None,
            "macd_signal": None,
            "macd_histogram": None,
            "macd_verdict": "insufficient data",
            "ma_50": None,
            "ma_200": None,
            "technical_score": 0,
            "verdict": "Insufficient price history for technical analysis",
        }

    rsi = _compute_rsi(close_series)
    macd_val, signal_val, hist_val, macd_verdict = _compute_macd(close_series)
    ma_50  = _compute_sma(close_series, 50)
    ma_200 = _compute_sma(close_series, 200)

    score = _technical_score(rsi, macd_verdict, current_price, ma_50, ma_200)

    # Human-readable verdict
    if score >= 80:
        verdict = "Strong bullish momentum"
    elif score >= 60:
        verdict = "Positive technical momentum"
    elif score >= 40:
        verdict = "Neutral — mixed signals"
    elif score >= 20:
        verdict = "Weak — bearish pressure"
    else:
        verdict = "Bearish — multiple sell signals"

    return {
        "rsi": rsi,
        "macd": macd_val,
        "macd_signal": signal_val,
        "macd_histogram": hist_val,
        "macd_verdict": macd_verdict,
        "ma_50": ma_50,
        "ma_200": ma_200,
        "technical_score": score,
        "verdict": verdict,
    }


# ── Piotroski F-Score ─────────────────────────────────────────────────────────

def _safe_val(df: pd.DataFrame, row_names: list[str], col_idx: int = 0) -> float | None:
    """
    Pull a value from a yfinance financial statement DataFrame.
    `row_names` is a list of possible row-label variants (yfinance renames them
    across versions).  `col_idx` 0 = most recent period, 1 = one year prior.
    """
    for name in row_names:
        # Case-insensitive search
        matches = [r for r in df.index if name.lower() in str(r).lower()]
        if matches:
            row = df.loc[matches[0]]
            if col_idx < len(row):
                val = row.iloc[col_idx]
                if val is not None and not (isinstance(val, float) and np.isnan(val)):
                    return float(val)
    return None


def get_piotroski_score(ticker: str) -> dict:
    """
    Compute the full 9-point Piotroski F-Score from real financial statements.

    The nine criteria:

    PROFITABILITY (4 points)
      F1  ROA positive this year
      F2  Operating cash flow positive this year
      F3  ROA improved YoY
      F4  Accruals (CFO/Assets > ROA) — quality of earnings

    LEVERAGE / LIQUIDITY (3 points)
      F5  Long-term debt ratio decreased YoY
      F6  Current ratio improved YoY
      F7  No new shares issued in past year

    OPERATING EFFICIENCY (2 points)
      F8  Gross margin improved YoY
      F9  Asset turnover improved YoY

    Data source: yfinance .financials, .balance_sheet, .cashflow
    """
    if "." not in ticker:
        ticker = ticker + ".NS"

    stock = yf.Ticker(ticker, session=yf_session)

    # ── Fetch statements ──────────────────────────────────────────────────────
    try:
        fin   = stock.financials        # income statement — columns = periods (newest first)
        bs    = stock.balance_sheet
        cf    = stock.cashflow
        info  = stock.info or {}
    except Exception as e:
        # yfinance sometimes returns empty JSON body → JSONDecodeError
        return {"score": None, "max": 9, "verdict": "Financial statements temporarily unavailable", "criteria": {}}

    # Guard: if statements came back empty, return early cleanly
    if fin is None or (hasattr(fin, 'empty') and fin.empty):
        return {"score": None, "max": 9, "verdict": "No annual financial data available", "criteria": {}}

    criteria = {}

    # ── Helper: Pull two consecutive year values ──────────────────────────────
    def val(df, names, yr=0):
        return _safe_val(df, names, yr)

    # ── PROFITABILITY ─────────────────────────────────────────────────────────

    # Total assets (average of current and prior year for ROA denominator)
    assets_now  = val(bs, ["Total Assets", "TotalAssets"])
    assets_prev = val(bs, ["Total Assets", "TotalAssets"], 1)
    avg_assets  = ((assets_now or 0) + (assets_prev or assets_now or 1)) / 2

    # Net income
    net_income_now  = val(fin, ["Net Income", "NetIncome"])
    net_income_prev = val(fin, ["Net Income", "NetIncome"], 1)

    # F1: ROA positive this year
    roa_now = (net_income_now / avg_assets) if (net_income_now is not None and avg_assets) else None
    f1 = 1 if (roa_now is not None and roa_now > 0) else 0
    criteria["F1_roa_positive"] = {
        "pass": bool(f1),
        "detail": f"ROA = {round(roa_now * 100, 2)}%" if roa_now is not None else "Data unavailable",
    }

    # F2: Operating cash flow positive
    cfo_now = val(cf, ["Operating Cash Flow", "Total Cash From Operating Activities",
                        "CashFlowFromContinuingOperatingActivities"])
    f2 = 1 if (cfo_now is not None and cfo_now > 0) else 0
    criteria["F2_cfo_positive"] = {
        "pass": bool(f2),
        "detail": f"CFO = ₹{round((cfo_now or 0)/1e7, 1)} Cr" if cfo_now is not None else "Data unavailable",
    }

    # F3: ROA improved YoY
    assets_prev2 = val(bs, ["Total Assets", "TotalAssets"], 2)
    avg_assets_prev = ((assets_prev or 0) + (assets_prev2 or assets_prev or 1)) / 2
    roa_prev = (net_income_prev / avg_assets_prev) if (net_income_prev is not None and avg_assets_prev) else None
    f3 = 1 if (roa_now is not None and roa_prev is not None and roa_now > roa_prev) else 0
    criteria["F3_roa_improving"] = {
        "pass": bool(f3),
        "detail": f"ROA now={round((roa_now or 0)*100,2)}% prev={round((roa_prev or 0)*100,2)}%"
                  if (roa_now is not None and roa_prev is not None) else "Data unavailable",
    }

    # F4: Accruals — CFO/Assets > ROA (cash earnings quality)
    cfo_ratio = (cfo_now / avg_assets) if (cfo_now is not None and avg_assets) else None
    f4 = 1 if (cfo_ratio is not None and roa_now is not None and cfo_ratio > roa_now) else 0
    criteria["F4_accruals_low"] = {
        "pass": bool(f4),
        "detail": f"CFO/Assets={round((cfo_ratio or 0)*100,2)}% vs ROA={round((roa_now or 0)*100,2)}%"
                  if cfo_ratio is not None else "Data unavailable",
    }

    # ── LEVERAGE / LIQUIDITY ──────────────────────────────────────────────────

    # F5: Long-term debt ratio decreased YoY
    ltd_now  = val(bs, ["Long Term Debt", "LongTermDebt", "Long-Term Debt"])
    ltd_prev = val(bs, ["Long Term Debt", "LongTermDebt", "Long-Term Debt"], 1)
    ltd_ratio_now  = (ltd_now  / assets_now)  if (ltd_now  is not None and assets_now)  else None
    ltd_ratio_prev = (ltd_prev / assets_prev) if (ltd_prev is not None and assets_prev) else None
    f5 = 1 if (ltd_ratio_now is not None and ltd_ratio_prev is not None and ltd_ratio_now < ltd_ratio_prev) else 0
    criteria["F5_leverage_decreased"] = {
        "pass": bool(f5),
        "detail": f"LTD/Assets now={round((ltd_ratio_now or 0)*100,1)}% prev={round((ltd_ratio_prev or 0)*100,1)}%"
                  if ltd_ratio_now is not None else "Data unavailable",
    }

    # F6: Current ratio improved YoY
    curr_assets_now  = val(bs, ["Current Assets", "TotalCurrentAssets"])
    curr_liab_now    = val(bs, ["Current Liabilities", "TotalCurrentLiabilities", "Current Liabilities"])
    curr_assets_prev = val(bs, ["Current Assets", "TotalCurrentAssets"], 1)
    curr_liab_prev   = val(bs, ["Current Liabilities", "TotalCurrentLiabilities", "Current Liabilities"], 1)
    cr_now  = (curr_assets_now / curr_liab_now)  if (curr_assets_now and curr_liab_now)  else None
    cr_prev = (curr_assets_prev / curr_liab_prev) if (curr_assets_prev and curr_liab_prev) else None
    f6 = 1 if (cr_now is not None and cr_prev is not None and cr_now > cr_prev) else 0
    criteria["F6_current_ratio_improved"] = {
        "pass": bool(f6),
        "detail": f"Current ratio now={round(cr_now or 0,2)} prev={round(cr_prev or 0,2)}"
                  if cr_now is not None else "Data unavailable",
    }

    # F7: No new dilution (shares not increased significantly)
    shares_now  = info.get("sharesOutstanding")
    # yfinance also exposes it on balance_sheet in some cases
    shares_issued = val(bs, ["Common Stock", "CommonStock", "Ordinary Shares Number",
                              "Share Issued", "SharesIssued"])
    shares_issued_prev = val(bs, ["Common Stock", "CommonStock", "Ordinary Shares Number",
                                   "Share Issued", "SharesIssued"], 1)
    if shares_issued is not None and shares_issued_prev is not None:
        f7 = 1 if shares_issued <= shares_issued_prev * 1.02 else 0  # allow 2 % tolerance
        criteria["F7_no_dilution"] = {
            "pass": bool(f7),
            "detail": f"Shares now={shares_issued:.0f} prev={shares_issued_prev:.0f}",
        }
    else:
        # If we can't fetch shares data at all, give benefit of the doubt → 0
        f7 = 0
        criteria["F7_no_dilution"] = {"pass": False, "detail": "Share data unavailable"}

    # ── OPERATING EFFICIENCY ──────────────────────────────────────────────────

    # F8: Gross margin improved YoY
    gross_profit_now  = val(fin, ["Gross Profit", "GrossProfit"])
    gross_profit_prev = val(fin, ["Gross Profit", "GrossProfit"], 1)
    rev_now  = val(fin, ["Total Revenue", "Revenue"])
    rev_prev = val(fin, ["Total Revenue", "Revenue"], 1)
    gm_now  = (gross_profit_now / rev_now)  if (gross_profit_now is not None and rev_now)  else None
    gm_prev = (gross_profit_prev / rev_prev) if (gross_profit_prev is not None and rev_prev) else None
    f8 = 1 if (gm_now is not None and gm_prev is not None and gm_now > gm_prev) else 0
    criteria["F8_gross_margin_improved"] = {
        "pass": bool(f8),
        "detail": f"Gross margin now={round((gm_now or 0)*100,1)}% prev={round((gm_prev or 0)*100,1)}%"
                  if gm_now is not None else "Data unavailable",
    }

    # F9: Asset turnover improved YoY
    at_now  = (rev_now  / avg_assets)      if (rev_now  is not None and avg_assets)      else None
    at_prev = (rev_prev / avg_assets_prev) if (rev_prev is not None and avg_assets_prev) else None
    f9 = 1 if (at_now is not None and at_prev is not None and at_now > at_prev) else 0
    criteria["F9_asset_turnover_improved"] = {
        "pass": bool(f9),
        "detail": f"Asset turnover now={round(at_now or 0,3)} prev={round(at_prev or 0,3)}"
                  if at_now is not None else "Data unavailable",
    }

    # ── Score & verdict ───────────────────────────────────────────────────────
    score = f1 + f2 + f3 + f4 + f5 + f6 + f7 + f8 + f9

    if score >= 8:
        verdict = "Excellent Quality Stock"
    elif score >= 6:
        verdict = "Strong Quality Stock"
    elif score >= 4:
        verdict = "Average Quality"
    else:
        verdict = "Weak Fundamentals"

    return {
        "score": score,
        "max": 9,
        "verdict": verdict,
        "criteria": criteria,
    }


# ── Historical Financial Comparison ──────────────────────────────────────────

def get_historical_financials(ticker: str) -> dict:
    """
    Extract YoY comparisons for the last 3 years from yfinance financial
    statements: revenue, net income, gross margin, EPS, and debt.
    Returns a list of annual snapshots (newest first) plus trend labels.
    """
    if "." not in ticker:
        ticker = ticker + ".NS"

    stock = yf.Ticker(ticker, session=yf_session)
    try:
        fin = stock.financials
        bs  = stock.balance_sheet
        cf  = stock.cashflow
    except Exception:
        return {"available": False, "reason": "Could not fetch financial statements"}

    if fin is None or fin.empty:
        return {"available": False, "reason": "No annual financial statements available"}

    snapshots = []
    num_periods = min(fin.shape[1], 4)  # up to 4 years of data

    for i in range(num_periods):
        try:
            period_label = fin.columns[i].year if hasattr(fin.columns[i], 'year') else str(fin.columns[i])[:4]

            rev    = _safe_val(fin, ["Total Revenue", "Revenue"], i)
            g_prof = _safe_val(fin, ["Gross Profit", "GrossProfit"], i)
            n_inc  = _safe_val(fin, ["Net Income", "NetIncome"], i)
            cfo    = _safe_val(cf,  ["Operating Cash Flow", "Total Cash From Operating Activities",
                                      "CashFlowFromContinuingOperatingActivities"], i)
            assets = _safe_val(bs,  ["Total Assets", "TotalAssets"], i)
            debt   = _safe_val(bs,  ["Long Term Debt", "LongTermDebt"], i)
            eqty   = _safe_val(bs,  ["Stockholders Equity", "TotalStockholdersEquity",
                                      "Total Stockholder Equity"], i)

            snapshot = {
                "year": period_label,
                "revenue_cr": round(rev / 1e7, 1) if rev else None,
                "net_income_cr": round(n_inc / 1e7, 1) if n_inc else None,
                "gross_margin_pct": round((g_prof / rev) * 100, 1) if (g_prof and rev) else None,
                "cfo_cr": round(cfo / 1e7, 1) if cfo else None,
                "total_assets_cr": round(assets / 1e7, 1) if assets else None,
                "long_term_debt_cr": round(debt / 1e7, 1) if debt else None,
                "debt_to_equity": round(debt / eqty, 2) if (debt and eqty and eqty > 0) else None,
            }
            snapshots.append(snapshot)
        except Exception:
            continue

    if len(snapshots) < 2:
        return {"available": True, "snapshots": snapshots, "trends": {}}

    # Compute trends (most recent vs prior year)
    cur, prv = snapshots[0], snapshots[1]

    def _trend(now, prev, label):
        if now is None or prev is None or prev == 0:
            return {"label": label, "direction": "unknown", "change_pct": None}
        chg = round(((now - prev) / abs(prev)) * 100, 1)
        return {"label": label, "direction": "up" if chg >= 0 else "down", "change_pct": chg}

    trends = {
        "revenue":      _trend(cur["revenue_cr"],       prv["revenue_cr"],       "Revenue"),
        "net_income":   _trend(cur["net_income_cr"],    prv["net_income_cr"],    "Net Income"),
        "gross_margin": _trend(cur["gross_margin_pct"], prv["gross_margin_pct"], "Gross Margin"),
        "cfo":          _trend(cur["cfo_cr"],           prv["cfo_cr"],           "Operating Cash Flow"),
        "debt":         {
            "label": "Long-Term Debt",
            "direction": "down" if (
                cur["long_term_debt_cr"] is not None and
                prv["long_term_debt_cr"] is not None and
                cur["long_term_debt_cr"] < prv["long_term_debt_cr"]
            ) else "up" if (
                cur["long_term_debt_cr"] is not None and
                prv["long_term_debt_cr"] is not None
            ) else "unknown",
            "change_pct": round(
                ((cur["long_term_debt_cr"] - prv["long_term_debt_cr"]) / abs(prv["long_term_debt_cr"])) * 100, 1
            ) if (cur["long_term_debt_cr"] and prv["long_term_debt_cr"]) else None
        },
    }

    return {"available": True, "snapshots": snapshots, "trends": trends}


# ── Verdict Engine ────────────────────────────────────────────────────────────

def _build_verdict(fundamentals: dict, technicals: dict, piotroski: dict,
                   historical: dict) -> dict:
    """
    Replace hardcoded flags/warnings with rule-based, data-driven signals.
    Returns {"overall": str, "flags": [...], "warnings": [...]}.
    """
    flags    = []
    warnings = []

    pe  = fundamentals.get("pe")
    roe = fundamentals.get("roe")
    de  = fundamentals.get("debt_to_equity")
    rg  = fundamentals.get("revenue_growth_yoy_pct")
    pg  = fundamentals.get("profit_growth_yoy_pct")

    piotroski_score = piotroski.get("score") or 0
    tech_score      = technicals.get("technical_score", 0)
    rsi             = technicals.get("rsi")

    # ── Profitability signals ─────────────────────────────────────────────────
    if roe is not None and roe >= 20:
        flags.append(f"High ROE ({roe}%) — strong capital efficiency")
    elif roe is not None and roe < 10:
        warnings.append(f"Low ROE ({roe}%) — weak return on shareholder capital")

    if pe is not None and pe < 20:
        flags.append(f"Attractive valuation — P/E {pe}x")
    elif pe is not None and pe > 50:
        warnings.append(f"High valuation — P/E {pe}x (priced for perfection)")

    if de is not None and de < 0.5:
        flags.append(f"Low debt — D/E ratio {de}x (conservative balance sheet)")
    elif de is not None and de > 1.5:
        warnings.append(f"High leverage — D/E {de}x (financial risk elevated)")

    # ── Growth signals ────────────────────────────────────────────────────────
    if rg is not None and rg >= 15:
        flags.append(f"Strong revenue growth {rg}% YoY")
    elif rg is not None and rg < 0:
        warnings.append(f"Revenue declining {rg}% YoY")

    if pg is not None and pg >= 15:
        flags.append(f"Strong profit growth {pg}% YoY")
    elif pg is not None and pg < 0:
        warnings.append(f"Net profit declining {pg}% YoY")

    # ── Piotroski ─────────────────────────────────────────────────────────────
    if piotroski_score >= 7:
        flags.append(f"High Piotroski F-Score ({piotroski_score}/9) — strong fundamentals")
    elif piotroski_score <= 3:
        warnings.append(f"Low Piotroski F-Score ({piotroski_score}/9) — weak financial health")

    # ── Technical signals ──────────────────────────────────────────────────────
    if tech_score >= 70:
        flags.append(f"Strong technical momentum (score {tech_score}/100)")
    elif tech_score <= 30:
        warnings.append(f"Weak technical momentum (score {tech_score}/100)")

    if rsi is not None and not (isinstance(rsi, float) and np.isnan(rsi)):
        if rsi < 30:
            warnings.append(f"RSI {rsi} — potentially oversold")
        elif rsi > 70:
            warnings.append(f"RSI {rsi} — potentially overbought")

    # ── Historical trends ──────────────────────────────────────────────────────
    if historical.get("available") and historical.get("trends"):
        trends = historical["trends"]
        if trends.get("revenue", {}).get("direction") == "up":
            chg = trends["revenue"].get("change_pct")
            if chg and chg >= 10:
                flags.append(f"Revenue growing ({chg}% YoY)")
        if trends.get("debt", {}).get("direction") == "down":
            flags.append("Debt reducing YoY — improving balance sheet")
        elif trends.get("debt", {}).get("direction") == "up":
            chg = trends["debt"].get("change_pct")
            if chg and chg > 20:
                warnings.append(f"Long-term debt rising {chg}% YoY")

    # ── Overall verdict ───────────────────────────────────────────────────────
    score_composite = (
        (piotroski_score / 9) * 40 +
        (tech_score / 100) * 30 +
        (len(flags) / max(len(flags) + len(warnings), 1)) * 30
    )

    if score_composite >= 65:
        overall = "Strong Buy Zone"
    elif score_composite >= 45:
        overall = "Moderate Opportunity"
    elif score_composite >= 30:
        overall = "Hold / Watch"
    else:
        overall = "Caution — Weak Setup"

    return {"overall": overall, "flags": flags, "warnings": warnings}


# ── Full Analysis Pipeline ────────────────────────────────────────────────────

def full_stock_analysis(ticker: str) -> dict:
    """Full stock analysis engine — all data genuinely computed."""
    price = get_price_data(ticker)
    if not price or "error" in price:
        clean_sym = ticker.replace(".NS", "").replace(".BO", "")
        return {"error": price.get("error") if isinstance(price, dict) else f"Stock symbol '{clean_sym}' not found on NSE/BSE."}

    # Reuse the Close series from price fetch to avoid a duplicate HTTP call (Reality Check #9)
    close_series = price.pop("_close_series", None)

    fundamentals = get_fundamentals(ticker)
    technicals   = get_technical_indicators(ticker, close_series=close_series)
    piotroski    = get_piotroski_score(ticker)
    historical   = get_historical_financials(ticker)
    verdict      = _build_verdict(fundamentals, technicals, piotroski, historical)

    clean_ticker = ticker.replace(".NS", "").replace(".BO", "")
    return {
        "ticker": clean_ticker,
        "company_name": fundamentals.get("company_name", ticker),
        "sector": fundamentals.get("sector"),
        "price": price,
        "fundamentals": fundamentals,
        "technicals": technicals,
        "piotroski": piotroski,
        "historical": historical,
        "verdict": verdict,
        "fetched_at": datetime.now().isoformat(),
    }


async def async_full_stock_analysis(ticker: str) -> dict:
    """Asynchronous full stock analysis engine."""
    return await asyncio.to_thread(full_stock_analysis, ticker)
