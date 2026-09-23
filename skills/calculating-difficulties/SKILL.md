---
name: calculating-difficulties
description: >
  Use when asked how hard a finished problem is, what rating it would
  get, what its expected Codeforces rating is, or when a package needs
  the difficulty.md that writing-editorials reads its number from.
  Triggers on expected rating, Codeforces rating, what would this be
  rated, how hard is this problem, rate this problem, difficulty.md,
  800-3500. Not the intended difficulty picked before the problem
  exists, which is competitive-programming:shaping-problems.
---

# Calculating difficulties

The deliverable is one file, `$PROBLEM/difficulty.md`: an estimate of
the rating this problem would receive as a single all-or-nothing
problem in a modern Div1/Div2 round, together with the anchors and the
arithmetic that produced it. Nothing else in the package changes.

The skill is **opt-in and detached**: not a phase of the setting
pipeline, a gate for no other skill, nothing downstream waiting on it
(its own `Gate` below decides only whether it estimates at all). What
does read it is `writing-editorials`, which otherwise invents a rating
on the spot for the page's `Difficulty` field and its
`<!-- EXPECTED_RATING -->` slot. When `difficulty.md` exists, that
skill copies the number out of it and does not re-estimate.

**Write the file in English**, even when the statement is Vietnamese
and the editorial will be. It is an audit trail for the setter and for
the agent that re-reads it, not a contestant-facing page, and the
anchors, tag names and calibration vocabulary it cites are all
English.

## Am I the right skill?

| If it's really about | Use |
|---|---|
| The difficulty the problem is being *aimed* at, before it exists — what `N`, what subtask ladder, is it original | `competitive-programming:shaping-problems` |
| The editorial page itself — restatement, derivation, complexity | `competitive-programming:writing-editorials` |
| Whether the test suite is strong enough to hold that difficulty up | `competitive-programming:validating-solutions` |
| Auditing a finished package before it ships | `competitive-programming:reviewing-problems` |
| Solving a problem rather than rating one | `competitive-programming:solving-problems` |

`shaping-problems` is the one worth separating carefully. It picks a
**target** and then chooses the numbers that hit it; this skill
measures what was actually built, after it was built and validated. A
package where the two disagree is a finding worth reporting, not a
contradiction to resolve by quietly editing either one.

## Bootstrap

`$BASE` is not an environment variable the harness sets — it is not
exported into a shell, only into MCP config. What you actually have is
the line **"Base directory for this skill"** printed in this skill's
own invocation preamble. Substitute that literal path for `BASE`
below:

```bash
BASE="<the path from this skill's own 'Base directory for this skill' line>"
PLUGIN_ROOT="$BASE/../.."
PROBLEM="<absolute path to the problem directory you are rating>"
cd "$PLUGIN_ROOT"
```

There is no `PREFS` line here and no `TESTLIB` one. This skill reads
no key of `preferences.toml`: the estimate is for the full-constraint
problem as a single all-or-nothing task, so neither the OI/ICPC format
nor the subtask policy changes it. It compiles nothing, runs no
solution, and executes no generator — it reads files and writes one.

The single `python3 -m tools.*` command below is a module inside
`tools/`, importable only with `PLUGIN_ROOT` as the working directory;
`cd` there first, or it fails with `ModuleNotFoundError: No module
named 'tools'` before doing anything. `$PROBLEM` is passed as an
argument, never `cd`'d into.

## Read first

- `$PROBLEM/problem.json` — `constraints`, `subtasks`, `tags` and
  `limits`. The constraints are what decide whether the intended
  solution is actually forced.
- The `.tex` statement under the problem directory, for what the
  problem asks and how much of it is disguised.
- `$PROBLEM/solutions/`, and in it the one solution tagged
  `@tag main` — the intended solution. Its metadata block carries
  `@algorithm` and `@complexity`, written by whoever set the problem.
  **Read them, then check them against the code.** They are a claim
  about the solution, not a measurement of it, and a rating built on a
  wrong `@complexity` is wrong in the same direction.

## The procedure at a glance

