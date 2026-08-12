"""Human help-desk dashboard for Dhan Saathi escalations (Day 7).

This is the "somewhere real" a request lands and the page a human uses to see it.
It is a tiny, dependency-free web page (Python's stdlib ``http.server`` only)
that reads the same ``escalations.db`` the agent writes to, shows open requests
newest-first with an urgency badge, and lets a team member move a request to
in-progress or resolved.

Run it in a second terminal while the agent runs:

    uv run python src/dashboard.py            # then open http://localhost:8770

Filter by status with the tabs at the top, or directly:
    http://localhost:8770/?status=open

It shows ONLY the short redacted summary the agent stored — never a transcript,
never an OTP/PIN/account number (``escalation._redact`` guarantees that upstream).
Status changes are plain GET links so the whole thing works with no JavaScript
and is easy to demo on camera.
"""

import argparse
import html
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import escalation

logger = logging.getLogger("agent.dashboard")

_URGENCY_COLOR = {
    "emergency": "#b00020",
    "high": "#d35400",
    "medium": "#b8860b",
    "low": "#2e7d32",
}
_STATUS_COLOR = {
    "open": "#d35400",
    "in_progress": "#1565c0",
    "resolved": "#2e7d32",
}
_TABS = ["open", "in_progress", "resolved", "all"]


def _esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def _badge(text: str, color: str) -> str:
    return (
        f'<span style="background:{color};color:#fff;border-radius:10px;'
        f'padding:2px 10px;font-size:12px;font-weight:600;white-space:nowrap">'
        f"{_esc(text)}</span>"
    )


def _card(rec: dict) -> str:
    ref = _esc(rec["ref_id"])
    urgency = rec["urgency"]
    status = rec["status"]
    actions = []
    if status != "in_progress":
        actions.append(f'<a href="/action?ref={ref}&status=in_progress">Start</a>')
    if status != "resolved":
        actions.append(f'<a href="/action?ref={ref}&status=resolved">Resolve</a>')
    if status != "open":
        actions.append(f'<a href="/action?ref={ref}&status=open">Reopen</a>')
    action_html = " &nbsp;·&nbsp; ".join(actions)

    rows = [
        ("Reason", _esc(rec["reason_label"])),
        ("Who", _esc(rec["caller_name"] or "unknown")),
        ("What happened", _esc(rec["summary"])),
    ]
    if rec.get("checked"):
        rows.append(("Agent already checked", _esc(rec["checked"])))
    if rec.get("language"):
        rows.append(("Language", _esc(rec["language"])))
    if rec.get("follow_up"):
        rows.append(("Preferred follow-up", _esc(rec["follow_up"])))
    rows.append(("Created", _esc(rec["created_at"])))
    if rec.get("webhook_sent"):
        rows.append(("Forwarded to team channel", "yes"))
    body = "".join(
        f'<tr><td style="color:#666;padding:2px 12px 2px 0;vertical-align:top;'
        f'white-space:nowrap">{label}</td><td style="padding:2px 0">{value}</td></tr>'
        for label, value in rows
    )

    return f"""
    <div style="border:1px solid #e2e2e2;border-radius:12px;padding:16px 18px;
                margin:14px 0;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.05)">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <span style="font-family:monospace;font-weight:700;font-size:15px">{ref}</span>
        {_badge(urgency.upper(), _URGENCY_COLOR.get(urgency, "#555"))}
        {_badge(status.replace("_", " "), _STATUS_COLOR.get(status, "#555"))}
        <span style="flex:1"></span>
        <span style="font-size:13px">{action_html}</span>
      </div>
      <table style="border-collapse:collapse;font-size:14px;line-height:1.4">{body}</table>
    </div>
    """


def _page(status_filter: str) -> str:
    active = status_filter if status_filter in _TABS else "open"
    query = None if active == "all" else active
    records = escalation.list_escalations(query)

    tabs = []
    for tab in _TABS:
        label = tab.replace("_", " ").title()
        if tab == active:
            tabs.append(
                f'<span style="padding:6px 14px;border-radius:8px;background:#111;'
                f'color:#fff;font-weight:600">{label}</span>'
            )
        else:
            tabs.append(
                f'<a href="/?status={tab}" style="padding:6px 14px;border-radius:8px;'
                f'background:#eee;color:#111;text-decoration:none">{label}</a>'
            )
    tab_html = " ".join(tabs)

    if records:
        cards = "".join(_card(r) for r in records)
    else:
        cards = (
            '<p style="color:#666;margin-top:30px">No requests in this view. '
            "A normal conversation should leave this empty.</p>"
        )

    open_count = len(escalation.list_escalations("open"))
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Dhan Saathi — Human Help Desk</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>a{{color:#1565c0}}</style></head>
<body style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
             max-width:820px;margin:0 auto;padding:28px 20px;background:#f6f6f7;color:#111">
  <h1 style="margin:0 0 4px">Dhan Saathi — Human Help Desk</h1>
  <p style="color:#666;margin:0 0 18px">
    Requests the voice agent raised when it needed a real person.
    <strong>{open_count}</strong> open.
  </p>
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">{tab_html}</div>
  {cards}
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def _send_html(self, body: str, status: int = 200) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/action":
            ref = (params.get("ref") or [""])[0]
            new_status = (params.get("status") or [""])[0]
            updated = escalation.update_status(ref, new_status)
            if updated is None:
                logger.warning(
                    "Ignored bad status action ref=%r status=%r", ref, new_status
                )
            # Back to the list; land on the tab the request just moved to.
            back = new_status if new_status in _TABS else "open"
            self._redirect(f"/?status={back}")
            return

        if parsed.path in ("/", "/index.html"):
            status_filter = (params.get("status") or ["open"])[0]
            self._send_html(_page(status_filter))
            return

        self._send_html("<h1>404</h1><p><a href='/'>Back to help desk</a></p>", 404)

    def log_message(self, fmt: str, *args) -> None:
        # Route the default access log through our logger, quietly.
        logger.debug("%s - %s", self.address_string(), fmt % args)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dhan Saathi human help-desk dashboard."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    logger.info("Help desk running at http://%s:%d", args.host, args.port)
    print(f"Human help desk: http://{args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down help desk")
        server.shutdown()


if __name__ == "__main__":
    main()
