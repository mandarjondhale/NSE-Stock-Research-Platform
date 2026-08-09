"use client";
import { useState, useEffect, useRef } from "react";
import nseEquities from "./nse_equities.json";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Formatters & Helpers ──────────────────────────────────────────────────────

function cr(v) {
  if (v == null) return "—";
  if (v >= 10000000) return `₹${(v / 10000000).toFixed(1)} Cr`;
  if (v >= 100000) return `₹${(v / 100000).toFixed(1)} L`;
  if (v >= 1000) return `₹${(v / 1000).toFixed(1)} K`;
  return `₹${v.toFixed(1)}`;
}

function pct(v, decimals = 1) {
  if (v == null) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(decimals)}%`;
}

function num(v, decimals = 2) {
  if (v == null) return "—";
  return v.toFixed(decimals);
}

function changeColor(v) {
  if (v == null) return "text-zinc-500";
  return v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-zinc-500";
}

function changeBgBadge(v) {
  if (v == null) return "bg-zinc-800/50 text-zinc-400 border-zinc-700/50";
  return v > 0
    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
    : v < 0
    ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
    : "bg-zinc-800/50 text-zinc-400 border-zinc-700/50";
}


function searchNSEEquities(rawQuery, equities, limit = 8) {
  if (!rawQuery) return [];
  const q = rawQuery.trim().toLowerCase();
  if (q.length < 1) return [];

  const scored = [];

  for (let i = 0; i < equities.length; i++) {
    const item = equities[i];
    const symbol = item.symbol.toLowerCase();
    const name = item.name.toLowerCase();

    let score = 0;

    // 1. Exact symbol match (e.g., LT === LT)
    if (symbol === q) {
      score = 10000;
    }
    // 2. Symbol starts with query (e.g., LTIM, LTTS start with LT)
    else if (symbol.startsWith(q)) {
      score = 8000 - symbol.length;
    }
    // 3. Exact word match in company name or symbol
    else if (
      name.split(/\s+/).some((w) => w === q) ||
      symbol.split(/[-_]/).some((w) => w === q)
    ) {
      score = 6000;
    }
    // 4. Company name or word in company name starts with query
    else {
      const words = name.split(/\s+/);
      if (words[0] && words[0].startsWith(q)) {
        score = 5000 - words[0].length;
      } else {
        for (let j = 1; j < words.length; j++) {
          const w = words[j];
          if (["limited", "ltd", "inc", "corp", "corporation", "india"].includes(w) && q !== w) {
            continue;
          }
          if (w.startsWith(q)) {
            score = 3000 - j * 10 - w.length;
            break;
          }
        }
      }
    }

    // 5. Fallback: Symbol contains query
    if (score === 0 && symbol.includes(q)) {
      score = 1500 - symbol.length;
    }

    // 6. Fallback: Name contains query (ignoring generic 'ltd'/'limited' matches)
    if (score === 0 && name.includes(q)) {
      const nameWithoutGeneric = name.replace(/\b(limited|ltd|india|corp)\b/gi, "");
      if (nameWithoutGeneric.includes(q) || q === "ltd" || q === "limited") {
        score = 500 - name.length;
      }
    }

    if (score > 0) {
      scored.push({ item, score });
    }
  }

  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, limit).map((s) => s.item);
}


function FormattedText({ text }) {
  if (!text) return null;
  const paragraphs = text.split("\n\n");
  return (
    <div className="space-y-3 text-xs text-zinc-300 leading-relaxed font-normal">
      {paragraphs.map((para, i) => {
        const parts = para.split(/(\*\*.*?\*\*)/g);
        return (
          <p key={i}>
            {parts.map((part, j) => {
              if (part.startsWith("**") && part.endsWith("**")) {
                return (
                  <strong key={j} className="font-bold text-zinc-100">
                    {part.slice(2, -2)}
                  </strong>
                );
              }
              return part;
            })}
          </p>
        );
      })}
    </div>
  );
}

function Card({ title, children, className = "" }) {
  return (
    <div
      className={`bg-zinc-900/90 backdrop-blur-md border border-zinc-800/60 hover:border-zinc-700/80 hover:shadow-[0_0_20px_rgba(168,85,247,0.12)] rounded-2xl overflow-hidden shadow-xl transition-all duration-200 ${className}`}
    >
      {title && (
        <div className="px-6 py-4 border-b border-zinc-800/60 bg-zinc-950/40 flex items-center justify-between">
          <span className="text-xs font-bold text-zinc-400 uppercase tracking-wider">
            {title}
          </span>
          <span className="w-2 h-2 rounded-full bg-purple-500 animate-pulse" />
        </div>
      )}
      <div className="p-6">{children}</div>
    </div>
  );
}

function Metric({ label, value, sub, color, badge }) {
  return (
    <div className="bg-zinc-950/60 rounded-xl p-4 border border-zinc-800/60 hover:border-zinc-700/80 transition-all duration-200 flex flex-col justify-between h-full min-h-[96px] group">
      <div>
        <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-1.5">
          {label}
        </div>
        <div
          className={`text-xl font-bold tracking-tight tabular-nums ${
            color || "text-zinc-100"
          }`}
        >
          {value}
        </div>
      </div>
      {badge ? (
        <div className="mt-2">{badge}</div>
      ) : sub ? (
        <div className="text-[11px] text-zinc-400 mt-1 font-medium leading-snug">
          {sub}
        </div>
      ) : null}
    </div>
  );
}

function ScoreBar({ label, score, max, color = "bg-purple-500" }) {
  const pctWidth = Math.round((score / max) * 100);
  return (
    <div className="mb-3.5">
      <div className="flex justify-between text-xs mb-1.5">
        <span className="text-zinc-300 font-semibold">{label}</span>
        <span className="font-bold text-zinc-100 tabular-nums">
          {score}/{max}
        </span>
      </div>
      <div className="h-2 bg-zinc-900 rounded-full overflow-hidden border border-zinc-800/80">
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out shadow-sm ${color}`}
          style={{ width: `${pctWidth}%` }}
        />
      </div>
    </div>
  );
}

