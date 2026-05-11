"""Flask web entry point for the anchored VWAP stock screener."""

from __future__ import annotations

import logging
import os

from flask import Flask, jsonify, render_template, request

from scan_runner import STATE, execute_scan, start_scheduled_scans

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)


@app.get("/")
def index():
    """Render the single-page stock screener dashboard."""
    return render_template("index.html")


@app.get("/scan/status")
def scan_status():
    """Return current scheduler and latest stored scan status."""
    return jsonify(STATE.snapshot())


@app.post("/scan")
def scan():
    """Run the screener and return JSON results."""
    payload = request.get_json(silent=True) or {}
    threshold = float(payload.get("threshold", 0.1))
    max_workers = int(payload.get("max_workers", os.getenv("SCAN_WORKERS", "4")))
    return jsonify(execute_scan(threshold=threshold, max_workers=max_workers))


if __name__ == "__main__":
    if os.getenv("AUTO_SCAN_ENABLED", "true").lower() in {"1", "true", "yes", "on"}:
        start_scheduled_scans()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True, use_reloader=False)
