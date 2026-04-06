"""
chat_agent.py — BLUE AI Conversational Agent (CLI)
BLUE | Phase 3
"""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI, BadRequestError, RateLimitError

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("WARNING: GROQ_API_KEY not set. LLM features disabled. Get a free key at https://console.groq.com")
    client = None
else:
    client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

CHAT_MODEL    = "llama-3.1-8b-instant"
TOOL_MODEL    = "llama-3.3-70b-versatile"
EXTRACT_MODEL = "llama-3.1-8b-instant"

MAX_HISTORY_TURNS = 5

# ── Paths ──────────────────────────────────────────────────────────────────────
# chat_agent.py lives at src/llm/chat_agent.py → go up two levels to project root

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROFILES_DIR = PROJECT_ROOT / "config" / "profiles"
SRC_DIR      = PROJECT_ROOT / "src"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# ── Engine import ──────────────────────────────────────────────────────────────

_wqi_module = None
_wqi_import_error = None

def _get_wqi():
    global _wqi_module, _wqi_import_error
    if _wqi_module is not None:
        return _wqi_module, None
    if _wqi_import_error is not None:
        return None, _wqi_import_error
    try:
        from src.engine import wqi_calculator
        _wqi_module = wqi_calculator
        print("  [✓ WQI engine loaded]")
        return _wqi_module, None
    except ImportError:
        try:
            # Fallback: if src/ is already on sys.path (e.g. when running from src/)
            from engine import wqi_calculator
            _wqi_module = wqi_calculator
            print("  [✓ WQI engine loaded (fallback path)]")
            return _wqi_module, None
        except ImportError as e:
            _wqi_import_error = str(e)
            print(f"  [✗ Engine import failed: {e}]")
            return None, _wqi_import_error

# ── Parameter aliases — handled in Python, NEVER sent to the LLM ──────────────
# This was the main token killer: ~3000 tokens per extraction call.
# Now it's just a code lookup, costs zero tokens.

PARAM_ALIASES = {
    "total dissolved solids": "TDS", "dissolved solids": "TDS", "tds": "TDS",
    "potential hydrogen": "pH", "ph": "pH",
    "electrical conductivity": "EC", "conductivity": "EC", "ec": "EC",
    "hardness": "Hardness", "total hardness": "Hardness",
    "nitrate": "Nitrate", "nitrates": "Nitrate", "no3": "Nitrate",
    "nitrite": "Nitrite", "no2": "Nitrite",
    "turbidity": "Turbidity", "ntu": "Turbidity",
    "iron": "Iron", "fe": "Iron",
    "fluoride": "Fluoride",
    "arsenic": "Arsenic",
    "lead": "Lead", "pb": "Lead",
    "manganese": "Manganese", "mn": "Manganese",
    "zinc": "Zinc", "zn": "Zinc",
    "copper": "Copper", "cu": "Copper",
    "chromium": "Chromium", "cr": "Chromium",
    "cadmium": "Cadmium", "cd": "Cadmium",
    "mercury": "Mercury", "hg": "Mercury",
    "chloride": "Chloride", "chlorides": "Chloride", "cl": "Chloride",
    "sulphate": "Sulphate", "sulphates": "Sulphate",
    "sulfate": "Sulphate", "sulfates": "Sulphate", "so4": "Sulphate",
    "phosphate": "Phosphate", "po4": "Phosphate",
    "bicarbonate": "Bicarbonate", "hco3": "Bicarbonate",
    "carbonate": "Carbonate", "co3": "Carbonate",
    "sodium": "Sodium", "na": "Sodium",
    "calcium": "Calcium", "ca": "Calcium",
    "magnesium": "Magnesium", "mg": "Magnesium",
    "potassium": "Potassium",
    "total coliform": "TotalColiform", "coliform": "TotalColiform",
    "coliform bacteria": "TotalColiform",
    "e. coli": "EColi", "ecoli": "EColi", "e.coli": "EColi",
    "fecal coliform": "EColi",
    "bod": "BOD", "biological oxygen demand": "BOD",
    "cod": "COD", "chemical oxygen demand": "COD",
    "dissolved oxygen": "DO", "do": "DO",
    "ammonia": "Ammonia", "nh3": "Ammonia", "nh4": "Ammonia",
    "temperature": "Temperature", "temp": "Temperature",
    "sar": "SAR", "sodium adsorption ratio": "SAR",
    "boron": "Boron",
    "selenium": "Selenium",
    "nickel": "Nickel", "ni": "Nickel",
    "aluminium": "Aluminium", "aluminum": "Aluminium", "al": "Aluminium",
    "molybdenum": "Molybdenum",
    "cobalt": "Cobalt", "lithium": "Lithium", "vanadium": "Vanadium",
    "beryllium": "Beryllium",
}