| Pass | Does | The rule that binds it |
|---|---|---|
| Gate | Confirms the implementation being rated was validated | No proof ⇒ write the `not estimable` file and stop |
| A | Extracts features: techniques, independent observations, hardest step, implementation weight | No number is written in this pass |
| B | Reads the prerequisite floor from `references/tag-floors.md` | The hardest technique *required*, not merely present; nothing listed ⇒ `1100` |
| C | Places the problem against 2-3 anchors from `references/anchors.md`, selected in `[floor, floor+600]` on printed ratings and compared on their Pass C.1 today ratings | Ids copied verbatim; the estimate ends within `300` of an anchor compared |
| C.1 | Era-corrects each selected anchor's printed rating to today's scale, before Pass C states its estimate | Corrects the anchors, never the estimate and never the floor |
| D | Applies feature adjustments | Total capped at `±300` |
| E | Floor gate, round, clamp, interval, anchor-id check, write | Interval is `± 300`; every id cited exists in `anchors.md` |

Each pass below states its rule in full. The table is the map, not the
procedure.

## What the number means

**The rating the full-constraint version would receive as a single
all-or-nothing problem in a modern Div1/Div2 round.**

The word **modern** is load-bearing. The scale drifts, so a rating only
means something with a date attached; this skill states its answer on
today's scale, and Pass C.1 is what puts it there.

**One number, for the whole problem.** Never a per-subtask rating: a
package whose ladder pays for three distinct insights still gets one
integer here, on the Codeforces scale, or `not estimable`. The subtask
ladder is the grading scheme, and this figure is deliberately blind to
it.

**The placement range is about `1100` to `2900`, narrower than the
scale.** The anchor table runs from `1100` to `2600`, the lowest floor
is `1100`, and Pass C's window starts at the floor, so nothing below
`1100` can be placed against an anchor and nothing above `2600` plus
Pass D's cap can. The top three rows of `tag-floors.md` have no anchor
carrying their technique. A problem that Pass A suggests lies outside
this range still gets a number, but `Confidence` must say so in the
words the template offers: a floor at `2100` or above, or a placement
at `2500` or above, is where the anchor table thins out.

The number is a **comparability figure, not a prediction**. It tells a
Codeforces-literate reader what class of problem this is. It does not
predict how a particular contest field will perform, and it says
nothing about individual subtasks. The output file must repeat this,
or the number will be over-trusted.

Codeforces ratings are fitted from contest performance — roughly the
rating at which in-contest solve probability is 50%. Tags and
constraints are not inputs to that fit. There is no formula to
recover; this skill places a problem against real rated problems
instead.

## Gate: is this estimable at all?

Estimate only when the implementation being rated has been run against
the package's own tests and met its declared expectation. One command
is the proof:

```bash
python3 -m tools.package_status "$PROBLEM"
```

Accept only these two:

1. that command prints `[x] matrix` with the detail
   `holes 0, mismatches 0` — `invocation.json` exists, is not stale,
   and the invocation matrix found neither a hole nor a mismatch —
   **and** the one `@tag main` solution declares `OK` for every group
   in its `@expect`; or
2. the user states that `validating-solutions` ran the matrix clean in
   this session.

`[ ] matrix  invocation.json is stale: ...` is **not** proof. That
detail is the status tool reporting that a solution, a test,
`problem.json` or the checker changed after the matrix was written, so
nobody currently knows whether the code being rated still passes.
Neither is `[ ] matrix  2 hole(s), 0 mismatch(es)`. A file that exists
is not a validation, and a clean compile is not an audit.

With neither, **stop and write the `not estimable` file** in `Failure
branch` below, naming which proof is missing. Do not guess from the
statement alone, and do not block anything waiting for a solution.

## Pass A — features, no numbers

Read `problem.json`, the statement, and the `@tag main` solution.
Write down, before considering any number:

- the prerequisite techniques the intended solution genuinely
  requires;
- the count of **independent** non-obvious observations. Two
  restatements of one idea count once. A step that follows routinely
  once the main technique is chosen is not a separate observation,
  however separable it looks — reducing a range query to two prefix
  queries, or compressing a state to its residue, is scaffolding, not
  insight. Count an observation only if a solver could have the main
  idea and still fail to find it;
- the single hardest step, in one sentence;
- implementation weight: how much code, and how error-prone;
- whether `constraints` force the intended solution, or a simpler one
  also fits inside `limits.time_ms_published`;
- whether the statement disguises a standard object (a graph described
  as a story, a DP described as a game).

