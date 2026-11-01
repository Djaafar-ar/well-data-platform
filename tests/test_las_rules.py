import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "loader"))

from las_rules import check_depths, classify, depth_factor, valid_range  # noqa: E402


def test_metres_and_feet():
    assert depth_factor("M") == 1.0
    assert depth_factor("ft") == pytest.approx(0.3048)
    assert depth_factor("F") == pytest.approx(0.3048)


def test_unknown_depth_unit_refused():
    with pytest.raises(ValueError):
        depth_factor("CUBITS")


def test_declared_null_is_null():
    assert classify(-999.25, -999.25, (0, 1500)) == "null"


def test_nan_is_null():
    assert classify(float("nan"), -999.25, None) == "null"


def test_impossible_density_out_of_range():
    rng = valid_range("Bulk density", "G/CC")
    assert classify(9.99, -999.25, rng) == "out_of_range"
    assert classify(2.45, -999.25, rng) == "valid"


def test_neutron_range_depends_on_unit():
    assert classify(25.0, None, valid_range("Neutron porosity", "%")) == "valid"
    assert classify(25.0, None, valid_range("Neutron porosity", "V/V")) == "out_of_range"


def test_hidden_fake_null_is_caught_as_out_of_range():
    # real case: a gamma-ray curve using -2324.28 as an undeclared "no data" value
    assert classify(-2324.28, -99999, valid_range("Gamma ray", "GAPI")) == "out_of_range"


def test_small_mining_borehole_caliper_is_valid():
    assert classify(48.0, None, valid_range("Caliper", "MM")) == "valid"


def test_unmapped_curve_has_no_range_check():
    assert valid_range(None, "DEGC") is None
    assert classify(12345.0, -999.25, None) == "valid"


def test_depths_must_be_monotonic():
    assert check_depths([100.0, 100.5, 101.0]) is None
    assert check_depths([101.0, 100.5, 100.0]) is None              # logged bottom-up is fine
    assert "not strictly" in check_depths([100.0, 100.5, 100.5, 101.0])
    assert "fewer than 2" in check_depths([100.0])


# --- milestone 7: North Sea wells --------------------------------------------------------------

from las_rules import looks_like_utm, utm31n_ed50_to_latlon, wellbore_name  # noqa: E402


def test_wellbore_name_strips_description_after_uwi():
    assert wellbore_name("15/9-13 Sleipner East Appr", "15/9-13") == "15/9-13"


def test_wellbore_name_keeps_well_when_uwi_is_a_different_id():
    assert wellbore_name("DEMO-A1", "DEMO-0000-A1") == "DEMO-A1"
    assert wellbore_name("Scorpio E1", "6038-187") == "Scorpio E1"
    assert wellbore_name(None, "15/9-13") == "15/9-13"


def test_utm_detection():
    assert looks_like_utm(437642.0, 6470975.0)
    assert not looks_like_utm(0.0, 0.0)            # common placeholder
    assert not looks_like_utm(1.93, 58.37)         # already degrees


def test_sleipner_well_lands_in_the_north_sea():
    lat, lon = utm31n_ed50_to_latlon(437642.15625, 6470975.5)    # well 15/9-13
    assert lat == pytest.approx(58.373, abs=0.002)
    assert lon == pytest.approx(1.932, abs=0.002)


def test_lithology_codes_must_exist():
    codes = {30000, 65000}
    assert classify(30000.0, -999.25, None, codes) == "valid"
    assert classify(12345.0, -999.25, None, codes) == "out_of_range"
    assert classify(30000.5, -999.25, None, codes) == "out_of_range"
    assert classify(-999.25, -999.25, None, codes) == "null"


def test_barite_mud_pef_is_excluded():
    # real case, well 29/6-1: PEF up to 377 b/e where barite-weighted mud dominates the reading
    assert classify(376.6, -999.25, valid_range("Photoelectric factor", "b/e")) == "out_of_range"