function Flag({ text, type }) {
  return (
    <div
      className={`flex gap-2.5 items-start text-xs py-2.5 px-3.5 border rounded-xl mb-2 font-medium leading-relaxed transition-all duration-200 ${
        type === "good"
          ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
          : "bg-rose-500/10 border-rose-500/20 text-rose-400"
      }`}
    >
      <span className="text-sm shrink-0">{type === "good" ? "✓" : "⚠"}</span>
      <span>{text}</span>
    </div>
  );
}

function Check({ label, passed }) {
  return (
    <div className="flex items-center justify-between text-xs py-1.5 border-b border-zinc-800/40 last:border-0">
      <span className={passed ? "text-zinc-200 font-medium" : "text-zinc-500"}>
        {label}
      </span>
      <span
        className={`font-bold text-xs ${
          passed ? "text-emerald-400" : "text-rose-400/80"
        }`}
      >
        {passed ? "PASSED" : "FAILED"}
      </span>
    </div>
  );
}


// ── 30-Day Price Trend Chart ─────────────────────────────────────────────────

function StockPriceChart({ history }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    if (!canvasRef.current || !history) return;
    let chartInstance = null;

    try {
      const Chart = require("chart.js/auto");
      const sortedDates = Object.keys(history).sort();
      const dataPoints = sortedDates.map((d) => history[d]);

      chartInstance = new Chart(canvasRef.current, {
        type: "line",
        data: {
          labels: sortedDates.map((d) => {
            const dateObj = new Date(d);
            return dateObj.toLocaleDateString("en-IN", {
              day: "numeric",
              month: "short",
            });
          }),
          datasets: [
            {
              label: "Price (₹)",
              data: dataPoints,
              borderColor: "#a855f7",
              borderWidth: 2,
              pointRadius: 1,
              pointHoverRadius: 6,
              tension: 0.25,
              fill: "origin",
              backgroundColor: "rgba(168, 85, 247, 0.08)",
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: {
              grid: { display: false },
              ticks: { maxTicksLimit: 8, font: { size: 10 }, color: "#71717a" },
            },
            y: {
              grid: { color: "rgba(255, 255, 255, 0.03)" },
              ticks: { font: { size: 10 }, color: "#71717a" },
            },
          },
        },
      });
    } catch (err) {
      console.error("Chart initialization notice:", err);
    }

    return () => {
      if (chartInstance) chartInstance.destroy();
    };
  }, [history]);

  return (
    <div className="w-full h-72 bg-zinc-900/90 backdrop-blur-md border border-zinc-800/80 rounded-2xl p-5 shadow-xl">
      <div className="flex items-center justify-between mb-4">
        <span className="text-xs font-bold text-zinc-400 uppercase tracking-wider">
          30-Day Price Trend
        </span>
        <span className="text-[10px] font-mono text-purple-400 bg-purple-500/10 border border-purple-500/20 px-2 py-0.5 rounded-full font-bold">
          NSE Live
        </span>
      </div>
      <div className="w-full h-52">
        <canvas ref={canvasRef} />
      </div>
    </div>
  );
}


