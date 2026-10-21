# DataReady

DataReady helps small businesses bring spreadsheet and document data together, standardize common fields, review possible duplicate records, and export cleaner data. Uploaded originals remain in private storage; cleanup events are recorded in the audit log.

## Run locally with Docker

1. Install Docker Desktop and make sure its engine is running.
2. Copy `.env.example` to `.env`. Replace `JWT_SECRET` with a long random value.
3. From this directory run `docker compose up --build`.
4. Open [http://localhost:5173](http://localhost:5173). API docs are at [http://localhost:8000/docs](http://localhost:8000/docs).
5. Create an account, add a project, and upload CSV or Excel data. Try the sample `sample_customers.csv`.

The default Compose database credentials are for local development only. Change them before any deployment and keep `.env` out of version control.

## Features

- Email/password signup and login with expiring, HTTP-only session cookies and sign-in rate limits.
- Isolated projects and per-user upload folders, file-content checks, expanded-workbook limits, and a configurable per-file limit.
- CSV and Excel row import, preview, automatic header suggestions, standard field cleanup, quality flags, progress/status, and a record table.
- Phone, email, date, amount, spacing, capitalization and GST format normalization. Invalid data is flagged instead of guessed.
- Blocked fuzzy duplicate matching. Matches over 90% are merged with an audit entry; 70–90% are shown for user review; lower scores stay separate.
- Server-side record search, field editing with undo, CSV/XLSX/JSON exports, summary report, and change history.
- Text PDF extraction; scanned PDF and image text use Tesseract when installed.
- Unit tests for cleanup and deduplication.

## Production deployment

The development Compose file serves Vite and exposes development ports. Use `docker-compose.prod.yml` for a built frontend, internal-only API/database/Redis, persistent volumes, health checks, database migrations, and Docker secrets.

1. Create `secrets/db_password.txt` with a unique database password and `secrets/jwt_secret.txt` with at least 32 random characters. Keep the `secrets/` directory private; it is ignored by Git.
2. Set `ALLOWED_ORIGINS` to the exact public HTTPS origin, such as `https://data.example.com`. Set `HTTP_PORT` if the web container should use a port other than 8080.
3. Start the stack with `docker compose -f docker-compose.prod.yml up --build -d`.
4. Put a TLS reverse proxy in front of the web container. The session cookie is secure-only in production.

The production Compose file does not publish PostgreSQL, Redis, or the API port. Back up the database and the `uploads` volume together.

## Tests

```sh
cd backend
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest
```

## Privacy and processing

AI-assisted mapping and document extraction are disabled by default. Enable the checkbox on a project before uploading only if you want unresolved column labels or document text sent to Anthropic. Spreadsheet row contents are not sent for column mapping. Set `ANTHROPIC_API_KEY` and, if desired, `ANTHROPIC_MODEL` in `.env`. Without a key or without opting in, deterministic cleanup still works and files needing document extraction are flagged for review. No raw file rows or personal data should be written to application logs. Upload work is queued in Redis/RQ when available, with an in-process background fallback for direct local development. Alembic migrations run when the API starts.
