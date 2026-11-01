"""Generate a synthetic production file in the same column format as Volve's 'Daily Production Data'.

Fictional wells and numbers. It lets the loader run (and CI test it) without the real dataset,
and it contains deliberate errors so validation has something to catch.

Run:  python make_sample.py ../data/sample_production.csv
"""
from __future__ import annotations

import csv
import math
import random
import sys
from datetime import date, timedelta

random.seed(42)
START, DAYS = date(2015, 1, 1), 365
WELLS = [  # name, type, initial oil Sm3/d, decline per year, initial water cut
    ("DEMO-A1", "OP", 2400, 0.35, 0.05),
    ("DEMO-A2", "OP", 1700, 0.25, 0.20),
    ("DEMO-A3", "OP", 900, 0.15, 0.45),
    ("DEMO-I1", "WI", 0, 0, 0),
]
HEADER = ["DATEPRD", "WELL_BORE_CODE", "NPD_WELL_BORE_NAME", "ON_STREAM_HRS", "AVG_DOWNHOLE_PRESSURE",
          "AVG_DOWNHOLE_TEMPERATURE", "AVG_DP_TUBING", "AVG_ANNULUS_PRESS", "AVG_CHOKE_SIZE_P",
          "AVG_CHOKE_UOM", "AVG_WHP_P", "AVG_WHT_P", "DP_CHOKE_SIZE", "BORE_OIL_VOL", "BORE_GAS_VOL",
          "BORE_WAT_VOL", "BORE_WI_VOL", "FLOW_KIND", "WELL_TYPE"]


def rows():
    for name, wtype, q0, decline, wc0 in WELLS:
        for d in range(DAYS):
            day = START + timedelta(days=d)
            down = random.random() < 0.03                      # 3% of days: well shut in
            hours = 0.0 if down else round(min(24, random.gauss(23.5, 0.6)), 2)
            frac = hours / 24
            if wtype == "OP":
                oil = q0 * math.exp(-decline * d / 365) * frac * random.uniform(0.95, 1.05)
                wc = min(0.9, wc0 + 0.25 * d / 365)                # water cut rises over time
                water = oil * wc / (1 - wc)
                gas = oil * random.uniform(140, 160)
                wi = 0.0
                whp = 35 + 25 * math.exp(-decline * d / 365) + random.gauss(0, 1)
                flow = "production"
            else:
                oil = water = gas = 0.0
                wi = 5000 * frac * random.uniform(0.9, 1.1)
                whp = 180 + random.gauss(0, 3)
                flow = "injection"
            yield {
                "DATEPRD": day.strftime("%d-%b-%y"),           # Volve's date style, e.g. 01-Jan-15
                "WELL_BORE_CODE": f"NO {name}",
                "NPD_WELL_BORE_NAME": name,
                "ON_STREAM_HRS": hours,
                "AVG_DOWNHOLE_PRESSURE": round(random.gauss(240, 4), 2) if not down else "",
                "AVG_DOWNHOLE_TEMPERATURE": round(random.gauss(105, 0.5), 2) if not down else "",
                "AVG_DP_TUBING": "",
                "AVG_ANNULUS_PRESS": round(random.gauss(18, 1), 2),
                "AVG_CHOKE_SIZE_P": round(random.uniform(30, 60), 2) if not down else 0,
                "AVG_CHOKE_UOM": "%",
                "AVG_WHP_P": round(whp, 2) if not down else "",
                "AVG_WHT_P": round(random.gauss(85, 2), 2) if not down else "",
                "DP_CHOKE_SIZE": "",
                "BORE_OIL_VOL": round(oil, 1),
                "BORE_GAS_VOL": round(gas, 1),
                "BORE_WAT_VOL": round(water, 1),
                "BORE_WI_VOL": round(wi, 1),
                "FLOW_KIND": flow,
                "WELL_TYPE": wtype,
            }


def main(path: str) -> None:
    data = list(rows())
    # Deliberate data problems, the kind real exports contain
    data[10]["BORE_OIL_VOL"] = -350.0                                  # negative volume
    data[20]["AVG_CHOKE_SIZE_P"] = 150.0                               # choke above 100 %
    data[30]["DATEPRD"] = "31-Feb-15"                                  # impossible date
    data[40]["NPD_WELL_BORE_NAME"] = ""                                # missing wellbore
    data[50]["ON_STREAM_HRS"] = 0.0                                    # volumes with 0 hours -> flag
    data[400]["AVG_WHP_P"] = 9999.0                                    # pressure spike
    data.insert(61, dict(data[60]))                                    # duplicated row
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(data)
    print(f"wrote {len(data)} rows to {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sample_production.csv")
