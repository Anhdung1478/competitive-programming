# Metrics

Every round is appended, never overwritten: the comparison between rounds is the
only evidence that tuning helped. A 24-problem eval set carries roughly ±40
standard error — a movement smaller than that is not an improvement.

Targets: MAE ≤ 200, ≥65% within ±200, |bias| ≤ 75, **worst-band |bias| ≤ 200**.

The fourth target was added on 2026-09-19, after the retrodiction study below showed the
third one is close to worthless on its own: round 4 met |bias| ≤ 75 with an aggregate of −29
while carrying per-band biases of +400 and −367. Aggregate signed bias is an average of
signed errors, so a scale compressed symmetrically from both ends scores perfectly on it.
Any round that reports the aggregate without the per-band column is reporting a number that
cannot fail. Record `worst band` (largest |bias| of any single band) and `spread` (most
over-rated band minus most under-rated band) for every round from here on.

## predictions-baseline

n = 24   MAE = 658   bias = +625   within200 = 25%   within300 = 29%

| band | n | MAE | bias |
|---|---|---|---|
| 1100-1299 | 3 | 800 | +800 |
| 1300-1499 | 3 | 900 | +900 |
| 1500-1699 | 3 | 400 | +400 |
| 1700-1899 | 3 | 1233 | +1233 |
| 1900-2099 | 3 | 633 | +633 |
| 2100-2299 | 3 | 633 | +633 |
| 2300-2499 | 3 | 367 | +233 |
| 2500-2699 | 3 | 300 | +167 |

| slot | true | predicted | error |
|---|---|---|---|
| eval-01 | 2400 | 2300 | -100 |
| eval-02 | 2400 | 3300 | +900 |
| eval-03 | 2100 | 2900 | +800 |
| eval-04 | 2500 | 2300 | -200 |
| eval-05 | 2300 | 2200 | -100 |
| eval-06 | 1600 | 2000 | +400 |
| eval-07 | 1100 | 1700 | +600 |
| eval-08 | 1900 | 2900 | +1000 |
| eval-09 | 2500 | 2500 | +0 |
| eval-10 | 1500 | 1700 | +200 |
| eval-11 | 1800 | 3200 | +1400 |
| eval-12 | 2000 | 2500 | +500 |
| eval-13 | 1100 | 2700 | +1600 |
| eval-14 | 1600 | 2200 | +600 |
| eval-15 | 1700 | 2900 | +1200 |
| eval-16 | 2000 | 2400 | +400 |
| eval-17 | 2200 | 2500 | +300 |
| eval-18 | 1300 | 2200 | +900 |
| eval-19 | 2500 | 3200 | +700 |
| eval-20 | 1300 | 2000 | +700 |
| eval-21 | 1700 | 2800 | +1100 |
| eval-22 | 1400 | 2500 | +1100 |
| eval-23 | 2200 | 3000 | +800 |
| eval-24 | 1100 | 1300 | +200 |

## predictions-round1

n = 24   MAE = 408   bias = +192   within200 = 29%   within300 = 46%

| band | n | MAE | bias |
|---|---|---|---|
| 1100-1299 | 3 | 300 | +300 |
| 1300-1499 | 3 | 600 | +600 |
| 1500-1699 | 3 | 433 | +433 |
| 1700-1899 | 3 | 300 | +300 |
| 1900-2099 | 3 | 467 | +467 |
| 2100-2299 | 3 | 233 | +100 |
| 2300-2499 | 3 | 467 | -400 |
| 2500-2699 | 3 | 467 | -267 |

| slot | true | predicted | error |
|---|---|---|---|
| eval-01 | 2400 | 2000 | -400 |
| eval-02 | 2400 | 2500 | +100 |
| eval-03 | 2100 | 2200 | +100 |
| eval-04 | 2500 | 1800 | -700 |
| eval-05 | 2300 | 1400 | -900 |
| eval-06 | 1600 | 1700 | +100 |
| eval-07 | 1100 | 1300 | +200 |
| eval-08 | 1900 | 2400 | +500 |
| eval-09 | 2500 | 2100 | -400 |
| eval-10 | 1500 | 1800 | +300 |
| eval-11 | 1800 | 2100 | +300 |
| eval-12 | 2000 | 2300 | +300 |
| eval-13 | 1100 | 1700 | +600 |
| eval-14 | 1600 | 2500 | +900 |
| eval-15 | 1700 | 2100 | +400 |
| eval-16 | 2000 | 2600 | +600 |
| eval-17 | 2200 | 2000 | -200 |
| eval-18 | 1300 | 1700 | +400 |
| eval-19 | 2500 | 2800 | +300 |
| eval-20 | 1300 | 1700 | +400 |
| eval-21 | 1700 | 1900 | +200 |
| eval-22 | 1400 | 2400 | +1000 |
| eval-23 | 2200 | 2600 | +400 |
| eval-24 | 1100 | 1200 | +100 |
## predictions-round2

n = 24   MAE = 475   bias = +250   within200 = 33%   within300 = 38%

| band | n | MAE | bias |
|---|---|---|---|
| 1100-1299 | 3 | 400 | +400 |
| 1300-1499 | 3 | 700 | +700 |
| 1500-1699 | 3 | 300 | +300 |
| 1700-1899 | 3 | 733 | +733 |
| 1900-2099 | 3 | 400 | +400 |
| 2100-2299 | 3 | 300 | +167 |
| 2300-2499 | 3 | 533 | -533 |
| 2500-2699 | 3 | 433 | -167 |

| slot | true | predicted | error |
|---|---|---|---|
| eval-01 | 2400 | 1800 | -600 |
| eval-02 | 2400 | 2300 | -100 |
| eval-03 | 2100 | 1900 | -200 |
| eval-04 | 2500 | 1800 | -700 |
| eval-05 | 2300 | 1400 | -900 |
| eval-06 | 1600 | 1700 | +100 |
| eval-07 | 1100 | 1400 | +300 |
| eval-08 | 1900 | 2000 | +100 |
| eval-09 | 2500 | 2300 | -200 |
| eval-10 | 1500 | 1600 | +100 |
| eval-11 | 1800 | 2600 | +800 |
| eval-12 | 2000 | 2500 | +500 |
| eval-13 | 1100 | 1900 | +800 |
| eval-14 | 1600 | 2300 | +700 |
| eval-15 | 1700 | 2600 | +900 |
| eval-16 | 2000 | 2600 | +600 |
| eval-17 | 2200 | 2400 | +200 |
| eval-18 | 1300 | 2000 | +700 |
| eval-19 | 2500 | 2900 | +400 |
| eval-20 | 1300 | 1800 | +500 |
| eval-21 | 1700 | 2200 | +500 |
| eval-22 | 1400 | 2300 | +900 |
| eval-23 | 2200 | 2700 | +500 |
| eval-24 | 1100 | 1200 | +100 |
## predictions-round3

n = 24   MAE = 329   bias = +179   within200 = 50%   within300 = 62%

| band | n | MAE | bias |
|---|---|---|---|
| 1100-1299 | 3 | 167 | +167 |
| 1300-1499 | 3 | 800 | +800 |
| 1500-1699 | 3 | 200 | +200 |
| 1700-1899 | 3 | 467 | +467 |
| 1900-2099 | 3 | 233 | +233 |
| 2100-2299 | 3 | 33 | +33 |
| 2300-2499 | 3 | 433 | -300 |
| 2500-2699 | 3 | 300 | -167 |

| slot | true | predicted | error |
|---|---|---|---|
| eval-01 | 2400 | 2100 | -300 |
| eval-02 | 2400 | 2600 | +200 |
| eval-03 | 2100 | 2200 | +100 |
| eval-04 | 2500 | 1900 | -600 |
| eval-05 | 2300 | 1500 | -800 |
| eval-06 | 1600 | 1600 | +0 |
| eval-07 | 1100 | 1200 | +100 |
| eval-08 | 1900 | 2100 | +200 |
| eval-09 | 2500 | 2400 | -100 |
| eval-10 | 1500 | 1600 | +100 |
| eval-11 | 1800 | 2100 | +300 |
| eval-12 | 2000 | 2200 | +200 |
| eval-13 | 1100 | 1500 | +400 |
| eval-14 | 1600 | 2100 | +500 |
| eval-15 | 1700 | 2400 | +700 |
| eval-16 | 2000 | 2300 | +300 |
| eval-17 | 2200 | 2200 | +0 |
| eval-18 | 1300 | 1900 | +600 |
| eval-19 | 2500 | 2700 | +200 |
| eval-20 | 1300 | 2600 | +1300 |
| eval-21 | 1700 | 2100 | +400 |
| eval-22 | 1400 | 1900 | +500 |
| eval-23 | 2200 | 2200 | +0 |
| eval-24 | 1100 | 1100 | +0 |

