"""
recommender.py
Profile-aware water treatment recommendation engine.

Two usage modes:

    1. Engine path (primary) — pass wqi_result from calculate_wqi():
         result = calculate_wqi(sample, profile_id="bis_drinking")
         recs   = get_recommendations(wqi_result=result, profile_id="bis_drinking")

    2. Sample path (fallback) — pass raw sample dict:
         recs = get_recommendations(sample={"pH": 5.2, ...}, profile_id="bis_drinking")
         Engine is run internally. If engine fails, threshold rules are used.

Output format:
    {
        "profile":         str,
        "overall_status":  str,          # SAFE | NON_COMPLIANT | UNSAFE | UNKNOWN
        "source":          str,          # engine | engine_via_sample | fallback
        "recommendations": list[dict],   # sorted by priority
        "summary":         dict,
    }
"""

import json
from pathlib import Path
from loguru import logger


# ── Profile → treatment group ─────────────────────────────────────────────────

PROFILE_GROUP = {
    "bis_drinking":    "drinking",
    "who_drinking":    "drinking",
    "fao_agriculture": "agriculture",
    "aquaculture":     "aquaculture",
    "industrial":      "industrial",
}

PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


# ── Treatment rules ───────────────────────────────────────────────────────────
# Structure: group → param → "high" | "low" → { treatment, urgency }
# urgency: "immediate" | "short_term" | "routine"

