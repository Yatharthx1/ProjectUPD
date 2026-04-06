"""
server.py - BLUE FastAPI backend.

This server now routes analysis through the real WQI engine and treatment
recommender in src/, instead of maintaining a separate scoring implementation.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.engine.wqi_calculator import calculate_wqi
from src.llm.chat_agent import SYSTEM_PROMPT, _tool_extract_and_validate_parameters, _turn, is_report_request
from src.reports.generator import generate_batch_report, generate_pdf_report
from src.treatment.recommender import get_recommendations

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


def _parse_allowed_origins() -> list[str]:
    configured = [
        origin.strip().rstrip("/")
        for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ]
    if configured:
        return configured
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]


ALLOWED_ORIGINS = _parse_allowed_origins()
MAX_REQUEST_BYTES = int(os.getenv("MAX_REQUEST_BYTES", str(512 * 1024)))
MAX_CHAT_MESSAGE_LENGTH = int(os.getenv("MAX_CHAT_MESSAGE_LENGTH", "1500"))
MAX_CSV_BYTES = int(os.getenv("MAX_CSV_BYTES", str(2 * 1024 * 1024)))
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_RULES = {
    "/api/chat/extract": int(os.getenv("RATE_LIMIT_CHAT_PER_MINUTE", "20")),
    "/api/analyze": int(os.getenv("RATE_LIMIT_ANALYZE_PER_MINUTE", "60")),
    "/api/analyze/csv": int(os.getenv("RATE_LIMIT_CSV_PER_MINUTE", "10")),
    "/api/report": int(os.getenv("RATE_LIMIT_REPORT_PER_MINUTE", "10")),
    "/api/report/csv": int(os.getenv("RATE_LIMIT_REPORT_PER_MINUTE", "10")),
}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
_rate_limit_state: dict[tuple[str, str], list[float]] = {}


app = FastAPI(title="BLUE API", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR / "Main-page"
PROFILES_DIR = BASE_DIR / "config" / "profiles"

PROFILE_MAP = {
    "drinking": "bis_drinking",
    "who": "who_drinking",
    "agriculture": "fao_agriculture",
    "industrial": "industrial",
    "aquaculture": "aquaculture",
}

_PARAM_KEY_MAP: dict[str, dict[str, str]] = {
    "bis_drinking": {
        "Coliform": "coliform",
        "TotalColiform": "coliform",
        "Arsenic": "arsenic",
        "Lead": "lead",
        "Nitrates": "nitrates",
        "Nitrate": "nitrates",
        "pH": "pH",
        "Turbidity": "turbidity",
        "TDS": "TDS",
        "Hardness": "hardness",
        "Chlorides": "chlorides",
        "Chloride": "chlorides",
        "Sulphate": "sulphate",
        "Sulfate": "sulphate",
        "Fluoride": "fluoride",
        "Iron": "iron",
        "Dissolved Oxygen": "dissolved_oxygen",
        "DissolvedOxygen": "dissolved_oxygen",
        "DO": "dissolved_oxygen",
        "BOD": "BOD",
    },
    "who_drinking": {
        "Turbidity": "turbidity",
        "Hardness": "hardness",
        "Chloride": "chlorides",
        "Sulfate": "sulphate",
        "Nitrate": "nitrates",
        "Nitrite": "nitrites",
        "Fluoride": "fluoride",
        "Iron": "iron",
        "Arsenic": "arsenic",
        "Lead": "lead",
        "DO": "dissolved_oxygen",
        "Coliform": "coliform",
    },
    "fao_agriculture": {
        "Nitrate": "Nitrate_N",
        "Sulfate": "Sulfate",
    },
    "aquaculture": {
        "Ammonia": "Ammonia_N",
        "Salinity": "TDS",
    },
}

_DISPLAY_NAMES = {
    "nitrates": "Nitrates",
    "nitrites": "Nitrite",
    "chlorides": "Chlorides",
    "sulphate": "Sulphate",
    "turbidity": "Turbidity",
    "hardness": "Hardness",
    "fluoride": "Fluoride",
    "iron": "Iron",
    "arsenic": "Arsenic",
    "lead": "Lead",
    "coliform": "Coliform",
    "dissolved_oxygen": "Dissolved Oxygen",
    "Ammonia_N": "Ammonia",
    "Nitrate_N": "Nitrate-N",
    "H2S": "Hydrogen Sulfide",
    "Oil_Grease": "Oil & Grease",
    "BOD": "BOD",
}

CLASSIFICATION_TO_ZONE = {
    "Excellent": "IDEAL",
    "Good": "ACCEPTABLE",
    "Poor": "PERMISSIBLE",
    "Very Poor": "BREACH",
    "Unsuitable": "DEFICIENT",
    "UNSAFE": "DEFICIENT",
}

FLAG_TYPE_MAP = {
    "critical": "bad",
    "violation": "bad",
    "warning": "warn",
    "info": "ok",
}

FOLLOW_UP_HINTS = {
    "bis_drinking": "If you have them, share arsenic, lead, coliform, nitrates, and dissolved oxygen for a stronger drinking-water assessment.",
    "who_drinking": "If you have them, share nitrite, cadmium, manganese, and coliform values too.",
    "fao_agriculture": "If you have them, share SAR, boron, sodium, bicarbonate, and chloride for irrigation analysis.",
    "industrial": "If you have them, share hardness, silica, dissolved oxygen, and alkalinity for industrial suitability.",
    "aquaculture": "If you have them, share dissolved oxygen, ammonia, nitrite, and temperature for aquaculture analysis.",
}

_session: dict[str, Any] = {"profile": "drinking", "chat_params": {}, "chat_history": None}


class ProfileRequest(BaseModel):
    profile: str


class AnalyzeRequest(BaseModel):
    profile: str
    mode: str
    params: dict[str, float] | None = None
    filename: str | None = Field(default=None, max_length=200)
    chat_session: bool = False


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_CHAT_MESSAGE_LENGTH)
    profile: str


class ReportRequest(BaseModel):
    profile: str
    mode: str
    params: dict[str, float] | None = None
    filename: str | None = Field(default=None, max_length=200)
    chat_session: bool = False
    meta: dict[str, str] | None = None


def _profile_id(profile_key: str) -> str:
    backend_id = PROFILE_MAP.get(profile_key, profile_key)
    path = PROFILES_DIR / f"{backend_id}.json"
    if not path.exists():
        raise HTTPException(404, f"Profile config not found: {backend_id}")
    return backend_id


def _load_profile(profile_key: str) -> dict:
    backend_id = _profile_id(profile_key)
    return json.loads((PROFILES_DIR / f"{backend_id}.json").read_text(encoding="utf-8-sig"))


def _sanitize_meta_value(value: str, fallback: str = "") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 _.,:/()-]", "", (value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:120] or fallback


def _safe_filename_stem(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", (value or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_.-")
    return cleaned[:64] or fallback


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(request: Request) -> None:
    limit = RATE_LIMIT_RULES.get(request.url.path)
    if not limit:
        return
    now = time.monotonic()
    key = (_client_ip(request), request.url.path)
    timestamps = [ts for ts in _rate_limit_state.get(key, []) if now - ts < RATE_LIMIT_WINDOW_SECONDS]
    if len(timestamps) >= limit:
        raise HTTPException(429, "Too many requests. Please slow down and try again shortly.")
    timestamps.append(now)
    _rate_limit_state[key] = timestamps


async def _run_with_timeout(func, *args):
    return await asyncio.wait_for(asyncio.to_thread(func, *args), timeout=LLM_TIMEOUT_SECONDS)


def _validate_csv_upload(file: UploadFile, content: bytes) -> None:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Only CSV uploads are allowed.")
    if len(content) > MAX_CSV_BYTES:
        raise HTTPException(413, f"CSV file is too large. Maximum allowed size is {MAX_CSV_BYTES} bytes.")


def _normalise_params(params: dict[str, Any], profile_id: str) -> dict[str, float]:
    key_map = _PARAM_KEY_MAP.get(profile_id, {})
    out: dict[str, float] = {}
    for raw_key, raw_value in params.items():
        if raw_value in ("", None):
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        out[key_map.get(raw_key, raw_key)] = value
    return out


def _format_value(value: Any) -> str:
    if value is None:
        return "--"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:.3g}"
    return str(value)


def _frontend_param_zone(sub_zone: str) -> str:
    return {
        "ideal": "IDEAL",
        "acceptable": "ACCEPTABLE",
        "permissible": "PERMISSIBLE",
        "breach": "BREACH",
        "deficient": "DEFICIENT",
    }.get((sub_zone or "").lower(), "ACCEPTABLE")


def _format_frontend_result(result: dict, profile_id: str, recommendations: dict | None = None) -> dict:
    profile_cfg = _load_profile(profile_id)
    params_cfg = profile_cfg.get("parameters", {})
    sub_indices = result.get("sub_indices", {})

    formatted_params = []
    for param, info in sub_indices.items():
        if info.get("zone") in {"NO_DATA", "INVALID", "SUSPECT"}:
            continue
        cfg = params_cfg.get(param, {})
        unit = cfg.get("unit", "")
        if unit == "dimensionless":
            unit = ""
        formatted_params.append(
            {
                "name": _DISPLAY_NAMES.get(param, param),
                "value": _format_value(info.get("value")),
                "unit": unit,
                "zone": _frontend_param_zone(info.get("zone")),
            }
        )

    zone_order = {"DEFICIENT": 0, "BREACH": 1, "PERMISSIBLE": 2, "ACCEPTABLE": 3, "IDEAL": 4}
    formatted_params.sort(key=lambda item: zone_order.get(item["zone"], 99))

    formatted_flags = []
    for flag in result.get("flags", []):
        formatted_flags.append(
            {
                "type": FLAG_TYPE_MAP.get(flag.get("severity", "info"), "ok"),
                "msg": flag.get("message", ""),
            }
        )

    if recommendations:
        for rec in recommendations.get("recommendations", [])[:3]:
            label = _DISPLAY_NAMES.get(rec.get("parameter", ""), rec.get("parameter", ""))
            formatted_flags.append(
                {
                    "type": "warn" if rec.get("priority") != "LOW" else "ok",
                    "msg": f"{label}: {rec.get('treatment', '')}",
                }
            )

    raw_wqi = result.get("wqi")
    classification = result.get("classification", "UNSAFE")
    return {
        "score": round(raw_wqi, 2) if raw_wqi is not None else None,
        "zone": CLASSIFICATION_TO_ZONE.get(classification, "DEFICIENT"),
        "status": result.get("status", "UNKNOWN"),
        "classification": classification,
        "confidence": result.get("confidence", 0),
        "params": formatted_params,
        "flags": formatted_flags[:10],
        "raw_wqi": raw_wqi,
        "recommendations": recommendations or {},
        "dominant_issues": result.get("dominant_issues", []),
    }


def _groq_client() -> Any | None:
    if OpenAI is None:
        return None
    if os.getenv("GROQ_API_KEY"):
        return OpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1",
        )
    return None


def _build_reply(params: dict[str, float], profile_id: str) -> str:
    if params:
        extracted = ", ".join(f"{k}={v}" for k, v in params.items())
        return f"Captured {extracted}. {FOLLOW_UP_HINTS.get(profile_id, 'Share any remaining measurements and then run the analysis.')}"
    return (
        "I could not find numeric readings yet. Try a message like "
        "\"Coliform 0, Arsenic 0.005, Lead 0.01, Nitrates 32, pH 7.2, TDS 480\"."
    )


def _llm_extract(message: str, profile_id: str) -> dict:
    try:
        extracted = _tool_extract_and_validate_parameters(message, "")
    except Exception as exc:
        return {
            "reply": f"LLM connection failed, so I could not parse that message fully. { _build_reply({}, profile_id) }",
            "params": {},
            "validation_issues": [],
            "extraction_method": f"error:{type(exc).__name__}",
        }
    params = _normalise_params(extracted.get("parameters", {}), profile_id)
    issues = extracted.get("validation_issues", [])
    notes = extracted.get("qualitative_notes", [])
    method = extracted.get("_extraction_method", "unknown")

    if params:
        reply = _build_reply(params, profile_id)
    elif notes:
        reply = " ".join(str(note) for note in notes if note)
    else:
        reply = (
            f"No parameters were extracted by the {method} path. "
            "Try sending readings like \"pH: 7.2, TDS: 480, turbidity: 3\"."
        )

    if issues:
        issue_bits = ", ".join(f"{item.get('parameter')}: {item.get('issue')}" for item in issues[:3])
        reply = f"{reply} Please recheck these values: {issue_bits}."

    return {
        "reply": reply,
        "params": params,
        "validation_issues": issues,
        "extraction_method": method,
    }


def build_timeout_extract_result() -> dict:
    return {
        "reply": "The AI extraction request timed out. Please try again or send a shorter message with direct readings.",
        "params": {},
        "validation_issues": [],
        "extraction_method": "timeout",
    }


def _report_ready_reply(params: dict[str, float], profile_id: str) -> str:
    result, _recommendations = _compute_analysis_bundle(params, profile_id)
    status = str(result.get("status", "")).upper()
    classification = str(result.get("classification", ""))
    raw_wqi = result.get("wqi")

    if raw_wqi is None or status == "UNSAFE":
        return (
            "Your PDF report is ready. This sample is marked UNSAFE, so no numeric WQI is shown in the report."
        )

    return (
        f"Your PDF report is ready. The analysis shows a WQI of {round(float(raw_wqi), 2)} "
        f"with classification {classification or 'available'}."
    )


@app.middleware("http")
async def harden_requests(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_REQUEST_BYTES:
                    return JSONResponse(status_code=413, content={"detail": "Request body too large."})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header."})

    try:
        _enforce_rate_limit(request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
    return response


def _analyze_params(params: dict[str, float], profile_id: str) -> dict:
    if not params:
        return {
            "score": None,
            "zone": "ACCEPTABLE",
            "status": "UNKNOWN",
            "classification": "Pending",
            "confidence": 0,
            "params": [],
            "flags": [{"type": "warn", "msg": "No parameters available yet. Add readings first."}],
            "raw_wqi": None,
            "recommendations": {},
            "dominant_issues": [],
        }

    result = calculate_wqi(params, profile_id)
    recommendations = get_recommendations(wqi_result=result, profile_id=profile_id)
    return _format_frontend_result(result, profile_id, recommendations)


def _compute_analysis_bundle(params: dict[str, float], profile_id: str) -> tuple[dict, dict]:
    result = calculate_wqi(params, profile_id)
    recommendations = get_recommendations(wqi_result=result, profile_id=profile_id)
    return result, recommendations


def _resolve_report_meta(meta: dict[str, str] | None, profile_id: str) -> dict[str, str]:
    meta = meta or {}
    sample_id = _safe_filename_stem(meta.get("sample_id", f"S{datetime.now().strftime('%H%M%S')}"), "sample")
    return {
        "sample_id": sample_id,
        "location": _sanitize_meta_value(meta.get("location", "Unknown"), "Unknown"),
        "profile_id": profile_id,
        "tested_by": _sanitize_meta_value(meta.get("tested_by", "")),
        "lab_ref": _sanitize_meta_value(meta.get("lab_ref", "")),
        "date": _sanitize_meta_value(meta.get("date", datetime.now().strftime("%d %b %Y")), datetime.now().strftime("%d %b %Y")),
    }


def _analyze_csv_data(csv_text: str, profile_key: str) -> list[dict]:
    profile_id = _profile_id(profile_key)
    reader = csv.DictReader(io.StringIO(csv_text))
    results: list[dict] = []

    for index, row in enumerate(reader, start=1):
        sample_id = row.get("sample_id") or f"S{index:03d}"
        location = row.get("location") or row.get("site") or "--"
        params = _normalise_params(
            {k: v for k, v in row.items() if k not in {"sample_id", "location", "site"}},
            profile_id,
        )
        if not params:
            continue

        formatted = _analyze_params(params, profile_id)
        formatted["sample_id"] = sample_id
        formatted["location"] = location
        results.append(formatted)

    return results


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "1.1.0",
        "profile": _session["profile"],
        "llm_configured": _groq_client() is not None,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.post("/api/profile")
async def set_profile(req: ProfileRequest):
    backend_id = _profile_id(req.profile)
    cfg = _load_profile(req.profile)
    _session["profile"] = req.profile
    _session["chat_params"] = {}
    _session["chat_history"] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return {"ok": True, "profile": req.profile, "backend_profile": backend_id, "name": cfg.get("name", backend_id)}


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest, request: Request):
    profile_id = _profile_id(req.profile)

    if req.mode == "csv":
        return {
            "score": None,
            "zone": "ACCEPTABLE",
            "status": "UNKNOWN",
            "classification": "Pending",
            "confidence": 0,
            "params": [],
            "flags": [{"type": "warn", "msg": "Upload a CSV file and use Run Batch Analysis."}],
            "raw_wqi": None,
            "recommendations": {},
            "dominant_issues": [],
        }

    if req.mode == "manual" and req.params:
        return _analyze_params(_normalise_params(req.params, profile_id), profile_id)

    if req.mode == "llm" or req.chat_session:
        return _analyze_params(dict(_session.get("chat_params", {})), profile_id)

    raise HTTPException(400, "Unsupported analysis mode or missing parameters.")


@app.post("/api/analyze/csv")
async def analyze_csv(request: Request, profile: str = "drinking", file: UploadFile = File(...)):
    content = await file.read()
    _validate_csv_upload(file, content)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    results = _analyze_csv_data(text, profile)
    if not results:
        raise HTTPException(400, "No valid rows found in CSV. Check columns like sample_id,location,pH,TDS,...")

    return {"results": results, "count": len(results)}


@app.post("/api/chat/extract")
async def chat_extract(req: ChatRequest, request: Request):
    profile_id = _profile_id(req.profile)
    if not _session.get("chat_history"):
        _session["chat_history"] = [{"role": "system", "content": SYSTEM_PROMPT}]
    wants_report = is_report_request(req.message)

    try:
        agent_reply = await _run_with_timeout(_turn, _session["chat_history"], req.message)
    except Exception:
        agent_reply = None

    try:
        extracted = await _run_with_timeout(_llm_extract, req.message, profile_id)
    except asyncio.TimeoutError:
        extracted = build_timeout_extract_result()
    new_params = extracted.get("params", {})
    if new_params:
        _session.setdefault("chat_params", {}).update(new_params)

    total_params = len(_session.get("chat_params", {}))
    report_ready = wants_report and total_params > 0
    report_missing_data = wants_report and total_params == 0
    if report_missing_data and not agent_reply:
        agent_reply = "I can generate the PDF once you share at least one measured reading or run an analysis first."
    elif report_ready:
        agent_reply = _report_ready_reply(dict(_session.get("chat_params", {})), profile_id)

    return {
        "reply": agent_reply or extracted.get("reply", "Parameters noted. Run the analysis when ready."),
        "params_extracted": new_params,
        "total_params": total_params,
        "validation_issues": extracted.get("validation_issues", []),
        "extraction_method": extracted.get("extraction_method", "unknown"),
        "report_ready": report_ready,
        "report_missing_data": report_missing_data,
    }


@app.post("/api/report")
async def create_report(req: ReportRequest, request: Request):
    profile_id = _profile_id(req.profile)

    if req.mode == "manual" and req.params:
        params = _normalise_params(req.params, profile_id)
    elif req.mode == "llm" or req.chat_session:
        params = dict(_session.get("chat_params", {}))
    else:
        raise HTTPException(400, "Report generation currently supports manual and chat-session analysis.")

    if not params:
        raise HTTPException(400, "No parameters available for report generation.")

    result, recommendations = _compute_analysis_bundle(params, profile_id)
    meta = _resolve_report_meta(req.meta, profile_id)

    reports_dir = BASE_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)
    output_path = reports_dir / f"report_{_safe_filename_stem(meta['sample_id'], 'report')}.pdf"
    path = generate_pdf_report(result, recommendations, str(output_path), meta)
    return FileResponse(path, media_type="application/pdf", filename=Path(path).name, headers={"Content-Disposition": f'attachment; filename="{Path(path).name}"'})


@app.post("/api/report/csv")
async def create_batch_report(request: Request, profile: str = "drinking", file: UploadFile = File(...)):
    profile_id = _profile_id(profile)
    content = await file.read()
    _validate_csv_upload(file, content)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    results: list[dict] = []
    recs: list[dict] = []
    meta_list: list[dict] = []

    for index, row in enumerate(reader, start=1):
        params = _normalise_params(
            {k: v for k, v in row.items() if k not in {"sample_id", "location", "site"}},
            profile_id,
        )
        if not params:
            continue
        result, recommendations = _compute_analysis_bundle(params, profile_id)
        results.append(result)
        recs.append(recommendations)
        meta_list.append(
            _resolve_report_meta(
                {
                    "sample_id": row.get("sample_id", f"S{index:03d}"),
                    "location": row.get("location") or row.get("site") or "--",
                },
                profile_id,
            )
        )

    if not results:
        raise HTTPException(400, "No valid rows found in CSV for report generation.")

    reports_dir = BASE_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)
    output_path = reports_dir / f"batch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    path = generate_batch_report(results, recs, str(output_path), meta_list, f"{profile_id} Batch Report")
    return FileResponse(path, media_type="application/pdf", filename=Path(path).name, headers={"Content-Disposition": f'attachment; filename="{Path(path).name}"'})


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    print("\n  BLUE - API Server")
    print("  Frontend : http://localhost:8000/")
    print("  API docs : http://localhost:8000/docs")
    print("  Health   : http://localhost:8000/health\n")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