## Post-freeze corrections

- **`1797C` label corrected after measurement.** `anchors.md` carried `1500 | Div1+2`; the
  corpus (written from the Codeforces API) says `1600 | Div2`. Corrected in `anchors.md` on
  2026-09-16, after the rounds above were measured. `1797C` was a comparison anchor for
  `eval-21` in rounds 1 and 3, so the shipped anchor table differs by this one 100-point
  label from the table those rounds used. Not re-measured: a 100-point change to one of 55
  anchors is far inside the ±40 standard error on MAE, and re-running a round to chase it
  would cost more than it could resolve.
- **Two prediction rows cite an anchor id that does not exist.** `predictions-round2.md`
  (`eval-21`) and `predictions-round3.md` (`eval-11`) both name `1063D`; the anchor table
  contains `1063C`. The blindness check in the eval protocol looks for agents naming real
  Codeforces problem ids, so a mistyped id passed through it. Effect on the aggregate is at
  most 1 row of 24 and the figures above are unchanged; recorded here rather than left silent.
## predictions-round4

n = 24   MAE = 279   bias = -29   within200 = 58%   within300 = 62%

| band | n | MAE | bias |
|---|---|---|---|
| 1100-1299 | 3 | 233 | +233 |
| 1300-1499 | 3 | 400 | +400 |
| 1500-1699 | 3 | 167 | -33 |
| 1700-1899 | 3 | 200 | +133 |
| 1900-2099 | 3 | 133 | +0 |
| 2100-2299 | 3 | 333 | -267 |
| 2300-2499 | 3 | 400 | -333 |
| 2500-2699 | 3 | 367 | -367 |

| slot | true | predicted | error |
|---|---|---|---|
| eval-01 | 2400 | 1800 | -600 |
| eval-02 | 2400 | 2500 | +100 |
| eval-03 | 2100 | 2000 | -100 |
| eval-04 | 2500 | 2100 | -400 |
| eval-05 | 2300 | 1800 | -500 |
| eval-06 | 1600 | 1400 | -200 |
| eval-07 | 1100 | 1200 | +100 |
| eval-08 | 1900 | 2000 | +100 |
| eval-09 | 2500 | 2200 | -300 |
| eval-10 | 1500 | 1400 | -100 |
| eval-11 | 1800 | 1700 | -100 |
| eval-12 | 2000 | 2100 | +100 |
| eval-13 | 1100 | 1600 | +500 |
| eval-14 | 1600 | 1800 | +200 |
| eval-15 | 1700 | 2200 | +500 |
| eval-16 | 2000 | 1800 | -200 |
| eval-17 | 2200 | 1400 | -800 |
| eval-18 | 1300 | 1700 | +400 |
| eval-19 | 2500 | 2100 | -400 |
| eval-20 | 1300 | 1500 | +200 |
| eval-21 | 1700 | 1700 | +0 |
| eval-22 | 1400 | 2000 | +600 |
| eval-23 | 2200 | 2300 | +100 |
| eval-24 | 1100 | 1200 | +100 |
## predictions-round5

n = 24   MAE = 275   bias = +8   within200 = 54%   within300 = 62%

| band | n | MAE | bias |
|---|---|---|---|
| 1100-1299 | 3 | 200 | +200 |
| 1300-1499 | 3 | 433 | +433 |
| 1500-1699 | 3 | 167 | +33 |
| 1700-1899 | 3 | 400 | +133 |
| 1900-2099 | 3 | 100 | -33 |
| 2100-2299 | 3 | 300 | -100 |
| 2300-2499 | 3 | 300 | -300 |
| 2500-2699 | 3 | 300 | -300 |

| slot | true | predicted | error |
|---|---|---|---|
| eval-01 | 2400 | 1900 | -500 |
| eval-02 | 2400 | 2400 | +0 |
| eval-03 | 2100 | 2200 | +100 |
| eval-04 | 2500 | 2300 | -200 |
| eval-05 | 2300 | 1900 | -400 |
| eval-06 | 1600 | 1400 | -200 |
| eval-07 | 1100 | 1200 | +100 |
| eval-08 | 1900 | 1900 | +0 |
| eval-09 | 2500 | 2100 | -400 |
| eval-10 | 1500 | 1500 | +0 |
| eval-11 | 1800 | 1400 | -400 |
| eval-12 | 2000 | 2100 | +100 |
| eval-13 | 1100 | 1500 | +400 |
| eval-14 | 1600 | 1900 | +300 |
| eval-15 | 1700 | 2400 | +700 |
| eval-16 | 2000 | 1800 | -200 |
| eval-17 | 2200 | 1600 | -600 |
| eval-18 | 1300 | 1800 | +500 |
| eval-19 | 2500 | 2200 | -300 |
| eval-20 | 1300 | 1500 | +200 |
| eval-21 | 1700 | 1800 | +100 |
| eval-22 | 1400 | 2000 | +600 |
| eval-23 | 2200 | 2400 | +200 |
| eval-24 | 1100 | 1200 | +100 |

## Retrodiction study — Pass C.1 and Pass D.1 (2026-09-19, post-freeze)

**Not a blind round.** Rounds 4 and 5 recorded, per slot, the predicted rating, the
prerequisite floor, and the ids of the anchors compared. That is enough to recompute what a
different post-placement arithmetic would have produced, holding the agent's anchor choice
and raw placement fixed. Reproduce with `python calibration/retrodict.py`.

### The defect being attacked

Regressing predicted on true gives a slope of **0.49** in round 4 and **0.54** in round 5:
the estimator recovers about half the spread of the truth. Aggregate signed bias was already
near zero (−29, +8) purely by cancellation, so it was never the quantity worth optimising.
The quantity worth optimising is per-band bias — reported below as `worst band` (the largest
|bias| of any band) and `spread` (most over-rated band minus most under-rated band).

### Results

| round | configuration | MAE | bias | within ±200 | worst band | spread |
|---|---|---|---|---|---|---|
| 4 | frozen | 279 | −29 | 58% | 400 | 767 |
| 4 | + era correction | 269 | −40 | 50% | 383 | 683 |
| 4 | + era + de-compression (shipped) | 277 | −48 | 46% | 283 | 550 |
| 5 | frozen | 275 | +8 | 54% | 433 | 733 |
| 5 | + era correction | 260 | +15 | 54% | 333 | 617 |
| 5 | + era + de-compression (shipped) | 277 | +2 | 46% | 300 | 517 |

Worst-band bias falls by 117 and 133; spread falls by 217 and 216; MAE is flat (279→277,
275→277, both far inside the ±40 standard error). Within ±200 falls from 58%→46% and
54%→46% — a deliberate trade of hit rate for per-band bias, and the honest cost of Pass D.1.

Per-band bias, frozen → shipped:

| band | round 4 | round 5 |
|---|---|---|
| 1100-1299 | +233 → +233 | +200 → +200 |
| 1300-1499 | +400 → +267 | +433 → +300 |
| 1500-1699 | −33 → −67 | +33 → +0 |
| 1700-1899 | +133 → +50 | +133 → +117 |
| 1900-2099 | +0 → −33 | −33 → −67 |
| 2100-2299 | −267 → −267 | −100 → −100 |
| 2300-2499 | −333 → −283 | −300 → −217 |
| 2500-2699 | −367 → −283 | −300 → −217 |

The two extreme bands (1300-1499 over-rated, 2300+ under-rated) are where the gain is. The
1100-1299 band does not move: the prerequisite floor holds those estimates up, which is the
floor doing its job and is not something de-compression should override.

### Parameter choice