PHYSICAL_BOUNDS = {
    "pH": (0, 14), "Temperature": (-10, 100), "DO": (0, 20),
    "TDS": (0, 100_000), "EC": (0, 100_000), "Turbidity": (0, 10_000),
    "BOD": (0, 50_000), "COD": (0, 100_000), "Nitrate": (0, 10_000),
    "Nitrite": (0, 1_000), "Ammonia": (0, 10_000), "SAR": (0, 200),
}

def _canonicalise(raw_name: str) -> str:
    """Map any raw parameter name to its canonical form using PARAM_ALIASES."""
    key = raw_name.strip().lower()
    return PARAM_ALIASES.get(key, raw_name.strip().title())

def _validate_bounds(params: dict) -> list:
    """Check physical bounds in Python — zero LLM tokens spent."""
    issues = []
    for param, value in params.items():
        if param in PHYSICAL_BOUNDS and isinstance(value, (int, float)):
            lo, hi = PHYSICAL_BOUNDS[param]
            if not (lo <= value <= hi):
                issues.append({
                    "parameter": param,
                    "value": value,
                    "issue": f"Must be {lo}–{hi}",
                    "action": "ask_user_to_recheck"
                })
    return issues

# ── Tiny regex-first extractor (zero LLM tokens for clean numeric input) ───────

_PAIR_RE = re.compile(
    r'([A-Za-z][A-Za-z0-9 _.]*?)\s*[:=]\s*([\d]+(?:\.\d+)?)',
    re.IGNORECASE
)

def _regex_extract(text: str) -> dict | None:
    """
    Try to extract key:value pairs with pure regex.
    Returns dict if successful, None if the text is too messy.
    """
    pairs = _PAIR_RE.findall(text)
    if not pairs:
        return None
    result = {}
    for raw_name, raw_val in pairs:
        canonical = _canonicalise(raw_name)
        try:
            result[canonical] = float(raw_val) if '.' in raw_val else int(raw_val)
        except ValueError:
            pass
    return result if result else None

# ── Profile hint from text (pure Python, zero tokens) ─────────────────────────

def _infer_profile_hint(text: str) -> tuple[str | None, str | None]:
    t = text.lower()
    if any(w in t for w in ("drink", "peena", "peene", "ghar ka paani", "potable")):
        return "bis_drinking", None
    if "who" in t:
        return "who_drinking", None
    if any(w in t for w in ("fish", "aqua", "talaab", "pond", "machli")):
        return "aquaculture", None
    if any(w in t for w in ("factory", "industrial", "boiler", "industry")):
        return "industrial", None
    if any(w in t for w in ("pashu", "livestock", "cattle", "animal", "maweshi")):
        return "fao_agriculture", "livestock"
    if any(w in t for w in ("kheti", "irrigat", "crop", "farm", "kisan")):
        return "fao_agriculture", "irrigation"
    return None, None

# ── Extraction: regex first, LLM only as fallback ─────────────────────────────

