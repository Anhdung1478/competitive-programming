#!/usr/bin/env python
"""Build-time corpus tool for the calculating-difficulties skill.

This never runs at skill runtime. The skill itself is offline.

    sample    pick PER_BAND rated Div1/Div2 problems per 200-point band -> corpus.md
    extend    append EXTEND_PER_BAND fresh Div1/Div2 anchors per band -> corpus.md,
              append-only, refuses once the corpus reaches its target size
    starter   pick 1 per band and fetch it, for the provisional anchor set
    fetch     download every sampled statement into the cache as plain text
    split     assign each corpus row an anchor/eval/excluded role -> eval-set.md
    blind     write eval statements to CACHE/blind, title stripped, for eval agents
    check     verify corpus/eval-set/anchors integrity (row counts, roles,
              anchor/eval disjointness, no eval leakage, label integrity)
    metrics   score a predictions file against the eval set's true ratings
    metrics-today  same, but against era-corrected (today-scale) labels
    fresh-build    sample+fetch the held-out eval set (disjoint from corpus.md) -> eval-set-2.md
    fresh-blind    write held-out statements to CACHE/blind2, title stripped

WARNING: do not re-run `sample` once corpus.md is committed. The Codeforces
problemset grows, so a second run selects a different corpus and silently
invalidates every measurement taken against the first.
"""
import html
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../calculating-difficulties/calibration
SKILL = HERE.parent                             # .../calculating-difficulties
REPO = SKILL.parents[1]                         # repository root
CACHE = REPO / ".cache-cf-corpus"
CORPUS = HERE / "corpus.md"

SEED = 20260916
EXTEND_SEED = 20260919
CUTOFF = 1514764800                             # 2018-01-01 UTC
BANDS = [(1100 + 200 * i, 1299 + 200 * i) for i in range(8)]
PER_BAND = 25                                   # problems per band in the frozen corpus
EXTEND_PER_BAND = 15
UA = "Mozilla/5.0 (compatible; cp-problem-generation calibration)"
COLUMNS = ["id", "rating", "div", "date", "band", "role"]

EVAL_PER_BAND = 3
EVAL = HERE / "eval-set.md"
ANCHORS = SKILL / "references" / "anchors.md"

# Anchor ids cited by a recorded round that are not in anchors.md. Both are the same
# typo for 1063C and both are already written up under `Post-freeze corrections` in
# metrics.md. Nothing goes in here without being recorded there the same way.
KNOWN_BAD_CITATIONS = {"1063D"}

# Selecting anchors by year rather than by match quality is what blind round 6 measured
# at +42 MAE (metrics.md, round 6). The instruction was deleted from SKILL.md but left
# in anchors.md, which Pass C also reads, so round 7 measured a half-removed preference.
# This guard is what would have caught that.
RECENCY_GUARD = re.compile(r"prefer the (more recent|newer)", re.I)

# `| eval-NN | predicted | floor | anchors used |` in a predictions file. Round 1
# separates the ids with spaces, later rounds with commas.
PREDICTION_ROW = re.compile(r"^\|\s*eval-\d+\s*\|[^|]*\|[^|]*\|([^|]*)\|")

# The held-out set. eval-set.md was tuned against for seven rounds and is no longer
# held out in any strict sense; this one is drawn from problems absent from corpus.md
# entirely, so it overlaps neither the anchors nor the old eval set.
FRESH_EVAL = HERE / "eval-set-2.md"
FRESH_PER_BAND = 6                              # 6 x 8 bands = 48, ~+/-28 standard error
FRESH_SEED = 20260920
FRESH_BLIND = "blind2"

# Codeforces serves 1181C's statement as a native PDF, so it cannot be fetched
# or summarized. It stays in the frozen corpus as a record of the sample and is
# excluded from both roles.
EXCLUDED = {"1181C"}


