# Bulk Certificate Generator API

A high-performance, resilient backend API built with FastAPI, SQLAlchemy 2.0, Alembic, and Pillow. The service accepts batches of certificate recipients, asynchronously renders individualized certificates, provides real-time progress tracking, isolates per-recipient failures, and serves generated files.

---

## 1. Setup

### Prerequisites
- Python 3.11+ (tested on Python 3.13)
- Git

### Installation Steps

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Susil-commits/CertGen.git
   cd CertGen
   ```

2. **Create and activate a virtual environment** (optional but recommended):
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux / macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
   Default configuration in `.env`:
   ```env
   APP_NAME="Bulk Certificate Generator"
   APP_ENV=development
   DATABASE_URL=sqlite:///./cert_generator.db
   OUTPUT_DIR=generated
   LOG_LEVEL=INFO
   ```

5. **Run database migrations**:
   Apply Alembic schema migrations:
   ```bash
   alembic upgrade head
   ```

---

## 2. Running the App

Start the FastAPI application using Uvicorn:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Once running:
- **API Base URL**: `http://localhost:8000`
- **Interactive OpenAPI Documentation (Swagger UI)**: `http://localhost:8000/docs`
- **Alternative ReDoc Documentation**: `http://localhost:8000/redoc`
- **Health Check**: `http://localhost:8000/health`

---

## 3. Running Tests

Execute the automated test suite using pytest:

```bash
pytest -v
```

To run with coverage reporting:
```bash
pytest --cov=app -v
```

---

## 4. API Usage

Here are complete `curl` examples for every endpoint defined in the API contract:

### 4.1 Submit a Bulk Certificate Job
Submits a list of recipients for asynchronous batch processing.

```bash
curl -X POST "http://localhost:8000/api/jobs/" \
  -H "Content-Type: application/json" \
  -d '{
    "recipients": [
      {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "course": "Pioneering Computing"
      },
      {
        "name": "Alan Turing",
        "email": "alan@example.com",
        "course": "Theoretical Computer Science"
      },
      {
        "name": "Grace Hopper",
        "email": "grace@example.com",
        "course": "Compiler Construction"
      }
    ]
  }'
```

**Response (HTTP 202 Accepted)**:
```json
{
  "job_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "status": "PENDING",
  "total_count": 3
}
```

---

### 4.2 Query Job Status & Counters
Inspects overall status, total counts, successful generations, and isolated failure counts.

```bash
curl -X GET "http://localhost:8000/api/jobs/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d/"
```

**Response (HTTP 200 OK)**:
```json
{
  "job_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "status": "COMPLETED",
  "total_count": 3,
  "success_count": 3,
  "failure_count": 0,
  "created_at": "2026-10-07T14:45:00.000000Z",
  "updated_at": "2026-10-07T14:45:01.200000Z"
}
```

*Possible Job Statuses*: `PENDING`, `PROCESSING`, `COMPLETED`, `COMPLETED_WITH_ERRORS`, `FAILED`.

---

### 4.3 Query Job Records
Retrieves detailed per-recipient record statuses, error diagnostics, and generated file paths.

```bash
curl -X GET "http://localhost:8000/api/jobs/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d/records/"
```

**Response (HTTP 200 OK)**:
```json
[
  {
    "record_id": "4a737f1e-f35c-4f9e-9907-28d844c8c7f3",
    "recipient_name": "Ada Lovelace",
    "status": "SUCCESS",
    "error_message": null,
    "file_path": "generated/4a737f1e-f35c-4f9e-9907-28d844c8c7f3.pdf"
  },
  {
    "record_id": "e67e3a35-4dbb-4ae1-8d23-28da9d871239",
    "recipient_name": "Alan Turing",
    "status": "SUCCESS",
    "error_message": null,
    "file_path": "generated/e67e3a35-4dbb-4ae1-8d23-28da9d871239.pdf"
  },
  {
    "record_id": "31f41b9c-8519-482d-8b04-b91cbb80cb89",
    "recipient_name": "Grace Hopper",
    "status": "SUCCESS",
    "error_message": null,
    "file_path": "generated/31f41b9c-8519-482d-8b04-b91cbb80cb89.pdf"
  }
]
```

---

### 4.4 Download Certificate File
Streams the generated certificate file (`application/pdf` or `image/png`).

```bash
curl -X GET "http://localhost:8000/api/certificates/4a737f1e-f35c-4f9e-9907-28d844c8c7f3/download/" \
  --output "certificate.pdf"
```

**Response (HTTP 200 OK)**:
- Binary PDF stream saved to `certificate.pdf`.
- If certificate generation failed or is still pending: returns HTTP 409 Conflict with explanation.
- If record does not exist: returns HTTP 404 Not Found.

---

## 5. Design Decisions

For full technical rationale and architecture deep dives, refer to [DESIGN.md](file:///c:/Users/nayak/OneDrive/Desktop/CertificateGen/DESIGN.md).

Key highlights:
- **FastAPI + Async Starlette**: Chosen for non-blocking I/O, automatic OpenAPI schema generation, and high throughput during polling and concurrent downloads.
- **FastAPI `BackgroundTasks` vs. Celery**: `BackgroundTasks` provides zero-infrastructure simplicity for lightweight workloads. Celery + Redis is documented as the architectural target for horizontal scalability and CPU isolation at high volumes.
- **Failure Isolation Boundary**: Every certificate rendering is encapsulated in its own `try/except` block. One corrupt recipient cannot fail the batch; failed records capture the exact error traceback, and the parent job settles as `COMPLETED_WITH_ERRORS`.
- **Storage Strategy**: Local storage under `generated/` with relative database path references; documented migration to AWS S3 / GCS pre-signed download URLs for cloud-native deployment.
- **Structured JSON Logging**: Implemented with contextual tracing fields (`event`, `job_id`, `record_id`, `duration_ms`, `error`) for production log aggregation.

---

## 6. Learnings & Future Scope

### Learnings
1. **Windows Native Graphics Drivers**: WeasyPrint relies on native system libraries (Cairo, Pango, GDK-PixBuf) that frequently cause complex DLL configuration hurdles in non-containerized Windows environments. Leveraging Pillow for typography rendering alongside Jinja2 template validation ensures reliable, cross-platform PDF/PNG generation without external C library dependencies.
2. **FastAPI BackgroundTask Lifecycle in Testing**: When using `httpx.AsyncClient` with an ASGI app, background tasks run synchronously during client response resolution. Managing database session lifecycles with dedicated test session overrides prevents SQLite concurrency lockups and ensures reliable assertion checks.
3. **Graceful Degraded States**: Transitioning bulk jobs to `COMPLETED_WITH_ERRORS` rather than binary `FAILED`/`COMPLETED` allows downstream clients to offer users actionable retries for only the failed subset of recipients.

### Future Scope
- **Distributed Celery + Redis Task Queue**: Decouple CPU-intensive rendering from web servers and deploy auto-scaling worker nodes.
- **AWS S3 Cloud Storage with Pre-signed URLs**: Offload file serving bandwidth from API servers to object storage.
- **Dynamic Template Customizer**: Support user-uploaded HTML/CSS or Jinja2 certificate templates with customizable variable substitution and custom logos.
- **Batch Export**: Provide a `GET /api/jobs/{job_id}/download-all/` endpoint that streams a compressed `.zip` archive containing all successfully generated certificates.
- **Webhook & Email Dispatcher**: Send automated email notifications containing certificate download links to recipients upon successful generation.