**Write no rating in this pass.** Separating extraction from scoring is
what stops the estimate being reverse-engineered from a number you
already had in mind. The solution's own `@algorithm` and `@complexity`
are evidence for this pass, not a verdict for it: they record what the
setter believed, and this pass is where that belief is checked against
the code and the constraints.

## Pass B — the prerequisite floor

Read [`references/tag-floors.md`](references/tag-floors.md). Take the
hardest technique the solution *requires* — not one that merely
appears — and read off its floor.

A floor is not an estimate. It is the level below which this problem
cannot land, whatever the code looks like. It exists to block the
common failure of rating a digit-DP problem 1400 because the
implementation came out clean.

`problem.json`'s `tags` field is a hint, not the input. Tags are
written for contestants and for search; the floor is read off what the
code actually needs. If the solution requires nothing on the list, the
floor is `1100`.

**A `1100` floor caps what the later passes can reach at about
`2200`**, because Pass C's window starts at the floor. That is a limit
of the floor table, not a judgement about the problem: 37% of the
anchors are themselves untagged while spanning roughly 1100 to 2600.
So when Pass B lands on `1100`, treat the final number as a **lower
bound** and say so in `Confidence`.

## Pass C — anchor placement

**This pass produces the estimate and carries the accuracy.** Judging
magnitude on an unfamiliar scale is hard; comparing two concrete
problems is not. Do the second.

Read [`references/anchors.md`](references/anchors.md). Select the
window `[floor, floor+600]` on the table's **printed** `rating`
column — the window is fixed by the floor, and selection happens
before any correction, or the window would slide with every anchor.
Inside it, pick 2-3 anchors and place this problem against them:

- one that is clearly **harder** than this problem — one sentence
  saying why;
- one **similar** — one sentence;
- one clearly **easier** — one sentence.

**Copy each anchor's `id`, `rating` and `year` out of the table,
character for character.** An id you cannot find in `anchors.md` is
one you invented, and the comparison resting on it is worth nothing —
two recorded calibration rounds cited `1063D`, which is not a
Codeforces problem.

**Choose the best-matched anchors, and let their years fall where they
may.** Blind round 6 measured a preference for recent anchors at +42
MAE: only 30 of the 171 anchors are from 2025-2026, so the preference
shrank the usable table to a fifth of its size and the comparisons got
worse. Pass C.1 puts an old anchor onto today's scale arithmetically,
which is exactly so that you never have to avoid one.

**Two categories are enough when the third cannot exist.** The window
starts at the floor, so a problem that genuinely sits at its floor has
nothing easier to compare against — that is the floor working, not a
gap to paper over. Fill the categories the window supports, name the
missing one in the output, and do not reach below the floor or invent
a comparison to fill a slot.

**Trust the anchor's rating over your own sense of difficulty.** The
characteristic failure of this pass is treating the anchors as a
sanity check on a number you already formed — which leaves the scale
compressed, easy problems rated too high and hard ones too low. Read
the anchor's rating first, decide whether this problem is harder or
easier than *that specific problem*, and let the number follow from
the comparison. If your estimate ends more than `300` away from every
anchor you compared against, you did not place the problem against
them — redo the comparison rather than keeping the number.

State the estimate this placement implies, using the corrected ratings
from Pass C.1. If no anchor in the window is comparable, widen to
`[floor, floor+800]` and say in the output that the placement was
weak. Widening searches upward only; it can never supply an easier
anchor, so never widen for that reason.

## Pass C.1 — era correction

A Codeforces rating is fitted from how the field that competed **that
year** actually performed. The field has not stayed still: techniques
that were exotic in 2018 are standard preparation now, editorial and
blog coverage of them is far denser, and the median contestant has
seen more of them. Set the same problem in a round today and more of
the field solves it, so it is fitted lower.

Two consequences follow, and they point the same way:

- **The older the problem, the lower its difficulty on today's
  scale.** An old printed rating overstates what the same problem
  would be rated now.
- **The older the problem, the larger the bias in its label.** Old
  ratings were fitted on a smaller, noisier field and on a scale that
  has since drifted, so age adds uncertainty as well as offset.

So for every anchor Pass C selected, compute a **today rating** and
compare against that, never against the printed one:

```
today(anchor) = printed rating - era discount(year)
```

