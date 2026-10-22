# CareNest Clinic Booking

A FastAPI clinic booking application with service pricing, appointment booking,
WhatsApp contact links, callback requests, an admin dashboard, and SQLite persistence.
The existing HTML/CSS/JavaScript frontend is served by the same application.

## Run locally

Requires Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Open http://127.0.0.1:8000 for the app and http://127.0.0.1:8000/docs
for interactive API documentation. OpenAPI is available at `/openapi.json`.
You can also start the server with `python app.py`.

The app initializes `clinic.db` on startup and preserves existing records.

## API

- `GET /api/services` — service catalog
- `POST /api/appointments` — create an appointment
- `POST /api/leads` — request a callback
- `GET /api/admin/summary` — dashboard counts
- `GET /api/admin/appointments?limit=50` — appointment list
- `GET /api/admin/leads?limit=50` — callback list
- `POST /api/appointments/{id}/status` — set New, Confirmed, Completed, or Cancelled

List limits must be between 1 and 100. Invalid requests return HTTP 422 with an
`error` field for the frontend. See `/docs` for request schemas.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Tests use a temporary database and leave `clinic.db` untouched.
