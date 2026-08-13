"""Call analytics dashboard for Dhan Saathi (Day 8).

A tiny, dependency-free web page (Python's stdlib ``http.server`` only) that
reads the ``call_analytics.db`` the agent writes to and shows how the agent is
doing: the three required numbers — **total, successful, and failed calls** —
plus a few cheap extras (success rate, split by channel, failure types, and a
recent-call history).

Run it in a second terminal while the agent runs:

    uv run python src/analytics_dashboard.py     # then open http://localhost:8771

The numbers come only from real browser and phone calls recorded by
``analytics.py`` — nothing here is hardcoded. The page auto-refreshes every few
seconds so a live call's outcome shows up on its own, which is handy on camera.

Privacy is built in: the underlying store keeps no caller name, phone number,
transcript, OTP, PIN, or account number, so there is nothing sensitive to show.
Each call appears only as its random room id, channel, time, duration, and a
coarse outcome. A ``/stats.json`` endpoint serves the same numbers as JSON.
"""

import argparse
import html
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import analytics

logger = logging.getLogger("agent.analytics_dashboard")

# How often the page reloads itself (seconds). Small enough to feel live on a
# demo, large enough not to hammer the SQLite file.
REFRESH_SECONDS = 5

_CHANNEL_LABEL = {"browser": "Browser", "phone": "Phone (SIP)"}
_OUTCOME_COLOR = {
    "success": "#2e7d32",
    "failed": "#b00020",
    "in_progress": "#1565c0",
}
# Human-friendly labels for the closed set of reasons, so the page never shows a
# raw enum value.
_FAILURE_LABEL = {
    "incomplete": "Ended before success",
    "no_answer": "No answer",
    "busy": "Busy",
    "declined": "Declined",
    "dial_failed": "Dial failed",
    "error": "Tool / API error",
    "unknown": "Unknown",
}
_SUCCESS_LABEL = {
    "eligibility_check": "Eligibility / documents given",
    "human_escalation": "Human help raised",
    "unknown": "Success",
}


