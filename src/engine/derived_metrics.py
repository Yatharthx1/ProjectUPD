"""
derived_metrics.py
──────────────────
Pre-processor that computes derived parameters from raw inputs
before they reach the WQI engine.

Pipeline position:
    raw sample → compute(sample) → WeightingEngine.compute(sample)

Currently handles:
    SAR (Sodium Adsorption Ratio) — for fao_agriculture profile

Design rules:
    - Engine never knows or cares whether SAR was passed directly or computed.
    - If SAR already exists in sample, computation is skipped entirely.
    - Returns a new dict — never mutates caller's input.
    - Audit trail stored under "_derived_meta" — engine ignores unknown keys.
"""

import math


# ── Conversion factors: mg/L → meq/L ──────────────────────────────────────
# meq/L = mg/L / equivalent_weight
# Equivalent weight = atomic_mass / valence
_MEQ_FACTORS = {
    "Na": 22.990,   # monovalent:  meq/L = mg/L / 22.990
    "Ca": 20.040,   # divalent:    meq/L = mg/L / 20.040
    "Mg": 12.153,   # divalent:    meq/L = mg/L / 12.153
}


# ── Public API ─────────────────────────────────────────────────────────────

def compute(sample: dict, units: str = "mg/L") -> dict:
    """
    Run all derived metric resolutions on a sample dict.

    Args:
        sample : { "pH": 7.2, "Na": 230, "Ca": 80, "Mg": 24, ... }
        units  : unit of ionic species (Na, Ca, Mg).
                 "mg/L"  → auto-converts to meq/L before SAR formula.
                 "meq/L" → uses values directly.

    Returns:
        New dict with derived values injected + "_derived_meta" audit key.

    Usage:
        sample = compute(sample, units="mg/L")
        result = engine.compute(sample)         # engine ignores _derived_meta
    """
    sample = dict(sample)   # shallow copy — do not mutate caller's dict
    meta = {}

    sample, meta["SAR"] = _resolve_sar(sample, units)

    sample["_derived_meta"] = meta
    return sample


def compute_sar(Na: float, Ca: float, Mg: float, units: str = "mg/L") -> float:
    """
    Compute SAR directly from ionic concentrations.

    Formula (FAO Ayers & Westcot, 1985):
        SAR = Na⁺ / sqrt((Ca²⁺ + Mg²⁺) / 2)
        where all values are in meq/L.

    Args:
        Na, Ca, Mg : concentrations of sodium, calcium, magnesium.
        units      : "mg/L" (default) or "meq/L".

    Returns:
        SAR as a dimensionless float.

    Raises:
        ValueError : if any input is negative.
        ValueError : if Ca + Mg = 0 (division by zero).
        ValueError : if units is unrecognised.
    """
    if any(v < 0 for v in (Na, Ca, Mg)):
        raise ValueError(
            f"Negative ionic concentration is not physically valid. "
            f"Got Na={Na}, Ca={Ca}, Mg={Mg}."
        )

    if units == "mg/L":
        Na = Na / _MEQ_FACTORS["Na"]
        Ca = Ca / _MEQ_FACTORS["Ca"]
        Mg = Mg / _MEQ_FACTORS["Mg"]
    elif units != "meq/L":
        raise ValueError(f"Unknown units '{units}'. Use 'mg/L' or 'meq/L'.")

    denom = (Ca + Mg) / 2.0
    if denom <= 0:
        raise ValueError(
            f"Ca + Mg must be > 0 to compute SAR. "
            f"Got Ca={Ca:.4f} meq/L, Mg={Mg:.4f} meq/L."
        )

    return Na / math.sqrt(denom)


# ── Internal helpers ───────────────────────────────────────────────────────

def _resolve_sar(sample: dict, units: str) -> tuple:
    """
    Resolve SAR via one of three paths:
        1. SAR already in sample  → passthrough, no computation.
        2. Na + Ca + Mg present   → compute and inject.
        3. Partial / missing ions → skip, log in meta.

    Returns: (updated_sample, sar_meta_dict)
    """
    # Path 1 — SAR passed directly
    if "SAR" in sample and sample["SAR"] is not None:
        return sample, {
            "source": "direct",
            "value":  sample["SAR"],
        }

    # Path 2 — compute from ionic inputs
    has_na = "Na" in sample and sample["Na"] is not None
    has_ca = "Ca" in sample and sample["Ca"] is not None
    has_mg = "Mg" in sample and sample["Mg"] is not None

    if has_na and has_ca and has_mg:
        try:
            sar = compute_sar(
                Na=float(sample["Na"]),
                Ca=float(sample["Ca"]),
                Mg=float(sample["Mg"]),
                units=units,
            )
            sample["SAR"] = round(sar, 4)
            return sample, {
                "source": "computed",
                "value":  sample["SAR"],
                "inputs": {
                    "Na": sample["Na"],
                    "Ca": sample["Ca"],
                    "Mg": sample["Mg"],
                    "units": units,
                },
            }
        except ValueError as exc:
            return sample, {"source": "error", "value": None, "error": str(exc)}

    # Path 3 — insufficient inputs, skip cleanly
    missing = [k for k, ok in [("Na", has_na), ("Ca", has_ca), ("Mg", has_mg)] if not ok]
    return sample, {
        "source":  "skipped",
        "value":   None,
        "missing": missing,
    }
