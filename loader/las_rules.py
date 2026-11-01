"""Rules for well-log (LAS) data. Pure functions, no database (except the optional pyproj import).

A LAS file is a table: one depth column and one column per curve (gamma ray, density...).
File-level problems (no depth, no well name) stop the load. Sample-level problems are counted:
  - null        : the file's NULL value (e.g. -999.25) or empty -> not stored
  - out of range: physically impossible for that measurement (density 9.99 g/cc),
                  or a lithology code that does not exist -> not stored, counted
"""
from __future__ import annotations

import math

FEET_TO_M = 0.3048
DEPTH_UNITS = {"M": 1.0, "METER": 1.0, "METERS": 1.0, "METRES": 1.0,
               "FT": FEET_TO_M, "F": FEET_TO_M, "FEET": FEET_TO_M, "FOOT": FEET_TO_M}

# Physical ranges by family and unit. A value outside is a tool or processing error, not geology.
RANGES = {
    ("Gamma ray", None): (0, 1500),
    ("Bulk density", None): (1.0, 3.5),
    ("Neutron porosity", "%"): (-15, 100),
    ("Neutron porosity", "PU"): (-15, 100),
    ("Neutron porosity", None): (-0.15, 1.0),         # fraction (V/V, m3/m3)
    ("Deep resistivity", None): (0.01, 100000),
    ("Medium resistivity", None): (0.01, 100000),
    ("Shallow resistivity", None): (0.01, 100000),
    ("Flushed-zone resistivity", None): (0.01, 100000),
    ("Sonic slowness", "US/M"): (100, 830),
    ("Sonic slowness", None): (30, 250),               # us/ft
    ("Shear sonic slowness", None): (50, 800),         # us/ft
    ("Caliper", "MM"): (25, 1000),                     # small mining boreholes are ~48 mm
    ("Caliper", None): (1, 40),                        # inches
    ("Photoelectric factor", None): (0, 20),
    ("Lithology confidence", None): (1, 3),            # FORCE 2020: 1 = high ... 3 = low
}

# Curves kept as statistics in the catalog but not stored sample by sample (they would
# multiply the table size without adding value for this platform)
SUMMARY_ONLY_FAMILIES = {"Position"}


def depth_factor(unit: str | None) -> float:
    """Multiplier from the file's depth unit to metres. Unknown unit -> error (never guess depths)."""
    key = (unit or "").strip().upper().rstrip(".")
    if key not in DEPTH_UNITS:
        raise ValueError(f"unknown depth unit '{unit}'")
    return DEPTH_UNITS[key]


def valid_range(family: str | None, unit: str | None) -> tuple[float, float] | None:
    if family is None:
        return None
    unit = (unit or "").strip().upper()
    return RANGES.get((family, unit)) or RANGES.get((family, None))


def classify(value, null_value: float | None, rng: tuple[float, float] | None,
             allowed_codes: set[int] | None = None) -> str:
    """'null', 'out_of_range' or 'valid' for one sample."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "null"
    if null_value is not None and math.isclose(value, null_value, rel_tol=0, abs_tol=1e-6):
        return "null"
    if allowed_codes is not None:
        return "valid" if value == int(value) and int(value) in allowed_codes else "out_of_range"
    if rng is not None and not rng[0] <= value <= rng[1]:
        return "out_of_range"
    return "valid"


def check_depths(depths: list[float]) -> str | None:
    """File-level check of the depth column. Returns a reason to refuse the file, or None."""
    if len(depths) < 2:
        return "fewer than 2 depth samples"
    if any(d is None or (isinstance(d, float) and math.isnan(d)) for d in depths):
        return "depth column contains empty values"
    increasing = all(b > a for a, b in zip(depths, depths[1:]))
    decreasing = all(b < a for a, b in zip(depths, depths[1:]))
    if not (increasing or decreasing):
        return "depth column is not strictly increasing or decreasing (repeated or shuffled depths)"
    return None


def wellbore_name(well: str | None, uwi: str | None) -> str | None:
    """The wellbore key. Some exports put a description after the id ('15/9-13 Sleipner East Appr'
    with UWI '15/9-13'): then the UWI is the clean name. Otherwise the WELL field is used."""
    well = (well or "").strip() or None
    uwi = (uwi or "").strip() or None
    if well and uwi and well != uwi and well.startswith(uwi + " "):
        return uwi
    return well or uwi


def looks_like_utm(x: float | None, y: float | None) -> bool:
    """UTM eastings are 100,000-900,000 m; northern-hemisphere northings 0-10,000,000 m."""
    return x is not None and y is not None and 100_000 <= x <= 900_000 and 1_000_000 <= y <= 10_000_000


def utm31n_ed50_to_latlon(x: float, y: float) -> tuple[float, float]:
    """ED50 / UTM zone 31N (EPSG:23031, the usual system for Norwegian North Sea data) -> WGS84 lat, lon."""
    from pyproj import Transformer
    lon, lat = Transformer.from_crs("EPSG:23031", "EPSG:4326", always_xy=True).transform(x, y)
    return lat, lon