TREATMENT_RULES = {

    "drinking": {
        "pH": {
            "low":  {"treatment": "Add lime (Ca(OH)₂) or soda ash to raise pH. Aeration helps off-gas CO₂.", "urgency": "short_term"},
            "high": {"treatment": "Inject CO₂ or dose dilute acid (HCl/H₂SO₄). Investigate carbonate hardness source.", "urgency": "short_term"},
        },
        "TDS": {
            "high": {"treatment": "Reverse Osmosis (RO) recommended. Check ion exchange units for dissolved solids.", "urgency": "short_term"},
        },
        "turbidity": {
            "high": {"treatment": "Coagulation-flocculation + sedimentation + sand filtration. Inspect source for runoff events.", "urgency": "short_term"},
        },
        "hardness": {
            "high": {"treatment": "Lime-soda softening, cation exchange softener, or RO. Investigate calcium/magnesium source.", "urgency": "routine"},
        },
        "chlorides": {
            "high": {"treatment": "RO or electrodialysis reversal (EDR). Check for saline intrusion or industrial discharge.", "urgency": "short_term"},
        },
        "sulphate": {
            "high": {"treatment": "RO or anion exchange resin. Can cause laxative effects above 500 mg/L.", "urgency": "short_term"},
        },
        "fluoride": {
            "high": {"treatment": "Activated alumina filtration or RO. Excess fluoride causes dental/skeletal fluorosis.", "urgency": "short_term"},
            "low":  {"treatment": "Consider fluoridation per local health authority guidelines if consistently below 0.5 mg/L.", "urgency": "routine"},
        },
        "iron": {
            "high": {"treatment": "Oxidation (aeration or chlorination) + filtration or greensand filter. Check for iron bacteria.", "urgency": "short_term"},
        },
        "dissolved_oxygen": {
            "low":  {"treatment": "Cascade or diffused aeration. Investigate organic pollution or algae bloom upstream.", "urgency": "short_term"},
        },
        "BOD": {
            "high": {"treatment": "Biological treatment (activated sludge or trickling filter). Investigate organic load source upstream.", "urgency": "short_term"},
        },
        "coliform": {
            "high": {"treatment": "IMMEDIATE: chlorination, UV irradiation, or ozonation. Identify contamination source. Do NOT consume until resolved.", "urgency": "immediate"},
        },
        "arsenic": {
            "high": {"treatment": "Oxidation + coagulation-filtration or RO. Do NOT consume — chronic carcinogen. Notify authorities.", "urgency": "immediate"},
        },
        "lead": {
            "high": {"treatment": "Inspect and replace lead pipes/fittings. Coagulation or RO for source treatment. Do NOT consume.", "urgency": "immediate"},
        },
        "nitrates": {
            "high": {"treatment": "Ion exchange or biological denitrification. Risk of methemoglobinemia in infants — do NOT give to bottle-fed babies.", "urgency": "immediate"},
        },
    },

    "agriculture": {
        "pH": {
            "low":  {"treatment": "Apply agricultural lime (CaCO₃) to soil. Inject calcium carbonate into irrigation line to correct source water.", "urgency": "short_term"},
            "high": {"treatment": "Inject dilute sulfuric or nitric acid into irrigation line. Apply sulfur amendments to soil. Monitor soil pH each cycle.", "urgency": "short_term"},
        },
        "EC": {
            "high": {"treatment": "Dilute with low-salinity source water. Improve subsurface drainage. Switch to salt-tolerant cultivars. RO if no dilution source available.", "urgency": "short_term"},
        },
        "SAR": {
            "high": {"treatment": "Apply gypsum (CaSO₄) to soil or inject calcium chloride into irrigation water. Dilute with lower-SAR water. Improve drainage to leach sodium.", "urgency": "short_term"},
        },
        "TDS": {
            "high": {"treatment": "Dilute with fresher source water. RO if source water only. Monitor crop for osmotic stress symptoms.", "urgency": "short_term"},
        },
        "Boron": {
            "high": {"treatment": "RO is the only reliable removal method — Boron bypasses most conventional filters. Dilute if possible. Avoid Boron-sensitive crops (citrus, avocado, beans).", "urgency": "short_term"},
        },
        "Chloride": {
            "high": {"treatment": "Dilute with low-chloride water. Improve subsurface drainage. Use overhead irrigation only for Cl-tolerant crops to reduce leaf burn.", "urgency": "short_term"},
        },
        "Sodium": {
            "high": {"treatment": "Gypsum amendment to displace sodium from soil exchange sites. Dilute irrigation water. Avoid furrow or flood irrigation methods.", "urgency": "short_term"},
        },
        "Nitrate_N": {
            "high": {"treatment": "Dilute source water. Apply split fertigation and eliminate N fertilizer inputs. Monitor crops for excessive vegetative growth.", "urgency": "routine"},
        },
        "Bicarbonate": {
            "high": {"treatment": "Inject acid (sulfuric or citric) to reduce Residual Sodium Carbonate (RSC) and prevent secondary sodium hazard build-up. Target post-injection pH 6.5–7.0.", "urgency": "short_term"},
        },
        "Sulfate": {
            "high": {"treatment": "Dilute if possible. Improve drainage to flush from root zone. Monitor livestock for scours if water also used for animal watering.", "urgency": "routine"},
        },
        "Iron": {
            "high": {"treatment": "Aeration + settling pond upstream of drip system. Oxidation filtration (greensand). Clean emitters regularly to prevent plugging.", "urgency": "short_term"},
        },
        "Manganese": {
            "high": {"treatment": "Oxidation filtration. Maintain pH > 7.5 to precipitate manganese. Flush irrigation lines frequently.", "urgency": "short_term"},
        },
        "Arsenic": {
            "high": {"treatment": "RO required. Do NOT use for food crop irrigation without treatment — risk of soil accumulation and food chain contamination. Notify authorities.", "urgency": "immediate"},
        },
        "Cadmium": {
            "high": {"treatment": "Stop irrigation immediately. RO required. Cadmium accumulates in leafy vegetables and cereals — serious food safety risk. Notify authorities.", "urgency": "immediate"},
        },
        "Lead": {
            "high": {"treatment": "Stop irrigation immediately. RO required. Lead accumulates in soil and root vegetables. Notify authorities.", "urgency": "immediate"},
        },
        "Mercury": {
            "high": {"treatment": "Stop irrigation immediately. Do not use for any food production without treatment. Notify environmental authorities.", "urgency": "immediate"},
        },
        "Selenium": {
            "high": {"treatment": "RO required. Narrow safe range — above limit causes selenosis in livestock consuming crops. Monitor selenium concentration in produce.", "urgency": "immediate"},
        },
    },

    "aquaculture": {
        "pH": {
            "low":  {"treatment": "Add agricultural lime (Ca(OH)₂) to pond at 20–50 kg/ha. Apply in morning and allow circulation. Recheck after 24h.", "urgency": "short_term"},
            "high": {"treatment": "Inject CO₂ or perform partial water exchange with lower-pH source. Investigate daytime algal bloom — photosynthesis can spike pH above 9.", "urgency": "short_term"},
        },
        "DO": {
            "low":  {"treatment": "EMERGENCY: activate paddle wheel aerators. Stop feeding immediately. Reduce stocking density if chronic hypoxia. Investigate organic load or algal crash.", "urgency": "immediate"},
        },
        "Ammonia_N": {
            "high": {"treatment": "CRITICAL: stop feeding. Perform 30–50% water exchange. Add zeolite (clinoptilolite) at 50–100 kg/ha to adsorb NH₃. Optimise biofilter. Note: NH₃ toxicity increases with pH — check and lower pH if elevated.", "urgency": "immediate"},
        },
        "Nitrite": {
            "high": {"treatment": "Add NaCl at 1–3 g/L (chloride competitively inhibits nitrite uptake at gills). Perform partial water exchange. Optimise biofilter — nitrite spike indicates incomplete nitrification.", "urgency": "immediate"},
        },
        "H2S": {
            "high": {"treatment": "CRITICAL: emergency aeration. Add lime to raise pH (H₂S is less toxic at pH > 8). Avoid disturbing bottom sediments. Investigate and remove anoxic sediment layer.", "urgency": "immediate"},
        },
        "Chlorine": {
            "high": {"treatment": "Do NOT use this source water. If unavoidable, dechlorinate with sodium thiosulfate at 7 mg per 1 mg/L Cl₂. Allow full de-chlorination before stocking.", "urgency": "immediate"},
        },
        "Copper": {
            "high": {"treatment": "Stop intake immediately — Copper is acutely toxic to fish gills at trace levels. Investigate pipe corrosion or upstream industrial input. Notify authorities.", "urgency": "immediate"},
        },
        "Zinc": {
            "high": {"treatment": "Stop intake immediately. Investigate industrial discharge upstream. RO if no alternate source available.", "urgency": "immediate"},
        },
        "Mercury": {
            "high": {"treatment": "Abandon this water source. Mercury bioaccumulates in fish tissue — produces unsafe seafood regardless of fish health. Notify environmental authorities.", "urgency": "immediate"},
        },
        "Arsenic": {
            "high": {"treatment": "Stop intake from this source. Arsenic bioaccumulates in aquatic organisms. RO if no alternate source. Notify authorities.", "urgency": "immediate"},
        },
        "Lead": {
            "high": {"treatment": "Stop intake from this source. Investigate upstream contamination. Notify authorities.", "urgency": "immediate"},
        },
        "Temperature": {
            "high": {"treatment": "Install shade netting (30–50% cover). Increase pond depth. Perform night-time water exchange with cooler source. Reduce stocking density to lower metabolic heat load.", "urgency": "short_term"},
            "low":  {"treatment": "Install greenhouse or polytunnel. Use geothermal or heated water source if available. Reduce feeding (fish metabolism slows significantly at low temperature).", "urgency": "short_term"},
        },
        "Nitrate": {
            "high": {"treatment": "Partial water exchange. Increase biofilter capacity. Introduce aquatic macrophytes (water hyacinth, duckweed) for nitrate uptake. Reduce feeding rate.", "urgency": "routine"},
        },
        "CO2": {
            "high": {"treatment": "Increase surface aeration (splash aerators, paddle wheels). Reduce stocking density. Investigate decomposition load. Free CO₂ is lowest at sunrise — schedule feeding then.", "urgency": "short_term"},
        },
        "BOD": {
            "high": {"treatment": "Reduce feeding rate. Increase aeration. Perform partial water exchange. Remove dead organic matter (uneaten feed, faeces) from pond bottom.", "urgency": "short_term"},
        },
        "Turbidity": {
            "high": {"treatment": "Allow settling. For clay turbidity apply alum (aluminium sulphate) at 15–30 kg/ha. Check and stabilise pond bank soil to reduce erosion.", "urgency": "routine"},
        },
        "Alkalinity": {
            "low":  {"treatment": "Add agricultural lime (CaCO₃) or sodium bicarbonate (NaHCO₃) to increase buffering capacity. Target 80–120 mg/L as CaCO₃ for stable pH.", "urgency": "short_term"},
            "high": {"treatment": "Dilute with low-alkalinity source water. High alkalinity correlates with elevated pH — monitor pH diurnally.", "urgency": "routine"},
        },
        "Hardness": {
            "low":  {"treatment": "Add gypsum (CaSO₄·2H₂O) or calcium chloride. Soft water amplifies heavy metal toxicity and causes osmotic stress in fish.", "urgency": "short_term"},
            "high": {"treatment": "Dilute with softer water source. Very hard water can interfere with fish osmoregulation and fry development.", "urgency": "routine"},
        },
        "TDS": {
            "high": {"treatment": "Partial water exchange with lower-TDS source. Reduce saline inputs. Monitor fish behaviour for osmotic stress (freshwater species).", "urgency": "short_term"},
        },
        "Iron": {
            "high": {"treatment": "Aerate source water before intake to oxidise Fe²⁺ → Fe³⁺ (precipitates). Pass through settling pond. Avoid intake during storm runoff when iron is highest.", "urgency": "short_term"},
        },
    },

    "industrial": {
        "pH": {
            "low":  {"treatment": "Dose caustic soda (NaOH) or trisodium phosphate (Na₃PO₄) to raise pH. Low pH in boiler water causes acid corrosion of steel — immediate risk to boiler integrity.", "urgency": "short_term"},
            "high": {"treatment": "Dose dilute acid (H₂SO₄ or HCl) or inject CO₂. Excessively high pH causes caustic embrittlement in boiler drums.", "urgency": "short_term"},
        },
        "Alkalinity": {
            "low":  {"treatment": "Dose sodium carbonate (Na₂CO₃) or sodium bicarbonate. Insufficient alkalinity means inadequate corrosion buffering — boiler is at risk.", "urgency": "short_term"},
            "high": {"treatment": "Increase blowdown rate. Dose acid to neutralise excess bicarbonate. Prevents steam-side carryover and priming in boiler drums.", "urgency": "short_term"},
        },
        "Chloride": {
            "high": {"treatment": "Install RO or mixed-bed deioniser upstream. Increase blowdown frequency. Chlorides cause stress corrosion cracking in stainless steel and pitting in carbon steel boiler tubes.", "urgency": "short_term"},
        },
        "TDS": {
            "high": {"treatment": "CRITICAL: increase blowdown immediately to prevent scale carryover. Install RO or deionisation upstream. Review makeup water quality — this indicates water treatment is not adequate.", "urgency": "immediate"},
        },
        "Hardness": {
            "high": {"treatment": "CRITICAL: install cation exchange softener (zeolite) or lime-soda softening upstream immediately. Hardness causes CaCO₃/CaSO₄ scale on boiler tubes — risk of tube failure and pressure vessel rupture.", "urgency": "immediate"},
        },
        "Silica": {
            "high": {"treatment": "Hot lime-soda softening with magnesia addition. Strong-base anion exchange resin. RO polishing. Silica deposits on turbine blades in high-pressure systems — causes catastrophic efficiency loss and blade failure.", "urgency": "immediate"},
        },
        "Iron": {
            "high": {"treatment": "Install chlorination + multimedia filtration or magnetic treatment upstream. Iron deposits foul heat transfer surfaces and initiate under-deposit corrosion cells in boilers.", "urgency": "immediate"},
        },
        "DO": {
            "high": {"treatment": "CRITICAL: install mechanical deaerator (spray or tray type). Dose oxygen scavengers: sodium sulphite (low-pressure boilers) or hydrazine/DEHA/carbohydrazide (high-pressure boilers). Dissolved O₂ causes electrochemical pitting corrosion of boiler steel.", "urgency": "immediate"},
        },
        "Copper": {
            "high": {"treatment": "Inspect copper alloy condenser tubes and heat exchangers for corrosion. Implement filming amine corrosion inhibitor programme. Copper deposits on boiler surface catalyse corrosion and form galvanic cells.", "urgency": "immediate"},
        },
        "Manganese": {
            "high": {"treatment": "Oxidation filtration or clarification upstream. Manganese fouling of heat exchangers and cooling tower fill reduces efficiency.", "urgency": "short_term"},
        },
        "Arsenic": {
            "high": {"treatment": "Install RO or activated alumina upstream. Worker safety risk in process steam. Notify occupational health authority.", "urgency": "immediate"},
        },
        "Lead": {
            "high": {"treatment": "Inspect lead-containing alloys or soldered joints. Install RO upstream. Serious worker safety risk in steam and condensate systems.", "urgency": "immediate"},
        },
        "Mercury": {
            "high": {"treatment": "Suspend operations pending investigation. Mercury in process steam is an extreme occupational health hazard. Identify source and notify authorities immediately.", "urgency": "immediate"},
        },
        "Sulfate": {
            "high": {"treatment": "Anion exchange resin or RO. Increase blowdown rate. High sulfate promotes CaSO₄ scaling and can form corrosive compounds at boiler temperatures.", "urgency": "routine"},
        },
        "Turbidity": {
            "high": {"treatment": "Upstream multimedia filtration (sand/anthracite). Add coagulation-sedimentation if turbidity is variable. Particulates cause abrasive fouling of pumps and heat exchangers.", "urgency": "short_term"},
        },
        "COD": {
            "high": {"treatment": "Biological pre-treatment (activated sludge). Activated carbon adsorption. UV/H₂O₂ advanced oxidation. Organic matter promotes biological fouling under deposits (MIC — microbially influenced corrosion).", "urgency": "short_term"},
        },
        "Oil_Grease": {
            "high": {"treatment": "API gravity separator for free oil. Dissolved Air Flotation (DAF) for emulsified oil. Activated carbon polishing. Oil films severely reduce heat transfer efficiency and promote biofilm formation.", "urgency": "short_term"},
        },
        "Phosphate": {
            "high": {"treatment": "Coagulation-precipitation with iron or aluminium salts. Ion exchange. Excess phosphate forms calcium phosphate scale in heat exchangers.", "urgency": "routine"},
        },
        "Zinc": {
            "high": {"treatment": "Hydroxide precipitation at pH 9–10. Ion exchange. Zinc deposits on heat transfer surfaces and can interfere with corrosion inhibitor programmes.", "urgency": "routine"},
        },
    },
}


