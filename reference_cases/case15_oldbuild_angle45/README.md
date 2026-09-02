# case15 — old build, 45° horizontal angle: merging and width are separate corrections

Two runs on the **older exe build** (the one without the carbonate module), on the baseline
Macoma project: `test14.dat` at the usual 90° horizontal angle, and `test15.dat` with it
set to **45°**. Nothing else changed.

`test14.dat` turns out to be **bit-identical to [case01](../case01_macoma_cms/)** — same
84 rows, same events, dilution 387.996 — which incidentally tells us case01 was produced by
this older build too. It is kept here as the matched control for test15.

## Result 1 — merging is build-invariant; the width formula is not

The oblique-angle question splits cleanly in two, and they behave differently:

| quantity | old build | new build |
|---|---|---|
| **merging trigger** | identical | identical |
| **wastefield width** | ≈ no angle correction | `× cos(offset)` |

The merging evidence is direct: the shipped upstream example (old build, 30° offset) and
[case13](../case13_generated_example/) (new build, same project) have **bit-identical**
trajectories and merge at the same step, 260. So the merging criterion did not change
between builds. The wastefield width did — 109.59 m against 96.29 m for the same inputs.

So the cosine correction we decoded from case13 belongs specifically to the
**wastefield-width calculation in the current build**, and was evidently added between
releases. `Diffuser.effective_spacing` is scoped to exactly that.

## Result 2 — the merging criterion's angle dependence is *not* the cosine

Bracketing the merge from the output rows either side of the banner:

| run | build | offset | cos | diameter / nominal spacing at merge | cos inside? |
|---|---|---|---|---|---|
| case05 | new | 0° | 1.0000 | 0.982 – 1.012 | ✅ |
| case07 | new | 0° | 1.0000 | 0.985 – 1.038 | ✅ |
| case10 | new | 0° | 1.0000 | 0.985 – 1.038 | ✅ |
| example | old | 30° | 0.8660 | 0.895 – 0.938 | ❌ too low |
| case13 | new | 30° | 0.8660 | 0.895 – 0.938 | ❌ too low |
| **case15** | **old** | **45°** | **0.7071** | **0.793 – 0.843** | ❌ too low |

At a zero offset merging fires when the diameter reaches the spacing, exactly. At oblique
angles it fires at a *smaller* fraction of the nominal spacing — but consistently **above**
cos(offset), so the merging criterion uses a weaker angle reduction than the width does.

Candidate functions against all three brackets:

| function | 0° | 30° | 45° | fits? |
|---|---|---|---|---|
| `cos` | 1.000 | 0.866 | 0.707 | ❌ below both oblique brackets |
| `cos^(1/2)` | 1.000 | 0.931 | 0.841 | ✅ inside all three |
| `cos^(2/3)` | 1.000 | 0.909 | 0.794 | ✅ inside all three (at the lower edge) |
| `(1 + cos)/2` | 1.000 | 0.933 | 0.854 | ❌ above the 45° bracket |

So the exponent is somewhere around ½ to ⅔ and the brackets cannot separate them. We are
**not** implementing a guess: the merging criterion is recorded as measured and flagged.

### What would pin it down

The brackets are wide only because the output interval is 5 steps and the diameter grows
fast near the merge. **A single run at an oblique angle with the output interval set to 1**
would narrow each bracket by about 5×, which should separate ½ from ⅔ immediately. Any
angle works; 45° gives the biggest spread.

## Result 3 — a side effect worth noting

At 45° the plumes **merge** (step 335) where at 90° they never do — test14's diameter tops
out at 1.967 m against a 2.00 m spacing, just short. Reducing the effective spacing brings
the merge within reach. That is a nice qualitative confirmation that *some* angle reduction
is real, quite apart from which function it is.

Neither run produced a far-field section, so neither contributes a width measurement.
