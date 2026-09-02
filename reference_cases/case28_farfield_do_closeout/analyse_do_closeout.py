"""Adjudicate the close-out runs against the predictions in README.md.

Run from the repository root once the three traces are in this folder:

    .venv/Scripts/python generated/experiments/farfield_do_closeout/analyse.py

This exists so the verdict is decided by arithmetic fixed **before** the runs rather than by
whatever reading looks best afterwards. It prints what was predicted, what came back, and which
hypothesis each observable picks. The golden tests get written from the result, as they always are
-- a test asserting a prediction would only pin what we hoped for.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from plumes2.biochem.do_bod import far_field_oxygen, near_field_oxygen  # noqa: E402
from plumes2.config import EffluentDO  # noqa: E402
from plumes2.io.dat import read_dat  # noqa: E402

HERE = Path(__file__).resolve().parent

LEVELS = np.array([0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0])
FALLING = np.array([12.0, 10.0, 8.5, 7.5, 6.0, 4.0, 2.0])
RISING = FALLING[::-1].copy()

#: What the DO tab is meant to hold. ⚠️ Confirm against what was typed before trusting any of this
#: -- the tab is unsaved and retains values, which is what cost two rounds on case25 and case26.
BASE = {"cbod5": 20.0, "nbod5": 30.0, "cbod_decay": 0.23, "nbod_decay": 0.1}

#: The IDOD K3 is meant to carry. Lower it here if the exe refused 100.
IDOD = 100.0

#: Pre-registered, from README.md. `(DO_f, {hypothesis: (102 m, 300 m, 500 m)})`.
PREDICTED = {
    "K1": (8.013, {"trapping depth": (7.725, 7.476, 7.409), "depth-mean": (7.672, 7.090, 6.814)}),
    "K2": (6.375, {"trapping depth": (6.074, 5.742, 5.624), "depth-mean": (6.113, 6.028, 6.064)}),
    "K3": (
        -91.612,
        {
            "no second IDOD term": (-87.032, -57.210, -38.350),
            "second term, undiluted": (-182.134, -122.046, -84.137),
            "second term, /D_near": (-87.418, -57.473, -38.535),
        },
    ),
}

#: ⚠️ **Edit this if the exe's output counter continued** rather than restarting at 1 -- it counts
#: up across sessions, so case27's runs came back as ModelResults_1 through _10. The mapping is
#: here rather than guessed from mtimes because getting it wrong silently swaps two runs.
RUNS = {"K1": "ModelResults_1.dat", "K2": "ModelResults_2.dat", "K3": "ModelResults_3.dat"}

#: Below this, Brooks' factor is too close to 1 to invert eq 30 -- the `1 - 1/FF` divisor goes to
#: zero and amplifies the printed 0.001 without limit. 1.3 keeps the spread inside 0.03 mg/L,
#: checked against case27 run 8, whose answer is known independently.
INVERTIBLE = 1.3

#: The geometry every run must reproduce, from case27 runs 5 and 6. DO is a pure overlay (row 215),
#: so a different step count means a GUI setting moved and the run is not comparable.
GEOMETRY = (572, 246.607)


def load(name: str):  # type: ignore[no-untyped-def]
    """Everything one trace contributes, or `None` if it has not been run yet."""
    path = HERE / RUNS[name]
    if not path.exists():
        return None
    dat = read_dat(path)
    near, far = dat.nearfield, dat.farfield
    if far is None or "DO" not in far.columns:
        print(f"  {path.name}: no far-field DO column -- did the far field run?")
        return None
    dilution = float(near["Dilutn"].iloc[-1])
    return (
        path.name,
        near,
        dilution,
        float(near["DO"].iloc[-1]),
        far["Dilution"].to_numpy(dtype=float) / dilution,
        far["Time"].to_numpy(dtype=float) / 24.0,
        far["Distance"].to_numpy(dtype=float),
        far["DO"].to_numpy(dtype=float),
    )


def at_distances(distance: np.ndarray, values: np.ndarray) -> tuple[float, ...]:
    return tuple(float(values[int(np.argmin(np.abs(distance - q)))]) for q in (102.0, 300.0, 500.0))


def show(values) -> str:  # type: ignore[no-untyped-def]
    return " / ".join(f"{v:.3f}" for v in values)


def geometry_check(near, dilution: float) -> None:  # type: ignore[no-untyped-def]
    steps, expected = GEOMETRY
    trapping = -float(near["Depth"].iloc[-1])
    ok = abs(dilution - expected) < 0.01 and len(near) == steps
    print(f"  geometry: {len(near)} steps, D_near {dilution:.3f}, trapping depth "
          f"{trapping:.3f} m  [{'ok' if ok else 'CHANGED'}]")
    if not ok:
        print("     ⚠️ the trajectory moved, so this run is not comparable with the others and DO "
              "is no longer a pure overlay. Check the GUI settings before reading on.")


def report_profile_run(label, profile, loaded) -> None:  # type: ignore[no-untyped-def]
    name, near, dilution, do_f, factor, days, distance, printed = loaded
    predicted_f, hypotheses = PREDICTED[label]
    print(f"\n{label} -- {name}")
    geometry_check(near, dilution)

    steps = near["Dilutn"].to_numpy(dtype=float)
    depth = -near["Depth"].to_numpy(dtype=float)
    effluent = EffluentDO(dissolved_oxygen=2.0, idod=0.0, **BASE)
    ours = near_field_oxygen(effluent, np.interp(depth, LEVELS, profile), steps)
    worst = float(np.max(np.abs(ours - near["DO"].to_numpy(dtype=float))))
    print(f"  near field: DO_f {do_f:.3f} (predicted {predicted_f:.3f}); "
          f"the path integral reproduces the column to {worst:.4f} mg/L")

    print(f"  far field at 102/300/500 m: {show(at_distances(distance, printed))}")
    for hypothesis, values in hypotheses.items():
        print(f"     predicted, {hypothesis:16s} {show(values)}")

    # Invert eq 30 for the ambient the exe actually used, then read it back as a depth.
    demand = -factor * far_field_oxygen(
        effluent, 0.0, 0.0, 0.0, 0.0, dilution, factor, days, reproduce_undiluted_bod=True
    )
    usable = factor > INVERTIBLE
    implied = (printed - (do_f - demand) / factor)[usable] / (1.0 - 1.0 / factor[usable])
    ambient = float(np.median(implied))
    order = np.argsort(profile)
    depth_of = float(np.interp(ambient, profile[order], LEVELS[order]))
    print(f"  ⭐ implied DO_a = {ambient:.3f} mg/L over {int(usable.sum())} invertible rows "
          f"(spread {implied.min():.3f} to {implied.max():.3f})")
    print(f"     which is the profile's value at {depth_of:.3f} m")
    print(f"     candidates: trapping 4.472 m = {np.interp(4.472, LEVELS, profile):.3f}, "
          f"depth-mean = {float(np.trapezoid(profile, LEVELS) / 12.0):.3f}, "
          f"mid-depth 6 m = {np.interp(6.0, LEVELS, profile):.3f}, "
          f"port 11 m = {np.interp(11.0, LEVELS, profile):.3f}")


def report_idod_run(loaded) -> None:  # type: ignore[no-untyped-def]
    name, near, dilution, do_f, factor, days, distance, printed = loaded
    predicted_f, hypotheses = PREDICTED["K3"]
    print(f"\nK3 -- {name}")
    geometry_check(near, dilution)

    column = near["DO"].to_numpy(dtype=float)
    steps = near["Dilutn"].to_numpy(dtype=float)
    print(f"  near field: DO_f {do_f:.3f} (predicted {predicted_f:.3f}), min {column.min():.3f}")
    if column.min() >= 0.0:
        print("  ⭐⭐ THE NEAR FIELD CLAMPS -- no negative DO printed, where -91 was predicted. "
              "That is a finding in itself, and near_field_oxygen needs the clamp behind a flag.")
    else:
        print("  ⭐ no clamp: the near field prints negative oxygen, as the far field does.")

    effluent = EffluentDO(dissolved_oxygen=2.0, idod=IDOD, **BASE)
    ours = near_field_oxygen(
        effluent, np.full_like(column, 8.0), steps, reproduce_idod_on_ambient=True
    )
    developed = steps > 5.0
    print(f"  IDOD on the ambient reproduces the column to "
          f"{float(np.max(np.abs((ours - column)[developed]))):.4f} mg/L past D > 5 "
          f"(row 242 got 0.0010 at IDOD 3)")

    print(f"  far field at 102/300/500 m: {show(at_distances(distance, printed))}")
    base = far_field_oxygen(
        effluent, 8.0, 0.0, 0.0, do_f, dilution, factor, days, reproduce_undiluted_bod=True
    )
    offsets = {
        "no second IDOD term": 0.0,
        "second term, undiluted": IDOD,
        "second term, /D_near": IDOD / dilution,
    }
    for hypothesis, values in hypotheses.items():
        residual = float(np.max(np.abs((base - offsets[hypothesis] / factor) - printed)))
        print(f"     {hypothesis:24s} predicted {show(values):>26s}   worst {residual:9.3f}")


def main() -> None:
    print("Close-out runs against the predictions registered in README.md")
    print("=" * 78)
    for label, profile in (("K1", FALLING), ("K2", RISING)):
        loaded = load(label)
        if loaded is None:
            print(f"\n{label}: {RUNS[label]} not found -- run it, or fix RUNS above")
            continue
        report_profile_run(label, profile, loaded)

    loaded = load("K3")
    if loaded is None:
        print(f"\nK3: {RUNS['K3']} not found -- run it, or fix RUNS above")
    else:
        report_idod_run(loaded)

    first, second = load("K1"), load("K2")
    if first and second:
        gap = at_distances(first[6], first[7])[2] - at_distances(second[6], second[7])[2]
        nearer = "trapping depth" if abs(gap - 1.785) < abs(gap - 0.750) else "depth-mean"
        margin = abs(abs(gap - 1.785) - abs(gap - 0.750))
        print(f"\n⭐⭐ THE DISCRIMINATOR: K1 - K2 at 500 m = {gap:.3f} mg/L")
        print("   predicted 1.785 if eq 30's DO_a is the trapping-depth value, 0.750 if the "
              "depth-mean.")
        print(f"   -> nearer to **{nearer}**, by {margin:.3f} mg/L. A result near neither means "
              "DO_a is something else, and the implied-depth lines above say what.")


if __name__ == "__main__":
    main()