# ── Fallback thresholds ───────────────────────────────────────────────────────
# Used only when WQI engine is unavailable. Covers the most critical parameters
# per group. Values match profile acceptable limits.

FALLBACK_THRESHOLDS = {
    "drinking": {
        "pH":               [("low", 0, 6.5), ("high", 8.5, 99)],
        "TDS":              [("high", 500, float("inf"))],
        "turbidity":        [("high", 1, float("inf"))],
        "nitrates":         [("high", 45, float("inf"))],
        "fluoride":         [("low", 0, 0.5), ("high", 1.5, float("inf"))],
        "dissolved_oxygen": [("low", 0, 4)],
        "BOD":              [("high", 3, float("inf"))],
        "coliform":         [("high", 0, float("inf"))],
        "arsenic":          [("high", 0.01, float("inf"))],
        "lead":             [("high", 0.01, float("inf"))],
    },
    "agriculture": {
        "EC":      [("high", 0.7, float("inf"))],
        "SAR":     [("high", 3.0, float("inf"))],
        "pH":      [("low", 0, 6.0), ("high", 8.4, 99)],
        "Boron":   [("high", 0.7, float("inf"))],
        "Arsenic": [("high", 0.1, float("inf"))],
        "Cadmium": [("high", 0.01, float("inf"))],
    },
    "aquaculture": {
        "DO":        [("low", 0, 5.0)],
        "pH":        [("low", 0, 6.5), ("high", 9.0, 99)],
        "Ammonia_N": [("high", 0.02, float("inf"))],
        "Nitrite":   [("high", 0.1, float("inf"))],
        "H2S":       [("high", 0.002, float("inf"))],
        "Chlorine":  [("high", 0.003, float("inf"))],
    },
    "industrial": {
        "pH":      [("low", 0, 8.0), ("high", 10.5, 99)],
        "Hardness":[("high", 50, float("inf"))],
        "Silica":  [("high", 5, float("inf"))],
        "DO":      [("high", 0.1, float("inf"))],
        "TDS":     [("high", 500, float("inf"))],
    },
}


