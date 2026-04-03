"""
test_recommender.py
Tests for the profile-aware treatment recommender.
Covers engine path, sample fallback path, and all four profiles.
"""

import sys
import pytest
sys.path.insert(0, 'src')

from treatment.recommender import get_recommendations
from engine.wqi_calculator import calculate_wqi


# ── Helpers ───────────────────────────────────────────────────────────────────

def params(result):
    return [r["parameter"] for r in result["recommendations"]]

def priorities(result):
    return [r["priority"] for r in result["recommendations"]]

def first_priority(result):
    return result["recommendations"][0]["priority"]


# ── Engine path (wqi_result provided) ────────────────────────────────────────

class TestEnginePath:

    def test_drinking_contaminated_engine(self):
        """CRITICAL params trigger CRITICAL priority via engine path."""
        wqi = calculate_wqi({"pH": 5.5, "coliform": 8, "nitrates": 60}, profile_id="bis_drinking")
        result = get_recommendations(wqi_result=wqi, profile_id="bis_drinking")
        assert result["source"] == "engine"
        assert result["overall_status"] == "UNSAFE"
        assert "coliform" in params(result)
        assert "nitrates" in params(result)
        # coliform/nitrate should be CRITICAL (hard_gate)
        coliform_rec = next(r for r in result["recommendations"] if r["parameter"] == "coliform")
        assert coliform_rec["priority"] == "CRITICAL"

    def test_drinking_clean_sample_engine(self):
        """Clean sample → LOW priority clean bill."""
        wqi = calculate_wqi({"pH": 7.2, "TDS": 200, "dissolved_oxygen": 7.0}, profile_id="bis_drinking")
        result = get_recommendations(wqi_result=wqi, profile_id="bis_drinking")
        assert result["source"] == "engine"
        assert first_priority(result) == "LOW"
        assert result["summary"]["action_required"] is False

    def test_drinking_high_iron_engine(self):
        """Iron in breach zone → HIGH priority recommendation."""
        wqi = calculate_wqi({"pH": 7.0, "iron": 2.5, "TDS": 300}, profile_id="bis_drinking")
        result = get_recommendations(wqi_result=wqi, profile_id="bis_drinking")
        iron_rec = next((r for r in result["recommendations"] if r["parameter"] == "iron"), None)
        assert iron_rec is not None
        assert iron_rec["priority"] == "HIGH"
        assert "oxidation" in iron_rec["treatment"].lower() or "filtration" in iron_rec["treatment"].lower()

    def test_drinking_low_do_engine(self):
        """Low DO → 'low' issue direction, aeration treatment."""
        wqi = calculate_wqi({"pH": 7.0, "dissolved_oxygen": 2.0, "BOD": 8}, profile_id="bis_drinking")
        result = get_recommendations(wqi_result=wqi, profile_id="bis_drinking")
        do_rec = next((r for r in result["recommendations"] if r["parameter"] == "dissolved_oxygen"), None)
        assert do_rec is not None
        assert "aeration" in do_rec["treatment"].lower()

    def test_recommendations_sorted_by_priority(self):
        """CRITICAL recommendations always appear before HIGH/MEDIUM/LOW."""
        wqi = calculate_wqi({"pH": 5.0, "coliform": 5, "turbidity": 3}, profile_id="bis_drinking")
        result = get_recommendations(wqi_result=wqi, profile_id="bis_drinking")
        p = priorities(result)
        priority_vals = [{"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}[x] for x in p]
        assert priority_vals == sorted(priority_vals), "Recommendations must be sorted by priority"

    def test_summary_counts_correct(self):
        """Summary counts match recommendation list."""
        wqi = calculate_wqi({"pH": 5.5, "coliform": 8, "turbidity": 4}, profile_id="bis_drinking")
        result = get_recommendations(wqi_result=wqi, profile_id="bis_drinking")
        s = result["summary"]
        assert s["critical"] + s["high"] + s["medium"] + s["low"] == s["total"]
        assert s["total"] == len(result["recommendations"])


# ── Sample path (engine runs internally) ─────────────────────────────────────

class TestSamplePath:

    def test_sample_path_contaminated(self):
        """Sample path runs engine internally and returns correct recommendations."""
        result = get_recommendations(
            sample={"pH": 5.5, "coliform": 8, "nitrates": 60},
            profile_id="bis_drinking"
        )
        assert result["source"] in ("engine_via_sample", "fallback")
        assert "coliform" in params(result) or "nitrates" in params(result)

    def test_sample_path_clean(self):
        """Clean sample via sample path → LOW priority."""
        result = get_recommendations(
            sample={"pH": 7.2, "TDS": 200, "dissolved_oxygen": 7.0},
            profile_id="bis_drinking"
        )
        assert first_priority(result) == "LOW"


# ── Agriculture profile ───────────────────────────────────────────────────────

class TestAgricultureProfile:

    def test_high_sar_treatment(self):
        """High SAR → gypsum/calcium amendment recommendation."""
        sample = {"pH": 7.2, "EC": 0.5, "Na": 345, "Ca": 40, "Mg": 12, "TDS": 800}
        wqi = calculate_wqi(sample, profile_id="fao_agriculture")
        result = get_recommendations(wqi_result=wqi, profile_id="fao_agriculture")
        sar_rec = next((r for r in result["recommendations"] if r["parameter"] == "SAR"), None)
        assert sar_rec is not None
        assert "gypsum" in sar_rec["treatment"].lower()

    def test_high_ec_treatment(self):
        """High EC → dilution/salt-tolerant crops recommendation."""
        sample = {"pH": 7.0, "EC": 2.5, "SAR": 2.0, "TDS": 1600}
        wqi = calculate_wqi(sample, profile_id="fao_agriculture")
        result = get_recommendations(wqi_result=wqi, profile_id="fao_agriculture")
        ec_rec = next((r for r in result["recommendations"] if r["parameter"] == "EC"), None)
        assert ec_rec is not None
        assert "dilute" in ec_rec["treatment"].lower() or "salt-tolerant" in ec_rec["treatment"].lower()

    def test_arsenic_agriculture_critical(self):
        """Arsenic breach in agriculture → CRITICAL, immediate urgency."""
        wqi = calculate_wqi({"pH": 7.0, "EC": 0.4, "SAR": 1.0, "Arsenic": 0.5}, profile_id="fao_agriculture")
        result = get_recommendations(wqi_result=wqi, profile_id="fao_agriculture")
        assert result["overall_status"] == "UNSAFE"
        as_rec = next((r for r in result["recommendations"] if r["parameter"] == "Arsenic"), None)
        assert as_rec is not None
        assert as_rec["priority"] == "CRITICAL"
        assert as_rec["urgency"] == "immediate"


# ── Aquaculture profile ───────────────────────────────────────────────────────

class TestAquacultureProfile:

    def test_low_do_emergency(self):
        """Low DO → CRITICAL/HIGH priority with emergency aeration advice."""
        wqi = calculate_wqi({"pH": 7.5, "DO": 2.5, "Nitrate": 30}, profile_id="aquaculture")
        result = get_recommendations(wqi_result=wqi, profile_id="aquaculture")
        do_rec = next((r for r in result["recommendations"] if r["parameter"] == "DO"), None)
        assert do_rec is not None
        assert do_rec["priority"] in ("CRITICAL", "HIGH")
        assert "aerat" in do_rec["treatment"].lower()

    def test_ammonia_critical(self):
        """Ammonia hard gate breach → CRITICAL, immediate."""
        wqi = calculate_wqi({"pH": 7.5, "DO": 7.0, "Ammonia_N": 0.1}, profile_id="aquaculture")
        result = get_recommendations(wqi_result=wqi, profile_id="aquaculture")
        nh3_rec = next((r for r in result["recommendations"] if r["parameter"] == "Ammonia_N"), None)
        assert nh3_rec is not None
        assert nh3_rec["priority"] == "CRITICAL"
        assert nh3_rec["urgency"] == "immediate"

    def test_high_ph_aquaculture(self):
        """High pH → CO2 injection or water exchange recommendation."""
        wqi = calculate_wqi({"DO": 7.0, "pH": 9.5, "Nitrate": 20, "CO2": 5, "BOD": 2,
                             "Turbidity": 10, "TDS": 300, "Alkalinity": 120, "Hardness": 100,
                             "Iron": 0.1, "Temperature": 26}, profile_id="aquaculture")
        result = get_recommendations(wqi_result=wqi, profile_id="aquaculture")
        ph_rec = next((r for r in result["recommendations"] if r["parameter"] == "pH"), None)
        assert ph_rec is not None
        assert "co₂" in ph_rec["treatment"].lower() or "co2" in ph_rec["treatment"].lower() or "exchange" in ph_rec["treatment"].lower()

    def test_nitrite_critical(self):
        """Nitrite hard gate → CRITICAL, salt/exchange recommendation."""
        wqi = calculate_wqi({"pH": 7.2, "DO": 6.5, "Nitrite": 0.5}, profile_id="aquaculture")
        result = get_recommendations(wqi_result=wqi, profile_id="aquaculture")
        no2_rec = next((r for r in result["recommendations"] if r["parameter"] == "Nitrite"), None)
        assert no2_rec is not None
        assert no2_rec["priority"] == "CRITICAL"

    def test_clean_pond_no_recs(self):
        """Healthy pond water → clean bill."""
        wqi = calculate_wqi(
            {"pH": 7.5, "DO": 8.0, "Nitrate": 20, "CO2": 5, "BOD": 3,
             "Turbidity": 10, "TDS": 300, "Alkalinity": 100, "Hardness": 120,
             "Iron": 0.1, "Temperature": 25},
            profile_id="aquaculture"
        )
        result = get_recommendations(wqi_result=wqi, profile_id="aquaculture")
        assert first_priority(result) == "LOW"
        assert result["summary"]["action_required"] is False


# ── Industrial profile ────────────────────────────────────────────────────────

class TestIndustrialProfile:

    def test_hardness_critical_boiler(self):
        """Hardness breach → CRITICAL, lime/IX treatment."""
        wqi = calculate_wqi({"pH": 9.0, "Alkalinity": 100, "Hardness": 200}, profile_id="industrial")
        result = get_recommendations(wqi_result=wqi, profile_id="industrial")
        h_rec = next((r for r in result["recommendations"] if r["parameter"] == "Hardness"), None)
        assert h_rec is not None
        assert h_rec["priority"] == "CRITICAL"
        assert "softener" in h_rec["treatment"].lower() or "exchange" in h_rec["treatment"].lower() or "lime" in h_rec["treatment"].lower()

    def test_do_boiler_critical(self):
        """High DO in boiler water → CRITICAL, deaeration recommendation."""
        wqi = calculate_wqi({"pH": 9.0, "Alkalinity": 100, "Chloride": 20, "DO": 5.0}, profile_id="industrial")
        result = get_recommendations(wqi_result=wqi, profile_id="industrial")
        do_rec = next((r for r in result["recommendations"] if r["parameter"] == "DO"), None)
        assert do_rec is not None
        assert do_rec["priority"] == "CRITICAL"
        assert "deaerat" in do_rec["treatment"].lower() or "oxygen scavenger" in do_rec["treatment"].lower()

    def test_low_ph_boiler(self):
        """Low pH (below boiler acceptable) → NON_COMPLIANT, alkali dosing."""
        wqi = calculate_wqi({"pH": 7.0, "Alkalinity": 100, "Chloride": 30,
                             "Sulfate": 80, "Turbidity": 3}, profile_id="industrial")
        result = get_recommendations(wqi_result=wqi, profile_id="industrial")
        assert result["overall_status"] == "NON_COMPLIANT"
        ph_rec = next((r for r in result["recommendations"] if r["parameter"] == "pH"), None)
        assert ph_rec is not None
        assert "naoh" in ph_rec["treatment"].lower() or "caustic" in ph_rec["treatment"].lower() or "phosphate" in ph_rec["treatment"].lower()

    def test_silica_critical_boiler(self):
        """Silica hard gate breach → CRITICAL."""
        wqi = calculate_wqi({"pH": 9.0, "Alkalinity": 100, "Silica": 20}, profile_id="industrial")
        result = get_recommendations(wqi_result=wqi, profile_id="industrial")
        si_rec = next((r for r in result["recommendations"] if r["parameter"] == "Silica"), None)
        assert si_rec is not None
        assert si_rec["priority"] == "CRITICAL"

    def test_good_boiler_water(self):
        """Good boiler water → clean bill."""
        wqi = calculate_wqi(
            {"pH": 9.0, "Alkalinity": 100, "Chloride": 20,
             "Sulfate": 80, "Turbidity": 2, "COD": 10,
             "Oil_Grease": 0.5, "Phosphate": 0.5, "Zinc": 0.3},
            profile_id="industrial"
        )
        result = get_recommendations(wqi_result=wqi, profile_id="industrial")
        assert first_priority(result) == "LOW"


# ── Output structure ──────────────────────────────────────────────────────────

class TestOutputStructure:

    def test_required_keys_present(self):
        """All required keys present in output."""
        wqi = calculate_wqi({"pH": 7.2, "TDS": 300}, profile_id="bis_drinking")
        result = get_recommendations(wqi_result=wqi, profile_id="bis_drinking")
        assert "profile" in result
        assert "overall_status" in result
        assert "source" in result
        assert "recommendations" in result
        assert "summary" in result

    def test_recommendation_keys(self):
        """Each recommendation has required fields."""
        wqi = calculate_wqi({"pH": 5.0, "coliform": 5}, profile_id="bis_drinking")
        result = get_recommendations(wqi_result=wqi, profile_id="bis_drinking")
        for rec in result["recommendations"]:
            assert "parameter" in rec
            assert "priority" in rec
            assert "urgency" in rec
            assert "treatment" in rec
            assert "source" in rec

    def test_no_args_raises(self):
        """Calling with no sample and no wqi_result raises ValueError."""
        with pytest.raises(ValueError):
            get_recommendations(profile_id="bis_drinking")

    def test_profile_stored_in_output(self):
        """Output contains the correct profile_id."""
        wqi = calculate_wqi({"pH": 7.5, "DO": 8.0}, profile_id="aquaculture")
        result = get_recommendations(wqi_result=wqi, profile_id="aquaculture")
        assert result["profile"] == "aquaculture"
