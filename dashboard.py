#!/usr/bin/env python3
"""
Live dashboard for autoresearch-diagrams.
Usage:  python dashboard.py [--port 8501]
Then open http://localhost:8501
Auto-refreshes every 15 seconds.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
STATE_FILE = DATA_DIR / "state.json"
RESULTS_FILE = DATA_DIR / "results.jsonl"
BEST_PROMPT_FILE = DATA_DIR / "best_prompt.txt"
PROMPT_FILE = DATA_DIR / "prompt.txt"

MAX_SCORE = 80  # 10 diagrams × 8 binary criteria each

CRITERIA = [
    "symbol_correctness", "label_clarity", "flow_direction", "no_overlap",
    "branch_completeness", "edge_crossings", "color_semantics", "node_density",
]

CRITERIA_LABELS = [
    "Symbols", "Labels", "Flow", "Overlap", "Branches", "Crossings", "Colors", "Density",
]

CRITERIA_COLORS = [
    "#34d399", "#f9a8d4", "#93c5fd", "#fcd34d", "#a78bfa", "#fb923c", "#67e8f9", "#86efac",
]


# ── Data helpers ───────────────────────────────────────────────────────────────

def read_results() -> list[dict]:
    if not RESULTS_FILE.exists():
        return []
    runs = []
    for line in RESULTS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                runs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return runs


def read_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"run_number": 0, "best_score": 0, "baseline_score": None}


def read_best_prompt() -> str:
    for f in (BEST_PROMPT_FILE, PROMPT_FILE):
        if f.exists():
            return f.read_text(encoding="utf-8").strip()
    return "No prompt yet — run autoresearch.py to start."


def avg_criterion(run: dict, key: str) -> float:
    evals = run.get("evals", [])
    if not evals:
        return 0.0
    return round(sum(e.get(key, 0) for e in evals) / len(evals), 1)


# ── HTML builder ───────────────────────────────────────────────────────────────

def build_html() -> str:
    results = read_results()
    state = read_state()
    best_prompt = read_best_prompt()

    runs_total = state.get("run_number", 0)
    runs_kept = sum(1 for r in results if r.get("kept"))
    best_score = state.get("best_score", 0)
    baseline = state.get("baseline_score") or 0
    improvement = (
        round(((best_score - baseline) / max(baseline, 1)) * 100, 1)
        if baseline else 0
    )

    # Chart data
    labels = json.dumps([str(r["run"]) for r in results])
    scores = json.dumps([r["score"] for r in results])
    colors = json.dumps([
        "rgba(74,222,128,0.85)" if r.get("kept") else "rgba(248,113,113,0.75)"
        for r in results
    ])

    # Latest run per-criterion for radar
    latest = results[-1] if results else {}
    radar_data = json.dumps([avg_criterion(latest, c) for c in CRITERIA])
    radar_labels = json.dumps(CRITERIA_LABELS)

    # Line series per criterion (last 30 runs)
    recent = results[-30:]
    crit_labels = json.dumps([str(r["run"]) for r in recent])
    criteria_series = {
        c: json.dumps([avg_criterion(r, c) for r in recent])
        for c in CRITERIA
    }

    # Run history table (most recent 20, newest first)
    table_rows = ""
    for r in reversed(results[-20:]):
        badge = (
            '<span style="color:#4ade80;font-weight:600">✓ kept</span>'
            if r.get("kept")
            else '<span style="color:#f87171">✗ disc</span>'
        )
        prompt_preview = r.get("prompt", "")[:90].replace("<", "&lt;").replace(">", "&gt;")
        table_rows += (
            f"<tr>"
            f"<td>{r['run']}</td>"
            f"<td>{r['score']}/{MAX_SCORE}</td>"
            f"<td>{badge}</td>"
            f"<td class='prompt-cell'>{prompt_preview}…</td>"
            f"</tr>"
        )
    if not table_rows:
        table_rows = "<tr><td colspan='4' style='color:#475569;text-align:center'>No runs yet</td></tr>"

    safe_prompt = best_prompt.replace("<", "&lt;").replace(">", "&gt;")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="15">
<title>Autoresearch Diagrams</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; padding: 1.5rem; }}
  h1 {{ font-size: 1.3rem; font-weight: 700; margin-bottom: 1.25rem; color: #f8fafc; letter-spacing: -0.01em; }}
  .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 1.25rem; }}
  .card {{ background: #1e293b; border-radius: 0.75rem; padding: 1rem 1.25rem; border: 1px solid #334155; }}
  .card-label {{ font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 0.3rem; }}
  .card-value {{ font-size: 1.9rem; font-weight: 700; line-height: 1; }}
  .card-sub {{ font-size: 0.9rem; color: #475569; }}
  .charts-row {{ display: grid; grid-template-columns: 3fr 2fr; gap: 1rem; margin-bottom: 1.25rem; }}
  .charts-row2 {{ display: grid; grid-template-columns: 1fr; gap: 1rem; margin-bottom: 1.25rem; }}
  .box {{ background: #1e293b; border-radius: 0.75rem; padding: 1rem 1.25rem; border: 1px solid #334155; }}
  .box-title {{ font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.75rem; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: 0.5rem 0.75rem; text-align: left; font-size: 0.82rem; border-bottom: 1px solid #1e293b; }}
  th {{ color: #64748b; font-weight: 500; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  tr:last-child td {{ border-bottom: none; }}
  .prompt-cell {{ max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #94a3b8; }}
  .prompt-box {{ background: #1e293b; border-radius: 0.75rem; padding: 1.25rem; border: 1px solid #334155; margin-bottom: 1.25rem; }}
  .prompt-box pre {{ white-space: pre-wrap; font-size: 0.85rem; color: #a5f3fc; line-height: 1.65; font-family: inherit; }}
  .footer {{ font-size: 0.7rem; color: #334155; text-align: right; }}
</style>
</head>
<body>

<h1>Autoresearch Diagrams — Live Dashboard</h1>

<div class="cards">
  <div class="card">
    <div class="card-label">Best Score</div>
    <div class="card-value" style="color:#4ade80">{best_score}<span class="card-sub"> /{MAX_SCORE}</span></div>
  </div>
  <div class="card">
    <div class="card-label">Baseline</div>
    <div class="card-value" style="color:#94a3b8">{baseline}<span class="card-sub"> /{MAX_SCORE}</span></div>
  </div>
  <div class="card">
    <div class="card-label">Improvement</div>
    <div class="card-value" style="color:#fb923c">+{improvement}<span class="card-sub">%</span></div>
  </div>
  <div class="card">
    <div class="card-label">Runs / Kept</div>
    <div class="card-value" style="color:#c084fc">{runs_total}<span class="card-sub"> / {runs_kept}</span></div>
  </div>
</div>

<div class="charts-row">
  <div class="box">
    <div class="box-title">Score per run &nbsp;<span style="color:#4ade80">■ kept</span> &nbsp;<span style="color:#f87171">■ discarded</span></div>
    <canvas id="scoreChart" height="160"></canvas>
  </div>
  <div class="box">
    <div class="box-title">Latest run — per-criterion breakdown</div>
    <canvas id="radarChart" height="160"></canvas>
  </div>
</div>

<div class="charts-row2">
  <div class="box">
    <div class="box-title">Per-criterion trend (last 30 runs)</div>
    <canvas id="criteriaChart" height="120"></canvas>
  </div>
</div>

<div class="box" style="margin-bottom:1.25rem">
  <div class="box-title">Run history (latest 20)</div>
  <table>
    <thead><tr><th>Run</th><th>Score</th><th>Result</th><th>Prompt</th></tr></thead>
    <tbody>{table_rows}</tbody>
  </table>
</div>

<div class="prompt-box">
  <div class="box-title">Current Best Prompt</div>
  <pre>{safe_prompt}</pre>
</div>

<p class="footer">Auto-refreshes every 15 s</p>

<script>
const CHART_DEFAULTS = {{
  plugins: {{ legend: {{ display: false }} }},
  animation: false,
}};

// Score bar chart
new Chart(document.getElementById('scoreChart'), {{
  type: 'bar',
  data: {{
    labels: {labels},
    datasets: [{{
      data: {scores},
      backgroundColor: {colors},
      borderRadius: 3,
    }}]
  }},
  options: {{
    ...CHART_DEFAULTS,
    scales: {{
      y: {{ min: 0, max: {MAX_SCORE}, grid: {{ color: '#1e293b' }}, ticks: {{ color: '#475569' }} }},
      x: {{ grid: {{ display: false }}, ticks: {{ color: '#475569', maxTicksLimit: 20 }} }}
    }}
  }}
}});

// Radar — latest run
new Chart(document.getElementById('radarChart'), {{
  type: 'radar',
  data: {{
    labels: {radar_labels},
    datasets: [{{
      label: 'Latest run avg',
      data: {radar_data},
      backgroundColor: 'rgba(99,102,241,0.2)',
      borderColor: 'rgba(99,102,241,0.9)',
      pointBackgroundColor: '#6366f1',
    }}]
  }},
  options: {{
    animation: false,
    scales: {{
      r: {{
        min: 0, max: 1,
        ticks: {{ display: false }},
        grid: {{ color: '#334155' }},
        pointLabels: {{ color: '#94a3b8', font: {{ size: 10 }} }}
      }}
    }},
    plugins: {{ legend: {{ labels: {{ color: '#94a3b8' }} }} }}
  }}
}});

// Criteria line chart
new Chart(document.getElementById('criteriaChart'), {{
  type: 'line',
  data: {{
    labels: {crit_labels},
    datasets: [
      {{ label: '{CRITERIA_LABELS[0]}', data: {criteria_series[CRITERIA[0]]}, borderColor: '{CRITERIA_COLORS[0]}', tension: 0.3, pointRadius: 2 }},
      {{ label: '{CRITERIA_LABELS[1]}', data: {criteria_series[CRITERIA[1]]}, borderColor: '{CRITERIA_COLORS[1]}', tension: 0.3, pointRadius: 2 }},
      {{ label: '{CRITERIA_LABELS[2]}', data: {criteria_series[CRITERIA[2]]}, borderColor: '{CRITERIA_COLORS[2]}', tension: 0.3, pointRadius: 2 }},
      {{ label: '{CRITERIA_LABELS[3]}', data: {criteria_series[CRITERIA[3]]}, borderColor: '{CRITERIA_COLORS[3]}', tension: 0.3, pointRadius: 2 }},
      {{ label: '{CRITERIA_LABELS[4]}', data: {criteria_series[CRITERIA[4]]}, borderColor: '{CRITERIA_COLORS[4]}', tension: 0.3, pointRadius: 2 }},
      {{ label: '{CRITERIA_LABELS[5]}', data: {criteria_series[CRITERIA[5]]}, borderColor: '{CRITERIA_COLORS[5]}', tension: 0.3, pointRadius: 2 }},
      {{ label: '{CRITERIA_LABELS[6]}', data: {criteria_series[CRITERIA[6]]}, borderColor: '{CRITERIA_COLORS[6]}', tension: 0.3, pointRadius: 2 }},
      {{ label: '{CRITERIA_LABELS[7]}', data: {criteria_series[CRITERIA[7]]}, borderColor: '{CRITERIA_COLORS[7]}', tension: 0.3, pointRadius: 2 }},
    ]
  }},
  options: {{
    animation: false,
    scales: {{
      y: {{ min: 0, max: 1, grid: {{ color: '#1e293b' }}, ticks: {{ color: '#475569' }} }},
      x: {{ grid: {{ display: false }}, ticks: {{ color: '#475569', maxTicksLimit: 15 }} }}
    }},
    plugins: {{ legend: {{ labels: {{ color: '#94a3b8', boxWidth: 10, font: {{ size: 10 }} }} }} }}
  }}
}});
</script>
</body>
</html>"""


# ── HTTP server ────────────────────────────────────────────────────────────────

class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        html = build_html().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, format, *args):
        pass  # suppress request logs


def main():
    parser = argparse.ArgumentParser(description="Autoresearch Diagrams -- live dashboard")
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()
    addr = ("0.0.0.0", args.port)
    server = HTTPServer(addr, DashboardHandler)
    print(f"Dashboard running -> http://localhost:{args.port}  (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