| Anchor year | Era discount | Label bias it carries |
|---|---|---|
| 2025-2026 | `0` | none |
| 2023-2024 | `-50` | small |
| 2021-2022 | `-100` | moderate |
| 2019-2020 | `-150` | large |
| 2018 or earlier | `-200` | large |

The `year` column of `references/anchors.md` supplies the year.

**This is a level shift, not a de-compression.** Across the anchor
table the discount averages `-102` and its per-band mean stays between
`-84` and `-127`, so in practice it lowers the whole comparison set by
about `100` rather than stretching it. That is all it is meant to do.
An explicit de-compression step was measured blind on held-out
problems and made every figure worse — see `Calibration status`.

Four rules keep this honest:

1. **Correct the anchor, never the estimate.** Once the anchors are on
   today's scale, the placement they imply is already on today's
   scale. Discounting the result again double-counts the same drift.
2. **Never correct the floor.** `tag-floors.md` states what knowledge a
   solution presupposes, which is a fact about the technique, not
   about the year some other problem was set. An era correction that
   pushes a placement under the floor is resolved by Pass E, which
   raises it back.
3. **The discount caps at `-200`.** It moves a placement by at most two
   rating steps. It is a correction, not a second opinion, and it can
   never carry a problem across the scale.
4. **Old anchors cost confidence.** If half or more of the anchors
   compared are from `2020` or earlier, the placement rests on the
   labels needing the largest and least certain correction: drop
   confidence one level (high→medium, medium→low) and say so in
   `Confidence`.

Report the printed rating, the year, and the today rating for every
anchor, so a reader can audit the correction instead of trusting it.

## Pass D — adjustments, capped at ±300

Apply only what Pass A actually found:

| Adjustment | When |
|---|---|
| `+100` each, cap `+200` | each independent insight beyond the first |
| `+100` | the statement disguises a standard object |
| `+100` | genuinely heavy implementation, not merely long |
| `-100` to `-200` | a textbook exercise in its technique. `-100` is the default; charge `-200` only when the problem is the technique's bare demonstration case, with no secondary constraint and nothing combined on top |
| `-100` | constraint leakage — a bound that names the technique by itself, readable from the constraints line alone without the legend, as `n <= 20` broadcasts "bitmask". A bound that merely rules out brute force is not leakage |

**The total is capped at ±300**, and that cap is the point: deltas must
never override the anchors. If the deltas want more than ±300, the
anchor placement in Pass C was wrong — redo Pass C instead of raising
the cap.

The era correction is not one of these adjustments and does not count
against this cap. It applies to the anchors in Pass C.1, before a
placement exists; these deltas apply to the placement afterwards.

## Pass E — gates and output

1. **If Pass D pushed the number below the Pass B floor, raise it back
   to that floor.** The floor binds the final answer, not merely the
   anchor placement — otherwise a negative adjustment reopens exactly
   the failure Pass B exists to close. When this fires, say so in
   `Confidence`: the adjustments disagreed with the floor, and the
   floor won.
2. Round to the nearest `100`.
3. Clamp to `[800, 3500]`.
4. Emit an interval, not a bare point estimate: `<number> ± 300`. The
   measured error earns `± 300` and nothing tighter; the figure itself
   lives in `Calibration status` below and nowhere else. Clamp the
   interval's endpoints to `[800, 3500]` too, the same bound as step
   3. **The output must say what that interval is** — a measured error
   band, not a confidence interval, and a reader who is not told will
   assume otherwise.
5. **Look up every anchor id you wrote in `references/anchors.md`.**
   One that is not there means Pass C compared this problem against
   one that does not exist — redo Pass C rather than shipping the
   placement.
6. Write `$PROBLEM/difficulty.md`.

The era correction can be what drives a placement under the floor, and
step 1 then raises it back. That is the design working, not a
conflict: a discount says an old *label* reads high, while the floor
says a *technique* cannot be learned cheaply. When both fire, report
both in `Confidence`.

## The output file

Write exactly this shape, in English, to `$PROBLEM/difficulty.md`:

~~~markdown
# Estimated difficulty

**Expected rating: 2100 ± 300 (estimated)**

This is a comparability figure on the Codeforces scale, not a prediction
of how any particular contest field will perform, and it does not apply
to individual subtasks. It is stated on today's scale: anchor ratings
were era-corrected before comparison. The `± 300` is a measured error
band from the skill's blind calibration, not a confidence interval; the
coverage it achieved is recorded in the skill's `Calibration status`.