Pivot `1800` is the midpoint of the anchor table's 1100-2600 range and was fixed before
measuring. Pivot sensitivity at factor 1.20, both rounds: pivots 1600-1800 give worst-band
283-300 and spread 483-550; pivots 1900-2000 degrade round 4 (worst-band 350). The step does
not balance on the constant within the 1600-1800 range.

Factor `1.20` deliberately under-corrects: fully inverting a 0.49 slope means expanding by
2.04, and the sweep shows the cost rising steeply past 1.30 (round 4 MAE 302 at 1.30, 331 at
1.50 with the floor gate applied after expansion). 1.20 is the conservative end of the range
that helped both rounds.

**The factor and pivot were chosen from a sweep over the same 24 problems**, which is
fitting. The mitigations are that the direction replicates across two rounds, the factor sits
at the conservative end, and the pivot is stable across a 200-point window. A blind round 6
is what would settle it.

### Rejected, recorded so they are not retried

| candidate | round 4 MAE | round 4 spread | verdict |
|---|---|---|---|
| estimate := median(anchors compared) | 292 | 900 | worse — the anchors an agent *selects* are themselves compressed toward the middle, so the agent's own judgement is adding value over its anchor picks |
| estimate := hardest anchor compared | 283 | 900 | worse |
| estimate := mean(prediction, anchor median) | 271 | 867 | MAE fine, spread worse |

The first result is the informative one: it rules out "pin the estimate to an anchor" as a
fix, and it means anchor *selection* is compressed as well as the final number.

### What this study cannot see

It holds the agent's behaviour fixed. Pass C.1 tells the agent to prefer recent anchors when
the window offers a choice; the retrodiction can only re-score the anchor set the agent
actually picked. It also runs on the same 24 problems used for six rounds of tuning, which
are no longer held out in any strict sense. Both push the figures optimistic by an unmeasured
amount.

## predictions-round6

n = 24   MAE = 321   bias = -21   within200 = 50%   within300 = 62%

| band | n | MAE | bias |
|---|---|---|---|
| 1100-1299 | 3 | 167 | +167 |
| 1300-1499 | 3 | 467 | +467 |
| 1500-1699 | 3 | 233 | -100 |
| 1700-1899 | 3 | 467 | +67 |
| 1900-2099 | 3 | 100 | -33 |
| 2100-2299 | 3 | 367 | -167 |
| 2300-2499 | 3 | 500 | -300 |
| 2500-2699 | 3 | 267 | -267 |

| slot | true | predicted | error |
|---|---|---|---|
| eval-01 | 2400 | 1800 | -600 |
| eval-02 | 2400 | 2700 | +300 |
| eval-03 | 2100 | 2200 | +100 |
| eval-04 | 2500 | 2200 | -300 |
| eval-05 | 2300 | 1700 | -600 |
| eval-06 | 1600 | 1200 | -400 |
| eval-07 | 1100 | 1100 | +0 |
| eval-08 | 1900 | 2000 | +100 |
| eval-09 | 2500 | 2300 | -200 |
| eval-10 | 1500 | 1400 | -100 |
| eval-11 | 1800 | 1300 | -500 |
| eval-12 | 2000 | 2000 | +0 |
| eval-13 | 1100 | 1500 | +400 |
| eval-14 | 1600 | 1800 | +200 |
| eval-15 | 1700 | 2500 | +800 |
| eval-16 | 2000 | 1800 | -200 |
| eval-17 | 2200 | 1400 | -800 |
| eval-18 | 1300 | 1800 | +500 |
| eval-19 | 2500 | 2200 | -300 |
| eval-20 | 1300 | 1300 | +0 |
| eval-21 | 1700 | 1600 | -100 |
| eval-22 | 1400 | 2300 | +900 |
| eval-23 | 2200 | 2400 | +200 |
| eval-24 | 1100 | 1200 | +100 |

### Round 6 rejected the retrodiction study's conclusion

Round 6 is the blind test the retrodiction study said was needed. **It refuted it.**

| | MAE | bias | ±200 | worst band | spread |
|---|---|---|---|---|---|
| round 4 (frozen) | 279 | −29 | 58% | 400 | 767 |
| retrodiction *predicted* for the shipped config | 277 | −48 | 46% | 283 | 550 |
| **round 6 (blind, actual)** | **321** | **−21** | **50%** | **467** | **767** |

Every headline number is worse than round 4 or unchanged, except aggregate bias, where
−29 → −21 is noise. The predicted worst-band collapse from 400 to 283 did not happen; the
measured value went the other way, to 467.

**Isolating the two passes.** Pass D.1 is deterministic arithmetic, so it can be inverted
from the recorded predictions (`pre = 1800 + (final − 1800) / 1.20`, approximate to ±50
because the recorded value is rounded to 100). That gives round 6 with the era correction
only:

| configuration | MAE | bias | ±200 | worst band | spread |
|---|---|---|---|---|---|
| round 4 (frozen) | 279 | −29 | 58% | 400 | 767 |
| round 6, era correction only (D.1 inverted) | 312 | −21 | 50% | 467 | 834 |
| round 6, era + de-compression (as run) | 321 | −21 | 50% | 467 | 767 |

So de-compression accounts for only 9 points of the 42-point MAE regression. **The bulk of
the damage is in the era correction pass, and specifically not in its arithmetic.**

**The mechanism.** The era discount is bounded by ±200 and near-flat across bands, so it
cannot move MAE by 33 points on its own — the retrodiction confirmed that, and the
retrodiction's arithmetic was correct. What the retrodiction could not see is the one thing
round 6 changed that it held fixed: **anchor selection.** Pass C told agents to prefer the
more recent of two comparable anchors. Only 30 of the 171 anchors are from 2025-2026 against
78 from 2018-2020, so that instruction steered every placement into a pool roughly a fifth
the size of the table, and the resulting comparisons are worse matched. The anchors cited in
round 6 are visibly dominated by 2025-2026 ids.

This is the failure mode the retrodiction study explicitly warned about under `What this
study cannot see` — "told to prefer recent anchors, it would pick a different set, and the
recorded set is all the retrodiction has." The warning was correct and the study was run
anyway; that is the lesson worth keeping.

**Action taken.** Pass D.1 deleted — it was never independently supported and costs 9 MAE.
The `prefer the more recent anchor` instruction deleted from Pass C — it is the identified
mechanism and it was an addition, not part of the era rule proper. The era discount
arithmetic is retained. Round 7 tests that combination; if it does not return to round-4
figures, the era correction goes too.

## predictions-round7

n = 24   MAE = 254   bias = -46   within200 = 54%   within300 = 62%

| band | n | MAE | bias |
|---|---|---|---|
| 1100-1299 | 3 | 200 | +200 |
| 1300-1499 | 3 | 300 | +300 |
| 1500-1699 | 3 | 167 | -33 |
| 1700-1899 | 3 | 300 | +33 |
| 1900-2099 | 3 | 100 | -100 |
| 2100-2299 | 3 | 300 | -100 |
| 2300-2499 | 3 | 333 | -333 |
| 2500-2699 | 3 | 333 | -333 |

| slot | true | predicted | error |
|---|---|---|---|
| eval-01 | 2400 | 1900 | -500 |
| eval-02 | 2400 | 2400 | +0 |
| eval-03 | 2100 | 2200 | +100 |
| eval-04 | 2500 | 2100 | -400 |
| eval-05 | 2300 | 1800 | -500 |
| eval-06 | 1600 | 1400 | -200 |
| eval-07 | 1100 | 1200 | +100 |
| eval-08 | 1900 | 1900 | +0 |
| eval-09 | 2500 | 2100 | -400 |
| eval-10 | 1500 | 1400 | -100 |
| eval-11 | 1800 | 1400 | -400 |
| eval-12 | 2000 | 2000 | +0 |
| eval-13 | 1100 | 1500 | +400 |
| eval-14 | 1600 | 1800 | +200 |
| eval-15 | 1700 | 2200 | +500 |
| eval-16 | 2000 | 1700 | -300 |
| eval-17 | 2200 | 1600 | -600 |
| eval-18 | 1300 | 1300 | +0 |
| eval-19 | 2500 | 2300 | -200 |
| eval-20 | 1300 | 1600 | +300 |
| eval-21 | 1700 | 1700 | +0 |
| eval-22 | 1400 | 2000 | +600 |
| eval-23 | 2200 | 2400 | +200 |
| eval-24 | 1100 | 1200 | +100 |