def api(path):
    req = urllib.request.Request("https://codeforces.com/api/" + path,
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.load(resp)
    if payload.get("status") != "OK":
        sys.exit("CF API refused %s: %s" % (path, payload.get("comment")))
    return payload["result"]


def division(contest_name):
    d1 = "Div. 1" in contest_name
    d2 = "Div. 2" in contest_name
    if d1 and d2:
        return "Div1+2"
    if d1:
        return "Div1"
    if d2:
        return "Div2"
    return None


def band_of(rating):
    return (rating - 1100) // 200


def candidates():
    problems = api("problemset.problems")["problems"]
    contests = {c["id"]: c for c in api("contest.list?gym=false")}
    pool = {b: [] for b in range(len(BANDS))}
    for p in problems:
        rating = p.get("rating")
        if rating is None or not (1100 <= rating <= 2699):
            continue
        contest = contests.get(p.get("contestId"))
        if not contest or contest.get("startTimeSeconds", 0) < CUTOFF:
            continue
        div = division(contest.get("name", ""))
        if not div:
            continue
        pool[band_of(rating)].append({
            "id": "%s%s" % (p["contestId"], p["index"]),
            "rating": rating,
            "div": div,
            "date": time.strftime("%Y-%m-%d", time.gmtime(contest["startTimeSeconds"])),
            "role": "",
        })
    return pool


def pick(pool, per_band, seed):
    rng = random.Random(seed)
    rows = []
    for b in range(len(BANDS)):
        entries = sorted(pool[b], key=lambda e: e["id"])
        if len(entries) < per_band:
            sys.exit("band %d has only %d candidates" % (BANDS[b][0], len(entries)))
        rows.extend(sorted(rng.sample(entries, per_band), key=lambda e: e["id"]))
    return rows


def write_corpus(rows):
    lines = [
        "# Corpus — the frozen sample",
        "",
        "Build-time only. Never read at skill runtime, never named by SKILL.md.",
        "Written by `fetch-corpus.py`. Do not edit the table by hand.",
        "",
        "| id | rating | div | date | band | role |",
        "|---|---|---|---|---|---|",
    ]
    for e in rows:
        b = band_of(int(e["rating"]))
        lines.append("| %s | %s | %s | %s | %d-%d | %s |" % (
            e["id"], e["rating"], e["div"], e["date"], BANDS[b][0], BANDS[b][1], e["role"]))
    CORPUS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_corpus():
    if not CORPUS.exists():
        sys.exit("%s does not exist — run `sample` first" % CORPUS)
    rows = []
    for line in CORPUS.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.startswith("| id ") or set(line) <= set("|- "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(dict(zip(COLUMNS, cells)))
    return rows


def to_text(page_html):
    match = re.search(r'<div class="problem-statement">(.*?)</html>', page_html, re.S)
    body = match.group(1) if match else page_html
    body = re.sub(r"<script.*?</script>", " ", body, flags=re.S)
    body = re.sub(r"<br\s*/?>", "\n", body)
    body = re.sub(r"</(p|div|li)>", "\n", body)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html.unescape(body)
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n\s*\n+", "\n\n", body)
    return body.strip()


def fetch_one(problem_id):
    match = re.match(r"(\d+)([A-Za-z]\d*)$", problem_id)
    if not match:
        return "malformed id"
    url = "https://codeforces.com/problemset/problem/%s/%s" % match.groups()
    # Codeforces sits behind a Cloudflare challenge. When it is active, plain curl
    # gets a 403 interstitial; pass a browser session through the environment:
    #   CF_UA="<navigator.userAgent>" CF_COOKIE="cf_clearance=..." python ... fresh-build
    # The cookie is bound to that user agent and to the machine's IP, and it is never
    # written to disk or committed.
    agent = os.environ.get("CF_UA") or UA
    cmd = ["curl", "-sS", "-m", "60", "--compressed", "-A", agent]
    cookie = os.environ.get("CF_COOKIE")
    if cookie:
        cmd += ["-H", "Cookie: " + cookie]
    proc = subprocess.run(cmd + [url], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        return "curl exit %d" % proc.returncode
    if "Just a moment" in proc.stdout or "challenge-platform" in proc.stdout:
        return "blocked by Cloudflare — set CF_UA and CF_COOKIE"
    if "problem-statement" not in proc.stdout:
        return "no statement in response"
    text = to_text(proc.stdout)
    if len(text) < 200:
        return "extracted only %d chars" % len(text)
    CACHE.mkdir(exist_ok=True)
    (CACHE / ("%s.txt" % problem_id)).write_text(text, encoding="utf-8")
    return None


def cmd_sample():
    if CORPUS.exists():
        sys.exit("%s already exists. Re-sampling invalidates every measurement taken "
                 "against it. Delete it deliberately if that is what you mean." % CORPUS)
    rows = pick(candidates(), PER_BAND, SEED)
    write_corpus(rows)
    print("sampled %d problems into %s" % (len(rows), CORPUS))


def cmd_extend():
    rows = read_corpus()
    if len(rows) >= len(BANDS) * PER_BAND:
        sys.exit("%s already holds %d rows — the corpus is at its target size and "
                 "`extend` is append-only. Raise PER_BAND deliberately to grow it "
                 "further." % (CORPUS, len(rows)))
    present = {r["id"] for r in rows}
    pool = candidates()
    rng = random.Random(EXTEND_SEED)
    added = []
    for b in range(len(BANDS)):
        fresh = sorted((e for e in pool[b] if e["id"] not in present),
                       key=lambda e: e["id"])
        if len(fresh) < EXTEND_PER_BAND:
            sys.exit("band %d has only %d unused candidates, need %d"
                     % (BANDS[b][0], len(fresh), EXTEND_PER_BAND))
        for entry in sorted(rng.sample(fresh, EXTEND_PER_BAND), key=lambda e: e["id"]):
            entry["role"] = "anchor"
            added.append(entry)
    write_corpus(sorted(rows + added, key=lambda r: (band_of(int(r["rating"])), r["id"])))
    print("appended %d anchors -> %s (%d rows total)"
          % (len(added), CORPUS, len(rows) + len(added)))


def cmd_starter():
    rows = pick(candidates(), 1, SEED + 99)
    print("| id | rating | div | date |")
    for e in rows:
        err = fetch_one(e["id"])
        print("| %s | %s | %s | %s |%s" % (
            e["id"], e["rating"], e["div"], e["date"], "" if err is None else "  FAILED: " + err))
        time.sleep(1.5)
    print("statements cached in %s" % CACHE)


def cmd_fetch():
    rows = read_corpus()
    missing = [r for r in rows if not (CACHE / ("%s.txt" % r["id"])).exists()]
    print("%d already cached, %d to fetch" % (len(rows) - len(missing), len(missing)))
    failures = []
    for i, row in enumerate(missing, 1):
        err = fetch_one(row["id"])
        print("  [%d/%d] %s%s" % (i, len(missing), row["id"],
                                  "" if err is None else "  FAILED: " + err))
        if err:
            failures.append(row["id"])
        time.sleep(1.5)
    print("cached: %d / %d" % (len(rows) - len(failures), len(rows)))
    if failures:
        print("re-run `fetch` to retry: %s" % " ".join(failures))
        sys.exit(1)


def cmd_split():
    rows = read_corpus()
    if any(r["role"] for r in rows):
        sys.exit("roles are already assigned in %s — re-splitting would move problems "
                 "between the anchor and eval sets and invalidate every measurement" % CORPUS)
    rng = random.Random(SEED + 1)
    by_band = {}
    for row in rows:
        if row["id"] in EXCLUDED:
            row["role"] = "excluded"
            continue
        by_band.setdefault(row["band"], []).append(row)
    for band in sorted(by_band):
        entries = sorted(by_band[band], key=lambda e: e["id"])
        chosen = {e["id"] for e in rng.sample(entries, EVAL_PER_BAND)}
        for entry in entries:
            entry["role"] = "eval" if entry["id"] in chosen else "anchor"
    write_corpus(rows)

    evals = sorted([r for r in rows if r["role"] == "eval"], key=lambda r: r["id"])
    excluded = [r for r in rows if r["role"] == "excluded"]
    lines = [
        "# Eval set — held out",
        "",
        "Build-time only. Never read at skill runtime, never named by SKILL.md, and never",
        "shown to an agent that is about to predict a rating. The whole accuracy claim",
        "rests on these 24 problems being unseen by the rubric.",
        "",
        "| slot | id | rating | band |",
        "|---|---|---|---|",
    ]
    for n, row in enumerate(evals, 1):
        lines.append("| eval-%02d | %s | %s | %s |" % (n, row["id"], row["rating"], row["band"]))
    EVAL.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("split: %d anchors, %d eval, %d excluded -> %s" % (
        len(rows) - len(evals) - len(excluded), len(evals), len(excluded), EVAL))


def read_eval(path=None, prefix="| eval-"):
    path = path or EVAL
    if not path.exists():
        sys.exit("%s does not exist — run `split` first" % path)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith(prefix):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(dict(zip(["slot", "id", "rating", "band", "date"], cells)))
    return rows


def read_any_eval(path):
    """Read either eval set, picking the slot prefix from the file's own rows.

    Deciding by path identity against FRESH_EVAL fails for a relative path that
    names the same file: the prefix then silently falls back to "| eval-", no row
    matches, and the caller scores an empty set instead of reporting the mistake.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    prefix = "| fresh-" if any(l.startswith("| fresh-") for l in lines) else "| eval-"
    rows = read_eval(path, prefix)
    if not rows:
        sys.exit("%s contains no '%s' rows" % (path, prefix.strip()))
    return rows


def cmd_blind():
    out = CACHE / "blind"
    out.mkdir(parents=True, exist_ok=True)
    for row in read_eval():
        src = CACHE / ("%s.txt" % row["id"])
        if not src.exists():
            sys.exit("missing %s — run `fetch` first" % src)
        body = src.read_text(encoding="utf-8")
        # Drop the leading "D. Problem Title" line so the slot cannot be traced by name.
        body = body.split("\n", 1)[1].lstrip() if "\n" in body else body
        (out / ("%s.txt" % row["slot"])).write_text(body, encoding="utf-8")
    print("wrote %d blind statements to %s" % (len(read_eval()), out))


def read_anchor_labels():
    """Parse id/rating/year/div out of every table row in references/anchors.md."""
    rows = []
    for line in ANCHORS.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.startswith("| id ") or set(line) <= set("|- "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        rows.append({"id": cells[0], "rating": cells[1], "year": cells[2], "div": cells[3]})
    return rows


def cmd_check():
    rows = read_corpus()
    failures = []
    if len(rows) != len(BANDS) * PER_BAND:
        failures.append("corpus has %d rows, expected %d" % (len(rows), len(BANDS) * PER_BAND))
    anchors = {r["id"] for r in rows if r["role"] == "anchor"}
    evals = {r["id"] for r in rows if r["role"] == "eval"}
    excluded = {r["id"] for r in rows if r["role"] == "excluded"}
    unassigned = [r["id"] for r in rows if r["role"] not in ("anchor", "eval", "excluded")]
    if unassigned:
        failures.append("unassigned rows: %s" % " ".join(unassigned))
    if excluded != EXCLUDED:
        failures.append("excluded set = %s, expected EXCLUDED constant = %s" % (
            sorted(excluded), sorted(EXCLUDED)))
    overlap = anchors & evals
    if overlap:
        failures.append("CONTAMINATION: %s in both sets" % " ".join(sorted(overlap)))
    for band in sorted({r["band"] for r in rows}):
        n_eval = sum(1 for r in rows if r["band"] == band and r["role"] == "eval")
        if n_eval != EVAL_PER_BAND:
            failures.append("band %s has %d eval, expected %d" % (band, n_eval, EVAL_PER_BAND))
    expected_eval = len(BANDS) * EVAL_PER_BAND
    expected_anchors = len(BANDS) * PER_BAND - expected_eval - len(EXCLUDED)
    if len(evals) != expected_eval:
        failures.append("%d eval rows, expected %d" % (len(evals), expected_eval))
    if len(anchors) != expected_anchors:
        failures.append("%d anchor rows, expected %d" % (len(anchors), expected_anchors))
    for band in sorted({r["band"] for r in rows}):
        n_band = sum(1 for r in rows if r["band"] == band)
        if n_band != PER_BAND:
            failures.append("band %s has %d rows, expected %d" % (band, n_band, PER_BAND))
    if ANCHORS.exists():
        text = ANCHORS.read_text(encoding="utf-8")
        leaked = sorted(e for e in evals if re.search(r"\|\s*%s\s*\|" % re.escape(e), text))
        if leaked:
            failures.append("CONTAMINATION: eval ids present in anchors.md: %s" % " ".join(leaked))
        corpus_by_id = {r["id"]: r for r in rows}
        for a in read_anchor_labels():
            c = corpus_by_id.get(a["id"])
            if c is None:
                failures.append("LABEL MISMATCH: %s in anchors.md not found in corpus.md" % a["id"])
                continue
            if a["rating"] != c["rating"] or a["div"] != c["div"]:
                failures.append(
                    "LABEL MISMATCH: %s anchors.md says %s | %s, corpus.md says %s | %s" % (
                        a["id"], a["rating"], a["div"], c["rating"], c["div"]))
            if a["year"] != c["date"][:4]:
                failures.append(
                    "YEAR MISMATCH: %s anchors.md says %s, corpus.md says %s" % (
                        a["id"], a["year"], c["date"]))
        cited = {a["id"] for a in read_anchor_labels()}
        for pred in sorted(HERE.glob("predictions-*.md")):
            for line in pred.read_text(encoding="utf-8").splitlines():
                row = PREDICTION_ROW.match(line)
                if not row:
                    continue
                for one in re.split(r"[,\s]+", row.group(1).strip()):
                    if one and one not in cited and one not in KNOWN_BAD_CITATIONS:
                        failures.append("BAD CITATION: %s cites %s, absent from anchors.md"
                                        % (pred.name, one))
        if RECENCY_GUARD.search(text):
            failures.append("anchors.md steers anchor selection by year; blind round 6 "
                            "measured that instruction at +42 MAE")
    if EVAL.exists():
        listed = {r["id"] for r in read_eval()}
        if listed != evals:
            failures.append("eval-set.md lists %d ids, corpus marks %d" % (len(listed), len(evals)))
    for failure in failures:
        print("FAIL  %s" % failure)
    if failures:
        sys.exit(1)
    print("anchors: %d   eval: %d   excluded: %d   disjoint: yes" % (
        len(anchors), len(evals), len(excluded)))
    if ANCHORS.exists():
        summarised = len(read_anchor_labels())
        print("anchors.md: %d of %d corpus anchors summarised" % (summarised, len(anchors)))
    print("ALL CHECKS PASSED")


def era_discount(year):
    """SKILL.md Pass C.1: how much an old label overstates today's scale."""
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


def cmd_metrics():
    _metrics(today=False)


def cmd_metrics_today():
    """Score against era-corrected labels.

    Since Pass C.1 the skill states its answer on today's scale, while the eval
    set's ratings are printed labels fitted in their own contest year. Comparing
    the two directly charges the skill for the drift it is correcting for, so this
    verb puts both sides on the same scale before scoring.
    """
    _metrics(today=True)


def _metrics(today):
    if len(sys.argv) not in (3, 4):
        sys.exit("usage: fetch-corpus.py %s <predictions-file.md> [eval-set-file.md]"
                 % sys.argv[1])
    evalpath = Path(sys.argv[3]) if len(sys.argv) == 4 else EVAL
    rows = read_any_eval(evalpath)
    truth = {r["slot"]: int(r["rating"]) for r in rows}
    bands = {r["slot"]: r["band"] for r in rows}
    if today:
        dates = {r["id"]: r["date"] for r in read_corpus()}
        for r in rows:
            # the fresh eval set carries its own date column; the old one does not
            date = r.get("date") or dates[r["id"]]
            truth[r["slot"]] -= era_discount(date[:4])
    path = Path(sys.argv[2])
    preds = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not (line.startswith("| eval-") or line.startswith("| fresh-")):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        preds[cells[0]] = int(cells[1])
    missing = sorted(set(truth) - set(preds))
    if missing:
        sys.exit("predictions missing for: %s" % " ".join(missing))
    errors = {s: preds[s] - truth[s] for s in truth}
    n = len(errors)
    mae = sum(abs(e) for e in errors.values()) / n
    bias = sum(errors.values()) / n
    within200 = 100.0 * sum(1 for e in errors.values() if abs(e) <= 200) / n
    within300 = 100.0 * sum(1 for e in errors.values() if abs(e) <= 300) / n
    print("## %s%s" % (path.stem, " (today-scale labels)" if today else ""))
    print()
    print("n = %d   MAE = %.0f   bias = %+.0f   within200 = %.0f%%   within300 = %.0f%%"
          % (n, mae, bias, within200, within300))
    print()
    print("| band | n | MAE | bias |")
    print("|---|---|---|---|")
    for band in sorted({bands[s] for s in truth}):
        slots = [s for s in truth if bands[s] == band]
        b_mae = sum(abs(errors[s]) for s in slots) / len(slots)
        b_bias = sum(errors[s] for s in slots) / len(slots)
        print("| %s | %d | %.0f | %+.0f |" % (band, len(slots), b_mae, b_bias))
    print()
    print("| slot | true | predicted | error |")
    print("|---|---|---|---|")
    for slot in sorted(truth):
        print("| %s | %d | %d | %+d |" % (slot, truth[slot], preds[slot], errors[slot]))


def cmd_fresh_build():
    """Sample, fetch and record the held-out eval set, disjoint from corpus.md."""
    if FRESH_EVAL.exists():
        sys.exit("%s already exists. It is the only uncontaminated measurement this "
                 "skill has; re-sampling it destroys that. Delete it deliberately if "
                 "that is what you mean." % FRESH_EVAL)
    taken = {r["id"] for r in read_corpus()}
    pool = candidates()
    rng = random.Random(FRESH_SEED)
    chosen = []
    for b in range(len(BANDS)):
        fresh = sorted((e for e in pool[b] if e["id"] not in taken), key=lambda e: e["id"])
        if len(fresh) < FRESH_PER_BAND:
            sys.exit("band %d has only %d candidates outside the corpus"
                     % (BANDS[b][0], len(fresh)))
        # Oversample: some statements are served as PDFs and cannot be fetched.
        order = rng.sample(fresh, min(len(fresh), FRESH_PER_BAND * 4))
        kept = []
        print("band %d-%d:" % BANDS[b])
        for entry in order:
            if len(kept) == FRESH_PER_BAND:
                break
            err = fetch_one(entry["id"])
            if err is None:
                kept.append(entry)
                print("  %-8s %s  ok" % (entry["id"], entry["rating"]))
            else:
                print("  %-8s %s  skipped: %s" % (entry["id"], entry["rating"], err))
            time.sleep(1)
        if len(kept) < FRESH_PER_BAND:
            sys.exit("band %d: fetched only %d of %d" % (BANDS[b][0], len(kept), FRESH_PER_BAND))
        chosen.extend(sorted(kept, key=lambda e: e["id"]))

    lines = [
        "# Eval set 2 — the held-out set",
        "",
        "Build-time only. Never read at skill runtime, never named by SKILL.md, and never",
        "shown to an agent that is about to predict a rating.",
        "",
        "Drawn from rated Div1/Div2 problems absent from `corpus.md` entirely, so it is",
        "disjoint from the 171 anchors *and* from the 24 problems in `eval-set.md` that",
        "seven rounds of tuning were measured against. This is the only set that can still",
        "support a held-out accuracy claim.",
        "",
        "| slot | id | rating | band | date |",
        "|---|---|---|---|---|",
    ]
    for i, e in enumerate(chosen, 1):
        b = band_of(int(e["rating"]))
        lines.append("| fresh-%02d | %s | %s | %d-%d | %s |" % (
            i, e["id"], e["rating"], BANDS[b][0], BANDS[b][1], e["date"]))
    FRESH_EVAL.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\nwrote %d held-out problems to %s" % (len(chosen), FRESH_EVAL))


def cmd_fresh_blind():
    out = CACHE / FRESH_BLIND
    out.mkdir(parents=True, exist_ok=True)
    rows = read_any_eval(FRESH_EVAL)
    for row in rows:
        src = CACHE / ("%s.txt" % row["id"])
        if not src.exists():
            sys.exit("missing %s — run `fresh-build` first" % src)
        body = src.read_text(encoding="utf-8")
        # Drop the leading "D. Problem Title" line so the slot cannot be traced by name.
        body = body.split("\n", 1)[1].lstrip() if "\n" in body else body
        (out / ("%s.txt" % row["slot"])).write_text(body, encoding="utf-8")
    print("wrote %d blind statements to %s" % (len(rows), out))


VERBS = {"sample": cmd_sample, "extend": cmd_extend, "starter": cmd_starter,
         "fetch": cmd_fetch, "split": cmd_split, "blind": cmd_blind,
         "check": cmd_check, "metrics": cmd_metrics,
         "metrics-today": cmd_metrics_today,
         "fresh-build": cmd_fresh_build, "fresh-blind": cmd_fresh_blind}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in VERBS:
        sys.exit("usage: fetch-corpus.py {%s}" % "|".join(VERBS))
    VERBS[sys.argv[1]]()
