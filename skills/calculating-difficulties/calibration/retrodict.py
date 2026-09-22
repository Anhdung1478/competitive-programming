# -*- coding: utf-8 -*-
"""Retrodiction study for Pass C.1 (era correction) and Pass D.1 (de-compression).

Build-time only. Never read at skill runtime.

*** THIS STUDY'S CONCLUSION WAS WRONG. Kept as the record of how. ***

It predicted MAE 277 and worst-band bias 283 for "era + de-compression". Blind round 6
measured 321 and 467. Pass D.1 was deleted and the era correction was reworked; round 7
(era correction alone) measures MAE 254. See `metrics.md` for both rounds.

Why it failed: rounds 4 and 5 recorded, per eval slot, the predicted rating, the
prerequisite floor, and the ids of the anchors compared, which is enough to recompute a
different post-placement *arithmetic* — but only by holding the agent's anchor choice and
raw placement fixed. The change that actually drove round 6's regression was behavioural
(a recency preference that emptied 46% of the anchor table), and this script is
structurally blind to that. It also runs on the same 24 problems used for every round.

The standing rule, recorded in SKILL.md: no change to the passes ships on retrodiction
evidence alone. Run a blind round.

Usage:  python calibration/retrodict.py
"""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
BANDS = [(1100 + 200 * i, 1299 + 200 * i) for i in range(8)]

PIVOT = 1800          # midpoint of the anchor table's 1100-2600 range, chosen before measuring
EXPAND = 1.20         # Pass D.1 factor


def rows(relpath):
    path = os.path.join(SKILL, relpath)
    for line in io.open(path, encoding="utf-8"):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or cells[0] in ("id", "slot", "band", "") or set(cells[0]) <= set("- "):
            continue
        yield cells


def discount(year):
    """Pass C.1 era discount, by the anchor's contest year."""
    y = int(year)
    if y >= 2025:
        return 0
    if y >= 2023:
        return 50
    if y >= 2021:
        return 100
    if y >= 2019:
        return 150
    return 200


ANCHORS = {c[0]: (int(c[1]), int(c[2])) for c in rows("references/anchors.md") if len(c) >= 5}
CORPUS = {c[0]: c[3] for c in rows("calibration/corpus.md") if len(c) >= 6}
TRUTH, EVID = {}, {}
for _c in rows("calibration/eval-set.md"):
    if len(_c) >= 4 and _c[0].startswith("eval-"):
        TRUTH[_c[0]] = int(_c[2])
        EVID[_c[0]] = _c[1]


def load(rnd):
    out = {}
    for c in rows("calibration/predictions-%s.md" % rnd):
        if c[0].startswith("eval-"):
            out[c[0]] = (int(c[1]), int(c[2]), [a.strip() for a in c[3].split(",")])
    return out


def band_of(rating):
    for lo, hi in BANDS:
        if lo <= rating <= hi:
            return "%d-%d" % (lo, hi)
    return "?"


def estimate(slot, pred, floor, ids, era, expand):
    """Recompute one slot under the chosen configuration."""
    used = [ANCHORS[a] for a in ids if a in ANCHORS]
    value = float(pred)
    if era and used:
        value += -sum(discount(y) for _, y in used) / float(len(used))
    if expand:
        value = PIVOT + (value - PIVOT) * EXPAND
    value = max(floor, value)                       # Pass E floor gate, after D.1
    value = int(round(value / 100.0) * 100)
    return min(3500, max(800, value))


def truth_for(slot, era):
    """Era-corrected ground truth: a printed label is on its own year's scale."""
    if not era:
        return TRUTH[slot]
    return TRUTH[slot] - discount(CORPUS.get(EVID[slot], "2020")[:4])


def measure(data, era, expand):
    errs, per = [], {}
    for slot, (pred, floor, ids) in data.items():
        e = estimate(slot, pred, floor, ids, era, expand) - truth_for(slot, era)
        errs.append(e)
        per.setdefault(band_of(TRUTH[slot]), []).append(e)
    bb = dict((k, sum(v) / float(len(v))) for k, v in per.items())
    return {
        "mae": sum(abs(x) for x in errs) / float(len(errs)),
        "bias": sum(errs) / float(len(errs)),
        "w200": 100.0 * sum(1 for x in errs if abs(x) <= 200) / len(errs),
        "worst": max(abs(x) for x in bb.values()),
        "spread": max(bb.values()) - min(bb.values()),
        "bands": bb,
    }


def slope(data):
    """Regress predicted on true. 1.0 means no compression."""
    xs = [TRUTH[s] for s in data]
    ys = [data[s][0] for s in data]
    mx = sum(xs) / float(len(xs))
    my = sum(ys) / float(len(ys))
    return (sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            / sum((x - mx) ** 2 for x in xs))


CONFIGS = [
    ("frozen", False, False),
    ("+ era correction", True, False),
    ("+ era + de-compression (REJECTED by round 6)", True, True),
]

if __name__ == "__main__":
    print("%-36s %5s %6s %6s %11s %7s" % ("", "MAE", "bias", "w200", "worst band", "spread"))
    for rnd in ("round4", "round5"):
        data = load(rnd)
        print("-" * 76 + " %s  (n=%d, compression slope %.2f)" % (rnd, len(data), slope(data)))
        for name, era, expand in CONFIGS:
            m = measure(data, era, expand)
            print("%-36s %5.0f %+6.0f %5.0f%% %11.0f %7.0f"
                  % (name, m["mae"], m["bias"], m["w200"], m["worst"], m["spread"]))

    print("\nper-band bias, frozen -> shipped")
    for rnd in ("round4", "round5"):
        data = load(rnd)
        a = measure(data, False, False)["bands"]
        b = measure(data, True, True)["bands"]
        print(" %s" % rnd)
        for lo, hi in BANDS:
            k = "%d-%d" % (lo, hi)
            if k in a:
                print("   %-10s %+5.0f  ->  %+5.0f" % (k, a[k], b[k]))