### Round 7 confirms the round 6 diagnosis, and is the best round recorded

| round | configuration | MAE | bias | ±200 | worst band | spread |
|---|---|---|---|---|---|---|
| 4 | frozen (no era correction) | 279 | −29 | 58% | 400 | 767 |
| 6 | era correction + recency preference + de-compression | 321 | −21 | 50% | 467 | 767 |
| 7 | **era correction alone (shipped)** | **254** | **−46** | **54%** | **333** | **633** |

Round 7 is the lowest MAE of any round (previous best 275, round 5), the lowest worst-band
bias (previous best 400, round 4), and the narrowest band spread (previous best 733, round
5). Within ±200 is 54% against round 4's 58%, a difference of one problem in 24.

**The mechanism is confirmed by the anchor citations.** Each round makes 72 anchor citations
(24 slots × 3). The table is 46% anchors from 2018-2020 and 18% from 2025-2026:

| round | recency instruction | citations from 2018-2020 | citations from 2025-2026 |
|---|---|---|---|
| 4 | absent | 33 | 10 |
| 6 | **present** | **3** | **38** |
| 7 | removed | 16 | 18 |

Round 6 used a 2018-2020 anchor 3 times out of 72 — a twelvefold under-use of nearly half
the table. One sentence of preference emptied the anchor pool, and MAE rose 42 points. That
is the entire round 6 regression, and removing the sentence recovered it and then some.

**What this says about the era correction.** Scored on printed labels — the same scoring
every round from 1 to 6 used — the era discount arithmetic is worth 279 → 254. It is now
supported by a blind round rather than by retrodiction. Scored against era-corrected labels
it gives MAE 256, bias +44, within ±300 79%; both scorings agree it helps, which the
retrodiction study could not establish.

**Targets after round 7:** MAE ≤ 200 missed (254). ≥65% within ±200 missed (54%).
|bias| ≤ 75 met (−46). Worst-band |bias| ≤ 200 missed (333). Two of four.

## Moved out of SKILL.md (2026-09-19)

`SKILL.md`'s `Calibration status` section was compressed to the figures that change how the
number is reported — roughly 40% of the runtime prompt was build-time narrative the
estimating agent never acts on. The reasoning it carried is kept here.

### Measurement conditions

The blind agents derived each intended solution from the statement alone. At runtime the
skill reads an implementation the invocation matrix validated instead, so every figure in this file was
measured under harder conditions than the skill normally works in — likely pessimistic, but
by an unmeasured amount.

### The ceiling on untagged problems

A problem whose prerequisites match no row in `tag-floors.md` floors at `1100`, and Pass C's
window `[floor, floor+600]` then caps the reachable estimate at about `2200`. That is a limit
of the floor table, not a judgement: 37% of the anchors are themselves untagged while
spanning roughly 1100 to 2600.

The ceiling binds inside the measurement. The highest estimate any floor-`1100` problem
received was exactly `2200`, and two floor-`1100` problems had true ratings above it — `2400`
and `2300`, both estimated `1800`. It is one cause of high-end under-rating but not the only
one: of the two largest under-estimates in that run, one floored at `1100` (true `2400`,
estimated `1800`) and the other at `1200` (true `2200`, estimated `1400`).

Pass B now instructs the agent to report a floor-`1100` result as a lower bound. That is
wording, not a fix — the fix is to stop anchoring the search window on the floor, which needs
a measured round.

### Selection honesty

The shipped configuration was chosen out of seven rounds measured against the same 24
problems. Choosing against a fixed eval set is itself a form of fitting: after seven rounds
those problems are not held out in any strict sense, so every figure here is optimistic by an
unmeasured amount, and the honest next step is a fresh eval set rather than an eighth round
against this one. One earlier round measured 275 and was rejected anyway, because it produced
a prerequisite floor above a problem's true rating — which disqualifies a construct whose
only job is to be a lower bound, whatever its MAE.

Round 7's 254 leads round 4's 279 by 25 points, inside the ±40 standard error, so the era
correction's headline gain is suggestive rather than established. What is established is the
negative result: round 6's 321 against round 4's 279, with a mechanism confirmed in the
anchor citations.

### The two standing lessons

1. **A preference that narrows the anchor pool costs more than any arithmetic correction
   gains.** Match quality is what Pass C runs on.
2. **No change to these passes ships on retrodiction evidence again.** Retrodiction holds the
   estimator's behaviour fixed and can only score arithmetic, so it is blind to exactly the
   changes that matter most: it predicted MAE 277 and worst-band 283 where blind round 6
   delivered 321 and 467.

## Configuration drift since round 7 (2026-09-19)

Round 7 is the newest measurement, but the shipped skill is no longer the configuration that
produced it. None of the changes below are measured.

| change | why | risk |
|---|---|---|
| recency preference deleted from `references/anchors.md` | round 7 deleted it from `SKILL.md` and left it in the reference, which Pass C also reads | should help; the direction is the one round 6 established |
| Pass B reports a floor-`1100` result as a lower bound | the ceiling was documented in a section the agent reads after answering | wording, no arithmetic |
| Pass C copies anchor `id`/`rating`/`year` verbatim; Pass E checks each id against the table | rounds 2 and 3 each cited `1063D`, which is not a Codeforces problem, and nothing caught it | wording, no arithmetic |
| `Calibration status` compressed, this narrative moved here | 40% of the runtime prompt was build-time history | changes what the estimating agent reads; unmeasured |

**Round 7 was mislabelled.** It is recorded above as "recency preference removed", but the
sentence was only removed from `SKILL.md`; `references/anchors.md` kept its own copy until
today. Each round makes 72 anchor citations:

| round | recency preference | cites 2018-2020 | cites 2025-2026 | mean era discount of cited anchors |
|---|---|---|---|---|
| 4 | absent | 33 | 10 | 107 |
| 6 | in `SKILL.md` | 3 | 38 | 33 |
| 7 | in `anchors.md` only | 16 | 18 | 70 |

Round 7 used the 2018-2020 era half as often as round 4 and drew anchors averaging 37 points
less era discount. The preference was still steering selection, so **MAE 254 is the figure
for a half-removed preference, not for its absence.** Reproduce the citation counts with:

```
python calibration/fetch-corpus.py check   # now also validates every cited id
```

Round 8 measures the current configuration, and it should run against the fresh held-out set
rather than these 24 problems.

## Round 8 — pre-registered decision rules

Written 2026-09-20, before any round-8 number exists.

Round 7's figures do not describe the shipped skill: `anchors.md` still carried the recency
preference, and Passes B, C, C.1, D and E have since gained wording (see **Configuration
drift since round 7**). Round 8 re-measures, and tests one change.

**Arms.** Both on the same 24 slots, the round-1 eval prompt verbatim, 5 subagents of 4-5
slots each.

| arm | configuration |
|---|---|
| 8A | the shipped skill as of this entry — the drift list applied, nothing else |
| 8B | 8A + anchor selection by match quality over the whole table, the floor demoted to the Pass E clamp it already is |

8B is the fix for the ceiling: a `1100` floor confines Pass C to `[1100, 1700]` and caps the
reachable estimate near `2200`, and the two largest under-estimates on record are floor-`1100`
and floor-`1200` problems.

**8A, not round 7, is 8B's control.** The two arms share a model; any comparison back to
rounds 1-7 additionally carries whatever model drift has occurred since those rounds ran, and
cannot be attributed to a rubric change.

**Primary endpoint: worst-band |bias|.** 8B targets high-end under-rating, which is a per-band
quantity. MAE is the guard, not the target — the round-4-to-6 history is what happens when a
change is judged on an aggregate that cannot fail.

**Ship rule for 8B**, `a` = arm 8A, `b` = arm 8B:

| condition | outcome |
|---|---|
| `b.worst_band ≤ a.worst_band − 100` and `b.MAE ≤ a.MAE + 40` | 8B ships |
| `b.MAE ≤ a.MAE − 40` | 8B ships whatever worst-band does |
| any estimate is clamped by the floor to above its true rating | 8B is disqualified whatever its MAE — the floor's only job is to be a lower bound |
| otherwise | 8B is reverted and recorded as a negative result; 8A ships |