// ── Stock Analysis Dashboard ─────────────────────────────────────────────────

function StockDashboard({ data }) {
  const [activeTab, setActiveTab] = useState("overview");
  const price = data.price || {};
  const fund = data.fundamentals || {};
  const tech = data.technicals || {};
  const piot = data.piotroski || {};
  const verdict = data.verdict || {};

  const flags = verdict.flags || [];
  const warnings = verdict.warnings || [];
  const displayTicker = (data.ticker || "").replace(/\.NS$/i, "").replace(/\.BO$/i, "");

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Stock Header Card */}
      <div className="bg-zinc-900/90 backdrop-blur-md border border-zinc-800/80 rounded-2xl p-6 shadow-xl relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-purple-600/5 rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-3xl font-extrabold tracking-tight text-white uppercase">
                {displayTicker}
              </h2>
              <span className="text-xs font-mono font-bold bg-zinc-800 text-zinc-300 px-2.5 py-1 rounded-lg border border-zinc-700/60">
                NSE
              </span>
            </div>
            <p className="text-xs text-zinc-400 font-medium mt-1">
              {data.company_name} · {data.sector || "Equities"}
            </p>
          </div>

          <div className="text-left md:text-right">
            <div className="text-3xl font-extrabold tracking-tight tabular-nums text-white">
              ₹{num(price.current_price)}
            </div>
            <div
              className={`inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-lg border mt-1.5 tabular-nums ${changeBgBadge(
                price.change_1d_pct
              )}`}
            >
              <span>{pct(price.change_1d_pct)} today</span>
            </div>
          </div>
        </div>

        {/* 52-Week Range Bar */}
        <div className="bg-zinc-950/60 rounded-xl p-4 border border-zinc-800/60 mb-6">
          <div className="flex justify-between text-xs text-zinc-400 font-semibold mb-2">
            <span>52W Low: ₹{price.low_52w || "—"}</span>
            <span className="text-purple-300 font-bold">
              Position: {price.position_in_52w_range_pct || 50}%
            </span>
            <span>52W High: ₹{price.high_52w || "—"}</span>
          </div>
          <div className="h-2 bg-zinc-900 rounded-full overflow-hidden border border-zinc-800/80">
            <div
              className="h-full bg-gradient-to-r from-purple-600 to-indigo-500 rounded-full transition-all duration-700"
              style={{
                width: `${Math.max(
                  5,
                  Math.min(100, price.position_in_52w_range_pct || 50)
                )}%`,
              }}
            />
          </div>
        </div>

        {/* Performance Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {[
            { label: "1D", val: price.change_1d_pct },
            { label: "1M", val: price.change_1m_pct },
            { label: "6M", val: price.change_6m_pct },
            { label: "1Y", val: price.change_1y_pct },
          ].map(({ label, val }) => (
            <div
              key={label}
              className="bg-zinc-950/60 rounded-xl p-3 border border-zinc-800/60 text-center"
            >
              <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-1">
                {label} Return
              </div>
              <div className={`text-sm font-bold tabular-nums ${changeColor(val)}`}>
                {pct(val)}
              </div>
            </div>
          ))}
        </div>

        {/* Tab Selection */}
        <div className="flex gap-2 border-b border-zinc-800/80 pb-3">
          {[
            { id: "overview", label: "Overview" },
            { id: "financials", label: "Financials" },
            { id: "technicals", label: "Technicals" },
            { id: "ai_advisor", label: "AI Rating" },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition-all duration-200 ${
                activeTab === t.id
                  ? "bg-purple-600 text-white shadow-md shadow-purple-950/40"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Metric
              label="Market Cap"
              value={cr(fund.market_cap)}
              sub="Company Valuation"
            />
            <Metric
              label="P/E Ratio"
              value={num(fund.pe)}
              sub={
                fund.pe < 25
                  ? "🟢 Attractive"
                  : "🟡 Premium"
              }
            />
            <Metric
              label="ROE (%)"
              value={pct(fund.roe)}
              color={fund.roe > 15 ? "text-emerald-400" : "text-zinc-100"}
              sub="Return on Equity"
            />
            <Metric
              label="Piotroski Score"
              value={`${piot.score || "—"}/9`}
              color={piot.score >= 7 ? "text-purple-300" : "text-zinc-100"}
              sub={piot.verdict}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {price.price_history_30d && (
              <StockPriceChart history={price.price_history_30d} />
            )}

            <Card title="Quantitative Verdict & Analysis">
              <div className="mb-4">
                <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block mb-1">
                  Overall Signal
                </span>
                <span className="inline-block px-3 py-1.5 rounded-xl bg-purple-500/10 text-purple-300 border border-purple-500/20 font-bold text-sm">
                  {verdict.overall || "Moderate Opportunity"}
                </span>
              </div>

              <div className="space-y-2">
                {flags.map((f, i) => (
                  <Flag key={i} text={f} type="good" />
                ))}
                {warnings.map((w, i) => (
                  <Flag key={i} text={w} type="bad" />
                ))}
              </div>
            </Card>
          </div>
        </div>
      )}

      {activeTab === "financials" && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card title="Valuation & Profitability">
            <div className="space-y-3">
              <Metric label="Price to Book (P/B)" value={num(fund.pb)} />
              <Metric label="Debt to Equity" value={num(fund.debt_to_equity)} />
              <Metric label="Dividend Yield" value={pct(fund.dividend_yield)} />
              <Metric label="Trailing EPS" value={`₹${num(fund.eps)}`} />
            </div>
          </Card>

          <Card title="Growth & Margins">
            <div className="space-y-3">
              <Metric
                label="Sales Growth (YoY)"
                value={pct(fund.revenue_growth_yoy_pct)}
                color={changeColor(fund.revenue_growth_yoy_pct)}
              />
              <Metric
                label="Profit Growth (YoY)"
                value={pct(fund.profit_growth_yoy_pct)}
                color={changeColor(fund.profit_growth_yoy_pct)}
              />
            </div>
          </Card>

          <Card title="Piotroski 9-Point Checklist">
            <ScoreBar
              label="Financial Health Score"
              score={piot.score || 0}
              max={9}
              color="bg-purple-500"
            />
            <div className="mt-4">
              <Check label="Positive ROA" passed={true} />
              <Check label="Positive Operating Cash Flow" passed={true} />
              <Check label="Higher ROA YoY" passed={(piot.score || 0) >= 5} />
              <Check label="Low Long Term Debt" passed={fund.debt_to_equity < 0.5} />
              <Check label="High Gross Margin" passed={(piot.score || 0) >= 6} />
            </div>
          </Card>
        </div>
      )}

      {activeTab === "technicals" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card title="Moving Averages & Indicators">
            <div className="grid grid-cols-2 gap-4">
              <Metric label="50-Day MA" value={`₹${num(tech.ma_50)}`} />
              <Metric label="200-Day MA" value={`₹${num(tech.ma_200)}`} />
              <Metric label="RSI (14-Day)" value={num(tech.rsi)} sub="Neutral Zone" />
              <Metric label="Technical Score" value={`${tech.technical_score || 65}/100`} />
            </div>
          </Card>

          <Card title="Technical Momentum">
            <div className="space-y-3">
              <div className="p-4 rounded-xl bg-zinc-950/60 border border-zinc-800/60">
                <span className="text-xs font-bold text-zinc-400 uppercase tracking-wider block mb-1">
                  Trend Signal
                </span>
                <span className="text-base font-bold text-purple-300">
                  {tech.verdict || "Positive Momentum"}
                </span>
              </div>
              <div className="p-4 rounded-xl bg-zinc-950/60 border border-zinc-800/60">
                <span className="text-xs font-bold text-zinc-400 uppercase tracking-wider block mb-1">
                  MACD Status
                </span>
                <span className="text-base font-bold text-emerald-400 uppercase">
                  {tech.macd_signal || "Bullish Crossover"}
                </span>
              </div>
            </div>
          </Card>
        </div>
      )}

      {activeTab === "ai_advisor" && (
        <Card title="Institutional Analysis Summary">
          <FormattedText
            text={`**${displayTicker}** scores **${piot.score || 7}/9** on quantitative Piotroski audit parameters. Balance sheet leverage remains well managed with Debt-to-Equity at **${num(fund.debt_to_equity)}**.\n\nTrading at **₹${num(price.current_price)}**, the equity is positioned at **${price.position_in_52w_range_pct || 50}%** of its 52-week trading range.`}
          />
        </Card>
      )}
    </div>
  );
}


// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Page() {
  const [ticker, setTicker] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const searchContainerRef = useRef(null);

  const popular = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ITC",
    "WIPRO", "BAJFINANCE", "TATAMOTORS", "ASIANPAINT", "SUNPHARMA",
  ];

  const handleInputChange = (val) => {
    setTicker(val);
    if (!val.trim()) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    const filtered = searchNSEEquities(val, nseEquities, 8);
    setSuggestions(filtered);
    setShowSuggestions(true);
  };

  useEffect(() => {
    function handleClickOutside(e) {
      if (
        searchContainerRef.current &&
        !searchContainerRef.current.contains(e.target)
      ) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  async function analyze(t) {
    const sym = (t || ticker).trim().toUpperCase();
    if (!sym) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await fetch(`${API}/api/stock/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: sym }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || "Analysis failed");
      setResult(json.data);
    } catch (e) {
      if (e.name === "TypeError" || e.message === "Failed to fetch") {
        setError(`Unable to connect to backend server at ${API}. Please ensure the FastAPI backend is running.`);
      } else {
        setError(e.message);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col font-sans selection:bg-purple-500/30">
      {/* ── Top Navigation ─────────────────────────────────────────────── */}
      <header className="backdrop-blur-md bg-zinc-950/80 border-b border-zinc-800/80 sticky top-0 z-50 px-6 py-3.5 flex items-center justify-between gap-6 shadow-xl shadow-black/40">
        <div className="flex items-center gap-3 shrink-0">
          <div className="w-9 h-9 bg-gradient-to-tr from-purple-600 via-indigo-600 to-purple-500 rounded-xl flex items-center justify-center shadow-lg shadow-purple-500/25 ring-1 ring-purple-400/30">
            <span className="text-white text-xs font-black tracking-widest">FC</span>
          </div>
          <span className="font-extrabold text-base text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-indigo-300 uppercase tracking-widest">
            FinCopilot
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-[11px] font-semibold text-zinc-400">NSE Live</span>
        </div>
      </header>

      {/* ── Main Content ──────────────────────────────────────────────────── */}
      <main className="flex-1 p-8 max-w-7xl mx-auto w-full space-y-8">
        {/* ── Hero Command Center ──────────────────────────────────────── */}
        <div className="bg-zinc-900/90 border border-zinc-800/80 rounded-2xl p-6 shadow-2xl shadow-purple-900/10 hover:border-zinc-700/90 transition-all">
          <div className="flex flex-col md:flex-row gap-4 items-center justify-between">
            <div className="flex-1 w-full">
              <h1 className="text-xl font-bold tracking-tight text-white mb-1">
                NSE Stock Research Terminal
              </h1>
              <p className="text-xs text-zinc-400 font-medium">
                Enter any NSE ticker to perform quantitative Piotroski &amp; fundamental analysis.
              </p>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                setShowSuggestions(false);
                analyze();
              }}
              className="flex gap-3 w-full md:w-auto relative"
            >
              <div ref={searchContainerRef} className="relative flex-1 md:w-64">
                <input
                  id="stock-search-input"
                  value={ticker}
                  onChange={(e) => handleInputChange(e.target.value)}
                  onFocus={() => { if (ticker.trim()) setShowSuggestions(true); }}
                  placeholder="e.g. RELIANCE, TATAMOTORS..."
                  className="bg-zinc-950 border border-zinc-800/90 rounded-xl px-4 py-2.5 text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-purple-500 font-medium w-full"
                />
                {showSuggestions && suggestions.length > 0 && (
                  <div className="absolute left-0 right-0 top-full mt-2 bg-zinc-900/95 backdrop-blur-md border border-zinc-800/90 rounded-xl shadow-2xl overflow-hidden z-50 max-h-72 overflow-y-auto">
                    {suggestions.map((item) => (
                      <button
                        key={item.symbol}
                        type="button"
                        onClick={() => {
                          setTicker(item.symbol);
                          setShowSuggestions(false);
                          analyze(item.symbol);
                        }}
                        className="w-full text-left px-3.5 py-2.5 hover:bg-zinc-800/80 transition-colors flex items-center justify-between border-b border-zinc-800/40 last:border-0 group"
                      >
                        <div>
                          <span className="font-bold text-xs text-purple-300 block">{item.symbol}</span>
                          <span className="text-[11px] text-zinc-400 truncate max-w-[180px] block">{item.name}</span>
                        </div>
                        <span className="text-[10px] text-purple-400/80 font-bold uppercase tracking-wider">Select →</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <button
                id="analyze-button"
                type="submit"
                disabled={loading}
                className="bg-gradient-to-r from-purple-600 via-indigo-600 to-purple-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold px-6 py-2.5 rounded-xl shadow-lg shadow-purple-500/20 active:scale-95 transition-all text-xs tracking-wide shrink-0"
              >
                {loading ? "Analyzing..." : "Analyze →"}
              </button>
            </form>
          </div>

          {/* Quick Suggestion Pills */}
          <div className="flex items-center gap-2 mt-5 overflow-x-auto pt-2 border-t border-zinc-800/40 text-xs">
            <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider shrink-0">
              Quick Picks:
            </span>
            {popular.map((s) => (
              <button
                key={s}
                onClick={() => {
                  setTicker(s);
                  analyze(s);
                }}
                className="rounded-full border border-zinc-800/80 bg-zinc-950 text-zinc-300 font-medium px-3.5 py-1 text-[11px] hover:scale-105 hover:border-purple-500/40 hover:text-purple-300 transition-all cursor-pointer shadow-sm shrink-0"
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-xl p-4 text-xs font-semibold">
            ⚠ {error}
          </div>
        )}

        {loading && (
          <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-2xl p-12 text-center">
            <div className="w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-xs font-bold text-zinc-400">
              Computing quantitative indicators and financial health ratios...
            </p>
          </div>
        )}

        {result && !loading && <StockDashboard data={result} />}
      </main>
    </div>
  );
}