# Bulk Certificate Generator — Build Spec

> Give this file to your coding agent as the full build brief. It defines architecture, file structure, data model, API contract, and a phased task list. Follow phases in order — don't skip ahead. Commit after each phase with the message shown.

---

## 1. Objective

Build a backend API that accepts a list of recipients, generates a certificate for each one from a single predefined template, tracks job/record status, isolates per-recipient failures, and lets the client retrieve generated certificates.

This must **not** look AI-generated in a single pass. Build it in the phased commits below, with real tests, real error handling, and a documented design rationale.

---

## 2. Tech stack

- **Language**: Python 3.11+
- **Framework**: FastAPI
- **DB (dev)**: SQLite
- **DB (documented as prod target)**: PostgreSQL (Neon or Supabase free tier)
- **ORM**: SQLAlchemy 2.0 + Alembic for migrations
- **Validation**: Pydantic v2
- **Background processing**: FastAPI `BackgroundTasks` (document Celery+Redis as the scaling alternative in DESIGN.md — don't build it unless time allows)
- **Certificate rendering**: Jinja2 HTML template + WeasyPrint (or Pillow if WeasyPrint install is problematic in the environment)
- **Testing**: pytest, pytest-asyncio, httpx.AsyncClient
- **Storage**: local `/generated/` directory, path stored in DB; document S3 as future scope

---

## 3. Project structure

```
cert-generator/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/
│   │   ├── job.py
│   │   └── certificate.py
│   ├── schemas/
│   │   ├── job.py
│   │   └── certificate.py
│   ├── routers/
│   │   └── jobs.py
│   ├── services/
│   │   ├── job_service.py
│   │   └── certificate_service.py
│   ├── workers/
│   │   └── tasks.py
│   ├── templates/
│   │   └── certificate.html
│   └── utils/
│       └── exceptions.py
├── tests/
│   ├── conftest.py
│   ├── test_jobs.py
│   ├── test_validation.py
│   └── test_certificate_generation.py
├── alembic/
├── generated/              # gitignored, output certificates
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── DESIGN.md
```

Rules:
- Routers stay thin — only request parsing and calling a service function.
- All business logic lives in `services/`.
- No raw SQL in routers — only in `services/` or `models/`, via the ORM.

---

## 4. Data model

```python
class Job(Base):
    id: UUID (pk)
    status: Enum("PENDING", "PROCESSING", "COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED")
    total_count: int
    success_count: int
    failure_count: int
    created_at: datetime
    updated_at: datetime

class CertificateRecord(Base):
    id: UUID (pk)
    job_id: UUID (fk -> Job)
    recipient_name: str
    recipient_email: str | None
    status: Enum("PENDING", "SUCCESS", "FAILED")
    error_message: str | None
    file_path: str | None
    created_at: datetime
```

---

## 5. API contract

```
POST   /api/jobs/
  Body: { "recipients": [ { "name": str, "email": str? , ...extra fields }, ... ] }
  → 202 Accepted
  → { "job_id": "<uuid>", "status": "PENDING", "total_count": N }

GET    /api/jobs/{job_id}/
  → { "job_id", "status", "total_count", "success_count", "failure_count", "created_at", "updated_at" }

GET    /api/jobs/{job_id}/records/
  → [ { "record_id", "recipient_name", "status", "error_message", "file_path" }, ... ]

GET    /api/certificates/{record_id}/download/
  → serves the generated file (404 if not SUCCESS)
```

Validation rules:
- `recipients` must be a non-empty list.
- Each recipient requires at minimum a `name` field.
- Reject the whole request with 422 if the payload shape is invalid.
- A recipient that is structurally valid but fails during generation (e.g. template rendering error) must be caught individually — it must not abort the batch.

---

## 6. Phased build plan (commit after each phase)

### Phase 1 — Scaffold
- Create the folder structure above.
- Set up `config.py` with pydantic-settings reading from `.env`.
- Set up `database.py` with SQLAlchemy engine/session.
- Commit: `feat: scaffold FastAPI app structure`

### Phase 2 — Models & migrations
- Implement `Job` and `CertificateRecord` SQLAlchemy models.
- Initialize Alembic, generate first migration.
- Commit: `feat: add Job and CertificateRecord models + migrations`

### Phase 3 — Job creation endpoint
- Implement Pydantic request/response schemas.
- Implement `POST /api/jobs/`: validate payload, create Job + CertificateRecord rows (status PENDING), return 202.
- Write `test_create_job_valid_payload` and `test_create_job_invalid_recipient`.
- Commit: `feat: implement job creation endpoint with validation`

### Phase 4 — Certificate generation service
- Build the Jinja2/WeasyPrint (or Pillow) rendering function in `services/certificate_service.py`, taking a recipient dict and producing a file at `generated/{record_id}.pdf` (or `.png`).
- Write `test_certificate_generation_success` against this function directly (no HTTP layer yet).
- Commit: `feat: implement certificate generation service`

### Phase 5 — Background processing + failure isolation
- Wire generation into a `BackgroundTasks` function in `workers/tasks.py`: loop over the job's records, generate each one inside its own try/except, update that record's status/error_message, update the job's running counts, and set the job's final status once done.
- Write `test_certificate_generation_partial_failure` — force one bad recipient and confirm the others still succeed and the job ends `COMPLETED_WITH_ERRORS`.
- Commit: `feat: add background processing for bulk jobs` then `feat: add per-record failure isolation`

### Phase 6 — Status & download endpoints
- Implement `GET /api/jobs/{job_id}/`, `GET /api/jobs/{job_id}/records/`, `GET /api/certificates/{record_id}/download/`.
- Write `test_job_status_transitions` and `test_download_generated_certificate`.
- Commit: `feat: add job status and certificate download endpoints`

### Phase 7 — Edge cases & polish
- Handle: empty recipient list, duplicate recipients, missing job_id (404), missing record_id (404), downloading a FAILED record (409 or 404 with clear message).
- Add structured logging around generation failures.
- Commit: `fix: handle edge cases and add logging`

### Phase 8 — Documentation
- Write `README.md` (see section 7 below).
- Write `DESIGN.md` covering: why FastAPI, why BackgroundTasks over Celery for this scope (and what would change at higher volume), failure isolation strategy, storage choice, what you'd change for production scale.
- Commit: `docs: add README and design decisions`

### Phase 9 (optional) — Minimal frontend
- Single static HTML page: upload a CSV/paste recipients, submit job, poll `/records/` for status, list download links.
- Plain HTML/CSS/vanilla JS — no framework needed. Clean layout, one accent color, monospace for IDs/status, simple progress bar.
- Commit: `feat: add minimal frontend for job submission and status`

---

## 7. README requirements

Must include, in this order:
1. **Setup** — how to install deps, set up `.env`, run migrations
2. **Running the app** — exact command
3. **Running tests** — exact command
4. **API usage** — curl example for every endpoint in section 5
5. **Design decisions** — link to or inline summary of DESIGN.md
6. **Learnings & future scope** — explicitly required by the original assignment

---

## 8. Testing checklist (must all pass before calling this done)

- [ ] `test_create_job_valid_payload`
- [ ] `test_create_job_invalid_recipient`
- [ ] `test_certificate_generation_success`
- [ ] `test_certificate_generation_partial_failure`
- [ ] `test_job_status_transitions`
- [ ] `test_download_generated_certificate`

---

## 9. Non-negotiables (don't skip these even under time pressure)

- Separate routers/services/models — no business logic in route handlers.
- Every certificate generation wrapped in its own try/except inside the batch loop.
- Real Alembic migration, not just `create_all()`.
- At least 8 distinct, logically-scoped commits — never one large dump commit.
- `.env.example` committed, actual `.env` gitignored.
- No hardcoded secrets or paths.