# ── Public API ────────────────────────────────────────────────────────────────

def get_recommendations(
    sample:     dict = None,
    profile_id: str  = "bis_drinking",
    wqi_result: dict = None,
) -> dict:
    """
    Generate profile-aware treatment recommendations.

    Args:
        sample:     Raw parameter dict { "pH": 7.2, "TDS": 310, ... }.
                    Used as fallback if wqi_result not provided.
        profile_id: Profile identifier (e.g. "bis_drinking", "fao_agriculture").
        wqi_result: Output from calculate_wqi() — used as primary input.

    Returns:
        {
            "profile":         str,
            "overall_status":  str,
            "source":          str,
            "recommendations": list[dict],
            "summary":         dict,
        }
    """
    if sample is None and wqi_result is None:
        raise ValueError("Provide either sample or wqi_result.")

    group = PROFILE_GROUP.get(profile_id, "drinking")

    # ── Engine path (primary) ────────────────────────────────────────────────
    if wqi_result is not None:
        profile_params = _load_profile_params(profile_id)
        return _from_engine(wqi_result, profile_id, group, "engine", profile_params)

    # ── Sample path: run engine internally, then use engine path ─────────────
    try:
        from .wqi_calculator import calculate_wqi
        wqi_result = calculate_wqi(sample, profile_id)
        profile_params = _load_profile_params(profile_id)
        return _from_engine(wqi_result, profile_id, group, "engine_via_sample", profile_params)
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Engine failed for fallback path: {e}")

    # ── True fallback: raw threshold rules ───────────────────────────────────
    return _from_raw(sample, profile_id, group)


