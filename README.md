# Anchored VWAP Russell 1000 Screener

A Flask dashboard that scans Russell 1000 constituents for stocks currently trading near earnings-anchored or yearly anchored VWAP levels.

## Features

- Single-page Flask UI with a **Run Scan** button, loading spinner, and ranked results table.
- Russell 1000 ticker cache in `russell1000.csv`; the app fetches constituents when the cache is empty or missing.
- yfinance OHLCV downloads, resampled to 4-hour candles when intraday data is available.
- Earnings-anchored and calendar-year anchored VWAP calculations using HLC3 and cumulative volume weighting.
- Concurrent ticker processing with `ThreadPoolExecutor`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open <http://localhost:5000> and click **Run Scan**.

## API

```bash
curl -X POST http://localhost:5000/scan \
  -H 'Content-Type: application/json' \
  -d '{"threshold": 0.1, "max_workers": 12}'
```

The response shape is:

```json
{
  "results": [
    {
      "ticker": "ABC",
      "near_earnings": true,
      "near_yearly": false,
      "min_distance_earnings": 0.04,
      "min_distance_yearly": 0.31,
      "distance_score": 0.04,
      "last_price": 123.45
    }
  ]
}
```

This project is screening-only and does not include trade execution.
