from datetime import datetime
import json
import mimetypes
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
DB_PATH = ROOT / "clinic.db"


SERVICES = [
    ("General Consultation", "20 min", 450, "Everyday care, acute concerns, prescriptions, and follow-ups."),
    ("Preventive Health Check", "45 min", 1400, "Vitals, history review, screening guidance, and doctor recommendations."),
    ("Diabetes Review", "30 min", 800, "Medication review, lifestyle support, sugar log analysis, and care planning."),
    ("Pediatric Visit", "25 min", 650, "Child-friendly consultations for fever, nutrition, vaccines, and growth."),
    ("Women's Wellness", "35 min", 950, "Confidential care for cycles, wellness checks, and ongoing concerns."),
    ("Teleconsultation", "15 min", 350, "Quick video or phone appointment for simple concerns and reports."),
]


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db():
    with connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT,
                service TEXT NOT NULL,
                appointment_date TEXT NOT NULL,
                appointment_time TEXT NOT NULL,
                notes TEXT,
                status TEXT NOT NULL DEFAULT 'New',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                interest TEXT NOT NULL,
                message TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                duration TEXT NOT NULL,
                price INTEGER NOT NULL,
                description TEXT NOT NULL
            )
            """
        )
        for service in SERVICES:
            conn.execute(
                """
                INSERT OR IGNORE INTO services (name, duration, price, description)
                VALUES (?, ?, ?, ?)
                """,
                service,
            )


def rows_to_dicts(rows):
    return [dict(row) for row in rows]


def json_response(handler, payload, status=200):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler):
    content_length = int(handler.headers.get("Content-Length", 0))
    raw = handler.rfile.read(content_length).decode("utf-8")
    if not raw:
        return {}
    return json.loads(raw)


def validate_required(data, fields):
    missing = [field for field in fields if not str(data.get(field, "")).strip()]
    if missing:
        return f"Missing required field: {', '.join(missing)}"
    return None


class ClinicHandler(BaseHTTPRequestHandler):
    server_version = "CareNestClinic/1.0"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api_get(parsed)
            return
        self.serve_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/appointments":
            self.create_appointment()
        elif parsed.path == "/api/leads":
            self.create_lead()
        elif parsed.path.startswith("/api/appointments/") and parsed.path.endswith("/status"):
            self.update_appointment_status(parsed.path)
        else:
            json_response(self, {"error": "Not found"}, 404)

    def handle_api_get(self, parsed):
        query = parse_qs(parsed.query)
        with connect_db() as conn:
            if parsed.path == "/api/services":
                rows = conn.execute("SELECT * FROM services ORDER BY price").fetchall()
                json_response(self, {"services": rows_to_dicts(rows)})
            elif parsed.path == "/api/admin/summary":
                summary = {
                    "appointments": conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0],
                    "leads": conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0],
                    "newAppointments": conn.execute(
                        "SELECT COUNT(*) FROM appointments WHERE status = 'New'"
                    ).fetchone()[0],
                    "todayAppointments": conn.execute(
                        "SELECT COUNT(*) FROM appointments WHERE appointment_date = ?",
                        (datetime.now().date().isoformat(),),
                    ).fetchone()[0],
                }
                json_response(self, summary)
            elif parsed.path == "/api/admin/appointments":
                limit = min(int(query.get("limit", ["50"])[0]), 100)
                rows = conn.execute(
                    """
                    SELECT * FROM appointments
                    ORDER BY appointment_date ASC, appointment_time ASC, id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                json_response(self, {"appointments": rows_to_dicts(rows)})
            elif parsed.path == "/api/admin/leads":
                limit = min(int(query.get("limit", ["50"])[0]), 100)
                rows = conn.execute(
                    "SELECT * FROM leads ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                json_response(self, {"leads": rows_to_dicts(rows)})
            else:
                json_response(self, {"error": "Not found"}, 404)

    def create_appointment(self):
        try:
            data = read_json(self)
            error = validate_required(
                data, ["name", "phone", "service", "appointment_date", "appointment_time"]
            )
            if error:
                json_response(self, {"error": error}, 400)
                return
            with connect_db() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO appointments
                        (name, phone, email, service, appointment_date, appointment_time, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["name"].strip(),
                        data["phone"].strip(),
                        data.get("email", "").strip(),
                        data["service"].strip(),
                        data["appointment_date"].strip(),
                        data["appointment_time"].strip(),
                        data.get("notes", "").strip(),
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
            json_response(self, {"ok": True, "id": cursor.lastrowid}, 201)
        except (json.JSONDecodeError, sqlite3.Error, ValueError) as exc:
            json_response(self, {"error": str(exc)}, 400)

    def create_lead(self):
        try:
            data = read_json(self)
            error = validate_required(data, ["name", "phone", "interest"])
            if error:
                json_response(self, {"error": error}, 400)
                return
            with connect_db() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO leads (name, phone, interest, message, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        data["name"].strip(),
                        data["phone"].strip(),
                        data["interest"].strip(),
                        data.get("message", "").strip(),
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
            json_response(self, {"ok": True, "id": cursor.lastrowid}, 201)
        except (json.JSONDecodeError, sqlite3.Error) as exc:
            json_response(self, {"error": str(exc)}, 400)

    def update_appointment_status(self, path):
        try:
            appointment_id = int(path.split("/")[3])
            data = read_json(self)
            status = data.get("status", "").strip()
            if status not in {"New", "Confirmed", "Completed", "Cancelled"}:
                json_response(self, {"error": "Invalid status"}, 400)
                return
            with connect_db() as conn:
                cursor = conn.execute(
                    "UPDATE appointments SET status = ? WHERE id = ?",
                    (status, appointment_id),
                )
            if cursor.rowcount == 0:
                json_response(self, {"error": "Appointment not found"}, 404)
                return
            json_response(self, {"ok": True})
        except (json.JSONDecodeError, ValueError, sqlite3.Error) as exc:
            json_response(self, {"error": str(exc)}, 400)

    def serve_static(self, request_path):
        path = PUBLIC / ("index.html" if request_path in {"/", ""} else request_path.lstrip("/"))
        try:
            resolved = path.resolve()
            if PUBLIC not in resolved.parents and resolved != PUBLIC:
                self.send_error(403)
                return
            if not resolved.exists() or resolved.is_dir():
                resolved = PUBLIC / "index.html"
            content = resolved.read_bytes()
            content_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except OSError:
            self.send_error(404)

    def log_message(self, fmt, *args):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {fmt % args}")


def run():
    initialize_db()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), ClinicHandler)
    print("CareNest Clinic running at http://127.0.0.1:8000")
    server.serve_forever()


if __name__ == "__main__":
    run()
