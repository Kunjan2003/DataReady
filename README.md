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

- Email/password signup and login with expiring JWT sessions.
- Isolated projects and per-user upload folders, file type validation and a 50 MB per-file limit.
- CSV and Excel row import, preview, automatic header suggestions, standard field cleanup, quality flags, progress/status, and a record table.
- Phone, email, date, amount, spacing, capitalization and GST format normalization. Invalid data is flagged instead of guessed.
- Blocked fuzzy duplicate matching. Matches over 90% are merged with an audit entry; 70–90% are shown for user review; lower scores stay separate.
- CSV, XLSX and JSON exports, summary report, and change history.
- Text PDF extraction; scanned PDF and image text use Tesseract when installed.
- Unit tests for cleanup and deduplication.

## Tests

```sh
cd backend
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest
```

## Notes

The Anthropic key is optional and is not needed for deterministic cleanup. When configured, only unresolved column labels and document text are sent for mapping or invoice extraction; ordinary spreadsheet rows are not sent to Claude. Set `ANTHROPIC_API_KEY` and, if desired, `ANTHROPIC_MODEL` in `.env`. Without a key, column rules still work and documents needing extraction are clearly flagged for review. No raw file rows or personal data should be written to application logs. Upload work is queued in Redis/RQ when Redis is available, with an in-process background fallback for direct local development. The Compose API runs Alembic migrations at startup.
