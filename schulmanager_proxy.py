#!/usr/bin/env python3
"""
Schulmanager Proxy für den Wochenplaner
========================================
Starten mit:  python schulmanager_proxy.py
Beenden mit:  Strg+C

Voraussetzung: pip install requests icalendar
"""

import json
import logging
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

# Logging in Datei neben dem Skript
_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'proxy.log')
logging.basicConfig(
    filename=_LOG_FILE, level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s', encoding='utf-8'
)

try:
    import requests
except ImportError:
    print("Fehler: 'requests' ist nicht installiert.")
    print("Bitte ausführen: pip install requests icalendar")
    sys.exit(1)

try:
    from icalendar import Calendar as ICal
    from zoneinfo import ZoneInfo
    import recurring_ical_events
    _BERLIN = ZoneInfo('Europe/Berlin')
    HAS_ICAL = True
    _ical_err_msg = ''
except ImportError as _ical_err:
    HAS_ICAL = False
    _ical_err_msg = f"Fehlendes Paket: {_ical_err.name}. Bitte ausführen: pip install icalendar recurring-ical-events"

PORT = 8765
LOGIN_URL  = "https://login.schulmanager-online.de/api/login"
API_URL    = "https://login.schulmanager-online.de/api/calls"

# Globaler Zustand (läuft nur im lokalen Prozess)
_token    = None
_user     = None
_student  = None


def sm_login(username: str, password: str, institution_id=None) -> dict:
    """Meldet sich bei Schulmanager an und gibt die Antwort zurück."""
    global _token, _user, _student
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.post(LOGIN_URL, json={
                "emailOrUsername": username,
                "password":        password,
                "mobileApp":       False,
                "institutionId":   institution_id
            }, timeout=10)
            break  # Verbindung erfolgreich
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last_err = e
            if attempt < 2:
                time.sleep(2)
    else:
        raise last_err
    resp.raise_for_status()
    data = resp.json()
    logging.debug(f"Login-Antwort: {data}")
    # Mehrere Konten – Schulauswahl nötig
    if "multipleAccounts" in data:
        return {"multipleAccounts": data["multipleAccounts"]}
    if "jwt" not in data:
        msg = data.get("message") or data.get("error") or data.get("msg") or str(data)
        raise ValueError(f"Anmeldung fehlgeschlagen: {msg}")
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
        logging.info(f"{self.command} {self.path} → {args[1]}")

    def _send(self, code: int, data: dict):
        if code >= 400:
            logging.warning(f"{self.path} → {code}: {data}")
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
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout):
                self._send(503, {"error": "Schulmanager nicht erreichbar – Internetverbindung prüfen."})
            except Exception as e:
                self._send(500, {"error": str(e)})

        elif parsed.path == "/gcal-sync":
            week = (params.get("week") or [None])[0]
            if not week:
                self._send(400, {"error": "Parameter 'week' fehlt"}); return
            try:
                events = parse_gcal_week(week)
                self._send(200, {"ok": True, "week": week, "events": events,
                                 "count": len(events)})
            except Exception as e:
                self._send(500, {"error": str(e)})

        elif parsed.path == "/gcal-status":
            self._send(200, {"configured": bool(_gcal_url),
                             "hasIcal": HAS_ICAL})

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
            username       = body.get("username", "").strip()
            password       = body.get("password", "")
            institution_id = body.get("institutionId", None)
            if not username or not password:
                self._send(400, {"error": "Benutzername und Passwort erforderlich"}); return
            try:
                data = sm_login(username, password, institution_id)
                if "multipleAccounts" in data:
                    self._send(200, {"multipleAccounts": data["multipleAccounts"]})
                    return
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
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout):
                self._send(503, {"error": (
                    "Schulmanager nicht erreichbar.\n"
                    "Mögliche Ursachen:\n"
                    "• Kein Internet\n"
                    "• Windows-Firewall blockiert pythonw.exe\n"
                    "  → Windows-Sicherheit → Firewall → App zulassen → pythonw.exe erlauben"
                )})
            except Exception as e:
                logging.error(f"Login-Fehler: {traceback.format_exc()}")
                self._send(500, {"error": f"{type(e).__name__}: {e}"})

        elif parsed.path == "/gcal-url":
            url = body.get("url", "").strip()
            if not url:
                self._send(400, {"error": "URL fehlt"}); return
            try:
                _save_gcal_config(url)
                self._send(200, {"ok": True})
            except Exception as e:
                self._send(500, {"error": str(e)})

        else:
            self._send(404, {"error": "Nicht gefunden"})


# ── GOOGLE CALENDAR ──
_gcal_url    = None
_GCAL_CONFIG = 'gcal_config.json'

def _load_gcal_config():
    global _gcal_url
    try:
        with open(_GCAL_CONFIG) as f:
            _gcal_url = json.load(f).get('url') or None
    except Exception:
        _gcal_url = None

def _save_gcal_config(url: str):
    global _gcal_url
    _gcal_url = url or None
    with open(_GCAL_CONFIG, 'w') as f:
        json.dump({'url': url}, f)

def parse_gcal_week(week_key: str) -> list:
    """Holt und parst den Google Kalender iCal für die angegebene Woche."""
    if not HAS_ICAL:
        raise RuntimeError(_ical_err_msg or "icalendar/recurring-ical-events nicht installiert.")
    if not _gcal_url:
        raise RuntimeError("Kein iCal-URL konfiguriert")

    start_str, end_str = week_key_to_dates(week_key)
    week_start = datetime.strptime(start_str, '%Y-%m-%d').date()
    week_end   = datetime.strptime(end_str,   '%Y-%m-%d').date()

    resp = requests.get(_gcal_url, timeout=15)
    resp.raise_for_status()

    from datetime import date as date_type
    cal = ICal.from_ical(resp.content)

    # recurring_ical_events expandiert Serientermine automatisch
    start_dt = datetime(week_start.year, week_start.month, week_start.day)
    end_dt   = datetime(week_end.year,   week_end.month,   week_end.day, 23, 59, 59)
    occurrences = recurring_ical_events.of(cal).between(start_dt, end_dt)

    events = []
    for comp in occurrences:
        dtstart = comp.get('DTSTART')
        dtend   = comp.get('DTEND')
        summary = str(comp.get('SUMMARY', 'Ohne Titel'))
        if not dtstart:
            continue

        dt = dtstart.dt

        # Ganztägige Termine
        if isinstance(dt, date_type) and not isinstance(dt, datetime):
            events.append({'date': dt.strftime('%Y-%m-%d'), 'title': summary,
                           'start': '00:00', 'end': '23:59', 'allDay': True})
            continue

        # Zeitzone → Berliner Ortszeit
        if dt.tzinfo is not None:
            dt = dt.astimezone(_BERLIN).replace(tzinfo=None)

        if dtend:
            end = dtend.dt
            if isinstance(end, datetime) and end.tzinfo is not None:
                end = end.astimezone(_BERLIN).replace(tzinfo=None)
        else:
            end = dt + timedelta(hours=1)

        end_str_fmt = end.strftime('%H:%M') if isinstance(end, datetime) else '23:59'
        events.append({'date': dt.strftime('%Y-%m-%d'), 'title': summary,
                       'start': dt.strftime('%H:%M'), 'end': end_str_fmt,
                       'allDay': False})

    return events


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
    _load_gcal_config()
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