**Whatever ships**, `Calibration status` states that arm's measured figures and repeats that
these 24 problems have now been selected against eight times and are not held out in any
strict sense. The fresh 48-problem set is still unbuilt — `fresh-build` needs a Codeforces
session past the Cloudflare challenge (`CF_UA`, `CF_COOKIE`) — and remains the only route to
a figure that is not fitted.

**Not tested in this round:** de-compression on its own. Round 6 bundled it with the recency
preference and it was deleted with it, so it has never been measured alone. It is the
standing candidate for round 9, against whichever arm ships here.

## predictions-round8a

n = 24   MAE = 279   bias = -21   within200 = 46%   within300 = 67%

| band | n | MAE | bias |
|---|---|---|---|
| 1100-1299 | 3 | 133 | +133 |
| 1300-1499 | 3 | 500 | +500 |
| 1500-1699 | 3 | 200 | +0 |
| 1700-1899 | 3 | 333 | +67 |
| 1900-2099 | 3 | 100 | -100 |
| 2100-2299 | 3 | 333 | -200 |
| 2300-2499 | 3 | 300 | -233 |
| 2500-2699 | 3 | 333 | -333 |

| slot | true | predicted | error |
|---|---|---|---|
| eval-01 | 2400 | 2000 | -400 |
| eval-02 | 2400 | 2500 | +100 |
| eval-03 | 2100 | 2200 | +100 |
| eval-04 | 2500 | 2100 | -400 |
| eval-05 | 2300 | 1900 | -400 |
| eval-06 | 1600 | 1400 | -200 |
| eval-07 | 1100 | 1200 | +100 |
| eval-08 | 1900 | 1900 | +0 |
| eval-09 | 2500 | 2200 | -300 |
| eval-10 | 1500 | 1400 | -100 |
| eval-11 | 1800 | 1400 | -400 |
| eval-12 | 2000 | 1900 | -100 |
| eval-13 | 1100 | 1400 | +300 |
| eval-14 | 1600 | 1900 | +300 |
| eval-15 | 1700 | 2100 | +400 |
| eval-16 | 2000 | 1800 | -200 |
| eval-17 | 2200 | 1400 | -800 |
| eval-18 | 1300 | 1800 | +500 |
| eval-19 | 2500 | 2200 | -300 |
| eval-20 | 1300 | 1600 | +300 |
| eval-21 | 1700 | 1900 | +200 |
| eval-22 | 1400 | 2100 | +700 |
| eval-23 | 2200 | 2300 | +100 |
| eval-24 | 1100 | 1100 | +0 |

## predictions-round8b

n = 24   MAE = 246   bias = -29   within200 = 67%   within300 = 67%

| band | n | MAE | bias |
|---|---|---|---|
| 1100-1299 | 3 | 100 | +100 |
| 1300-1499 | 3 | 433 | +433 |
| 1500-1699 | 3 | 200 | -67 |
| 1700-1899 | 3 | 300 | +33 |
| 1900-2099 | 3 | 67 | -67 |
| 2100-2299 | 3 | 300 | -100 |
| 2300-2499 | 3 | 267 | -267 |
| 2500-2699 | 3 | 300 | -300 |

| slot | true | predicted | error |
|---|---|---|---|
| eval-01 | 2400 | 2000 | -400 |
| eval-02 | 2400 | 2400 | +0 |
| eval-03 | 2100 | 2200 | +100 |
| eval-04 | 2500 | 2300 | -200 |
| eval-05 | 2300 | 1900 | -400 |
| eval-06 | 1600 | 1400 | -200 |
| eval-07 | 1100 | 1200 | +100 |
| eval-08 | 1900 | 1800 | -100 |
| eval-09 | 2500 | 2000 | -500 |
| eval-10 | 1500 | 1300 | -200 |
| eval-11 | 1800 | 1400 | -400 |
| eval-12 | 2000 | 2000 | +0 |
| eval-13 | 1100 | 1300 | +200 |
| eval-14 | 1600 | 1800 | +200 |
| eval-15 | 1700 | 2100 | +400 |
| eval-16 | 2000 | 1900 | -100 |
| eval-17 | 2200 | 1600 | -600 |
| eval-18 | 1300 | 1500 | +200 |
| eval-19 | 2500 | 2300 | -200 |
| eval-20 | 1300 | 1800 | +500 |
| eval-21 | 1700 | 1800 | +100 |
| eval-22 | 1400 | 2000 | +600 |
| eval-23 | 2200 | 2400 | +200 |
| eval-24 | 1100 | 1100 | +0 |

### Round 8 ruling — 8B reverted under the pre-registered rule

| | 8A (shipped) | 8B | 7 (earlier model) |
|---|---|---|---|
| MAE | 279 | **246** | 254 |
| bias | −21 | −29 | −46 |
| within ±200 | 46% | **67%** | 54% |
| within ±300 | 67% | 67% | 62% |
| worst band | 500 | **433** | 333 |
| spread | 833 | **733** | 633 |
| slope | 0.544 | **0.618** | 0.574 |

**8B improved every figure and still does not ship.** The rule fixed before either number
existed required `worst_band ≤ 400` with `MAE ≤ 319`, or `MAE ≤ 239`. 8B returned worst-band
`433` and MAE `246` — short by 33 and by 7. Every movement between the arms is inside the ±40
standard error of a 24-problem set, so none of them is established, and the line does not move
after the number is known. That is the whole purpose of writing it down first.

8B is nonetheless **the leading candidate for round 9**, and the mechanism was observed
working rather than assumed: floor-`1100` problems compared against anchors at 1800, 2100 and
2500, all unreachable inside `[floor, floor+600]`, and eval-19 (true `2500`) moved `2200 →
2300` once the ceiling was gone. Re-run it against the fresh held-out set, where ±28 standard
error would let a difference this size resolve.

**Round 7 is not a control for either arm.** Rounds 1-7 ran on an earlier model; 8A and 8B
share one. The column above is for orientation only — no difference across that boundary is
attributable to a rubric change.

**A `tag-floors.md` defect, in both arms.** `eval-14` (true `1600`) was assigned a `1700`
floor. No estimate was clamped by it, so neither arm is disqualified under the pre-registered
rule, but a floor above a true rating is the property that disqualified an earlier round
outright, and it is a fact about the floor table rather than about either arm. The row that
produced it — `segment tree / BIT, standard DP over one dimension, shortest paths` at `1700` —
is the one to examine.

**What round 8 establishes about the changes shipped on 2026-09-19.** They are now measured
rather than asserted: 8A is exactly that configuration. It cannot be compared to round 7
across the model boundary, so what the drift list bought is still unquantified — but the
skill's stated figures now describe the skill that is shipped, which was the defect being
fixed.

**Standing candidates for round 9**, against the fresh set, one arm each:
1. 8B — whole-table anchor selection (narrowly missed here).
2. De-compression alone. Never measured in isolation; round 6 bundled it with the recency
   preference and it was deleted alongside it. The slope of `0.54` is what it targets.
3. A no-rubric baseline on the current model. The recorded `658` is from an earlier model, so
   the skill currently has no like-for-like control and cannot state what the rubric is worth.

## Round 9 — pre-registered decision rules

Written 2026-09-22, before any round-9 number exists, and before any arm was dispatched.

**The eval set is new and genuinely held out.** `eval-set-2.md`: 48 problems, 6 per band
across the same 8 bands, verified disjoint from the anchor table, from `eval-set.md`, and
from `corpus.md` entirely. Standard error is roughly ±28, against ±40 on the old 24. This is
the first un-fitted measurement this skill has ever had, and it is spendable exactly once.

**Arms.** Same 48 slots, the round-1 eval prompt verbatim against `blind2/`, 8 subagents of
6 slots each.

| arm | configuration |
|---|---|
| 9A | the shipped skill, unchanged — control |
| 9B | 9A + anchor selection by match quality over the whole table (round 8B, which missed its threshold by 33 points of worst-band bias) |
| 9C | 9A + de-compression alone: after Pass D, `final = 1800 + (estimate − 1800) × 1.20`, Pass E's floor gate applied after. Never measured in isolation — round 6 bundled it with the recency preference and it was deleted alongside it |
| 9D | no rubric at all, current model — the baseline control the skill has never had on this model |

