# Architecture & System Design Decisions

This document outlines the architectural principles, trade-offs, and scalability roadmap for the **Bulk Certificate Generator**.

---

## 1. Framework Choice: Why FastAPI

FastAPI was selected for this project based on several core architectural advantages:

- **Asynchronous Execution & Concurrency**: FastAPI is built on Starlette and ASGI, natively enabling high-concurrency non-blocking I/O. When handling large HTTP uploads or serving multiple concurrent status polls and file downloads, FastAPI maintains low latency without thread starvation.
- **Strict Data Validation with Pydantic v2**: Pydantic v2 (compiled with a Rust core) provides fast data parsing, strict typing, and validation. In a bulk generation workflow where client payloads contain hundreds or thousands of nested recipient dictionaries, Pydantic guarantees bad inputs fail fast at the boundary (HTTP 422) before touching database records or rendering pipelines.
- **Automatic OpenAPI Documentation**: Interactive OpenAPI (Swagger) and ReDoc documentation are generated natively, facilitating rapid API inspection and contract verification.
- **Dependency Injection**: FastAPI's dependency injection system cleanly isolates database sessions (`get_db`) and allows clean overriding in automated test suites without monkey-patching.

---

## 2. Background Processing: `BackgroundTasks` vs. Celery + Redis

### Current Implementation: FastAPI `BackgroundTasks`

For this service's immediate scope and initial deployment footprint, FastAPI's built-in `BackgroundTasks` provides the optimal balance of simplicity and capability:

- **Zero Operational Overhead**: No external broker (Redis, RabbitMQ) or worker processes (Celery workers, Celery beat) are required. Developers and continuous integration runners can execute the entire application and test suite with zero auxiliary services.
- **In-Process Thread Execution**: Background jobs run in Starlette's threadpool after the HTTP response (HTTP 202 Accepted) is flushed to the client, preventing HTTP timeouts.
- **Dedicated Database Sessions**: Background tasks instantiate an isolated database session (`SessionLocal()`), preventing lifecycle entanglement or connection leaks across the request-response cycle.

### What Changes at Higher Volume (10,000+ Certificates / Concurrent Batches)

At enterprise or high-volume scale, in-process `BackgroundTasks` presents fundamental limitations:

1. **Process Volatility**: If the web server process restarts, crashes, or scales down during deployment, any jobs currently running in memory will be terminated without recovery unless state recovery reconcilers exist.
2. **CPU Contention**: Certificate image rendering and PDF compilation are CPU-bound operations. Running heavy Pillow/PDF rendering inside web server worker processes contends with the web event loop and can degrade API responsiveness.
3. **Horizontal Scalability**: Background tasks cannot be distributed across dedicated compute instances.

### Scaling Architecture: Celery + Redis / Cloud Tasks

At scale, the task execution layer would transition to an out-of-process distributed queue:

```
[FastAPI Web API]
       │
       ▼ (Enqueue Job Task)
 [Redis / RabbitMQ Broker]
       │
       ▼ (Distribute tasks across CPU-optimized worker nodes)
[Celery Workers (Prefetch / Chunking / Concurrency Controls)]
       │
       ▼
[PostgreSQL Database]  <─── Status Updates
       │
       ▼
[Amazon S3 / GCS]       <─── Certificate Uploads
```

- **Chunking & Fan-Out**: Large jobs (e.g., 50,000 recipients) would be chunked into sub-tasks of 100 recipients each using Celery group workflows (`chord` or `chunks`).
- **Dead-Letter Queues (DLQ)**: System crashes or permanent failures would be routed to DLQs with exponential backoff and alerting.

---

## 3. Failure Isolation Strategy

Bulk generation pipelines must never fail atomically when processing heterogenous batches. If a batch contains 1,000 recipients and 1 recipient contains an invalid value or triggers a rendering edge case, aborting the entire job wastes resources and degrades user experience.

### Layered Resilience Model

1. **Ingestion-Time Boundary Validation (HTTP 422)**:
   - Malformed request shapes, empty lists, or missing compulsory fields are rejected immediately before any state is written to the database.
2. **Per-Recipient Try/Except Isolation**:
   - The background worker iterates through recipients, executing each certificate rendering inside an independent `try...except Exception as exc:` block.
   - An unhandled error in recipient $N$ never prevents recipient $N+1$ from being processed.
3. **Independent Record State Tracking**:
   - Each certificate has its own `CertificateRecord` row with statuses: `PENDING`, `SUCCESS`, or `FAILED`.
   - On error, `error_message` records the exact reason (e.g. invalid template variable, rendering exception) and `file_path` remains `None`.
4. **Intermediate Progress Persistence**:
   - Database updates are committed after each individual certificate is rendered. This provides clients with live progress counters (`success_count`, `failure_count`) when polling `GET /api/jobs/{job_id}/`.
5. **Aggregate Job Outcome Categorization**:
   - `COMPLETED`: All records succeeded ($failure\_count = 0, success\_count > 0$).
   - `COMPLETED_WITH_ERRORS`: Partial success ($success\_count > 0, failure\_count > 0$).
   - `FAILED`: Zero certificates could be produced ($success\_count = 0$).

---

## 4. Storage Architecture: Local Storage vs. Object Storage (S3)

### Current Implementation: Local Directory (`generated/`)

- Generated files are saved to `generated/{record_id}.pdf` (or `.png`).
- Relative file paths are stored in `certificate_records.file_path`.
- Files are served directly via FastAPI's `FileResponse` with appropriate MIME types (`application/pdf`, `image/png`).
- The directory is ignored in Git to prevent repository bloat.

### Production Roadmap: Cloud Object Storage (Amazon S3 / Google Cloud Storage)

For a production cloud deployment:

1. **Stateless Compute**: Containerized instances (e.g., AWS ECS, Kubernetes, Google Cloud Run) have ephemeral storage. Output certificates must be persisted to object storage.
2. **Direct Upload & Streaming**: Workers stream generated byte buffers directly to S3 via `boto3` (`upload_fileobj`) using standard naming schemes: `s3://bucket/certificates/{job_id}/{record_id}.pdf`.
3. **Pre-Signed URLs**: Rather than streaming multi-megabyte PDFs through the API server, `GET /api/certificates/{record_id}/download/` generates a time-limited pre-signed S3 download URL (e.g., 15-minute expiration) and returns an HTTP 307 Temporary Redirect, completely offloading bandwidth from the backend API.

---

## 5. Production Scalability Checklist

| Dimension | Development | Production Target |
| :--- | :--- | :--- |
| **Database** | SQLite with WAL mode | PostgreSQL (Neon / Supabase / AWS RDS) with PgBouncer connection pooling |
| **Migrations** | Alembic autogenerated migrations | Alembic migrations integrated in CI/CD deployment pipelines |
| **Background Processing** | FastAPI `BackgroundTasks` | Celery + Redis with separate CPU-bound worker pools |
| **Storage** | Local `generated/` directory | S3 / GCS with pre-signed download URLs |
| **Security & Rate Limiting** | Open endpoints | API Key / JWT authentication + SlowAPI rate limiting |
| **Observability** | Structured JSON console logging | OpenTelemetry tracing, Prometheus metrics, and centralized log aggregation |
