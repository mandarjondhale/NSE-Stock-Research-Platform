<div align="center">

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=32&duration=3000&pause=99999&color=E84545&center=true&vCenter=true&repeat=false&width=620&lines=NSE+Stock+Research+Platform" alt="NSE Stock Research Platform" />

<br/><br/>

<!-- Badges -->
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-14-black?style=for-the-badge&logo=next.js&logoColor=white)
![Tailwind](https://img.shields.io/badge/Tailwind-v3-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white)
![Render](https://img.shields.io/badge/Backend-Render-46E3B7?style=for-the-badge&logo=render&logoColor=black)
![Vercel](https://img.shields.io/badge/Frontend-Vercel-000000?style=for-the-badge&logo=vercel&logoColor=white)

</div>

---

## ✨ Features

<div align="center">

| 🔍 | Feature | Description |
|:--:|---------|-------------|
| 📡 | **NSE Symbol Search** | Fuzzy search across 4,000+ active NSE equities — exact match → prefix → contains |
| 💹 | **Live Price Data** | Current price, 1D / 1M / 6M / 1Y returns, 52-week range bar, annual volatility |
| 📊 | **30-Day Price Chart** | Interactive Chart.js line chart with hover tooltips |
| 🧮 | **Fundamental Analysis** | P/E, P/B, ROE, D/E, EPS, Revenue & Profit Growth (YoY), Market Cap |
| 🏆 | **Piotroski F-Score** | All 9 criteria evaluated from real financial statements — profitability, leverage, efficiency |
| 📈 | **Technical Indicators** | Wilder RSI (14), MACD (12/26/9), 50/200-Day SMA, signal-based score /100 |
| 🤖 | **AI Summary** *(optional)* | Gemini 1.5 Flash — 3-sentence plain-language summary, streamed token-by-token |
| ⚡ | **Smart Cache** | In-memory TTL cache with IST market-hours awareness; top 10 stocks pre-warmed every 4 min |
| 🔒 | **Zero-LLM Core** | Full analysis pipeline runs with zero AI API key — Gemini is purely optional |

</div>

---

## 🛠 Tech Stack

<div align="center">

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 14 (App Router), React 18 |
| **Styling** | Tailwind CSS v3 |
| **Charts** | Chart.js v4 |
| **Backend** | FastAPI + Uvicorn (ASGI) |
| **Data Validation** | Pydantic v2 |
| **Market Data** | yFinance (Yahoo Finance) |
| **Fundamental Data** | Screener.in scraper (BeautifulSoup4) |
| **AI Summaries** | Google Gemini 1.5 Flash *(optional)* |
| **Config** | python-dotenv |
| **Frontend Deploy** | Vercel |
| **Backend Deploy** | Render |

</div>

---

## 🗂 Project Structure

```
NSE-Stock-Research-Platform/
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

## 🌐 API Endpoints

<div align="center">

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Health check + endpoint list |
| `POST` | `/api/stock/analyze` | Full analysis — price, fundamentals, technicals, Piotroski, historical |
| `GET` | `/api/stock/price/{ticker}` | Live price data only |
| `GET` | `/api/search/symbols?q=<query>` | Fuzzy NSE symbol search |
| `POST` | `/api/stock/summarize` | AI summary (requires `GEMINI_API_KEY`) |
| `POST` | `/api/stock/summarize/stream` | Streaming AI summary (SSE) |

</div>

### Example Request

```bash
curl -X POST https://fincopilot-api.onrender.com/api/stock/analyze \
  -H "Content-Type: application/json" \
  -d '{"ticker": "RELIANCE"}'
```

---

## 🖥 Dashboard Tabs

<div align="center">

| Tab | What it shows |
|-----|--------------|
| **Overview** | Market cap, P/E, ROE, Piotroski score, 30-day chart, verdict flags & warnings |
| **Financials** | P/B, D/E, dividend yield, EPS, sales & profit growth YoY, Piotroski checklist |
| **Technicals** | 50/200-Day MA, RSI, MACD signal & histogram, technical score /100 |
| **Historical** | 4-year annual snapshots — revenue, net income, gross margin, CFO, debt trends |
| **AI Rating** | 3-sentence institutional-style analysis summary |

</div>

---

## 🚀 Local Setup

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt

cp .env.example .env
# Add GEMINI_API_KEY=... if you want AI summaries (optional)

uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install

echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

npm run dev
# → http://localhost:3000
```

---

## 🔑 Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Optional | Google Gemini API key for AI summaries |

### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Yes | Backend URL (e.g. `http://localhost:8000`) |

---

## ☁️ Deployment

### Backend → Render

The `render.yaml` at the root auto-configures the Render service:

```yaml
startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
```

Set `GEMINI_API_KEY` in the Render dashboard under **Environment → Secret Files**.

### Frontend → Vercel

1. Connect the `frontend/` directory to Vercel
2. Set `NEXT_PUBLIC_API_URL` to your Render backend URL
3. Deploy — Vercel auto-detects Next.js

---

## 📦 Data Sources

<div align="center">

| Source | Data |
|--------|------|
| **Yahoo Finance** *(yFinance)* | Live price, OHLCV history, financial statements, basic fundamentals |
| **Screener.in** *(scraped)* | P/E, P/B, ROE, ROCE, Debt/Equity, FCF, OPM, Sales/Profit growth |
| **NSE India** *(`EQUITY_L.csv`)* | Full list of active NSE equities — auto-refreshed weekly |

</div>

---

<div align="center">

**Made by [Mandar Jondhale](https://github.com/mandarjondhale)**

![Visitor Badge](https://visitor-badge.laobi.icu/badge?page_id=mandarjondhale.NSE-Stock-Research-Platform)

</div>
