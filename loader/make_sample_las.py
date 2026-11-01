"""Generate a synthetic LAS 2.0 well log for the fictional well DEMO-A1.

Geology (fictional): shale above, an oil-bearing sand at 1620-1680 m, a water-bearing sand below,
then shale again. Deliberate problems: impossible density values, negative gamma ray, nulls at the
top of the sonic log, and one curve with an unknown mnemonic (TEMPX) for the catalog to flag.

Run:  python make_sample_las.py ../tests/fixtures/DEMO-A1_logs.las
"""
from __future__ import annotations

import random
import sys

random.seed(7)
NULL = -999.25
TOP, BOTTOM, STEP = 1500.0, 1800.0, 0.5


def zone(depth: float) -> dict:
    if 1620 <= depth < 1680:      # oil sand: clean, porous, resistive
        return {"GR": 35, "RHOB": 2.25, "NPHI": 0.22, "RT": 80, "DT": 95}
    if 1680 <= depth < 1720:      # water sand: same rock, salty water -> low resistivity
        return {"GR": 38, "RHOB": 2.27, "NPHI": 0.23, "RT": 1.5, "DT": 97}
    return {"GR": 110, "RHOB": 2.52, "NPHI": 0.33, "RT": 2.5, "DT": 105}   # shale


def main(path: str) -> None:
    rows = []
    n = int((BOTTOM - TOP) / STEP) + 1
    for i in range(n):
        d = TOP + i * STEP
        z = zone(d)
        gr = z["GR"] + random.gauss(0, 6)
        rhob = z["RHOB"] + random.gauss(0, 0.02)
        nphi = z["NPHI"] + random.gauss(0, 0.01)
        rt = z["RT"] * random.uniform(0.85, 1.15)
        dt = z["DT"] + random.gauss(0, 2) if i >= 20 else NULL          # sonic starts 10 m lower
        temp = 60 + (d - TOP) * 0.03
        rows.append([d, gr, rhob, nphi, rt, dt, temp])
    for i in (100, 101, 400):
        rows[i][2] = 9.99                                                 # impossible density
    for i in (250, 251):
        rows[i][1] = -50.0                                                # negative gamma ray

    header = f"""~VERSION INFORMATION
 VERS.                 2.0 : CWLS LOG ASCII STANDARD - VERSION 2.0
 WRAP.                  NO : ONE LINE PER DEPTH STEP
~WELL INFORMATION
 STRT.M           {TOP:.4f} : START DEPTH
 STOP.M        {BOTTOM:.4f} : STOP DEPTH
 STEP.M             {STEP:.4f} : STEP
 NULL.             {NULL} : NULL VALUE
 COMP.        DEMO OPERATOR : COMPANY
 WELL.             DEMO-A1 : WELL
 WBN .          DEMO-A1 ST : WELLBORE
 FLD .          Demo Field : FIELD
 CTRY.                  DZ : COUNTRY
 SRVC.      DEMO LOGGING CO : SERVICE COMPANY
 DATE.          2015-06-01 : LOG DATE
 UWI .         DEMO-0000-A1 : UNIQUE WELL ID
~CURVE INFORMATION
 DEPT.M                    : DEPTH
 GR  .GAPI                 : GAMMA RAY
 RHOB.G/CC                 : BULK DENSITY
 NPHI.V/V                  : NEUTRON POROSITY
 RT  .OHMM                 : DEEP RESISTIVITY
 DT  .US/F                 : SONIC SLOWNESS
 TEMPX.DEGC                : TOOL TEMPERATURE (VENDOR MNEMONIC)
~ASCII
"""
    with open(path, "w", newline="\n") as f:
        f.write(header)
        for r in rows:
            f.write(" ".join(f"{v:10.4f}" for v in r) + "\n")
    print(f"wrote {len(rows)} depth samples to {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "DEMO-A1_logs.las")
