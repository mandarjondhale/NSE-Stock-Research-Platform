"""
main.py — FinCopilot API (NSE Stock Research Edition)
======================================================
Pure NSE stock research platform.
All core analysis is LLM-free.
Gemini is an optional /summarize endpoint used only if you want
a natural language paragraph. The app works 100% without it.
"""

import os
import io
import csv
import json
import math
import urllib.request
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from data_fetcher import (
    full_stock_analysis,
    async_full_stock_analysis,
    get_price_data,
    get_fundamentals,
    get_piotroski_score,
    yf_session
)
from cache import cache_instance
import asyncio


app = FastAPI(title="FinCopilot API — NSE Stock Research", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── NSE Equities List ────────────────────────────────────────────────────────

nse_list = []

def download_nse_list():
    global nse_list
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    req = urllib.request.Request(url, headers=headers)

    print("Downloading active NSE equities CSV...")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            csv_data = response.read().decode('utf-8')

        csv_file = io.StringIO(csv_data)
        reader = csv.DictReader(csv_file)

        temp_list = []
        for row in reader:
            symbol = row.get("SYMBOL")
            name = row.get("NAME OF COMPANY")
            if symbol and name:
                temp_list.append({
                    "symbol": symbol.strip(),
                    "name": name.strip()
                })

        if temp_list:
            nse_list = temp_list
            with open("nse_equities.json", "w", encoding="utf-8") as f:
                json.dump(nse_list, f, indent=2)
            print(f"Downloaded and saved {len(nse_list)} active NSE equities.")
    except Exception as e:
        print(f"Error downloading or parsing EQUITY_L.csv: {e}")
        if not nse_list:
            # Fallback mock list if file is completely missing
            nse_list = [
                {"symbol": "RELIANCE", "name": "RELIANCE INDUSTRIES LTD"},
                {"symbol": "TCS", "name": "TATA CONSULTANCY SERVICES LTD"},
                {"symbol": "INFY", "name": "INFOSYS LTD"},
                {"symbol": "HDFCBANK", "name": "HDFC BANK LTD"},
                {"symbol": "ITC", "name": "ITC LTD"},
                {"symbol": "WIPRO", "name": "WIPRO LTD"},
                {"symbol": "BAJFINANCE", "name": "BAJAJ FINANCE LTD"},
                {"symbol": "TATAMOTORS", "name": "TATA MOTORS LTD"},
                {"symbol": "ASIANPAINT", "name": "ASIAN PAINTS LTD"},
                {"symbol": "SUNPHARMA", "name": "SUN PHARMACEUTICAL INDUSTRIES LTD"}
            ]

def load_nse_list():
    global nse_list
    json_path = "nse_equities.json"
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                nse_list = json.load(f)
            print(f"Loaded {len(nse_list)} equities from nse_equities.json")
            return
        except Exception as e:
            print(f"Error reading nse_equities.json: {e}")

    # Try downloading if missing
    download_nse_list()


# ── Background Tasks ─────────────────────────────────────────────────────────

async def prewarm_cache_loop():
    popular_tickers = [
        "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ITC.NS",
        "WIPRO.NS", "BAJFINANCE.NS", "TATAMOTORS.NS", "ASIANPAINT.NS", "SUNPHARMA.NS"
    ]
    print("Pre-warming background task started.")
    while True:
        try:
            print("Pre-warming cache check...")
            for ticker in popular_tickers:
                cache_key = f"stock_analysis:{ticker}"
                # If cache is valid and we are off-market, skip refreshing
                if not cache_instance.is_market_hours() and cache_instance.get(cache_key) is not None:
                    continue

                print(f"Pre-warming ticker: {ticker}")
                try:
                    result = await async_full_stock_analysis(ticker)
                    if result and "error" not in result:
                        cache_instance.set(cache_key, result)
                except Exception as ex:
                    print(f"Error pre-warming {ticker}: {ex}")
                await asyncio.sleep(2)
        except Exception as e:
            print(f"Error in pre-warm cache loop: {e}")

        # Sleep for 4 minutes
        await asyncio.sleep(240)


async def weekly_nse_downloader_loop():
    # Sleep 1 day initially to avoid immediately redownloading on startup
    await asyncio.sleep(86400)
    while True:
        try:
            download_nse_list()
        except Exception as e:
            print(f"Error in weekly NSE downloader loop: {e}")
        await asyncio.sleep(7 * 86400)


@app.on_event("startup")
async def on_startup():
    load_nse_list()
    asyncio.create_task(prewarm_cache_loop())
    asyncio.create_task(weekly_nse_downloader_loop())


# ── Request Models ───────────────────────────────────────────────────────────

class TickerRequest(BaseModel):
    ticker: str

class SummarizeRequest(BaseModel):
    ticker: str
    analysis_data: dict   # pass the full_stock_analysis result


# ── Utility ──────────────────────────────────────────────────────────────────

def clean_nans(data):
    if isinstance(data, dict):
        return {k: clean_nans(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_nans(v) for v in data]
    elif isinstance(data, float):
        if math.isnan(data) or math.isinf(data):
            return None
        return data
    elif isinstance(data, np.generic):
        val = data.item()
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return val
    else:
        return data


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "status": "FinCopilot API v4 — NSE Stock Research",
        "endpoints": [
            "POST /api/stock/analyze",
            "GET  /api/stock/price/{ticker}",
            "GET  /api/search/symbols?q=<query>",
            "POST /api/stock/summarize",
            "POST /api/stock/summarize/stream",
        ]
    }


@app.post("/api/stock/analyze")
async def analyze_stock(req: TickerRequest):
    """
    Full stock analysis — price, fundamentals, technicals, Piotroski score.
    NO LLM. Cached for speed and API safety.
    """
    ticker = req.ticker.upper().strip()
    if "." not in ticker:
        ticker += ".NS"

    cache_key = f"stock_analysis:{ticker}"
    cached_data = cache_instance.get(cache_key)
    if cached_data:
        print(f"CACHE HIT for {ticker}")
        return clean_nans({"success": True, "data": cached_data})

    try:
        print(f"CACHE MISS for {ticker}. Running async analysis pipeline...")
        result = await async_full_stock_analysis(ticker)
        if "error" in result:
            raise HTTPException(404, result["error"])

        cache_instance.set(cache_key, result)
        return clean_nans({"success": True, "data": result})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/search/symbols")
def search_symbols(q: str = "", limit: int = 8):
    """
    Search NSE symbols and company names.
    Case-insensitive, scored by match relevance (prefix → contains).
    """
    if len(q.strip()) < 2:
        return []

    query = q.lower().strip()
    scored_items = []

    for item in nse_list:
        symbol = item["symbol"].lower()
        name = item["name"].lower()

        best_tier_score = 0

        # Tier 1: Exact symbol match
        if symbol == query:
            best_tier_score = max(best_tier_score, 10000 - len(symbol))
        # Tier 2: Symbol starts with query
        elif symbol.startswith(query):
            best_tier_score = max(best_tier_score, 8000 - len(symbol))

        # Tier 3 & 4: Name words start with query
        words = name.split()
        if words:
            if words[0].startswith(query):
                best_tier_score = max(best_tier_score, 6000 - len(words[0]))
            else:
                for idx, word in enumerate(words[1:]):
                    if word.startswith(query):
                        best_tier_score = max(best_tier_score, 4000 - idx - len(word))
                        break

        # Tier 5: Symbol contains query
        if query in symbol:
            best_tier_score = max(best_tier_score, 2000 - len(symbol))

        # Tier 6: Name contains query
        if query in name:
            best_tier_score = max(best_tier_score, 1000 - len(name))

        if best_tier_score > 0:
            scored_items.append((best_tier_score, item))

    scored_items.sort(key=lambda x: x[0], reverse=True)

    result = []
    seen = set()
    for score, item in scored_items:
        if item["symbol"] not in seen:
            seen.add(item["symbol"])
            result.append({
                "symbol": item["symbol"],
                "name": item["name"],
                "exchange": "NSE"
            })

    return result[:limit]


@app.get("/api/stock/price/{ticker}")
def get_price(ticker: str):
    """
    Live price data only — no LLM, great for periodic refresh.
    """
    ticker = ticker.upper()
    if "." not in ticker:
        ticker += ".NS"
    try:
        return clean_nans({"success": True, "data": get_price_data(ticker)})
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/stock/summarize")
def summarize_with_ai(req: SummarizeRequest):
    """
    OPTIONAL — uses Gemini to write a 3-sentence plain-language summary.
    Only called if GEMINI_API_KEY is set. App works 100% without this.
    Token usage: ~200 tokens per call (tiny).
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return {
            "success": True,
            "summary": None,
            "note": "Set GEMINI_API_KEY in .env to enable AI summaries.",
        }

    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        d = req.analysis_data
        verdict = d.get("verdict", {})
        fin = d.get("fundamentals", {})
        price = d.get("price", {})
        piotroski = d.get("piotroski", {})
        tech = d.get("technicals", {})

        prompt = f"""Write exactly 3 sentences summarizing this Indian stock for a retail investor.
Be specific, use the numbers, keep plain language. No jargon.

Stock: {d.get('company_name')} ({req.ticker})
Overall verdict: {verdict.get('overall')}
P/E: {fin.get('pe')} | ROE: {fin.get('roe')}% | D/E: {fin.get('debt_to_equity')}
Revenue growth: {fin.get('revenue_growth_yoy_pct')}% | Profit growth: {fin.get('profit_growth_yoy_pct')}%
1Y price change: {price.get('change_1y_pct')}%
Piotroski F-Score: {piotroski.get('score')}/9
Technical score: {tech.get('technical_score')}/100
Positives: {', '.join(verdict.get('flags', [])[:3])}
Warnings: {', '.join(verdict.get('warnings', [])[:3])}

3 sentences only. End with what type of investor this suits."""

        response = None
        for model_name in ["gemini-1.5-flash", "gemini-pro"]:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                break
            except Exception:
                continue

        if not response:
            try:
                available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                if available:
                    model_name = available[0].replace("models/", "")
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt)
            except Exception as e:
                return {"success": True, "summary": None, "note": f"AI unavailable: {str(e)}"}

        if response and hasattr(response, 'text'):
            return {"success": True, "summary": response.text.strip()}
        else:
            return {"success": True, "summary": None, "note": "Failed to generate summary content."}
    except Exception as e:
        return {"success": True, "summary": None, "note": f"AI error: {str(e)}"}


@app.post("/api/stock/summarize/stream")
def summarize_with_ai_stream(req: SummarizeRequest):
    """
    Streams a 3-sentence AI summary of the stock analysis using Gemini.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        def err_generator():
            yield "Set GEMINI_API_KEY in .env to enable AI summaries."
        return StreamingResponse(err_generator(), media_type="text/plain")

    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)

        d = req.analysis_data
        verdict = d.get("verdict", {})
        fin = d.get("fundamentals", {})
        price = d.get("price", {})
        piotroski = d.get("piotroski", {})
        tech = d.get("technicals", {})

        prompt = f"""Write exactly 3 sentences summarizing this Indian stock for a retail investor.
Be specific, use the numbers, keep plain language. No jargon.

Stock: {d.get('company_name')} ({req.ticker})
Overall verdict: {verdict.get('overall')}
P/E: {fin.get('pe')} | ROE: {fin.get('roe')}% | D/E: {fin.get('debt_to_equity')}
Revenue growth: {fin.get('revenue_growth_yoy_pct')}% | Profit growth: {fin.get('profit_growth_yoy_pct')}%
1Y price change: {price.get('change_1y_pct')}%
Piotroski F-Score: {piotroski.get('score')}/9
Technical score: {tech.get('technical_score')}/100
Positives: {', '.join(verdict.get('flags', [])[:3])}
Warnings: {', '.join(verdict.get('warnings', [])[:3])}

3 sentences only. End with what type of investor this suits."""

        def token_generator():
            try:
                model = genai.GenerativeModel("gemini-1.5-flash")
                response = model.generate_content(prompt, stream=True)
                for chunk in response:
                    if chunk.text:
                        yield chunk.text
            except Exception as e:
                try:
                    model = genai.GenerativeModel("gemini-pro")
                    response = model.generate_content(prompt, stream=True)
                    for chunk in response:
                        if chunk.text:
                            yield chunk.text
                except Exception as e2:
                    yield f"AI summary generation failed: {str(e2)}"

        return StreamingResponse(token_generator(), media_type="text/plain")
    except Exception as e:
        def fail_generator():
            yield f"AI error: {str(e)}"
        return StreamingResponse(fail_generator(), media_type="text/plain")