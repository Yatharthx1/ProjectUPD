"""
server.py — Project UPD  |  FastAPI REST Backend
=================================================
Serves the Main-page frontend with real WQI analysis.

Usage:
    pip install fastapi uvicorn python-multipart openai python-dotenv
    uvicorn server:app --reload --port 8000

Endpoints:
    GET  /health              — liveness check
    POST /api/profile         — set active profile
    POST /api/analyze         — run WQI analysis
    POST /api/analyze/csv     — batch CSV analysis
    POST /api/chat/extract    — LLM parameter extraction
"""

import io
import json
import os
import csv as csv_module
from pathlib import Path
from typing import Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# ── Optional LLM support ───────────────────────────────────────────────────────
try:
    from openai import OpenAI
    _openai_available = True
except ImportError:
    _openai_available = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── App setup ──────────────────────────────────────────────────────────────────

app = FastAPI(title="Project UPD API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Frontend directory
FRONTEND_DIR = Path(__file__).parent / "Main-page"

# ── Profile config paths ───────────────────────────────────────────────────────

PROFILES_DIR = Path(__file__).parent / "config" / "profiles"

# Maps frontend profile keys → backend JSON profile filenames
PROFILE_MAP = {
    "drinking":    "bis_drinking",
    "agriculture": "fao_agriculture",
    "industrial":  "industrial",
    "aquaculture": "aquaculture",
}

# In-memory session state (single-user dev server)
_session: dict[str, Any] = {
    "profile": "drinking",
    "chat_params": {},
}

# ── Pydantic models ────────────────────────────────────────────────────────────

class ProfileRequest(BaseModel):
    profile: str

class AnalyzeRequest(BaseModel):
    profile: str
    mode: str                          # llm | manual | csv
    params: dict[str, float] | None = None
    filename: str | None = None
    chat_session: bool = False

class ChatRequest(BaseModel):
    message: str
    profile: str

# ── Profile loader ─────────────────────────────────────────────────────────────

def load_profile(profile_key: str) -> dict:
    backend_id = PROFILE_MAP.get(profile_key, profile_key)
    path = PROFILES_DIR / f"{backend_id}.json"
    if not path.exists():
        raise HTTPException(404, f"Profile config not found: {backend_id}")
    return json.loads(path.read_text())

# ── WQI engine ─────────────────────────────────────────────────────────────────

ZONE_ORDER = ["IDEAL", "ACCEPTABLE", "PERMISSIBLE", "BREACH", "DEFICIENT"]

def _score_param(value: float, param_cfg: dict) -> tuple[float, str]:
    """
    Score a single parameter against its profile limits.
    Returns (sub_score 0-100, zone_name).
    """
    limits = param_cfg.get("limits", {})
    direction = param_cfg.get("direction", "up_bad")

    # Hard gate — any breach → DEFICIENT, score 0
    if param_cfg.get("layer") == "hard_gate":
        limit = limits.get("acceptable", 0)
        if direction == "up_bad" and value > limit:
            return 0.0, "DEFICIENT"
        return 100.0, "IDEAL"

    # ── up_bad: higher is worse ──────────────────────────────────────
    if direction == "up_bad":
        # ideal may be 0 (meaning "none is ideal"), or absent
        ideal_max   = limits.get("ideal",       limits.get("acceptable", float("inf")))
        accept_max  = limits.get("acceptable",  float("inf"))
        permit_max  = limits.get("permissible", float("inf"))

        # unwrap list → take upper bound
        if isinstance(ideal_max,  list): ideal_max  = ideal_max[1]  if len(ideal_max)  > 1 else ideal_max[0]
        if isinstance(accept_max, list): accept_max = accept_max[1] if len(accept_max) > 1 else accept_max[0]
        if isinstance(permit_max, list): permit_max = permit_max[1] if len(permit_max) > 1 else permit_max[0]

        # ideal_max == 0 means "zero is perfect, anything above degrades"
        if ideal_max == 0:
            if value == 0:
                return 100.0, "IDEAL"
            elif value <= accept_max:
                ratio = value / max(accept_max, 1e-9)
                return 85.0 - ratio * 25.0, "ACCEPTABLE"
            elif value <= permit_max:
                ratio = (value - accept_max) / max(permit_max - accept_max, 1e-9)
                return 60.0 - ratio * 20.0, "PERMISSIBLE"
            elif value <= permit_max * 2:
                return 25.0, "BREACH"
            else:
                return 0.0, "DEFICIENT"

        if value <= ideal_max:
            return 100.0, "IDEAL"
        elif value <= accept_max:
            ratio = (value - ideal_max) / max(accept_max - ideal_max, 1e-9)
            return 85.0 - ratio * 25.0, "ACCEPTABLE"
        elif value <= permit_max:
            ratio = (value - accept_max) / max(permit_max - accept_max, 1e-9)
            return 60.0 - ratio * 20.0, "PERMISSIBLE"
        elif value <= permit_max * 1.5:
            return 25.0, "BREACH"
        else:
            return 0.0, "DEFICIENT"

    # ── down_bad: lower is worse ─────────────────────────────────────
    elif direction == "down_bad":
        ideal_min  = limits.get("ideal",       limits.get("acceptable", 0))
        accept_min = limits.get("acceptable",  0)
        permit_min = limits.get("permissible", 0)

        if isinstance(ideal_min,  list): ideal_min  = ideal_min[0]
        if isinstance(accept_min, list): accept_min = accept_min[0]
        if isinstance(permit_min, list): permit_min = permit_min[0]

        if value >= ideal_min:
            return 100.0, "IDEAL"
        elif value >= accept_min:
            ratio = (ideal_min - value) / max(ideal_min - accept_min, 1e-9)
            return 85.0 - ratio * 25.0, "ACCEPTABLE"
        elif value >= permit_min:
            ratio = (accept_min - value) / max(accept_min - permit_min, 1e-9)
            return 60.0 - ratio * 20.0, "PERMISSIBLE"
        elif value >= permit_min * 0.5:
            return 25.0, "BREACH"
        else:
            return 0.0, "DEFICIENT"

    # ── both_bad: outside a range is worse ───────────────────────────
    elif direction == "both_bad":
        # Prefer "ideal" limits; fall back to "acceptable"
        ideal  = limits.get("ideal",       limits.get("acceptable", None))
        accept = limits.get("acceptable",  ideal)

        # Unwrap scalars to ranges where possible
        def _range(v):
            if isinstance(v, list) and len(v) == 2:
                return float(v[0]), float(v[1])
            if isinstance(v, (int, float)):
                return 0.0, float(v)          # treat scalar as upper bound, 0 as lower
            return None

        ir = _range(ideal)
        ar = _range(accept)

        if ir is None and ar is None:
            return 50.0, "ACCEPTABLE"          # can't score

        lo_i, hi_i = ir if ir else ar
        lo_a, hi_a = ar if ar else ir

        if lo_i <= value <= hi_i:
            return 100.0, "IDEAL"
        elif lo_a <= value <= hi_a:
            return 80.0, "ACCEPTABLE"
        else:
            lo_p = limits.get("permissible_low", lo_a * 0.7 if lo_a else 0)
            hi_p = limits.get("permissible",     hi_a * 1.3 if hi_a else float("inf"))
            if lo_p <= value <= hi_p:
                return 55.0, "PERMISSIBLE"
            elif lo_a * 0.4 <= value <= hi_a * 1.6:
                return 25.0, "BREACH"
            else:
                return 0.0, "DEFICIENT"

    return 50.0, "ACCEPTABLE"


def _zone_from_score(score: float) -> str:
    if score >= 90:  return "IDEAL"
    if score >= 70:  return "ACCEPTABLE"
    if score >= 45:  return "PERMISSIBLE"
    if score >= 20:  return "BREACH"
    return "DEFICIENT"


def _flag(param_name: str, value: float, unit: str, zone: str, limits: dict, direction: str) -> dict | None:
    """Generate a flag entry for a parameter."""
    val_str = f"{value} {unit}".strip()

    if zone == "IDEAL":
        return {"type": "ok", "msg": f"{param_name} {val_str} — within ideal range"}
    elif zone == "ACCEPTABLE":
        return {"type": "ok", "msg": f"{param_name} {val_str} — acceptable"}
    elif zone == "PERMISSIBLE":
        return {"type": "warn", "msg": f"{param_name} {val_str} — permissible but approaching limit; monitor closely"}
    elif zone == "BREACH":
        return {"type": "warn", "msg": f"{param_name} {val_str} — BREACH: exceeds recommended limit; treatment advised"}
    elif zone == "DEFICIENT":
        return {"type": "bad", "msg": f"{param_name} {val_str} — DEFICIENT / non-compliant; immediate action required"}
    return None


def compute_wqi(params: dict[str, float], profile_cfg: dict) -> dict:
    """
    Full WQI calculation against a loaded profile config.
    Returns result dict shaped for the frontend.
    """
    param_cfgs = profile_cfg.get("parameters", {})

    scored_params = []
    flags = []
    weighted_sum = 0.0
    total_weight = 0.0

    for key, cfg in param_cfgs.items():
        # Case-insensitive key match
        val = None
        for k, v in params.items():
            if k.lower() == key.lower():
                val = v
                break

        if val is None:
            continue  # skip params not provided

        sub_score, zone = _score_param(val, cfg)
        weight = cfg.get("weight", 0.05)

        # Hard gates with breach tank the whole score
        if cfg.get("layer") == "hard_gate" and zone == "DEFICIENT":
            weighted_sum += 0 * weight
        else:
            weighted_sum += sub_score * weight
        total_weight += weight

        unit = cfg.get("unit", "")
        if unit in ("dimensionless", ""):
            unit = ""

        # Format value: keep as integer if possible, else show up to 4 sig figs
        if val == int(val):
            val_str = str(int(val))
        else:
            val_str = f"{val:.4g}"

        scored_params.append({
            "name":  cfg.get("_display_name", key),
            "value": val_str,
            "unit":  unit,
            "zone":  zone,
        })

        flag = _flag(key, val, unit, zone, cfg.get("limits", {}), cfg.get("direction", "up_bad"))
        if flag:
            flags.append(flag)

    # Overall score
    if total_weight > 0:
        raw_score = weighted_sum / total_weight
    else:
        raw_score = 50.0

    # Hard gate override: any DEFICIENT param forces score cap
    has_hard_breach = any(
        p["zone"] == "DEFICIENT"
        for p in scored_params
        if param_cfgs.get(p["name"].lower(), {}).get("layer") == "hard_gate"
    )
    if has_hard_breach:
        raw_score = min(raw_score, 20.0)

    final_score = round(max(0, min(100, raw_score)))
    overall_zone = _zone_from_score(final_score)

    # Sort flags: bad → warn → ok
    order = {"bad": 0, "warn": 1, "ok": 2}
    flags.sort(key=lambda f: order.get(f["type"], 3))

    # Sort params: worst zone first
    zone_ord = {z: i for i, z in enumerate(ZONE_ORDER)}
    scored_params.sort(key=lambda p: zone_ord.get(p["zone"], 99))

    return {
        "score":   final_score,
        "zone":    overall_zone,
        "params":  scored_params,
        "flags":   flags[:10],   # cap at 10 flags
    }


# ── LLM extraction helper ──────────────────────────────────────────────────────

EXTRACT_SYSTEM = """You are a water quality parameter extractor.
The user will describe a water sample in natural language.
Extract all numeric water quality parameters you can identify.
Respond ONLY with a JSON object like:
{
  "reply": "Extracted: pH=7.2, TDS=480 mg/L. Do you have readings for iron or arsenic?",
  "params": {"pH": 7.2, "TDS": 480}
}
If no numeric parameters are found, return an empty params dict and ask a follow-up question.
Always be concise and helpful."""


def _llm_extract(message: str, profile: str) -> dict:
    """Call LLM to extract parameters from natural language. Falls back gracefully."""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")

    if not _openai_available or not api_key:
        # Fallback: simple keyword extraction
        return _keyword_extract(message)

    try:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user",   "content": f"Profile: {profile}\n\nSample description: {message}"},
            ],
            response_format={"type": "json_object"},
            max_tokens=400,
            temperature=0.2,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"[UPD] LLM extraction failed: {e}")
        return _keyword_extract(message)