def _esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def _fmt_duration(seconds: object) -> str:
    if seconds is None:
        return "—"
    try:
        total = round(float(seconds))
    except (TypeError, ValueError):
        return "—"
    m, s = divmod(total, 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def _fmt_time(ts: object) -> str:
    """Trim an ISO timestamp to a compact 'YYYY-MM-DD HH:MM' for the table."""
    text = str(ts or "")
    if "T" in text:
        date, _, rest = text.partition("T")
        return f"{date} {rest[:5]}"
    return text or "—"


def _metric_card(label: str, value: object, color: str, big: bool = False) -> str:
    size = "48px" if big else "34px"
    return f"""
    <div style="flex:1;min-width:150px;background:#fff;border:1px solid #e2e2e2;
                border-radius:14px;padding:20px 22px;box-shadow:0 1px 3px rgba(0,0,0,.05)">
      <div style="color:#666;font-size:13px;text-transform:uppercase;
                  letter-spacing:.04em">{_esc(label)}</div>
      <div style="font-size:{size};font-weight:700;color:{color};line-height:1.1;
                  margin-top:6px">{_esc(value)}</div>
    </div>
    """


def _bar(label: str, count: int, total: int, color: str) -> str:
    pct = round(count / total * 100) if total else 0
    return f"""
    <div style="margin:8px 0">
      <div style="display:flex;justify-content:space-between;font-size:13px;
                  color:#333;margin-bottom:3px">
        <span>{_esc(label)}</span><span>{count}</span>
      </div>
      <div style="background:#eee;border-radius:6px;height:10px;overflow:hidden">
        <div style="width:{pct}%;height:100%;background:{color}"></div>
      </div>
    </div>
    """


def _reason_panel(title: str, counts: dict, labels: dict, color: str) -> str:
    if not counts:
        return ""
    total = sum(counts.values())
    rows = "".join(
        _bar(labels.get(reason, reason), n, total, color)
        for reason, n in counts.items()
    )
    return f"""
    <div style="flex:1;min-width:240px;background:#fff;border:1px solid #e2e2e2;
                border-radius:14px;padding:18px 20px">
      <h3 style="margin:0 0 10px;font-size:15px">{_esc(title)}</h3>{rows}
    </div>
    """


def _channel_panel(by_channel: dict) -> str:
    if not by_channel:
        return ""
    rows = []
    for channel, b in sorted(by_channel.items()):
        label = _CHANNEL_LABEL.get(channel, channel.title())
        rows.append(
            f'<tr><td style="padding:4px 14px 4px 0">{_esc(label)}</td>'
            f'<td style="padding:4px 14px 4px 0;text-align:right">{b["total"]}</td>'
            f'<td style="padding:4px 14px 4px 0;text-align:right;color:#2e7d32">{b["successful"]}</td>'
            f'<td style="padding:4px 0;text-align:right;color:#b00020">{b["failed"]}</td></tr>'
        )
    return f"""
    <div style="flex:1;min-width:240px;background:#fff;border:1px solid #e2e2e2;
                border-radius:14px;padding:18px 20px">
      <h3 style="margin:0 0 10px;font-size:15px">By channel</h3>
      <table style="border-collapse:collapse;font-size:14px;width:100%">
        <tr style="color:#666;font-size:12px;text-transform:uppercase">
          <td>Channel</td><td style="text-align:right">Total</td>
          <td style="text-align:right">OK</td><td style="text-align:right">Fail</td>
        </tr>{''.join(rows)}
      </table>
    </div>
    """


def _history_table(calls: list[dict]) -> str:
    if not calls:
        return (
            '<p style="color:#666">No calls recorded yet. Make a browser or phone '
            "call to the agent and it will appear here.</p>"
        )
    head = (
        '<tr style="color:#666;font-size:12px;text-transform:uppercase;text-align:left">'
        "<th style='padding:6px 12px 6px 0'>Started</th>"
        "<th style='padding:6px 12px 6px 0'>Channel</th>"
        "<th style='padding:6px 12px 6px 0'>Duration</th>"
        "<th style='padding:6px 12px 6px 0'>Outcome</th>"
        "<th style='padding:6px 0'>Reason</th></tr>"
    )
    rows = []
    for c in calls:
        outcome = c["outcome"]
        color = _OUTCOME_COLOR.get(outcome, "#555")
        if outcome == "success":
            reason = _SUCCESS_LABEL.get(c.get("success_reason") or "", c.get("success_reason") or "")
        elif outcome == "failed":
            reason = _FAILURE_LABEL.get(c.get("failure_reason") or "", c.get("failure_reason") or "")
        else:
            reason = "live"
        badge = (
            f'<span style="background:{color};color:#fff;border-radius:10px;'
            f'padding:2px 10px;font-size:12px;font-weight:600">'
            f'{_esc(outcome.replace("_", " "))}</span>'
        )
        rows.append(
            "<tr style='border-top:1px solid #eee'>"
            f"<td style='padding:8px 12px 8px 0;white-space:nowrap'>{_esc(_fmt_time(c['started_at']))}</td>"
            f"<td style='padding:8px 12px 8px 0'>{_esc(_CHANNEL_LABEL.get(c['channel'], c['channel']))}</td>"
            f"<td style='padding:8px 12px 8px 0'>{_esc(_fmt_duration(c.get('duration_seconds')))}</td>"
            f"<td style='padding:8px 12px 8px 0'>{badge}</td>"
            f"<td style='padding:8px 0;color:#555'>{_esc(reason)}</td></tr>"
        )
    return f"""
    <div style="background:#fff;border:1px solid #e2e2e2;border-radius:14px;
                padding:18px 20px;overflow-x:auto">
      <h3 style="margin:0 0 10px;font-size:15px">Recent calls</h3>
      <table style="border-collapse:collapse;font-size:14px;width:100%">
        {head}{''.join(rows)}
      </table>
    </div>
    """


def _page() -> str:
    stats = analytics.get_stats()
    calls = analytics.recent_calls(25)

    active_note = (
        f' &nbsp;·&nbsp; <span style="color:#1565c0">{stats["active"]} live now</span>'
        if stats["active"]
        else ""
    )

    metrics = "".join(
        [
            _metric_card("Total calls", stats["total"], "#111", big=True),
            _metric_card("Successful", stats["successful"], "#2e7d32", big=True),
            _metric_card("Failed", stats["failed"], "#b00020", big=True),
            _metric_card("Success rate", f'{stats["success_rate"]}%', "#1565c0"),
        ]
    )

    panels = "".join(
        [
            _channel_panel(stats["by_channel"]),
            _reason_panel("Successes", stats["by_success"], _SUCCESS_LABEL, "#2e7d32"),
            _reason_panel("Failure types", stats["by_failure"], _FAILURE_LABEL, "#b00020"),
        ]
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Dhan Saathi — Call Analytics</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{REFRESH_SECONDS}">
</head>
<body style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
             max-width:900px;margin:0 auto;padding:28px 20px;background:#f6f6f7;color:#111">
  <h1 style="margin:0 0 4px">Dhan Saathi — Call Analytics</h1>
  <p style="color:#666;margin:0 0 6px">
    How the voice agent is performing, from real browser and phone calls.{active_note}
  </p>
  <p style="color:#999;margin:0 0 18px;font-size:12px">
    Success = the caller completed a scheme eligibility / document check, or a
    human-help request was raised. Auto-refreshes every {REFRESH_SECONDS}s. No
    caller names, numbers, or transcripts are stored or shown.
  </p>
  <div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:16px">{metrics}</div>
  <div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:16px">{panels}</div>
  {_history_table(calls)}
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def _send(self, body: str, content_type: str, status: int = 200) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/stats.json":
            self._send(
                json.dumps(analytics.get_stats(), indent=2),
                "application/json; charset=utf-8",
            )
            return
        if path in ("/", "/index.html"):
            self._send(_page(), "text/html; charset=utf-8")
            return
        self._send(
            "<h1>404</h1><p><a href='/'>Back to analytics</a></p>",
            "text/html; charset=utf-8",
            404,
        )

    def log_message(self, fmt: str, *args) -> None:
        logger.debug("%s - %s", self.address_string(), fmt % args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dhan Saathi call analytics dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8771)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    logger.info("Analytics dashboard at http://%s:%d", args.host, args.port)
    print(f"Call analytics: http://{args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down analytics dashboard")
        server.shutdown()


if __name__ == "__main__":
    main()
