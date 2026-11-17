"""Privacy-conscious pilot monitor for IndicVoice (Real-World Validation V2, Phase J).

Polls the server's read-only GET /metrics endpoint and prints/logs operational
gauges only: session counts, queue depths, event-loop delay, RSS, uptime. It
never requests, stores or prints transcripts, audio, or client IP addresses.
The access token is read from --token or INDICVOICE_TOKEN and is redacted from
every line of output.

This tool does NOT start a server; it observes an already-running pilot server.
Safe for localhost and authenticated LAN pilots.

Usage:
    python tools/pilot_monitor.py --port 8000 --interval 2 --duration 120
    INDICVOICE_TOKEN=... python tools/pilot_monitor.py --port 8444 --tls \
        --out pilot_metrics.jsonl --alert-loop-ms 250 --alert-rss-mb 1500
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

#: gauges collected from /metrics (counts and timings only — no content)
GAUGES = (
    "active_sessions", "client_ips", "outbound_queue_total", "outbound_queue_max",
    "asr_executor_queue", "event_loop_delay_ms", "rss_mb", "uptime_s",
)


def redact(text: str) -> str:
    """Strip token/ticket query values from any string before it is printed."""
    for key in ("token", "ticket"):
        parsed = urllib.parse.urlsplit(text)
        if not parsed.query:
            break
        pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if not any(k == key for k, _ in pairs):
            continue
        cleaned = [(k, "REDACTED" if k == key else v) for k, v in pairs]
        text = urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path,
             urllib.parse.urlencode(cleaned), parsed.fragment))
    return text


def check_alerts(m: dict, thresholds: dict) -> list[str]:
    """Return human-readable alert strings for gauges that exceed thresholds."""
    alerts = []
    loop = m.get("event_loop_delay_ms")
    if loop is not None and loop > thresholds["loop_ms"]:
        alerts.append(f"event-loop delay {loop} ms > {thresholds['loop_ms']} ms (audio may stutter)")
    qmax = m.get("outbound_queue_max")
    if qmax is not None and qmax > thresholds["queue"]:
        alerts.append(f"outbound queue max {qmax} > {thresholds['queue']} (backpressure)")
    qasr = m.get("asr_executor_queue")
    if qasr is not None and qasr > thresholds["asr_queue"]:
        alerts.append(f"ASR executor queue {qasr} > {thresholds['asr_queue']} (decode backlog)")
    rss = m.get("rss_mb")
    if rss is not None and rss > thresholds["rss_mb"]:
        alerts.append(f"server RSS {rss} MB > {thresholds['rss_mb']} MB (memory pressure)")
    sess = m.get("active_sessions")
    if sess is not None and sess > thresholds["sessions"]:
        alerts.append(f"active sessions {sess} > {thresholds['sessions']} (over pilot capacity)")
    return alerts


def format_status(m: dict) -> str:
    """One-line, secret-free status summary of a /metrics sample."""
    def g(k):
        v = m.get(k)
        return "-" if v is None else v
    return (f"sessions={g('active_sessions')} ips={g('client_ips')} "
            f"queue={g('outbound_queue_total')}/{g('outbound_queue_max')} "
            f"asr_q={g('asr_executor_queue')} loop_ms={g('event_loop_delay_ms')} "
            f"rss_mb={g('rss_mb')} up_s={g('uptime_s')}")


def peak_summary(series: list[dict]) -> dict:
    """Peak of each numeric gauge across the collected series."""
    out = {"samples": len(series)}
    for k in GAUGES:
        vals = [s[k] for s in series if isinstance(s.get(k), (int, float))]
        out["peak_" + k] = round(max(vals), 2) if vals else None
    return out


def fetch(url: str, timeout: float = 5.0, tls_insecure: bool = False):
    ctx = None
    if url.startswith("https") and tls_insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # self-signed pilot cert only
    with urllib.request.urlopen(url, timeout=timeout, context=ctx) as r:
        return json.loads(r.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--token", default=os.environ.get("INDICVOICE_TOKEN", ""))
    p.add_argument("--tls", action="store_true", help="use https (self-signed pilot cert)")
    p.add_argument("--interval", type=float, default=2.0)
    p.add_argument("--duration", type=float, default=120.0, help="seconds; 0 = until Ctrl+C")
    p.add_argument("--out", default=None, help="append JSONL time series to this path")
    p.add_argument("--alert-loop-ms", type=float, default=250.0)
    p.add_argument("--alert-queue", type=int, default=64)
    p.add_argument("--alert-asr-queue", type=int, default=8)
    p.add_argument("--alert-rss-mb", type=float, default=1500.0)
    p.add_argument("--alert-sessions", type=int, default=5)
    args = p.parse_args(argv)

    scheme = "https" if args.tls else "http"
    url = f"{scheme}://{args.host}:{args.port}/metrics"
    if args.token:
        url += "?token=" + urllib.parse.quote(args.token, safe="")
    thresholds = {"loop_ms": args.alert_loop_ms, "queue": args.alert_queue,
                  "asr_queue": args.alert_asr_queue, "rss_mb": args.alert_rss_mb,
                  "sessions": args.alert_sessions}

    print(redact(f"monitoring {url} every {args.interval}s"))
    series: list[dict] = []
    alert_count = 0
    out_fh = open(args.out, "a", encoding="utf-8") if args.out else None
    t_end = time.perf_counter() + args.duration if args.duration > 0 else None
    try:
        while t_end is None or time.perf_counter() < t_end:
            try:
                m = fetch(url, tls_insecure=args.tls)
            except Exception as exc:                      # noqa: BLE001
                print(redact(f"[warn] metrics fetch failed: {exc}"))
                time.sleep(args.interval)
                continue
            sample = {k: m.get(k) for k in GAUGES}
            sample["t"] = round(time.perf_counter(), 1)
            series.append(sample)
            if out_fh:
                out_fh.write(json.dumps(sample, ensure_ascii=False) + "\n")
                out_fh.flush()
            print(format_status(m))
            for a in check_alerts(m, thresholds):
                alert_count += 1
                print(f"[ALERT] {a}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        if out_fh:
            out_fh.close()
    summary = peak_summary(series)
    summary["alerts"] = alert_count
    print("summary: " + json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())