def _keyword_extract(message: str) -> dict:
    """Simple regex-free keyword extractor for offline mode."""
    import re
    params = {}
    patterns = {
        "pH":        r"ph\s*[=:~≈]?\s*(\d+\.?\d*)",
        "TDS":       r"tds\s*[=:~≈]?\s*(\d+\.?\d*)",
        "Turbidity": r"turbidity\s*[=:~≈]?\s*(\d+\.?\d*)",
        "Hardness":  r"hardness\s*[=:~≈]?\s*(\d+\.?\d*)",
        "Iron":      r"iron\s*[=:~≈]?\s*(\d+\.?\d*)",
        "Nitrate":   r"nitrate[s]?\s*[=:~≈]?\s*(\d+\.?\d*)",
        "Fluoride":  r"fluoride\s*[=:~≈]?\s*(\d+\.?\d*)",
        "Chloride":  r"chloride[s]?\s*[=:~≈]?\s*(\d+\.?\d*)",
        "DO":        r"(?:do|dissolved\s*o(?:xygen)?)\s*[=:~≈]?\s*(\d+\.?\d*)",
        "EC":        r"(?:ec|conductivity)\s*[=:~≈]?\s*(\d+\.?\d*)",
    }
    msg_lower = message.lower()
    for name, pat in patterns.items():
        m = re.search(pat, msg_lower)
        if m:
            params[name] = float(m.group(1))

    if params:
        extracted = ", ".join(f"{k}={v}" for k, v in params.items())
        reply = f"Extracted parameters: {extracted}. Any additional readings available (heavy metals, ions)?"
    else:
        reply = (
            "Could not extract specific numeric values. Please provide readings like: "
            "\"pH 7.2, TDS 480 mg/L, Turbidity 3 NTU\" or similar."
        )

    return {"reply": reply, "params": params}