**Primary endpoint: worst-band \|bias\|.** Both 9B and 9C target the compression, which is a
per-band quantity. At 6 problems per band these estimates are twice as stable as round 8's 3.
MAE is the guard, not the target.

**Ship rules**, `a` = 9A, evaluated independently for 9B and 9C:

| condition | outcome |
|---|---|
| `worst_band ≤ a.worst_band − 100` and `MAE ≤ a.MAE + 28` | that arm ships |
| `MAE ≤ a.MAE − 28` | that arm ships whatever worst-band does |
| any estimate clamped by the floor to above its true rating | that arm is disqualified whatever its MAE |
| otherwise | that arm is reverted and recorded as a negative result |

**If both qualify**, ship the lower worst-band; if they are within 30 of each other, ship the
lower MAE. **They are not combined.** Bundling two unmeasured changes is what produced round
6, and a combination is its own arm in a later round.

**9D is not ship-eligible.** It exists so the skill can finally state what the rubric is worth
on the model that runs it. The recorded `658` baseline is from an earlier model and the
`658 → 279` comparison is not attributable to the rubric.

**Whatever ships**, `Calibration status` is restated on the fresh-set figures, which become the
headline: they are the only measurement not taken on problems the rubric was tuned against.
The old 24-problem figures stay in this file as history and are no longer quoted as the
skill's accuracy.

**Selection cost, stated in advance.** Choosing a winner among four arms on one eval set is
itself mild selection, so the shipped arm's figures are optimistic by a small but real amount.
With four arms and a pre-registered rule this is far weaker than the eight-round selection the
old set carries, but it is not zero, and `Calibration status` says so.

## predictions-round9a

n = 48   MAE = 210   bias = +19   within200 = 71%   within300 = 85%

| band | n | MAE | bias |
|---|---|---|---|
| 1100-1299 | 6 | 217 | +150 |
| 1300-1499 | 6 | 200 | +200 |
| 1500-1699 | 6 | 200 | -200 |
| 1700-1899 | 6 | 133 | +0 |
| 1900-2099 | 6 | 200 | +167 |
| 2100-2299 | 6 | 150 | -50 |
| 2300-2499 | 6 | 267 | -233 |
| 2500-2699 | 6 | 317 | +117 |

| slot | true | predicted | error |
|---|---|---|---|
| fresh-01 | 1200 | 1200 | +0 |
| fresh-02 | 1200 | 1400 | +200 |
| fresh-03 | 1200 | 1100 | -100 |
| fresh-04 | 1100 | 1300 | +200 |
| fresh-05 | 1100 | 1800 | +700 |
| fresh-06 | 1200 | 1100 | -100 |
| fresh-07 | 1400 | 1400 | +0 |
| fresh-08 | 1400 | 1500 | +100 |
| fresh-09 | 1400 | 1500 | +100 |
| fresh-10 | 1400 | 1600 | +200 |
| fresh-11 | 1400 | 2200 | +800 |
| fresh-12 | 1400 | 1400 | +0 |
| fresh-13 | 1600 | 1300 | -300 |
| fresh-14 | 1500 | 1300 | -200 |
| fresh-15 | 1600 | 1200 | -400 |
| fresh-16 | 1600 | 1600 | +0 |
| fresh-17 | 1600 | 1500 | -100 |
| fresh-18 | 1600 | 1400 | -200 |
| fresh-19 | 1700 | 1600 | -100 |
| fresh-20 | 1700 | 1700 | +0 |
| fresh-21 | 1700 | 1500 | -200 |
| fresh-22 | 1800 | 2000 | +200 |
| fresh-23 | 1700 | 1900 | +200 |
| fresh-24 | 1700 | 1600 | -100 |
| fresh-25 | 1900 | 2000 | +100 |
| fresh-26 | 1900 | 1800 | -100 |
| fresh-27 | 1900 | 2200 | +300 |
| fresh-28 | 1900 | 2100 | +200 |
| fresh-29 | 1900 | 2100 | +200 |
| fresh-30 | 1900 | 2200 | +300 |
| fresh-31 | 2200 | 2000 | -200 |
| fresh-32 | 2100 | 2100 | +0 |
| fresh-33 | 2100 | 1800 | -300 |
| fresh-34 | 2100 | 2000 | -100 |
| fresh-35 | 2100 | 2100 | +0 |
| fresh-36 | 2100 | 2400 | +300 |
| fresh-37 | 2400 | 2300 | -100 |
| fresh-38 | 2300 | 1700 | -600 |
| fresh-39 | 2300 | 2400 | +100 |
| fresh-40 | 2400 | 2100 | -300 |
| fresh-41 | 2400 | 2200 | -200 |
| fresh-42 | 2400 | 2100 | -300 |
| fresh-43 | 2600 | 2800 | +200 |
| fresh-44 | 2500 | 2400 | -100 |
| fresh-45 | 2500 | 2000 | -500 |
| fresh-46 | 2500 | 2500 | +0 |
| fresh-47 | 2500 | 3000 | +500 |
| fresh-48 | 2500 | 3100 | +600 |

## predictions-round9b

n = 48   MAE = 217   bias = +100   within200 = 67%   within300 = 81%

| band | n | MAE | bias |
|---|---|---|---|
| 1100-1299 | 6 | 233 | +200 |
| 1300-1499 | 6 | 300 | +300 |
| 1500-1699 | 6 | 167 | -167 |
| 1700-1899 | 6 | 117 | +17 |
| 1900-2099 | 6 | 233 | +233 |
| 2100-2299 | 6 | 183 | +50 |
| 2300-2499 | 6 | 250 | +150 |
| 2500-2699 | 6 | 250 | +17 |

| slot | true | predicted | error |
|---|---|---|---|
| fresh-01 | 1200 | 1200 | +0 |
| fresh-02 | 1200 | 1400 | +200 |
| fresh-03 | 1200 | 1200 | +0 |
| fresh-04 | 1100 | 1300 | +200 |
| fresh-05 | 1100 | 2000 | +900 |
| fresh-06 | 1200 | 1100 | -100 |
| fresh-07 | 1400 | 1400 | +0 |
| fresh-08 | 1400 | 1500 | +100 |
| fresh-09 | 1400 | 1600 | +200 |
| fresh-10 | 1400 | 1700 | +300 |
| fresh-11 | 1400 | 2300 | +900 |
| fresh-12 | 1400 | 1700 | +300 |
| fresh-13 | 1600 | 1500 | -100 |
| fresh-14 | 1500 | 1300 | -200 |
| fresh-15 | 1600 | 1200 | -400 |
| fresh-16 | 1600 | 1600 | +0 |
| fresh-17 | 1600 | 1500 | -100 |
| fresh-18 | 1600 | 1400 | -200 |
| fresh-19 | 1700 | 1600 | -100 |
| fresh-20 | 1700 | 1600 | -100 |
| fresh-21 | 1700 | 1600 | -100 |
| fresh-22 | 1800 | 2100 | +300 |
| fresh-23 | 1700 | 1800 | +100 |
| fresh-24 | 1700 | 1700 | +0 |
| fresh-25 | 1900 | 2100 | +200 |
| fresh-26 | 1900 | 1900 | +0 |
| fresh-27 | 1900 | 2100 | +200 |
| fresh-28 | 1900 | 2200 | +300 |
| fresh-29 | 1900 | 2300 | +400 |
| fresh-30 | 1900 | 2200 | +300 |
| fresh-31 | 2200 | 2000 | -200 |
| fresh-32 | 2100 | 2100 | +0 |
| fresh-33 | 2100 | 1900 | -200 |
| fresh-34 | 2100 | 2100 | +0 |
| fresh-35 | 2100 | 2200 | +100 |
| fresh-36 | 2100 | 2700 | +600 |
| fresh-37 | 2400 | 2400 | +0 |
| fresh-38 | 2300 | 2000 | -300 |
| fresh-39 | 2300 | 2500 | +200 |
| fresh-40 | 2400 | 2900 | +500 |
| fresh-41 | 2400 | 2900 | +500 |
| fresh-42 | 2400 | 2400 | +0 |
| fresh-43 | 2600 | 2700 | +100 |
| fresh-44 | 2500 | 2300 | -200 |
| fresh-45 | 2500 | 2100 | -400 |
| fresh-46 | 2500 | 2400 | -100 |
| fresh-47 | 2500 | 2800 | +300 |
| fresh-48 | 2500 | 2900 | +400 |

