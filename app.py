from contextlib import asynccontextmanager, closing
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StringConstraints
from starlette.exceptions import HTTPException as StarletteHTTPException


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
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db():
    with closing(connect_db()) as conn, conn:
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



@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_db()
    yield


app = FastAPI(title="CareNest Clinic Booking", version="1.0.0", lifespan=lifespan)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AppointmentCreate(BaseModel):
    name: Text
    phone: Text
    service: Text
    appointment_date: Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    appointment_time: Annotated[str, StringConstraints(pattern=r"^\d{2}:\d{2}$")]
    email: str = ""
    notes: str = ""

    model_config = {"str_strip_whitespace": True}


class LeadCreate(BaseModel):
    name: Text
    phone: Text
    interest: Text
    message: str = ""

    model_config = {"str_strip_whitespace": True}


class StatusUpdate(BaseModel):
    status: Literal["New", "Confirmed", "Completed", "Cancelled"]


def get_db():
    with closing(connect_db()) as conn:
        with conn:
            yield conn


Database = Annotated[sqlite3.Connection, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=100)]


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Preserve the error field consumed by the existing frontend.
    errors = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors()
    )
    return JSONResponse(status_code=422, content={"error": errors})


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail}, headers=exc.headers)


@app.get("/api/services")
def list_services(conn: Database):
    return {"services": [dict(row) for row in conn.execute("SELECT * FROM services ORDER BY price")]}


@app.get("/api/admin/summary")
def admin_summary(conn: Database):
    return {
        "appointments": conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0],
        "leads": conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0],
        "newAppointments": conn.execute("SELECT COUNT(*) FROM appointments WHERE status = 'New'").fetchone()[0],
        "todayAppointments": conn.execute(
            "SELECT COUNT(*) FROM appointments WHERE appointment_date = ?",
            (datetime.now().date().isoformat(),),
        ).fetchone()[0],
    }


@app.get("/api/admin/appointments")
def list_appointments(conn: Database, limit: Limit = 50):
    rows = conn.execute(
        "SELECT * FROM appointments ORDER BY appointment_date ASC, appointment_time ASC, id DESC LIMIT ?",
        (limit,),
    )
    return {"appointments": [dict(row) for row in rows]}


@app.get("/api/admin/leads")
def list_leads(conn: Database, limit: Limit = 50):
    return {"leads": [dict(row) for row in conn.execute("SELECT * FROM leads ORDER BY id DESC LIMIT ?", (limit,))]}


@app.post("/api/appointments", status_code=201)
def create_appointment(data: AppointmentCreate, conn: Database):
    try:
        datetime.strptime(data.appointment_date, "%Y-%m-%d")
        datetime.strptime(data.appointment_time, "%H:%M")
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid appointment date or time")
    cursor = conn.execute(
        """INSERT INTO appointments
        (name, phone, email, service, appointment_date, appointment_time, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (data.name, data.phone, data.email, data.service, data.appointment_date,
         data.appointment_time, data.notes, datetime.now().isoformat(timespec="seconds")),
    )
    return {"ok": True, "id": cursor.lastrowid}


@app.post("/api/leads", status_code=201)
def create_lead(data: LeadCreate, conn: Database):
    cursor = conn.execute(
        "INSERT INTO leads (name, phone, interest, message, created_at) VALUES (?, ?, ?, ?, ?)",
        (data.name, data.phone, data.interest, data.message, datetime.now().isoformat(timespec="seconds")),
    )
    return {"ok": True, "id": cursor.lastrowid}


@app.post("/api/appointments/{appointment_id}/status")
def update_appointment_status(appointment_id: int, data: StatusUpdate, conn: Database):
    cursor = conn.execute("UPDATE appointments SET status = ? WHERE id = ?", (data.status, appointment_id))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return {"ok": True}


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
def unknown_api(path: str):
    raise HTTPException(status_code=404, detail="Not found")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(PUBLIC / "index.html")


app.mount("/", StaticFiles(directory=PUBLIC, html=True), name="public")


def run():
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