# ── CSV batch analysis ─────────────────────────────────────────────────────────

def analyze_csv_data(csv_text: str, profile_key: str) -> list[dict]:
    profile_cfg = load_profile(profile_key)
    results = []
    reader = csv_module.DictReader(io.StringIO(csv_text))
    for row in reader:
        sample_id = row.get("sample_id", f"S{len(results)+1:03d}")
        params = {}
        for k, v in row.items():
            if k == "sample_id":
                continue
            try:
                params[k] = float(v)
            except (ValueError, TypeError):
                pass
        if params:
            result = compute_wqi(params, profile_cfg)
            result["sample_id"] = sample_id
            results.append(result)
    return results


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "profile": _session["profile"],
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.post("/api/profile")
async def set_profile(req: ProfileRequest):
    if req.profile not in PROFILE_MAP:
        raise HTTPException(400, f"Unknown profile: {req.profile}. Valid: {list(PROFILE_MAP)}")
    _session["profile"] = req.profile
    _session["chat_params"] = {}  # clear accumulated chat params on profile switch

    # Load profile to confirm it exists
    cfg = load_profile(req.profile)
    return {
        "ok": True,
        "profile": req.profile,
        "name": cfg.get("name", req.profile),
    }


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    profile_cfg = load_profile(req.profile)

    params: dict[str, float] = {}

    if req.mode == "manual" and req.params:
        params = req.params

    elif req.mode == "llm" or req.chat_session:
        # Use params accumulated from chat turns
        params = dict(_session.get("chat_params", {}))
        if not params:
            # No chat params yet — return a prompt to the user
            return {
                "score": 0,
                "zone": "ACCEPTABLE",
                "params": [],
                "flags": [{"type": "warn", "msg": "No parameters extracted yet. Describe your water sample in the chat first, then click Run Analysis."}],
            }

    elif req.mode == "csv":
        # CSV mode: should use /api/analyze/csv endpoint
        return {"score": 0, "zone": "ACCEPTABLE", "params": [], "flags": [
            {"type": "warn", "msg": "Upload a CSV file and click Run Batch Analysis."}
        ]}

    if not params:
        raise HTTPException(400, "No parameters provided")

    return compute_wqi(params, profile_cfg)


@app.post("/api/analyze/csv")
async def analyze_csv(profile: str = "drinking", file: UploadFile = File(...)):
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    results = analyze_csv_data(text, profile)
    if not results:
        raise HTTPException(400, "No valid rows found in CSV. Check format: sample_id,pH,TDS,...")

    return {"results": results, "count": len(results)}


@app.post("/api/chat/extract")
async def chat_extract(req: ChatRequest):
    result = _llm_extract(req.message, req.profile)

    # Accumulate extracted params into session
    new_params = result.get("params", {})
    if new_params:
        _session.setdefault("chat_params", {}).update(new_params)

    return {
        "reply": result.get("reply", "Parameters noted. Click Run Analysis when ready."),
        "params_extracted": new_params,
        "total_params": len(_session.get("chat_params", {})),
    }


# ── Static files — MUST be mounted AFTER all API routes ───────────────────────
# This serves style.css, app.js, and any other assets from Main-page/ at root /
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ── Dev entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("\n  Project UPD — API Server")
    print("  ─────────────────────────────────────────")
    print("  Frontend : http://localhost:8000/")
    print("  API docs : http://localhost:8000/docs")
    print("  Health   : http://localhost:8000/health")
    print("  ─────────────────────────────────────────\n")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)