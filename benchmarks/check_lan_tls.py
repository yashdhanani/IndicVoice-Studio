"""Automated local TLS / ticket / WSS checks for the phone-LAN path (V2 Phase D).

Starts a task-owned ``src.call_server --tls`` on a free localhost port with a
random throwaway token (never the real .env token), then verifies over real
HTTPS/WSS sockets: health, self-signed certificate properties, fail-closed
auth (4401), ticket issuance/rejection/single-use, legacy token auth, and the
fail-closed non-localhost bind. Tears the server down afterwards.

This is NOT a phone test. Physical device scenarios stay NOT TESTED in
docs/INDICVOICE_PHONE_LAN_TEST.md. No token or ticket value is written to the
report.

Usage:
    .venv313/Scripts/python.exe benchmarks/check_lan_tls.py
    .venv313/Scripts/python.exe benchmarks/check_lan_tls.py --port 8444 \
        --out benchmarks/results/realworld_v2/lan_tls_check_v2.json

Exit codes: 0 = all checks pass, 1 = a check failed, 2 = setup error
(port occupied, server did not start).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parent.parent


def port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def inspect_cert(cert_path: Path) -> dict:
    """Public certificate properties only — never reads the private key."""
    from cryptography import x509

    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
    issuer_cn = cert.issuer.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        sans = san.get_values_for_type(x509.DNSName) + [
            str(ip) for ip in san.get_values_for_type(x509.IPAddress)]
    except x509.ExtensionNotFound:
        sans = []
    expires = cert.not_valid_after_utc
    return {
        "subject_cn": cn[0].value if cn else None,
        "issuer_cn": issuer_cn[0].value if issuer_cn else None,
        "self_signed": cert.subject == cert.issuer,
        "sans": sans,
        "not_valid_after": expires.isoformat(),
        "days_remaining": (expires - datetime.now(timezone.utc)).days,
    }


def kill_tree(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                       capture_output=True)
    else:
        try:
            os.kill(pid, 15)
        except ProcessLookupError:
            pass


async def _expect_close(session, base: str, path: str, code: int) -> tuple[bool, str]:
    try:
        async with session.ws_connect(base + path, ssl=False) as ws:
            msg = await asyncio.wait_for(ws.receive(), timeout=10)
            if msg.type == aiohttp.WSMsgType.CLOSE and msg.data == code:
                return True, f"closed with {code} as required"
            return False, f"expected close {code}, got {msg.type}:{msg.data}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


async def _expect_open(session, base: str, path: str) -> tuple[bool, str]:
    """/ws/voice sends no greeting event: admission = socket stays open."""
    try:
        async with session.ws_connect(base + path, ssl=False) as ws:
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=2)
            except asyncio.TimeoutError:
                return True, "WSS opened and stayed open (no rejection close)"
            if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.ERROR):
                return False, f"rejected: {msg.type}:{msg.data}"
            return True, f"WSS opened; first frame {msg.type}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


async def run_checks(port: int, python_exe: str, log_dir: Path) -> dict:
    checks: list[dict] = []

    def record(cid, name, ok, detail):
        checks.append({"id": cid, "name": name,
                       "status": "PASS" if ok else "FAIL", "detail": detail})

    token = secrets.token_urlsafe(16)  # throwaway; never written to the report
    env = dict(os.environ, INDICVOICE_TOKEN=token, PYTHONIOENCODING="utf-8")
    log_dir.mkdir(parents=True, exist_ok=True)
    server_log = log_dir / "lan_tls_server.log"
    base = f"https://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [python_exe, "-m", "src.call_server", "--host", "127.0.0.1",
         "--port", str(port), "--tls"],
        cwd=ROOT, env=env, stdout=server_log.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT)
    cert_info = None
    try:
        connector = aiohttp.TCPConnector(ssl=False)  # self-signed, local test only
        async with aiohttp.ClientSession(connector=connector) as session:
            health = None
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    record("L1", "HTTPS health endpoint", False,
                           f"server exited early (code {proc.returncode}); see {server_log}")
                    return _report(port, checks, cert_info)
                try:
                    async with session.get(base + "/health",
                                           timeout=aiohttp.ClientTimeout(total=3)) as r:
                        health = await r.json()
                    break
                except Exception:
                    await asyncio.sleep(1)
            if health is None:
                record("L1", "HTTPS health endpoint", False, "no response within 90 s")
                return _report(port, checks, cert_info)
            record("L1", "HTTPS health endpoint",
                   health.get("ok") is True and health.get("auth") == "token",
                   f"ok={health.get('ok')} auth={health.get('auth')} (token mode enforced)")

            cert_path = ROOT / "certs" / "indicvoice-cert.pem"
            try:
                cert_info = inspect_cert(cert_path)
                ok = (cert_info["self_signed"]
                      and "127.0.0.1" in cert_info["sans"]
                      and cert_info["days_remaining"] > 0)
                record("L2", "Self-signed certificate properties", ok,
                       f"CN={cert_info['subject_cn']}, SANs={cert_info['sans']}, "
                       f"expires {cert_info['not_valid_after']}")
            except Exception as exc:
                record("L2", "Self-signed certificate properties", False, str(exc))

            ok, detail = await _expect_close(session, base, "/ws/voice?lang=hi", 4401)
            record("L3", "WSS without credentials rejected (fail-closed)", ok, detail)

            ticket = None
            try:
                async with session.post(
                        base + "/auth/ticket",
                        headers={"Authorization": f"Bearer {token}"}) as r:
                    body = await r.json()
                    good = r.status == 200 and bool(body.get("ticket"))
                    ticket = body.get("ticket")
                async with session.post(
                        base + "/auth/ticket",
                        headers={"Authorization": "Bearer wrong-token"}) as r:
                    bad_status = r.status
                async with session.post(base + "/auth/ticket") as r:
                    no_status = r.status
                record("L4", "Ticket issuance via Authorization header",
                       good and bad_status == 401 and no_status == 401,
                       f"valid bearer→200, wrong bearer→{bad_status}, no header→{no_status}")
            except Exception as exc:
                record("L4", "Ticket issuance via Authorization header", False, str(exc))

            if ticket:
                ok, detail = await _expect_open(
                    session, base, f"/ws/voice?lang=hi&ticket={ticket}")
                record("L5", "WSS with one-time ticket admitted", ok, detail)
                ok, detail = await _expect_close(
                    session, base, f"/ws/voice?lang=hi&ticket={ticket}", 4401)
                record("L6", "Ticket is single-use (replay rejected)", ok, detail)
            else:
                record("L5", "WSS with one-time ticket admitted", False, "no ticket issued")
                record("L6", "Ticket is single-use (replay rejected)", False, "no ticket issued")

            ok, detail = await _expect_open(
                session, base, f"/ws/voice?lang=hi&token={token}")
            record("L7", "WSS with legacy ?token= admitted", ok, detail)

            try:
                async with session.get(f"http://127.0.0.1:{port}/health",
                                       timeout=aiohttp.ClientTimeout(total=5)) as r:
                    await r.read()
                record("L8", "Plain HTTP rejected on TLS port", False,
                       "HTTP request unexpectedly succeeded")
            except Exception as exc:
                record("L8", "Plain HTTP rejected on TLS port", True,
                       f"failed as expected ({type(exc).__name__})")
    finally:
        kill_tree(proc.pid)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pass

    # L9: fail-closed bind — separate short-lived process, refuses before listening
    bind_log = log_dir / "lan_tls_bind_refusal.log"
    bind_env = dict(os.environ, INDICVOICE_TOKEN="", PYTHONIOENCODING="utf-8")
    bind_proc = subprocess.Popen(
        [python_exe, "-m", "src.call_server", "--host", "0.0.0.0",
         "--port", str(port)],
        cwd=ROOT, env=bind_env, stdout=bind_log.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT)
    try:
        try:
            rc = bind_proc.wait(timeout=90)
        except subprocess.TimeoutExpired:
            kill_tree(bind_proc.pid)
            rc = None
        text = bind_log.read_text(encoding="utf-8", errors="replace")
        record("L9", "Non-localhost bind without token refuses startup",
               rc not in (None, 0) and "refusing to listen" in text,
               f"exit={rc}, refusal message present={'refusing to listen' in text}")
    finally:
        if bind_proc.poll() is None:
            kill_tree(bind_proc.pid)

    return _report(port, checks, cert_info)


def _report(port: int, checks: list[dict], cert_info: dict | None) -> dict:
    return {
        "program": "indicvoice_lan_tls_check_v2",
        "contract": ("Automated localhost TLS/auth checks only. Physical phone "
                     "scenarios are NOT TESTED (docs/INDICVOICE_PHONE_LAN_TEST.md). "
                     "A random throwaway token was used; no real credential "
                     "appears in this report."),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "port": port,
        "certificate": cert_info,
        "checks": checks,
        "all_pass": bool(checks) and all(c["status"] == "PASS" for c in checks),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8444)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--out", default=str(
        ROOT / "benchmarks" / "results" / "realworld_v2" / "lan_tls_check_v2.json"))
    args = parser.parse_args(argv)

    if not port_free(args.port):
        print(f"port {args.port} is occupied — investigate before reuse; aborting")
        return 2
    report = asyncio.run(run_checks(
        args.port, args.python,
        ROOT / "benchmarks" / "results" / "realworld_v2"))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    for c in report["checks"]:
        print(f"  {c['status']:4} {c['id']} {c['name']}: {c['detail']}")
    print(f"{'ALL PASS' if report['all_pass'] else 'FAILURES PRESENT'} → {out}")
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())