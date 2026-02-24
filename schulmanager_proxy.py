#!/usr/bin/env python3
"""
Schulmanager Proxy für den Wochenplaner
========================================
Starten mit:  python schulmanager_proxy.py
Beenden mit:  Strg+C

Voraussetzung: pip install requests
"""

import json
import sys
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

try:
    import requests
except ImportError:
    print("Fehler: 'requests' ist nicht installiert.")
    print("Bitte ausführen: pip install requests")
    sys.exit(1)

PORT = 8765
LOGIN_URL  = "https://login.schulmanager-online.de/api/login"
API_URL    = "https://login.schulmanager-online.de/api/calls"

# Globaler Zustand (läuft nur im lokalen Prozess)
_token    = None
_user     = None
_student  = None


def sm_login(username: str, password: str) -> dict:
    """Meldet sich bei Schulmanager an und gibt die Antwort zurück."""
    global _token, _user, _student
    resp = requests.post(LOGIN_URL, json={
        "emailOrUsername": username,
        "password":        password,
        "mobileApp":       False,
        "institutionId":   None
    }, timeout=10)
    resp.raise_for_status()
    data    = resp.json()
    _token   = data["jwt"]
    _user    = data["user"]
    _student = data["user"].get("associatedStudent")
    return data


def week_key_to_dates(week_key: str):
    """Wandelt 'YYYY-WNN' in Montag- und Freitagsdatum um."""
    year_str, wn_str = week_key.split("-W")
    year, wn = int(year_str), int(wn_str)
    jan4   = datetime(year, 1, 4)
    monday = jan4 - timedelta(days=jan4.weekday()) + timedelta(weeks=wn - 1)
    friday = monday + timedelta(days=4)
    return monday.strftime("%Y-%m-%d"), friday.strftime("%Y-%m-%d")


_DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def fetch_stundenplan(week_key: str) -> dict:
    """Holt den Stundenplan und konvertiert ihn in das Wochenplaner-Format."""
    start, end = week_key_to_dates(week_key)
    resp = requests.post(API_URL, json={
        "bundleVersion": 1,
        "modules": [{
            "moduleName":   "schedules",
            "endpointName": "get-actual-lessons",
            "body": {
                "student":   _student,
                "startDate": start,
                "endDate":   end
            }
        }]
    }, headers={
        "Authorization": f"Bearer {_token}",
        "Content-Type":  "application/json"
    }, timeout=10)
    resp.raise_for_status()
    return _transform(resp.json())


def _transform(sm_data: dict) -> dict:
    """Konvertiert die Schulmanager-Antwort in {dayKey: {periodNum: text}}."""
    result = {}
    try:
        lessons = sm_data["results"][0]["data"]
    except (KeyError, IndexError, TypeError):
        return result

    for lesson in lessons:
        try:
            date_obj   = datetime.strptime(lesson["date"], "%Y-%m-%d")
            weekday    = date_obj.weekday()          # 0 = Mo, 4 = Fr
            if weekday > 4:
                continue                             # Wochenende überspringen
            day_key    = _DAY_KEYS[weekday]
            period_num = lesson["classHour"]["number"]
            actual     = lesson.get("actualLesson")
            if not actual:
                continue

            subj  = actual.get("subject", {}).get("abbreviation", "?")
            room  = actual.get("room",    {}).get("name", "")
            text  = subj + (f" {room}" if room else "")

            # Vertretung markieren
            orig = lesson.get("originalLesson")
            if orig:
                orig_subj = orig.get("subject", {}).get("id")
                new_subj  = actual.get("subject", {}).get("id")
                if orig_subj and orig_subj != new_subj:
                    text = f"↔ {text}"

            if day_key not in result:
                result[day_key] = {}
            result[day_key][period_num] = text
        except (KeyError, TypeError, ValueError):
            continue

    return result


def _cors(handler):
    handler.send_header("Access-Control-Allow-Origin",  "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")


class ProxyHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # Nur relevante Meldungen ausgeben
        print(f"  {self.command} {self.path}  →  {args[1]}")

    def _send(self, code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        _cors(self)
        self.end_headers()
        self.wfile.write(body)

    # ---------- OPTIONS (CORS preflight) ----------
    def do_OPTIONS(self):
        self.send_response(204)
        _cors(self)
        self.end_headers()

    # ---------- GET ----------
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/status":
            self._send(200, {
                "loggedIn": _token is not None,
                "student":  _student,
                "user": {
                    "firstname": _user.get("firstname"),
                    "lastname":  _user.get("lastname"),
                } if _user else None
            })

        elif parsed.path == "/stundenplan":
            if not _token:
                self._send(401, {"error": "Nicht angemeldet"}); return
            if not _student:
                self._send(400, {"error": "Kein Schüler-Konto verknüpft"}); return
            week = (params.get("week") or [None])[0]
            if not week:
                self._send(400, {"error": "Parameter 'week' fehlt"}); return
            try:
                data = fetch_stundenplan(week)
                self._send(200, {"ok": True, "week": week, "data": data})
            except requests.HTTPError as e:
                self._send(502, {"error": f"Schulmanager-Fehler: {e.response.status_code}"})
            except Exception as e:
                self._send(500, {"error": str(e)})

        elif parsed.path == "/shutdown":
            self._send(200, {"ok": True})
            threading.Thread(target=_shutdown_server, daemon=True).start()

        else:
            self._send(404, {"error": "Nicht gefunden"})

    # ---------- POST ----------
    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length)) if length else {}

        if parsed.path == "/login":
            username = body.get("username", "").strip()
            password = body.get("password", "")
            if not username or not password:
                self._send(400, {"error": "Benutzername und Passwort erforderlich"}); return
            try:
                data = sm_login(username, password)
                self._send(200, {
                    "ok":      True,
                    "student": _student,
                    "user": {
                        "firstname": data["user"].get("firstname"),
                        "lastname":  data["user"].get("lastname"),
                    }
                })
            except requests.HTTPError as e:
                if e.response.status_code in (401, 403):
                    self._send(401, {"error": "Benutzername oder Passwort falsch"})
                else:
                    self._send(502, {"error": f"Schulmanager-Fehler: {e.response.status_code}"})
            except Exception as e:
                self._send(500, {"error": str(e)})

        else:
            self._send(404, {"error": "Nicht gefunden"})


_server_ref = None

def _shutdown_server():
    time.sleep(0.4)  # kurz warten damit die Antwort noch gesendet wird
    if _server_ref:
        _server_ref.shutdown()


def main():
    print("=" * 52)
    print("  Schulmanager Proxy  –  Wochenplaner")
    print("=" * 52)
    print(f"  Adresse : http://localhost:{PORT}")
    print(f"  Beenden : Strg+C")
    print("=" * 52)

    global _server_ref
    try:
        server = HTTPServer(("localhost", PORT), ProxyHandler)
    except OSError:
        print(f"  Port {PORT} bereits belegt – Proxy läuft bereits.")
        sys.exit(0)

    _server_ref = server
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        print("\nProxy beendet.")
        server.server_close()


if __name__ == "__main__":
    main()
