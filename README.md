# FinCopilot — NSE Stock Research Platform

> A full-stack quantitative stock research terminal for Indian equities listed on the NSE.
> Search any stock, get live price data, fundamental ratios, Piotroski scoring, technical indicators, and an optional AI-generated summary — all in one dark-mode dashboard.

**Live Demo →** [fincopilot.vercel.app](https://fincopilot.vercel.app) &nbsp;|&nbsp; **API →** [fincopilot-api.onrender.com](https://fincopilot-api.onrender.com)

---

## Features

- **NSE Symbol Search** — Fuzzy search across all active NSE equities (4,000+ stocks), scored by relevance (exact match → prefix → contains)
- **Live Price Data** — Current price, 1D / 1M / 6M / 1Y returns, 52-week high/low range bar, annual volatility
- **30-Day Price Chart** — Interactive Chart.js line chart with candlestick-style hover
- **Fundamental Analysis** — P/E, P/B, ROE, Debt/Equity, EPS, Revenue & Profit Growth (YoY), Market Cap
- **Piotroski F-Score** — 9-point financial health checklist (profitability, leverage, operating efficiency)
- **Technical Indicators** — RSI (14-day), MACD signal, 50-Day MA, 200-Day MA, Technical Score /100
- **AI Summary** *(optional)* — Gemini 1.5 Flash generates a 3-sentence plain-language summary for retail investors; streams token-by-token via SSE
- **Cache + Pre-warm** — In-memory cache with smart market-hours awareness; top 10 stocks pre-warmed every 4 minutes
- **Zero-LLM Core** — The entire analysis pipeline runs without any AI API key; Gemini is purely optional

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 14 (App Router), React 18 |
| **Styling** | Tailwind CSS v3 |
| **Charts** | Chart.js v4 |
| **Backend** | FastAPI + Uvicorn (ASGI) |
| **Data Validation** | Pydantic v2 |
| **Market Data** | yFinance (Yahoo Finance) |
| **Fundamental Data** | Screener.in scraper (BeautifulSoup4) |
| **AI Summaries** | Google Gemini 1.5 Flash (optional) |
| **Config** | python-dotenv |
| **Frontend Deploy** | Vercel |
| **Backend Deploy** | Render |

---

## Project Structure

```
FinAgent/
├── backend/
│   ├── main.py               # FastAPI app, all API routes, startup tasks
│   ├── data_fetcher.py       # Price data, fundamentals, technicals, Piotroski
│   ├── screener_fetcher.py   # Scrapes Screener.in for P/E, ROE, growth ratios
│   ├── cache.py              # In-memory cache with TTL + market-hours logic
│   ├── nse_equities.json     # Snapshot of all active NSE symbols (~4,000)
│   ├── requirements.txt      # Python dependencies
│   └── .env.example          # Environment variable template
│
├── frontend/
│   ├── app/
│   │   ├── page.js           # Main dashboard UI (search, tabs, charts)
│   │   ├── globals.css       # Global Tailwind styles
│   │   └── nse_equities.json # Client-side symbol list for instant search
│   ├── next.config.js
│   ├── tailwind.config.js
│   └── package.json
│
└── render.yaml               # Render deployment config for backend
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Health check + endpoint list |
| `POST` | `/api/stock/analyze` | Full analysis — price, fundamentals, technicals, Piotroski |
| `GET` | `/api/stock/price/{ticker}` | Live price data only |
| `GET` | `/api/search/symbols?q=<query>` | Fuzzy NSE symbol search |
| `POST` | `/api/stock/summarize` | AI summary (requires `GEMINI_API_KEY`) |
| `POST` | `/api/stock/summarize/stream` | Streaming AI summary (SSE) |

### Example Request

```bash
curl -X POST https://fincopilot-api.onrender.com/api/stock/analyze \
  -H "Content-Type: application/json" \
  -d '{"ticker": "RELIANCE"}'
```

---

## Frontend Dashboard Tabs

| Tab | What it shows |
|-----|--------------|
| **Overview** | Market cap, P/E, ROE, Piotroski score, 30-day chart, verdict flags |
| **Financials** | P/B, D/E, dividend yield, EPS, sales & profit growth YoY, Piotroski checklist |
| **Technicals** | 50/200-Day MA, RSI, MACD signal, technical score |
| **AI Rating** | Institutional-style 3-sentence analysis summary |

---

## Local Setup

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Add GEMINI_API_KEY=... if you want AI summaries (optional)

uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install

# Set backend URL
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

npm run dev
# → http://localhost:3000
```

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Optional | Google Gemini API key for AI summaries |

### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Yes | Backend URL (e.g. `http://localhost:8000`) |

---

## Deployment

### Backend → Render

The `render.yaml` at the root auto-configures the Render service:

```yaml
startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
```

Set `GEMINI_API_KEY` manually in the Render dashboard (Environment → Secret Files).

### Frontend → Vercel

1. Connect the `frontend/` directory to Vercel
2. Set `NEXT_PUBLIC_API_URL` to your Render backend URL in Vercel Environment Variables
3. Deploy — Vercel auto-detects Next.js

---

## Data Sources

| Source | Data |
|--------|------|
| **Yahoo Finance** (via yFinance) | Live price, OHLCV history, basic fundamentals |
| **Screener.in** (scraped) | P/E, P/B, ROE, ROCE, Debt/Equity, FCF, OPM, Sales/Profit growth |
| **NSE India** (`EQUITY_L.csv`) | Full list of active NSE equities (auto-refreshed weekly) |

---

## Author

**Mandar Jondhale** — [github.com/mandarjondhale](https://github.com/mandarjondhale)
