from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import case, cast, Integer
import pandas as pd
from io import BytesIO
import math
import re
from uuid import uuid4

from .database import SessionLocal, engine
from .models import Base, Loaner
from .validator import validate_and_clean, REQUIRED_FIELDS

app = FastAPI()

Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _normalize_column_name(name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", str(name).strip().lower())
    return re.sub(r"_+", "_", normalized).strip("_")


def _clean_nan(value):
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


FIELD_ALIASES = {
    "loaner_id": {"loaner_id", "loanerid", "id", "app_id", "application_id"},
    "fullname": {"fullname", "full_name", "name", "customer_name"},
    "mobile_no": {"mobile_no", "mobile", "mobile_number", "phone", "phone_no"},
    "loaner_adhar": {"loaner_adhar", "loaner_aadhar", "aadhar", "aadhaar", "adhar_no"},
    "total_amount": {"total_amount", "amount", "loan_amount", "total_loan_amount"},
    "total_land": {"total_land", "land", "land_size", "land_area"},
    "descrition": {"descrition", "description", "purpose", "remarks"},
}


def _resolve_field_mapping(df: pd.DataFrame):
    normalized_to_actual = {}
    for col in df.columns:
        normalized = _normalize_column_name(col)
        if not normalized.startswith("unnamed"):
            normalized_to_actual[normalized] = col

    field_to_column = {}
    for field in REQUIRED_FIELDS:
        candidates = FIELD_ALIASES.get(field, {field})
        matched_col = None
        for alias in candidates:
            alias_normalized = _normalize_column_name(alias)
            if alias_normalized in normalized_to_actual:
                matched_col = normalized_to_actual[alias_normalized]
                break
        if matched_col is None:
            return None
        field_to_column[field] = matched_col
    return field_to_column


def _build_alias_to_field():
    alias_to_field = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            alias_to_field[_normalize_column_name(alias)] = field
    return alias_to_field


ALIAS_TO_FIELD = _build_alias_to_field()


def _detect_header_row(file_bytes: bytes, max_rows: int = 15):
    probe_df = pd.read_excel(BytesIO(file_bytes), header=None)
    check_rows = min(len(probe_df.index), max_rows)
    best_idx = None
    best_score = 0
    for i in range(check_rows):
        raw_cells = probe_df.iloc[i].tolist()
        normalized = {
            _normalize_column_name(cell)
            for cell in raw_cells
            if cell is not None and str(cell).strip()
        }
        matched_fields = {ALIAS_TO_FIELD[n] for n in normalized if n in ALIAS_TO_FIELD}
        score = len(matched_fields)
        if score > best_score:
            best_score = score
            best_idx = i
        if score == len(REQUIRED_FIELDS):
            return i
    if best_score >= 4:
        return best_idx
    return None


def _load_excel_with_best_header(file_bytes: bytes):
    df = pd.read_excel(BytesIO(file_bytes))
    if _resolve_field_mapping(df) is not None:
        return df

    header_row = _detect_header_row(file_bytes)
    if header_row is not None:
        return pd.read_excel(BytesIO(file_bytes), header=header_row)
    return df


def _extract_direct_rows(df: pd.DataFrame):
    df = df.dropna(how="all")
    field_to_column = _resolve_field_mapping(df)
    if field_to_column is None:
        return None

    selected_cols = [field_to_column[field] for field in REQUIRED_FIELDS]
    direct_rows = []
    for record in df[selected_cols].to_dict(orient="records"):
        direct_row = {}
        for field, col in zip(REQUIRED_FIELDS, selected_cols):
            direct_row[field] = _clean_nan(record.get(col))
        direct_rows.append(direct_row)
    return direct_rows


def _extract_rows_by_content(df: pd.DataFrame):
    df = df.dropna(how="all")
    inferred_rows = []
    for idx, row in enumerate(df.itertuples(index=False), start=1):
        values = [_clean_nan(v) for v in row if _clean_nan(v) is not None]
        if not values:
            continue

        inferred = {field: None for field in REQUIRED_FIELDS}
        text_candidates = []
        numeric_candidates = []

        for value in values:
            text = str(value).strip()
            digits = re.sub(r"\D", "", text)
            lower = text.lower()

            if inferred["total_land"] is None and re.search(r"\b(acre|acres|hectare|hectares|ha)\b", lower):
                inferred["total_land"] = text
                continue

            if inferred["loaner_adhar"] is None and len(digits) == 12:
                inferred["loaner_adhar"] = digits
                continue

            if (
                inferred["mobile_no"] is None
                and len(digits) == 10
                and digits[0] in {"6", "7", "8", "9"}
            ):
                inferred["mobile_no"] = digits
                continue

            if re.match(r"^[A-Za-z]{1,5}[-_ ]?\d{1,}$", text) and inferred["loaner_id"] is None:
                inferred["loaner_id"] = text.replace(" ", "")
                continue

            if re.fullmatch(r"\d+(\.\d+)?", text):
                numeric_candidates.append(text)
            else:
                text_candidates.append(text)

        if text_candidates:
            inferred["descrition"] = max(text_candidates, key=len)
            for candidate in text_candidates:
                if candidate != inferred["descrition"] and len(candidate.split()) <= 4:
                    inferred["fullname"] = candidate
                    break

        for candidate in numeric_candidates:
            try:
                n = float(candidate)
            except ValueError:
                continue
            if inferred["total_amount"] is None and n >= 1000:
                inferred["total_amount"] = n
            if inferred["loaner_id"] is None and n.is_integer() and 0 < n < 10_000:
                inferred["loaner_id"] = str(int(n))

        if inferred["loaner_id"] is None:
            inferred["loaner_id"] = f"TEMP{idx}"

        inferred_rows.append(inferred)

    return inferred_rows if inferred_rows else None


def _ensure_loaner_id(value, index, batch_tag):
    if value is None:
        return f"AUTO{batch_tag}{index:04d}"
    text = str(value).strip()
    if not text:
        return f"AUTO{batch_tag}{index:04d}"
    if text.endswith(".0"):
        try:
            return str(int(float(text)))
        except Exception:
            return text
    return text


def _loaner_sort_key(loaner_id):
    text = "" if loaner_id is None else str(loaner_id).strip()
    match = re.match(r"^([A-Za-z]+)?0*([0-9]+)$", text)
    if match:
        prefix = (match.group(1) or "").lower()
        num = int(match.group(2))
        return (0, prefix, num, text.lower())
    return (1, text.lower(), 0, text.lower())


@app.get("/loaners")
def list_loaners(db: Session = Depends(get_db)):
    numeric_first = case(
        (Loaner.loaner_id.op("REGEXP")(r"^[0-9]+$"), 0),
        else_=1,
    )
    rows = (
        db.query(Loaner)
        .order_by(numeric_first, cast(Loaner.loaner_id, Integer), Loaner.loaner_id)
        .all()
    )
    return {
        "count": len(rows),
        "data": [
            {
                "loaner_id": r.loaner_id,
                "fullname": r.fullname,
                "mobile_no": r.mobile_no,
                "loaner_adhar": r.loaner_adhar,
                "total_amount": r.total_amount,
                "total_land": r.total_land,
                "descrition": r.descrition,
            }
            for r in rows
        ],
    }


@app.post("/upload/")
async def upload_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        df = _load_excel_with_best_header(file_bytes)

        direct_rows = _extract_direct_rows(df)
        mapping_source = "direct_header"
        if direct_rows is None:
            mapped_rows = _extract_rows_by_content(df)
            mapping_source = "content_heuristic"
            if mapped_rows is None:
                available_columns = [_normalize_column_name(col) for col in df.columns]
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Excel columns could not be mapped to required fields. "
                        f"Required fields: {REQUIRED_FIELDS}. "
                        f"Detected columns: {available_columns}"
                    ),
                )
        else:
            mapped_rows = direct_rows

        clean_data = validate_and_clean(mapped_rows)
        batch_tag = uuid4().hex[:8].upper()

        inserted = 0
        skipped = 0
        failed = 0

        for i, row in enumerate(clean_data, start=1):
            row["loaner_id"] = _ensure_loaner_id(row.get("loaner_id"), i, batch_tag)
            try:
                with db.begin_nested():
                    db.add(Loaner(**row))
                inserted += 1
            except IntegrityError:
                skipped += 1
            except Exception:
                failed += 1

        db.commit()

        numeric_first = case(
            (Loaner.loaner_id.op("REGEXP")(r"^[0-9]+$"), 0),
            else_=1,
        )
        ordered_rows = (
            db.query(Loaner)
            .order_by(numeric_first, cast(Loaner.loaner_id, Integer), Loaner.loaner_id)
            .all()
        )

        return {
            "status": "success",
            "mapping_source": mapping_source,
            "rows_inserted": inserted,
            "duplicates_skipped": skipped,
            "failed_rows": failed,
            "total_processed": len(clean_data),
            "preview": clean_data[:3],
            "data": [
                {
                    "loaner_id": r.loaner_id,
                    "fullname": r.fullname,
                    "mobile_no": r.mobile_no,
                    "loaner_adhar": r.loaner_adhar,
                    "total_amount": r.total_amount,
                    "total_land": r.total_land,
                    "descrition": r.descrition,
                }
                for r in ordered_rows
            ],
        }

    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
