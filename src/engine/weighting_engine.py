"""
weighting_engine.py

Orchestrator. Ties together:
  ProfileLoader → ParameterValidator → DirectionHandler → ZoneMapper → FlagEngine

Three-layer architecture:
  Layer 1 — hard_gate     : any breach → status = UNSAFE, wqi = None
  Layer 2a — non_relaxable : breach → status = NON_COMPLIANT (wqi still computed)
  Layer 2b — relaxable     : scored, blended into WQI

Output:
  {
    status:           "SAFE" | "NON_COMPLIANT" | "UNSAFE",
    wqi:              float | None,
    confidence:       float,        # valid_params / total_expected_params
    flags:            [...sorted by severity],
    dominant_issues:  [...top flagged params],
    sub_indices:      { param: { value, qi, zone, layer, impact } }
  }
"""

import json
from pathlib import Path

from .direction_handler import DirectionHandler
from .zone_mapper        import ZoneMapper
from .validator          import ParameterValidator
from .flag_engine        import FlagEngine
from .derived_metrics    import compute as compute_derived   # ← Phase 2 addition

PROFILES_DIR = Path(__file__).resolve().parents[2] / "config" / "profiles"


def load_profile(profile_id: str) -> dict:
    path = PROFILES_DIR / f"{profile_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Profile '{profile_id}' not found at {path}")
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


class WeightingEngine:

    def __init__(self, profile_id: str = "bis_drinking"):
        self.profile   = load_profile(profile_id)
        self.params    = self.profile["parameters"]
        self.direction = DirectionHandler()
        self.zone      = ZoneMapper()
        self.validator = ParameterValidator()
        self.flagger   = FlagEngine()

    # ──────────────────────────────────────────────────────────────────────────

    def compute(self, sample: dict) -> dict:
        """
        Run a sample through the full three-layer engine.
        sample: { "pH": 7.2, "TDS": 310, ... }
        """
        sample         = compute_derived(sample)   # inject SAR + future derived metrics; passthrough for drinking water profiles
        all_flags      = []
        sub_indices    = {}
        unsafe         = False
        non_compliant  = False

        relaxable_weighted_sum = 0.0
        relaxable_weight_total = 0.0
        valid_count            = 0
        total_expected         = len(self.params)

        for param, spec in self.params.items():
            value  = sample.get(param)
            layer  = spec["layer"]
            limits = spec["limits"]

            # ── Validate ─────────────────────────────────────────────────────
            vr = self.validator.validate(param, value, spec)
            if not vr.valid:
                flags = self.flagger.generate(
                    param, spec, zone="", qi=0.0,
                    safe=True, compliant=True,
                    validation_flag=vr.flag_code
                )
                all_flags.extend(flags)
                # Missing param still counts against confidence
                sub_indices[param] = {
                    "value": value, "qi": None,
                    "zone": vr.flag_code, "layer": layer,
                    "impact": spec.get("impact")
                }
                continue

            value = float(value)
            valid_count += 1

            # ── Direction + Zone ──────────────────────────────────────────────
            dr = self.direction.compute(value, spec["direction"], limits)
            zr = self.zone.map(value, dr, spec["direction"], limits, spec["relaxable"])

            qi         = zr.qi
            zone       = zr.zone
            safe       = True
            compliant  = True

            # ── Layer routing ─────────────────────────────────────────────────

            if layer == "hard_gate":
                # Check breach: zone == "breach" OR qi == 200 OR value > limit
                limit = limits["acceptable"]
                if isinstance(limit, (int, float)) and value > limit:
                    safe   = False
                    unsafe = True

            elif layer == "non_relaxable":
                acceptable = limits["acceptable"]
                lo, hi = acceptable if isinstance(acceptable, list) else (0, acceptable)
                if value < lo or value > hi:
                    compliant     = False
                    non_compliant = True

            elif layer == "relaxable":
                weight = spec.get("weight", 0)
                relaxable_weighted_sum += weight * qi
                relaxable_weight_total += weight

            # ── Flags ─────────────────────────────────────────────────────────
            flags = self.flagger.generate(
                param, spec, zone, qi, safe, compliant
            )
            all_flags.extend(flags)

            sub_indices[param] = {
                "value":  value,
                "qi":     round(qi, 2),
                "zone":   zone,
                "layer":  layer,
                "impact": spec.get("impact"),
                "normalized_distance": round(dr.normalized_distance, 4)
            }

        # ── Aggregate ─────────────────────────────────────────────────────────
        wqi = None
        if not unsafe:
            if relaxable_weight_total > 0:
                wqi = round(relaxable_weighted_sum / relaxable_weight_total, 2)
            else:
                wqi = 0.0

        confidence = round(valid_count / total_expected, 2) if total_expected > 0 else 0.0

        if unsafe:
            status = "UNSAFE"
        elif non_compliant:
            status = "NON_COMPLIANT"
        else:
            status = "SAFE"

        sorted_flags    = self.flagger.sort(all_flags)
        dominant_issues = [f.param for f in sorted_flags if f.severity in ("critical", "violation", "warning")][:3]

        return {
            "status":          status,
            "wqi":             wqi,
            "classification":  self._classify(wqi) if wqi is not None else "UNSAFE",
            "confidence":      confidence,
            "flags":           [self._flag_to_dict(f) for f in sorted_flags],
            "dominant_issues": dominant_issues,
            "sub_indices":     sub_indices,
        }

    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _classify(wqi: float) -> str:
        if wqi is None:   return "UNSAFE"
        if wqi <= 25:     return "Excellent"
        elif wqi <= 50:   return "Good"
        elif wqi <= 75:   return "Poor"
        elif wqi <= 100:  return "Very Poor"
        else:             return "Unsuitable"

    @staticmethod
    def _flag_to_dict(f) -> dict:
        return {
            "param":    f.param,
            "code":     f.code,
            "severity": f.severity,
            "message":  f.message,
            "qi":       f.qi
        }