## predictions-round9c

n = 48   MAE = 250   bias = +50   within200 = 60%   within300 = 79%

| band | n | MAE | bias |
|---|---|---|---|
| 1100-1299 | 6 | 283 | +183 |
| 1300-1499 | 6 | 350 | +350 |
| 1500-1699 | 6 | 233 | -233 |
| 1700-1899 | 6 | 83 | -17 |
| 1900-2099 | 6 | 283 | +150 |
| 2100-2299 | 6 | 217 | +17 |
| 2300-2499 | 6 | 267 | -133 |
| 2500-2699 | 6 | 283 | +83 |

| slot | true | predicted | error |
|---|---|---|---|
| fresh-01 | 1200 | 1100 | -100 |
| fresh-02 | 1200 | 1500 | +300 |
| fresh-03 | 1200 | 1100 | -100 |
| fresh-04 | 1100 | 1100 | +0 |
| fresh-05 | 1100 | 2200 | +1100 |
| fresh-06 | 1200 | 1100 | -100 |
| fresh-07 | 1400 | 1400 | +0 |
| fresh-08 | 1400 | 1600 | +200 |
| fresh-09 | 1400 | 1400 | +0 |
| fresh-10 | 1400 | 1600 | +200 |
| fresh-11 | 1400 | 3000 | +1600 |
| fresh-12 | 1400 | 1500 | +100 |
| fresh-13 | 1600 | 1400 | -200 |
| fresh-14 | 1500 | 1200 | -300 |
| fresh-15 | 1600 | 1300 | -300 |
| fresh-16 | 1600 | 1600 | +0 |
| fresh-17 | 1600 | 1300 | -300 |
| fresh-18 | 1600 | 1300 | -300 |
| fresh-19 | 1700 | 1700 | +0 |
| fresh-20 | 1700 | 1600 | -100 |
| fresh-21 | 1700 | 1500 | -200 |
| fresh-22 | 1800 | 1800 | +0 |
| fresh-23 | 1700 | 1900 | +200 |
| fresh-24 | 1700 | 1700 | +0 |
| fresh-25 | 1900 | 1600 | -300 |
| fresh-26 | 1900 | 1800 | -100 |
| fresh-27 | 1900 | 2100 | +200 |
| fresh-28 | 1900 | 2200 | +300 |
| fresh-29 | 1900 | 2300 | +400 |
| fresh-30 | 1900 | 2300 | +400 |
| fresh-31 | 2200 | 2200 | +0 |
| fresh-32 | 2100 | 2000 | -100 |
| fresh-33 | 2100 | 1700 | -400 |
| fresh-34 | 2100 | 2200 | +100 |
| fresh-35 | 2100 | 2000 | -100 |
| fresh-36 | 2100 | 2700 | +600 |
| fresh-37 | 2400 | 2200 | -200 |
| fresh-38 | 2300 | 1900 | -400 |
| fresh-39 | 2300 | 2700 | +400 |
| fresh-40 | 2400 | 2200 | -200 |
| fresh-41 | 2400 | 2200 | -200 |
| fresh-42 | 2400 | 2200 | -200 |
| fresh-43 | 2600 | 2600 | +0 |
| fresh-44 | 2500 | 2200 | -300 |
| fresh-45 | 2500 | 2200 | -300 |
| fresh-46 | 2500 | 2500 | +0 |
| fresh-47 | 2500 | 3000 | +500 |
| fresh-48 | 2500 | 3100 | +600 |

## predictions-round9d

n = 48   MAE = 277   bias = +140   within200 = 62%   within300 = 75%

| band | n | MAE | bias |
|---|---|---|---|
| 1100-1299 | 6 | 317 | +17 |
| 1300-1499 | 6 | 467 | +467 |
| 1500-1699 | 6 | 150 | -150 |
| 1700-1899 | 6 | 167 | +100 |
| 1900-2099 | 6 | 200 | +167 |
| 2100-2299 | 6 | 167 | +0 |
| 2300-2499 | 6 | 383 | +317 |
| 2500-2699 | 6 | 367 | +200 |

| slot | true | predicted | error |
|---|---|---|---|
| fresh-01 | 1200 | 800 | -400 |
| fresh-02 | 1200 | 1400 | +200 |
| fresh-03 | 1200 | 900 | -300 |
| fresh-04 | 1100 | 1100 | +0 |
| fresh-05 | 1100 | 1900 | +800 |
| fresh-06 | 1200 | 1000 | -200 |
| fresh-07 | 1400 | 1500 | +100 |
| fresh-08 | 1400 | 1500 | +100 |
| fresh-09 | 1400 | 1600 | +200 |
| fresh-10 | 1400 | 1600 | +200 |
| fresh-11 | 1400 | 3300 | +1900 |
| fresh-12 | 1400 | 1700 | +300 |
| fresh-13 | 1600 | 1600 | +0 |
| fresh-14 | 1500 | 1200 | -300 |
| fresh-15 | 1600 | 1500 | -100 |
| fresh-16 | 1600 | 1400 | -200 |
| fresh-17 | 1600 | 1600 | +0 |
| fresh-18 | 1600 | 1300 | -300 |
| fresh-19 | 1700 | 1600 | -100 |
| fresh-20 | 1700 | 1700 | +0 |
| fresh-21 | 1700 | 1700 | +0 |
| fresh-22 | 1800 | 2300 | +500 |
| fresh-23 | 1700 | 2000 | +300 |
| fresh-24 | 1700 | 1600 | -100 |
| fresh-25 | 1900 | 1800 | -100 |
| fresh-26 | 1900 | 1900 | +0 |
| fresh-27 | 1900 | 2000 | +100 |
| fresh-28 | 1900 | 1900 | +0 |
| fresh-29 | 1900 | 2300 | +400 |
| fresh-30 | 1900 | 2500 | +600 |
| fresh-31 | 2200 | 2100 | -100 |
| fresh-32 | 2100 | 2300 | +200 |
| fresh-33 | 2100 | 1900 | -200 |
| fresh-34 | 2100 | 2200 | +100 |
| fresh-35 | 2100 | 1900 | -200 |
| fresh-36 | 2100 | 2300 | +200 |
| fresh-37 | 2400 | 2200 | -200 |
| fresh-38 | 2300 | 2400 | +100 |
| fresh-39 | 2300 | 2500 | +200 |
| fresh-40 | 2400 | 2900 | +500 |
| fresh-41 | 2400 | 3400 | +1000 |
| fresh-42 | 2400 | 2700 | +300 |
| fresh-43 | 2600 | 3000 | +400 |
| fresh-44 | 2500 | 2700 | +200 |
| fresh-45 | 2500 | 2000 | -500 |
| fresh-46 | 2500 | 2600 | +100 |
| fresh-47 | 2500 | 2900 | +400 |
| fresh-48 | 2500 | 3100 | +600 |


### Round 9 ruling — both candidates reverted, 9A ships unchanged

| arm | MAE | bias | ±200 | worst band | slope |
|---|---|---|---|---|---|
| **9A control (ships)** | **210** | **+19** | **71%** | **233** | 0.875 |
| 9B whole-table selection | 217 | +100 | 67% | 300 | 0.926 |
| 9C de-compression alone | 250 | +50 | 60% | 350 | 0.849 |
| 9D no rubric | 277 | +140 | 62% | 467 | 1.077 |

Ship rule required `worst_band ≤ 133` with `MAE ≤ 238`, or `MAE ≤ 182`. Neither arm met
either condition. Neither was disqualified — no estimate in any arm was clamped by the floor
to above its true rating — they simply lost. All 144 anchor citations across 9A/9B/9C were
verified present in `anchors.md`.

