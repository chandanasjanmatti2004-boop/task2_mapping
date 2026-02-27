

# Task2 Mapping API

FastAPI service to upload Excel data, map it into a loaner schema, validate it, and store it in MySQL.

---

## Features

* Upload Excel file via `POST /upload/`
* Auto-detect header row (handles messy spreadsheets)
* Direct column mapping with alias support
* Content-based fallback mapping when headers do not match
* Row-level validation and cleaning
* MySQL persistence using SQLAlchemy
* Duplicate-safe inserts (per-row savepoint)
* Deterministic ordered read API via `GET /loaners`
* Alembic migration support

---

## Tech Stack

* Python
* FastAPI
* SQLAlchemy
* PyMySQL
* Pandas + OpenPyXL
* Alembic
* python-dotenv
* httpx (for optional LLM service helper)

---

## Project Structure

```
task2_mapping/
├─ app/
│  ├─ main.py          # API endpoints + Excel mapping pipeline
│  ├─ database.py      # SQLAlchemy engine/session/base setup
│  ├─ models.py        # Loaner ORM model
│  ├─ validator.py     # Data validation/cleanup rules
│  └─ llm_service.py   # Optional LLM mapping helper
├─ alembic/
│  ├─ env.py
│  └─ versions/
├─ alembic.ini
├─ requirements.txt
└─ .env
```

---

## Data Model

`loaners` table fields:

* `loaner_id` (PK, string)
* `fullname` (string)
* `mobile_no` (string)
* `loaner_adhar` (string)
* `total_amount` (float)
* `total_land` (string)
* `descrition` (string)

---

## Environment Variables

Create/update `.env`:

```
DB_USER=root
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=3306
DB_NAME=excel_dbt

API_URL=https://gateway.dvara.com/workflow-api/api/csj?data
DVARA_TOKEN=your_token
```

### Notes

* Database credentials are loaded in `app/database.py`.
* `URL.create(...)` is used, so special characters in password (like `@`) are handled safely.
* `API_URL` and `DVARA_TOKEN` are used by `app/llm_service.py` (optional helper).

---

## Installation

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

## Database Setup

1. Ensure MySQL is running.
2. Create database if needed:

```sql
CREATE DATABASE excel_dbt;
```

3. Run migrations:

```powershell
alembic upgrade head
```

---

## Run the API

```powershell
uvicorn app.main:app --reload
```

Swagger UI:

* [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## API Endpoints

### POST `/upload/`

Uploads an Excel file and processes rows into `loaners`.

Form-data:

* `file`: `.xlsx` file

### Behavior

1. Reads file bytes
2. Loads DataFrame with header auto-detection
3. Tries direct field mapping using aliases
4. If direct mapping fails, uses content heuristics
5. Validates row values (`validator.py`)
6. Inserts rows with duplicate-safe nested transactions
7. Returns insert summary plus ordered DB rows

### Response Keys

* `status`
* `mapping_source` (`direct_header` or `content_heuristic`)
* `rows_inserted`
* `duplicates_skipped`
* `failed_rows`
* `total_processed`
* `preview`
* `data` (all rows in sorted order)

---

### GET `/loaners`

Returns all rows sorted in natural ID order:

* Numeric IDs first (`1, 2, 3, ...`)
* Then non-numeric IDs

---

## Validation Rules (`app/validator.py`)

* Keeps only required fields:

  * `loaner_id`
  * `fullname`
  * `mobile_no`
  * `loaner_adhar`
  * `total_amount`
  * `total_land`
  * `descrition`
* `total_amount` cast to float; invalid becomes `None`
* `mobile_no` must match `^[6-9][0-9]{9}$`, else `None`
* `loaner_adhar` must be 12 digits, else `None`

---

## Mapping Logic (`app/main.py`)

* Column alias mapping supports common header variants.
* Header row detection scans initial rows to find likely header row.
* Content heuristic fallback infers:

  * Aadhaar from 12-digit values
  * Mobile from valid 10-digit values starting 6-9
  * Land from text containing `acre/hectare/ha`
  * Description from longer text fragments
* Missing/empty IDs are auto-generated to keep inserts stable.

---

## Optional LLM Mapping Helper (`app/llm_service.py`)

Contains async helper `call_llm_async(...)` that can call external workflow API and parse JSON payloads.

Current `upload` flow in `main.py` uses external LLM by default.

---

## Alembic Notes

* `alembic/env.py` is wired to `Base.metadata` for autogenerate support.
* Revision files include:

  * `0295b84f9ca6_recover_missing_revision.py`
  * `8fc4e72f6e5a_create_llm_mapping_table.py`

---

## Useful Commands

```powershell
# Show current Alembic revision
alembic current

# Upgrade to latest
alembic upgrade head

# Create new migration (if model changes)
alembic revision --autogenerate -m "your message"
```

---

## Troubleshooting

### 400 Uploaded file is empty

* Ensure file is selected and not zero bytes.

### 400 Excel columns could not be mapped...

* Check header row and required field presence/structure.

### 500 DB connection errors

* Validate `.env` DB values and MySQL availability.

### Order appears as 1,10,11,...

* Use API responses (`/loaners` or `/upload` `data`), which apply numeric-aware ordering.