## Basis

- **Prerequisite floor:** 1900 — digit DP is the hardest technique the
  solution requires.
- **Independent observations:** 2
- **Hardest step:** <one sentence>
- **Implementation weight:** <one sentence>
- **Validated by:** invocation matrix, holes 0, mismatches 0

## Anchor placement

| Problem | Printed | Year | Today | Comparison |
|---|---|---|---|---|
| 2210D | 2100 | 2026 | 2100 | Harder: <one sentence> |
| 1867E1 | 2000 | 2023 | 1950 | Similar: <one sentence> |
| 2133D | 1900 | 2025 | 1900 | Easier: <one sentence> |

Placement against the today ratings: 2000.

## Adjustments

| Adjustment | Reason |
|---|---|
| +100 | <reason> |

Total adjustment: +100 (capped at ±300). 2000 + 100 = 2100.

## Confidence

<high / medium / low, and one sentence saying why — a weak anchor window,
anchors mostly from 2020 or earlier, an unusual technique, a floor that
overrode the adjustments, a solution whose complexity depends on input
shape, a `1100` floor, which makes the number a lower bound rather than a
placement, or a floor at `2100` or above, or a placement at `2500` or
above, where the anchor table thins out>

---
Source: `calculating-difficulties` skill, calibration round 9A (2026-09-22), era
correction applied.
~~~

Keep it to that. This file is an audit trail, not an essay.

**Then say the number in the chat reply**, so a conversation that asked
"how hard is this" gets its answer without opening a file, and so
`writing-editorials` has it in context if it runs next.

## Failure branch

No validated implementation ⇒ write `$PROBLEM/difficulty.md`
containing:

~~~markdown
# Estimated difficulty

**Expected rating: not estimable**

The invocation matrix has not run clean on this package, so the
difficulty cannot be estimated. <one sentence naming what is missing>

---
Source: `calculating-difficulties` skill.
~~~

Then stop, and say so in the chat reply. A missing estimate is not a
failure of anything else: nothing in the pipeline is blocked on this
file, and `writing-editorials` simply leaves its `Difficulty` field for
the user to fill. **Never replace the absence with a guess** — an
invented rating in this file is indistinguishable from a measured one
the moment the conversation ends.

## Calibration status

The figures below are the only copy in the skill's runtime text; the
output template points here, and the round-by-round record lives in
`calibration/metrics.md`. Measured blind at round 9A on 2026-09-22
against 48 held-out problems the rubric was never tuned against,
disjoint from the anchor table, the old eval set and the frozen
corpus. Agents saw the statement and these references, never a true
rating. **They measure the skill's rubric as it stood that morning,
not the wording it has gained since**: `calibration/metrics.md` lists
that wording under `Configuration drift since round 9A`, together with
the round history, the rejected candidates and the pre-registered
rules for round 10, whose control arm measures it.

| | value | target | met |
|---|---|---|---|
| MAE | 210 | ≤ 200 | misses by 10 |
| within ±200 | 71% | ≥ 65% | yes |
| within ±300 | 85% | — | — |
| within ±400 | 88% | — | — |
| signed bias | +19 | \|bias\| ≤ 75 | yes |
| worst-band \|bias\| | 233 | ≤ 200 | misses by 33 |
| MAE, no rubric, same model | 277 | — | — |

The two misses are inside the ±28 standard error of a 48-problem set.
MAE 210 earns the `± 300` interval Pass E emits, and that interval is
a measured error band, not a confidence interval. Two results bind the
passes above: an explicit de-compression step measured worse on every
figure in a blind arm, so no such step is applied; and 19 of the 48
problems floored at the uninformative `1100`, so a `1100` floor leaves
the number resting on Pass C alone. Four arms were compared on this
set, so these figures carry a small multiple-comparison optimism.
Codeforces ratings themselves quantize to 100 and carry about ±150 of
inherent noise; no method places a problem more precisely than that.

The figures above measure the rubric — the passes, the floor table and
the anchor table — against problem statements. They do not measure
where the skill reads its inputs or writes its output, so they survive
a change to those. They would **not** survive a change to
`references/anchors.md`, `references/tag-floors.md` or any pass rule:
changing one of those means running round 10 as
`calibration/metrics.md` pre-registers it, not editing the table
above.