**The old eval set was manufacturing results.** On the 24 problems that eight rounds had been
tuned against, whole-table selection beat its control on *every* metric — MAE 246 vs 279,
±200 67% vs 46%, worst-band 433 vs 500 — and missed shipping by 33 points. On 48 problems it
had never seen it is worse on every metric that matters, and it pushes bias from +19 to +100
by letting placements drift up toward anchors that do not constrain them. The ceiling it
removes is real, and removing it costs more than it buys.

**The documented compression was largely an artifact of that set.** Slope of estimate on
truth is `0.875` on the fresh 48 against `0.544` on the old 24. The "scale compressed from
both ends, easy over-rated and hard under-rated" story — which motivated round 6, the
fourth accuracy target, and a long passage of `Calibration status` — does not reproduce on
held-out problems. 9C confirms it directly: an explicit ×1.20 de-compression, the exact step
round 6 shipped and deleted, measured **worse** on every figure (MAE 250 vs 210, ±200 60% vs
71%, worst-band 350 vs 233) and moved the slope the wrong way, from 0.875 to 0.849. The
question opened in round 6 is now closed by a blind arm rather than by retrodiction: **do not
de-compress.**

**The rubric's value, measured like-for-like at last.** 9D is the unaided control on the same
model: MAE 277, bias +140. The rubric is worth about **67 MAE points**, and most of its
contribution is calibration rather than raw accuracy — unaided guessing over-rates
systematically (+467 in the 1300-1499 band, +317 at 2300-2499) while the rubric sits at +19
overall. Note 9D's slope of 1.077: unaided estimates are *not* compressed at all, which is
further evidence the compression was a property of the old sample, not of the method.

The previously advertised `658 → 254` was never a measurement of the rubric — the 658 came
from an earlier model. The honest figure is `277 → 210`.

**`tag-floors.md` is now the binding limitation.** 19 of 48 problems floored at the
uninformative `1100`, and agents named the gaps unprompted: no row for tries, ad-hoc
constructive work, or counting. Two floors again landed above a true rating (`fresh-04`,
`fresh-05`, both `1200` against a true `1100`), making three such cases across rounds 8-9 in
the one construct whose only job is to be a lower bound. That is the candidate for round 10,
and it should be tested the same way: one arm, one change, threshold written first.

**What round 9 cost the fresh set.** Four arms were compared on it, so the shipped figures
carry a small multiple-comparison optimism. The shipped arm is the *control*, not a winner
selected for its score, which makes that cost smaller here than the pre-registration allowed
for — but the set is no longer pristine, and a round 10 should draw a third sample.

## Configuration drift since round 9A (2026-09-22)

Round 9A measured the skill as it stood on the morning of 2026-09-22. The shipped `SKILL.md`
has since gained wording. None of the changes below is measured; round 10's control arm
measures them together. The changes shipped between rounds 7 and 9A are listed under
**Configuration drift since round 7** and were measured by 8A and 9A.

| change | why | risk |
|---|---|---|
| Pass C.1: the "level shift, not a de-compression" paragraph; its per-band discount range corrected from `−75` to `−117` (false) to the measured `−84` to `−127` | round 9C's negative result, recorded where the next reader would otherwise re-propose the step; the range was recomputed from `anchors.md` on 2026-09-22 | wording, no arithmetic |
| Pass B: a `1100` floor caps the reachable estimate near `2200` and is reported as a lower bound | moved from `Calibration status`, which the agent reads after answering, into the pass that fires | wording, no arithmetic |
| `## The procedure at a glance`: a seven-row map at the top; row C says anchors are selected on printed ratings and compared on their Pass C.1 today ratings, so the map cannot be read as C.1 never reaching the estimate | 2,900 words with no overview; the map gives the passes an order and one binding rule each | changes what the agent reads first; unmeasured |
| "What the number means": the placement range is about `1100` to `2900`; `Confidence` names a floor ≥ `2100` or a placement ≥ `2500` in the template's own words; "It is a comparability figure" became "The number is" | the anchor table spans `1100`-`2600` and the top three floor rows have no anchor; the description advertises `800`-`3500` | `Confidence` text only |
| Gate: proof is `python3 -m tools.package_status "$PROBLEM"` printing `[x] matrix` with `holes 0, mismatches 0` while the `@tag main` solution declares `OK` for every group in its `@expect`, or the user's word that `validating-solutions` ran the matrix clean in this session; a stale `invocation.json` or any hole is rejected | the status tool is the plugin's own machine-readable evidence, the one the other setter skills already gate on; an `invocation.json` that exists but is stale, or reports holes, says nothing about the code now being rated | affects whether an estimate is produced, not its value |
| Pass C: the round-6 story cut to three sentences; `33 points` corrected to `42` | the figure contradicted `anchors.md` and this file | wording |
| `Calibration status` cut to the table and one paragraph; figures removed from Pass E, the template and `README.md`; the section says its figures predate the wording listed here and points at this table | five copies of the round figures, one already stale; the old "measures exactly the configuration shipped here" claim was no longer true | changes what the agent reads; unmeasured |
| Template: the coverage sentence and the `Source:` line carry no figures | same | output prose only |
| `anchors.md`: five rows (`2109C1`, `1129A2`, `2196C1`, `1063C`, `1783F`) had a seventh cell holding the unsure marker | the table misaligned in any renderer | none; the parser reads four cells |

## Round 10 — pre-registered decision rules

Written 2026-09-22, before any round-10 number exists, and before any arm was dispatched.

**Prerequisite: a third held-out sample.** The fresh 48 have been compared against by four
arms and are no longer pristine. Round 10 runs on `eval-set-3.md`: 48 problems, 6 per band
across the same 8 bands, disjoint from `corpus.md`, `eval-set.md` and `eval-set-2.md`.
`fetch-corpus.py fresh-build` writes `eval-set-2.md` by name and must be generalised before
this round can run; that is build tooling and touches nothing the skill reads.

**Arms.** Same 48 slots, the round-1 eval prompt verbatim, 8 subagents of 6 slots each.

| arm | configuration |
|---|---|
| 10A | the shipped skill as of this entry — the drift list above applied, nothing else — control |
| 10B | 10A with the `two pointers, prefix sums, sorting + greedy` row removed from `tag-floors.md`, so those problems floor at `1100`. Two anchors carrying that tag, `1923B` and `2245B`, are rated `1100`, and round 9 floored two true-`1100` problems, `fresh-04` and `fresh-05`, at `1200`: the row is not a lower bound |
| 10C | 10A with Pass C.1 removed: anchors compared on their printed ratings. The era correction has never been measured alone on held-out problems; round 7's 25-point lead over round 4 was inside a ±40 standard error |
| 10D | 10A plus one structural rule in Pass C: at least one of the anchors compared must lie in the base window `[floor, floor+600]`, and the output names it. In 9A, 30 of 142 citations sat outside the base window, and the worst miss, `fresh-11` (true `1400`, estimated `2200`), took all three anchors from the top of the widened window |

**Primary endpoints.** Worst-band |bias| for 10B and 10D; MAE for 10C, since the correction
claims a level shift. MAE is the guard for every arm. Reported alongside, without a threshold
of their own: for 10B the count of floors above a true rating (a disqualifier in the rules
below) and the `1100-1299` band bias; for 10D the `1100-1299` and `1300-1499` band biases.

**Ship rules**, `a` = 10A, evaluated independently for 10B and 10D:

| condition | outcome |
|---|---|
| `worst_band ≤ a.worst_band − 100` and `MAE ≤ a.MAE + 28` | that arm ships |
| `MAE ≤ a.MAE − 28` | that arm ships whatever worst-band does |
| any estimate clamped by the floor to above its true rating | that arm is disqualified whatever its MAE |
| otherwise | that arm is reverted and recorded as a negative result |

**The rule for 10C is inverted**, because it removes a pass rather than adding one:

| condition | outcome |
|---|---|
| `MAE ≤ a.MAE − 28` | Pass C.1 is removed: the correction was costing accuracy |
| otherwise | Pass C.1 stays, and its measured gain, `a.MAE` against 10C's, is stated in `Calibration status` for the first time, bounded by the ±28 standard error |

**If both 10B and 10D qualify**, ship the lower worst-band; within 30, the lower MAE. **They
are not combined.** A combination is its own arm in a later round.

**Whatever ships**, `Calibration status` is restated on the round-10 figures, which remain the
only copy in the skill's runtime text, and this file records every arm.
