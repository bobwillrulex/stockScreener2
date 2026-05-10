"""Flask web entry point for the anchored VWAP stock screener."""

from __future__ import annotations

import logging
import os

from flask import Flask, jsonify, render_template, request

from screener import run_scan

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)


@app.get("/")
def index():
    """Render the single-page stock screener dashboard."""
    return render_template("index.html")


@app.post("/scan")
def scan():
    """Run the screener and return JSON results."""
    payload = request.get_json(silent=True) or {}
    threshold = float(payload.get("threshold", 0.1))
    max_workers = int(payload.get("max_workers", os.getenv("SCAN_WORKERS", "4")))
    results = run_scan(threshold=threshold, max_workers=max_workers)
    return jsonify({"results": results})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