# ── Engine-based recommendation generation ────────────────────────────────────

def _from_engine(wqi_result: dict, profile_id: str, group: str,
                 source: str, profile_params: dict) -> dict:
    recs = []
    sub_indices    = wqi_result.get("sub_indices", {})
    overall_status = wqi_result.get("status", "UNKNOWN")

    for param, info in sub_indices.items():
        zone  = info.get("zone", "")
        layer = info.get("layer", "")
        qi    = info.get("qi") or 0
        value = info.get("value")

        # Skip params with no scoring issues
        if zone in ("ideal", "NO_DATA", "SUSPECT", "INVALID", ""):
            continue
        if zone == "acceptable" and qi < 40:
            continue

        issue    = _infer_issue(param, zone, profile_params)
        rule     = _get_rule(group, param, issue)
        priority = _zone_to_priority(zone, layer)

        if rule is None:
            # No specific rule — emit a generic recommendation for actionable zones
            if priority in ("CRITICAL", "HIGH"):
                rule = {
                    "treatment": f"Investigate and treat elevated {param}. Consult a water treatment specialist.",
                    "urgency":   "short_term",
                }
            else:
                continue

        recs.append({
            "parameter": param,
            "value":     value,
            "zone":      zone,
            "layer":     layer,
            "priority":  priority,
            "urgency":   rule["urgency"],
            "treatment": rule["treatment"],
            "source":    source,
        })
        logger.info(f"[{profile_id}][{priority}] {param} ({zone}) — {rule['treatment'][:60]}...")

    # Sort by priority, then by zone severity within same priority
    zone_rank = {"breach": 0, "deficient": 1, "permissible": 2, "acceptable": 3}
    recs.sort(key=lambda r: (
        PRIORITY_ORDER.get(r["priority"], 99),
        zone_rank.get(r["zone"], 9),
    ))

    if not recs:
        recs = [_clean_bill(source)]

    return {
        "profile":         profile_id,
        "overall_status":  overall_status,
        "source":          source,
        "recommendations": recs,
        "summary":         _summarize(recs, overall_status),
    }