def _tool_extract_and_validate_parameters(raw_input: str, conversation_context: str = "") -> dict:
    """
    Step 1: Try regex extraction (0 tokens).
    Step 2: Only call LLM if regex fails (messy / natural language input).
    Aliases and bounds are always handled in Python — never sent to LLM.
    """
    profile_hint, use_case_hint = _infer_profile_hint(raw_input + " " + conversation_context)

    # ── Fast path: regex ───────────────────────────────────────────────────────
    params = _regex_extract(raw_input)

    if params is not None:
        issues = _validate_bounds(params)
        return {
            "parameters": params,
            "validation_issues": issues,
            "profile_hint": profile_hint,
            "use_case_hint": use_case_hint,
            "qualitative_notes": [],
            "units_used": {k: "mg/L" for k in params if k not in ("pH", "Temperature", "EC", "Turbidity", "DO", "SAR")},
            "_extraction_method": "regex"
        }

    # ── Slow path: LLM for messy/natural language input ───────────────────────
    # Prompt is kept tiny — no alias table, no bounds table (handled in code).
    if client is None:
        return {
            "parameters": {}, "validation_issues": [],
            "profile_hint": profile_hint, "use_case_hint": use_case_hint,
            "qualitative_notes": ["LLM unavailable (GROQ_API_KEY not set). Please enter values as 'pH: 7.2, TDS: 500'."],
            "units_used": {}, "_extraction_method": "failed"
        }

    prompt = (
        f"Extract water quality parameter names and numeric values from this text.\n"
        f"Return ONLY a JSON object like {{\"pH\": 7.2, \"TDS\": 500}}. No markdown.\n\n"
        f"Text: {raw_input}"
    )

    response = client.chat.completions.create(
        model=EXTRACT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=400,
    )
    _track(response.usage)
    raw_text = response.choices[0].message.content.strip()
    if raw_text.startswith("```"):
        lines    = raw_text.split("\n")
        raw_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        raw_params = json.loads(raw_text.strip())
        # Canonicalise keys via Python alias table (still zero extra tokens)
        params = {_canonicalise(k): v for k, v in raw_params.items()}
        issues = _validate_bounds(params)
        return {
            "parameters": params,
            "validation_issues": issues,
            "profile_hint": profile_hint,
            "use_case_hint": use_case_hint,
            "qualitative_notes": [],
            "units_used": {},
            "_extraction_method": "llm"
        }
    except json.JSONDecodeError:
        return {
            "parameters": {}, "validation_issues": [],
            "profile_hint": profile_hint, "use_case_hint": use_case_hint,
            "qualitative_notes": ["Could not parse input — ask user to clarify."],
            "units_used": {}, "_extraction_method": "failed"
        }

# ── Profile loading ────────────────────────────────────────────────────────────

def _load_profile(filename: str) -> dict:
    path = PROFILES_DIR / filename
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}

PROFILES = {
    "bis_drinking":    _load_profile("bis_drinking.json"),
    "who_drinking":    _load_profile("who_drinking.json"),
    "fao_agriculture": _load_profile("fao_agriculture.json"),
    "industrial":      _load_profile("industrial.json"),
    "aquaculture":     _load_profile("aquaculture.json"),
}

# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are BLUE AI, a water quality assistant for BLUE.

RULES:
1. NEVER assume parameter values. Only use numbers the user explicitly wrote.
2. NEVER call any tool on greetings, symptoms, or questions without numeric data.
3. Match the user's language carefully:
   - English input -> reply in English only
   - Roman-script Hinglish input -> reply in natural Roman-script Hinglish only
   - Devanagari Hindi input -> reply in simple Hindi
   - Never switch scripts unless the user does
   - Never use broken Hindi or awkward literal translation
4. Keep replies concise.
5. NEVER invent a WQI number.
6. If analysis/report data says the sample is UNSAFE or has no numeric WQI, explicitly say the water is unsafe and that no numeric WQI is available.

FLOW: Greet -> ask use case -> collect numbers -> extract -> confirm -> analyse -> offer PDF.

PROFILES: bis_drinking | who_drinking | fao_agriculture | industrial | aquaculture
  drinking/peena/ghar->bis_drinking | WHO->who_drinking
  kheti/irrigation->fao_agriculture(irrigation) | pashu/livestock->fao_agriculture(livestock)
  fish/talaab/pond->aquaculture | factory/boiler->industrial

