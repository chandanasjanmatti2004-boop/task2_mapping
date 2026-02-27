import httpx
import os
import json
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL")
TOKEN = os.getenv("DVARA_TOKEN")


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()


def _parse_mapped_payload(mapped):
    if isinstance(mapped, dict):
        return [mapped]

    if isinstance(mapped, list):
        if all(isinstance(item, dict) for item in mapped):
            return mapped
        raise HTTPException(status_code=502, detail="LLM returned a list with non-object items")

    if isinstance(mapped, str):
        raw = _strip_code_fences(mapped)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail=f"LLM returned invalid JSON string: {exc.msg}") from exc
        return _parse_mapped_payload(parsed)

    raise HTTPException(status_code=502, detail="Unsupported LLM response format")


async def call_llm_async(excel_columns, sample_data, file_bytes=None, filename="upload.xlsx", content_type=None):
    if not API_URL:
        raise HTTPException(status_code=500, detail="Missing API_URL in environment")

    if not TOKEN:
        raise HTTPException(status_code=500, detail="Missing DVARA_TOKEN in environment")

    task = (
        "Read the uploaded file and map each input row to this exact schema, then return ONLY a JSON array: "
        "[loaner_id, fullname, mobile_no, loaner_adhar, total_amount, total_land, descrition]. "
        "Do not invent or modify people. Do not add demo/sample rows. "
        f"Output row count must equal input row count ({len(sample_data)}). "
        f"Input columns: {json.dumps(excel_columns)}."
    )

    headers = {
        "Authorization": f"Bearer {TOKEN}"
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            if file_bytes:
                response = await client.post(
                    API_URL,
                    headers=headers,
                    data={"task": task},
                    files={
                        "file": (
                            filename or "upload.xlsx",
                            file_bytes,
                            content_type or "application/octet-stream",
                        )
                    },
                )
            else:
                response = await client.post(
                    API_URL,
                    headers=headers,
                    json={"task": task},
                )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body_preview = response.text[:300]
            raise HTTPException(
                status_code=502,
                detail=f"LLM API HTTP {response.status_code}: {body_preview}",
            ) from exc

        try:
            result = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="LLM API returned non-JSON response") from exc

        if result.get("status") != "completed":
            upstream_error = result.get("error") or "LLM workflow did not complete"
            raise HTTPException(status_code=502, detail=f"LLM workflow failed: {upstream_error}")

        mapped_json = result.get("result", {}).get("result")

        if not mapped_json:
            raise HTTPException(status_code=502, detail="Empty mapped payload from LLM")

        return _parse_mapped_payload(mapped_json)

    except HTTPException:
        raise
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to call LLM API: {exc}") from exc

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