# ── Raw-value fallback ────────────────────────────────────────────────────────

def _from_raw(sample: dict, profile_id: str, group: str) -> dict:
    recs      = []
    thresholds = FALLBACK_THRESHOLDS.get(group, {})

    for param, value in sample.items():
        if value is None:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue

        rules = thresholds.get(param)
        if not rules:
            continue

        for (issue, lo, hi) in rules:
            triggered = (lo <= value < hi) if hi != float("inf") else (value > lo)
            if not triggered:
                continue

            rule = _get_rule(group, param, issue)
            if rule is None:
                continue

            # Fallback mode: derive rough priority from param criticality
            critical_params = {
                "coliform", "arsenic", "lead", "nitrates",  # drinking
                "Arsenic", "Cadmium", "Lead", "Mercury", "Selenium",  # agriculture/aquaculture
                "Ammonia_N", "Nitrite", "H2S", "Chlorine", "Copper",  # aquaculture
                "Hardness", "Silica", "DO", "TDS",  # industrial
            }
            priority = "CRITICAL" if param in critical_params else "HIGH"

            recs.append({
                "parameter": param,
                "value":     value,
                "zone":      None,
                "layer":     None,
                "priority":  priority,
                "urgency":   rule["urgency"],
                "treatment": rule["treatment"],
                "source":    "fallback",
            })

    recs.sort(key=lambda r: PRIORITY_ORDER.get(r["priority"], 99))

    if not recs:
        recs = [_clean_bill("fallback")]

    return {
        "profile":         profile_id,
        "overall_status":  "UNKNOWN",
        "source":          "fallback",
        "recommendations": recs,
        "summary":         _summarize(recs, "UNKNOWN"),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_profile_params(profile_id: str) -> dict:
    """Load parameter specs from profile JSON for direction lookup."""
    try:
        profiles_dir = Path(__file__).resolve().parents[2] / "config" / "profiles"
        path = profiles_dir / f"{profile_id}.json"
        if path.exists():
            with open(path, encoding="utf-8-sig") as f:
                return json.load(f).get("parameters", {})
    except Exception as e:
        logger.warning(f"Could not load profile params for {profile_id}: {e}")
    return {}


def _infer_issue(param: str, zone: str, profile_params: dict) -> str:
    """
    Determine if this is a 'high' or 'low' issue from zone + param direction.

    Rules:
      - 'deficient' zone always means the value is too low.
      - 'down_bad' direction always means low is bad (any non-ideal zone).
      - Everything else is a 'high' issue.
    """
    if zone == "deficient":
        return "low"
    direction = profile_params.get(param, {}).get("direction", "up_bad")
    if direction == "down_bad":
        return "low"
    return "high"


def _get_rule(group: str, param: str, issue: str) -> dict | None:
    """Look up a treatment rule. Returns None if not found."""
    return TREATMENT_RULES.get(group, {}).get(param, {}).get(issue)


def _zone_to_priority(zone: str, layer: str) -> str:
    """Map zone + layer → recommendation priority."""
    if layer == "hard_gate":
        return "CRITICAL"
    if zone in ("breach", "deficient"):
        return "HIGH"
    if zone == "permissible":
        return "MEDIUM"
    return "LOW"


def _summarize(recs: list, overall_status: str) -> dict:
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for r in recs:
        p = r.get("priority", "LOW")
        if p in counts:
            counts[p] += 1

    action = overall_status in ("UNSAFE", "NON_COMPLIANT") or counts["CRITICAL"] > 0 or counts["HIGH"] > 0

    return {
        "overall_status":  overall_status,
        "total":           len(recs),
        "critical":        counts["CRITICAL"],
        "high":            counts["HIGH"],
        "medium":          counts["MEDIUM"],
        "low":             counts["LOW"],
        "action_required": action,
    }


def _clean_bill(source: str) -> dict:
    return {
        "parameter": "ALL",
        "value":     None,
        "zone":      "ideal",
        "layer":     None,
        "priority":  "LOW",
        "urgency":   "routine",
        "treatment": "All measured parameters are within acceptable limits. Continue routine monitoring.",
        "source":    source,
    }