SYMPTOMS without numbers: name likely cause, ask for lab report.
Always end remediation advice with "Consult a certified water treatment professional." """.strip()

_HINDI_SCRIPT_RE = re.compile(r"[\u0900-\u097F]")
_HINGLISH_CUES = (
    "kya", "hai", "haan", "nahi", "nahin", "kar", "karo", "karna", "kar do",
    "chahiye", "bata", "samjha", "samjhao", "paani", "jal", "peene", "ghar ka",
    "kitna", "kaise", "kyun", "acha", "theek", "banao", "bhejo", "mujhe", "bhai",
)
_REPORT_REQUEST_RE = re.compile(
    r"(?:\b(?:pdf|report|download)\b)|(?:make|create|generate|send)\s+(?:a\s+)?(?:pdf|report)|"
    r"(?:report|pdf)\s*(?:banao|bana do|bhejo|send|chahiye|download|nikalo)|"
    r"(?:रिपोर्ट|पीडीएफ)",
    re.IGNORECASE,
)


def detect_reply_language(user_message: str) -> str:
    text = (user_message or "").strip()
    lower = text.lower()
    if _HINDI_SCRIPT_RE.search(text):
        return "hindi"
    cue_hits = sum(1 for cue in _HINGLISH_CUES if cue in lower)
    if cue_hits >= 1 and any(ch.isalpha() for ch in lower):
        return "hinglish"
    return "english"


def is_report_request(user_message: str) -> bool:
    return bool(_REPORT_REQUEST_RE.search(user_message or ""))


def _runtime_style_instruction(user_message: str) -> str:
    language = detect_reply_language(user_message)
    if language == "hindi":
        return (
            "Reply in simple, natural Hindi in Devanagari. "
            "Keep technical water-parameter names as commonly used in reports."
        )
    if language == "hinglish":
        return (
            "Reply in natural Hinglish using Roman script only. "
            "Do not use Devanagari. Do not write broken Hindi. "
            "Keep the tone conversational and clear."
        )
    return "Reply in clear English only. Do not switch into Hindi or Hinglish."

# ── Tools ──────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "extract_and_validate_parameters",
            "description": "Extract numeric water quality parameters the user explicitly provided. ONLY call when user has given actual numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "raw_input": {"type": "string", "description": "User message with numeric values."},
                    "conversation_context": {"type": "string", "description": "Use case from prior turns."}
                },
                "required": ["raw_input"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_wqi_analysis",
            "description": "Run WQI analysis. Call ONLY after extraction returned clean data AND user confirmed values.",
            "parameters": {
                "type": "object",
                "properties": {
                    "parameters": {"type": "string", "description": "JSON string of validated parameters."},
                    "profile": {"type": "string", "description": "bis_drinking|who_drinking|fao_agriculture|industrial|aquaculture"},
                    "use_case": {"type": "string", "description": "irrigation or livestock (fao only)"}
                },
                "required": ["parameters", "profile"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_pdf_report",
            "description": "Generate PDF report. Call when user says PDF chahiye / send report / download.",
            "parameters": {
                "type": "object",
                "properties": {
                    "analysis_result": {"type": "string", "description": "Full JSON result from run_wqi_analysis."},
                    "user_context": {"type": "string", "description": "Water source and use case."},
                    "language": {"type": "string", "description": "english or hindi. Default: english."}
                },
                "required": ["analysis_result", "user_context"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_parameter_context",
            "description": "Look up safe limits for a parameter. Use for 'What does high TDS mean?' type questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "parameter_name": {"type": "string"},
                    "profile": {"type": "string"},
                    "user_value": {"type": "number"}
                },
                "required": ["parameter_name", "profile"]
            }
        }
    }
]

# ── Remaining tool implementations ────────────────────────────────────────────

def _tool_run_wqi_analysis(parameters: str, profile: str, use_case: str = None) -> dict:
    try:
        params_dict = json.loads(parameters) if isinstance(parameters, str) else parameters
    except json.JSONDecodeError:
        return {"error": "Could not parse 'parameters' as JSON."}

    wqi, err = _get_wqi()
    if wqi is None:
        return {"error": f"WQI engine unavailable: {err}",
                "hint": f"Check {SRC_DIR / 'engine' / '__init__.py'} exists."}
    try:
        if hasattr(wqi, "analyze_single"):
            result = wqi.analyze_single(params_dict, profile=profile, use_case=use_case)
        elif hasattr(wqi, "calculate"):
            result = wqi.calculate(params_dict, profile=profile)
        elif hasattr(wqi, "WQICalculator"):
            result = wqi.WQICalculator(profile=profile).analyze(params_dict, use_case=use_case)
        else:
            return {"error": "No known API on wqi_calculator.",
                    "available": [x for x in dir(wqi) if not x.startswith("_")]}
        return json.loads(json.dumps(result, default=str))
    except Exception as e:
        return {"error": f"Engine error: {e}", "parameters_received": params_dict}


def _tool_get_parameter_context(parameter_name: str, profile: str, user_value: float = None) -> dict:
    if profile not in PROFILES or not PROFILES[profile]:
        return {"error": f"Profile '{profile}' not loaded."}
    params = PROFILES[profile].get("parameters", {})
    match  = next((k for k in params if k.lower() == parameter_name.lower()), None)
    if not match:
        return {"found": False, "message": f"'{parameter_name}' not in {profile}."}
    meta = params[match]
    out  = {"found": True, "parameter": match, "profile": profile,
            "unit": meta.get("unit",""), "layer": meta.get("layer",""),
            "direction": meta.get("direction",""), "limits": meta.get("limits",{})}
    if user_value is not None:
        out["user_value"] = user_value
    return out


def _tool_generate_pdf_report(analysis_result: str, user_context: str, language: str = "english") -> dict:
    try:
        result = json.loads(analysis_result) if isinstance(analysis_result, str) else analysis_result
    except json.JSONDecodeError:
        return {"success": False, "error": "Could not parse analysis_result as JSON."}
    try:
        from src.reports.generator import generate_pdf_report as shared_generate_pdf_report
        from src.treatment.recommender import get_recommendations
    except ImportError:
        shared_generate_pdf_report = None
        get_recommendations = None

    if shared_generate_pdf_report is not None and get_recommendations is not None:
        output_dir = PROJECT_ROOT / "reports"
        output_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"wqi_report_{timestamp}.pdf"
        profile_id = result.get("profile", "bis_drinking")
        recommendations = get_recommendations(wqi_result=result, profile_id=profile_id)
        meta = {
            "sample_id": f"S{timestamp[-6:]}",
            "location": user_context or "Unknown",
            "profile_id": profile_id,
            "tested_by": "",
            "lab_ref": "",
            "date": datetime.now().strftime("%d %b %Y"),
        }
        path = shared_generate_pdf_report(result, recommendations, str(output_path), meta)
        return {"success": True, "path": str(Path(path).absolute()), "filename": Path(path).name}
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer,
            Table, TableStyle, HRFlowable, KeepTogether
        )
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
    except ImportError:
        return {"success": False, "error": "pip install reportlab"}

    output_dir  = PROJECT_ROOT / "reports"
    output_dir.mkdir(exist_ok=True)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"wqi_report_{timestamp}.pdf"

    BRAND_BLUE  = colors.HexColor("#1a5276")
    BRAND_LIGHT = colors.HexColor("#eaf4fb")
    BRAND_DARK  = colors.HexColor("#154360")
    ZONE_COLORS = {
        "ideal": colors.HexColor("#27ae60"), "acceptable": colors.HexColor("#2ecc71"),
        "permissible": colors.HexColor("#f39c12"), "breach": colors.HexColor("#e74c3c"),
        "deficient": colors.HexColor("#8e44ad"), "unsafe": colors.HexColor("#c0392b"),
        "non_compliant": colors.HexColor("#e67e22"), "unscored": colors.HexColor("#95a5a6"),
        "unknown": colors.HexColor("#7f8c8d"),
    }

    doc   = SimpleDocTemplate(str(output_path), pagesize=A4,
                              rightMargin=0.75*inch, leftMargin=0.75*inch,
                              topMargin=0.75*inch, bottomMargin=0.75*inch)
    ss    = getSampleStyleSheet()
    story = []

    def S(name, **kw):
        return ParagraphStyle(name, parent=ss["Normal"], **kw)

    story.append(Paragraph("Water Quality Analysis Report",
        S("H1", fontSize=22, textColor=BRAND_BLUE, spaceAfter=2)))
    story.append(Paragraph(f"BLUE  ·  {datetime.now().strftime('%d %B %Y, %H:%M')}",
        S("Sub", fontSize=9, textColor=colors.grey, spaceAfter=3)))
    story.append(Paragraph(f"<b>Source / Use case:</b> {user_context}",
        S("Ctx", fontSize=10, textColor=BRAND_DARK, spaceAfter=3)))
    story.append(Paragraph(f"<b>Standard applied:</b> {result.get('profile', 'N/A')}",
        S("Std", fontSize=10, textColor=BRAND_DARK, spaceAfter=10)))
    story.append(HRFlowable(width="100%", thickness=2, color=BRAND_BLUE, spaceAfter=14))

    score   = result.get("wqi_score") or result.get("score")
    zone    = (result.get("zone") or "unknown").lower()
    verdict = result.get("verdict", "")
    zcolor  = ZONE_COLORS.get(zone, ZONE_COLORS["unknown"])
    score_display = str(round(score, 1)) if isinstance(score, (int, float)) else (score or "—")

    score_tbl = Table([[
        Paragraph(f"<b>{score_display}</b>",
            S("Sc", fontSize=48, textColor=zcolor, alignment=TA_CENTER)),
        Paragraph(f"<b>{zone.upper()}</b><br/><br/><font size=10>{verdict}</font>",
            S("Zn", fontSize=20, textColor=zcolor, leading=26, alignment=TA_LEFT))
    ]], colWidths=[1.8*inch, 5*inch])
    score_tbl.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("LEFTPADDING", (0,0), (-1,-1), 10),
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#f8f9fa")),
        ("BOX", (0,0), (-1,-1), 1.5, zcolor),
    ]))
    story.append(KeepTogether([score_tbl, Spacer(1, 18)]))

    param_results = result.get("parameter_results") or result.get("parameters") or {}
    if param_results:
        story.append(Paragraph("Parameter-Level Assessment",
            S("SH", fontSize=13, textColor=BRAND_BLUE, spaceBefore=4, spaceAfter=6)))
        rows = [["Parameter", "Measured", "Unit", "Safe Limit", "Zone / Status", "Score"]]
        for param, details in param_results.items():
            if isinstance(details, dict):
                pzone  = details.get("zone", details.get("status", "")).lower()
                pcolor = ZONE_COLORS.get(pzone, ZONE_COLORS["unknown"])
                pscore = details.get("score", details.get("sub_score", ""))
                hex_   = pcolor.hexval()[2:].upper()
                rows.append([
                    param, str(details.get("value", "")), details.get("unit", ""),
                    str(details.get("limit", details.get("safe_limit", "N/A"))),
                    Paragraph(f"<font color='#{hex_}'><b>{pzone.upper()}</b></font>",
                              S("ZC", fontSize=8, alignment=TA_CENTER)),
                    str(round(pscore, 2)) if isinstance(pscore, float) else str(pscore),
                ])
            else:
                rows.append([param, str(details), "", "", "", ""])

        t = Table(rows, colWidths=[1.6*inch, 0.85*inch, 0.7*inch, 1.0*inch, 1.1*inch, 0.65*inch], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",     (0,0),  (-1,0),  BRAND_BLUE),
            ("TEXTCOLOR",      (0,0),  (-1,0),  colors.white),
            ("FONTNAME",       (0,0),  (-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",       (0,0),  (-1,-1), 8.5),
            ("ROWBACKGROUNDS", (0,1),  (-1,-1), [colors.white, BRAND_LIGHT]),
            ("GRID",           (0,0),  (-1,-1), 0.4, colors.HexColor("#d5d8dc")),
            ("ALIGN",          (1,0),  (-1,-1), "CENTER"),
            ("VALIGN",         (0,0),  (-1,-1), "MIDDLE"),
            ("TOPPADDING",     (0,0),  (-1,-1), 6),
            ("BOTTOMPADDING",  (0,0),  (-1,-1), 6),
        ]))
        story.append(t)
        story.append(Spacer(1, 16))

    flags = result.get("flags", [])
    if flags:
        story.append(Paragraph("Flags & Warnings",
            S("FH", fontSize=13, textColor=colors.HexColor("#c0392b"), spaceBefore=4, spaceAfter=6)))
        ft = Table([[Paragraph(f"• {f}", S("FL", fontSize=9))] for f in flags], colWidths=[6.5*inch])
        ft.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#fdf2f2")),
            ("BOX",        (0,0), (-1,-1), 0.5, colors.HexColor("#e74c3c")),
            ("PADDING",    (0,0), (-1,-1), 6),
        ]))
        story.append(ft)
        story.append(Spacer(1, 14))

    derived = result.get("derived_metrics") or result.get("derived") or {}
    if derived:
        story.append(Paragraph("Derived Metrics",
            S("DH", fontSize=13, textColor=BRAND_BLUE, spaceBefore=4, spaceAfter=6)))
        d_rows = [["Metric", "Value", "Unit"]]
        for k, v in derived.items():
            d_rows.append([k, str(v.get("value","") if isinstance(v, dict) else v),
                           v.get("unit","") if isinstance(v, dict) else ""])
        dt = Table(d_rows, colWidths=[2.5*inch, 2*inch, 1.5*inch])
        dt.setStyle(TableStyle([
            ("BACKGROUND",     (0,0), (-1,0), BRAND_BLUE),
            ("TEXTCOLOR",      (0,0), (-1,0), colors.white),
            ("FONTNAME",       (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",       (0,0), (-1,-1), 9),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, BRAND_LIGHT]),
            ("GRID",           (0,0), (-1,-1), 0.4, colors.HexColor("#d5d8dc")),
            ("ALIGN",          (1,0), (-1,-1), "CENTER"),
            ("PADDING",        (0,0), (-1,-1), 5),
        ]))
        story.append(dt)
        story.append(Spacer(1, 14))

    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#aab7b8")))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        f"Standard: {result.get('profile','N/A')}  ·  BLUE  ·  "
        "Auto-generated — verify with a certified water treatment professional.",
        S("Ft", fontSize=7.5, textColor=colors.grey)))

    doc.build(story)
    return {"success": True, "path": str(output_path.absolute()), "filename": output_path.name}

# ── Token tracker ──────────────────────────────────────────────────────────────

_session_tokens = {"prompt": 0, "completion": 0}

def _track(usage):
    if usage:
        _session_tokens["prompt"]     += usage.prompt_tokens
        _session_tokens["completion"] += usage.completion_tokens
        total     = _session_tokens["prompt"] + _session_tokens["completion"]
        remaining = max(0, 100_000 - total)
        print(f"  [tokens: +{usage.total_tokens} | {total} used | ~{remaining} remaining today]")

# ── History trimming ───────────────────────────────────────────────────────────

def _trim_history(history: list) -> list:
    system = [history[0]]
    tail   = history[1:]
    kept, turns, i = [], 0, len(tail) - 1
    while i >= 0 and turns < MAX_HISTORY_TURNS:
        msg  = tail[i]
        role = msg.role if hasattr(msg, "role") else msg.get("role")
        kept.insert(0, tail[i])
        if role == "user":
            turns += 1
        i -= 1
    return system + kept

# ── Tool dispatcher ────────────────────────────────────────────────────────────

def dispatch_tool(fn_name: str, fn_args: dict) -> dict:
    try:
        if fn_name == "extract_and_validate_parameters":
            return _tool_extract_and_validate_parameters(**fn_args)
        elif fn_name == "run_wqi_analysis":
            return _tool_run_wqi_analysis(**fn_args)
        elif fn_name == "generate_pdf_report":
            return _tool_generate_pdf_report(**fn_args)
        elif fn_name == "get_parameter_context":
            return _tool_get_parameter_context(**fn_args)
        else:
            return {"error": f"Unknown tool: {fn_name}"}
    except TypeError as e:
        return {"error": f"Argument error in '{fn_name}': {str(e)}"}
    except Exception as e:
        return {"error": f"Execution failed in '{fn_name}': {str(e)}"}

# ── Groq chat wrapper ──────────────────────────────────────────────────────────

def _needs_tools(user_message: str) -> bool:
    has_numbers  = bool(re.search(r'\d', user_message))
    has_keywords = any(w in user_message.lower() for w in
                       ("pdf", "report", "download", "what does", "safe limit",
                        "dangerous", "compare", "who limit", "chahiye", "limit for"))
    return has_numbers or has_keywords


def _groq_chat(messages: list, use_tools: bool = True) -> object:
    if client is None:
        raise RuntimeError("GROQ_API_KEY not set — cannot call LLM.")
    model  = TOOL_MODEL if use_tools else CHAT_MODEL
    kwargs = dict(model=model, messages=messages, max_tokens=512)
    if use_tools:
        kwargs["tools"]       = TOOLS
        kwargs["tool_choice"] = "auto"
    try:
        resp = client.chat.completions.create(**kwargs)
        _track(resp.usage)
        return resp
    except RateLimitError as e:
        wait = re.search(r"in (\d+m[\d.]+s|\d+\.\d+s)", str(e))
        wait_str = wait.group(1) if wait else "a few minutes"
        print(f"\n  [⚠ Rate limit — wait {wait_str}]")
        raise
    except BadRequestError as e:
        if "tool_use_failed" not in str(e):
            raise
        print("  [⚠ Tool format error — retrying as plain text...]")
        recovery = list(messages) + [{
            "role": "system",
            "content": "Malformed tool call. Reply in plain text only, no tool calls."
        }]
        resp = client.chat.completions.create(model=CHAT_MODEL, messages=recovery, max_tokens=512)
        _track(resp.usage)
        return resp

# ── Agent turn ─────────────────────────────────────────────────────────────────

def _turn(history: list, user_message: str, force_no_tools: bool = False) -> str:
    history.append({"role": "user", "content": user_message})
    trimmed   = _trim_history(history)
    use_tools = (not force_no_tools) and _needs_tools(user_message)
    runtime_instruction = {"role": "system", "content": _runtime_style_instruction(user_message)}

    while True:
        request_messages = [trimmed[0], runtime_instruction, *trimmed[1:]] if trimmed else [runtime_instruction]
        response = _groq_chat(request_messages, use_tools=use_tools)
        msg      = response.choices[0].message
        history.append(msg)

        if not msg.tool_calls:
            return msg.content or ""

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)
            print(f"  [-> {fn_name}...]")
            result  = dispatch_tool(fn_name, fn_args)

            if fn_name == "generate_pdf_report" and result.get("success"):
                print(f"  [✓ PDF: {result.get('path')}]")

            tool_msg = {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)}
            history.append(tool_msg)
            trimmed.append(msg)
            trimmed.append(tool_msg)

        use_tools = True

# ── Main ───────────────────────────────────────────────────────────────────────

def run_agent():
    print("\n" + "=" * 60)
    print("  BLUE AI — Water Quality Assistant (BLUE)")
    print("=" * 60)
    print(f"  History window: {MAX_HISTORY_TURNS} turns  |  type 'exit' to quit\n")

    history  = [{"role": "system", "content": SYSTEM_PROMPT}]
    greeting = _turn(history, "Hello!", force_no_tools=True)
    print(f"\nBLUE AI: {greeting}\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye", "band karo"):
            print("BLUE AI: Stay safe! 💧")
            break
        try:
            reply = _turn(history, user_input)
            print(f"\nBLUE AI: {reply}\n")
        except RateLimitError:
            print("\nBLUE AI: Rate limit hit. Please wait a few minutes and try again.\n")
            break

if __name__ == "__main__":
    run_agent()
