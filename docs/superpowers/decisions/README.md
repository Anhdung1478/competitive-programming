# Decision records

The six SDD run ledgers, moved here from `.superpowers/sdd/*/progress.md` so
they survive. That directory is git-ignored scratch: `git clean -fdx` would
have destroyed every ruling below, and the rulings are the part that outlives
the run.

Each file is the verbatim ledger for one plan — nothing distilled away. They
are **historical records**: they describe what was decided and why, at the time,
and are not updated when later work supersedes them. Where a ledger contradicts
current code, the code wins and the ledger tells you what someone believed.

| Ledger | Plan | Outcome |
|---|---|---|
| [`2026-07-29-parallel-contest-solving`](2026-07-29-parallel-contest-solving.md) | judge-agnostic contests, interactive statements | shipped |
| [`2026-07-30-problem-setting-stage-1`](2026-07-30-problem-setting-stage-1.md) | 8 tools, `preparing-tests`, `validating-solutions` | PR #3, 151 tests |
| [`2026-07-30-problem-setting-stage-2`](2026-07-30-problem-setting-stage-2.md) | `shaping-`/`reviewing-`/`creating-problems` | PR #4, 214 tests |
| [`2026-07-31-file-io-support`](2026-07-31-file-io-support.md) | file-based IO, `NO_OUTPUT`, routing table | PR #5, 270 tests |
| [`2026-08-09-parallel-invocation-matrix`](2026-08-09-parallel-invocation-matrix.md) | per-user box-id lease pool, reentrant `_run_once`, parallel pass 2 | 321 tests, 2.79x measured |
| [`2026-08-09-matrix-followups`](2026-08-09-matrix-followups.md) | exit-code contract at `main()`, staleness gate on `invocation.json` | 353 tests |
| [`2026-09-14-polygon-upload-feedback`](2026-09-14-polygon-upload-feedback.md) | not a run ledger: the field report from uploading five problems to Polygon | acted on in 0.8.0 |

---

## Standing rules

Binding on all future work in this repo unless explicitly overturned.

- **R1** — externally-authored data must never surface a bare stdlib exception.
  Raise the module's own error type. Extended in Stage 1's final wave to cover
  wrong *types* and missing files, not just missing keys.
- **R2** — where a plan's reference code contradicts the plan's stated purpose,
  **the purpose governs** and the fix is dispatched without escalation.
- **Evidence standard** — a claim in a docstring, comment or skill is a testable
  assertion. If it says "X is guaranteed", a test must fail when X stops being
  true. Stage 1 shipped four comments asserting things the code did not do; two
  were the controller's own words transcribed into source.
- **Verification standard** — an error path you have not triggered is not
  handled, and a command you have not run from a foreign working directory is
  not runnable. Both were established the hard way.

## Design rulings

- **`status()` and `review_checks.run()` never raise.** They exist to inspect
  packages *under construction*, which are malformed by definition. A tool that
  dies on the thing it exists to inspect is useless; an unevaluable check
  becomes a `done=False` / `low` finding carrying the reason.
- **A clean shipped package must never contain a `NO_OUTPUT` row.** It means the
  harness could not evaluate the run — a package defect, not a solution class.
  `NO_OUTPUT` parallels `FAIL`: undeclarable, ranked above every solution
  verdict, always a mismatch, never a hole.
- **`holes` is the pipeline's one non-circular claim** — a hole is a solution
  declared wrong that no test killed. It has survived three stages unchanged and
  should outlive every future one.
- **isolate is a hard dependency, with no fallback runner** (human decision).
  The pipeline refuses to run where isolate is absent rather than silently
  measuring something weaker.
- **The unresolvable-HIGH statement ambiguity is a STOP, not a route.** All three
  of `creating-problems`, `validating-solutions` and `reviewing-problems` must
  agree; Stage 2 shipped them disagreeing, which would have let an agent hand off
  and continue while the umbrella believed the pipeline had halted.
- **Prose tasks have no red/green cycle.** Their verification is that every
  command in the file was actually run, from the directory a reader would be
  standing in — which is where prose skills actually fail.

## Human decisions

Recorded because they are editorial, not technical defaults an assistant can
infer. See the `ask-before-deciding` rule.

- The sandbox is `ioi/isolate`, no fallback.
- `NO_OUTPUT` is a **new verdict ranked next to `FAIL`** — not reused `RE`, and
  not "write an empty file and let the checker decide". Reporting a filename
  typo as `WA` would be the confident-wrong-verdict failure in miniature.
- **Keep** the guard refusing a model solution that writes no output file, over
  reverting it or downgrading it to a flag.
- The `writing-statements` routing table was pulled **back into** Stage 3
  mid-run, reversing an earlier "file IO only" scope decision.

## The failure mode this project keeps repeating

**Vacuous guards** — tests that pass for reasons unrelated to what they claim.
Eight instances are recorded across the four ledgers: a test that carried the
artifacts it checked for; one built in the orientation that could not trigger
the bug; three that died on an unrelated missing field before reaching the code
they named; one that regenerated the file it was inspecting; eight
`assertTrue`-only tests satisfied by an unconditional finding; two false-drift
guards that passed against a fully broken parser.

The clearest statement of it, from an implementer during the file-IO run:

> "Exercises existing code" is not the same as "the test's assertion actually
> depends on that code's correctness."

The counter-practice that works: **mutate the implementation and confirm the
test goes red.** Stage 3's final review ran 25 mutations and found no vacuous
guard — the first clean result on this weak spot.

A companion failure: **claims reported as verified after reading rather than
running.** Seven instances on record. Reviews on this project are held to
running.

## Open items

- ~~The suite is **not parallel-safe with itself**~~ — **Resolved** 2026-08-09
  by `docs/superpowers/plans/2026-08-09-parallel-invocation-matrix.md`: box
  ids are leased from a per-user, cross-process `flock` pool instead of
  derived from `pid`, and pass 2 now runs on that same pool.
- **The serial re-time is not machine-quiet.** `_run_pass2` drains its own
  thread pool before re-timing an ambiguous measurement, but `box_pool`'s
  leases are shared across invocations, so a sibling `run_matrix` can be
  holding boxes at that moment — and the re-timed value is never re-checked.
  A wall-kill re-time can wall-kill again and mask a hole. Bounded (total
  live boxes never exceed `pool_size`; a single invocation is unaffected) and
  documented in code, so it ships. The obvious fix deadlocks; see
  `docs/superpowers/specs/2026-08-09-retime-quiescence.md` for the analysis,
  four candidate approaches, and the acceptance criteria any fix must meet.
- **`running-contests` is an orphan** — no skill routes to it, not even
  `solving-problems`. A design question, not a defect.
- **`flight` promises absolute error ≤ 1e-6 but ships `rcmp6`**, which grants
  absolute-*or*-relative. A real finding about that package, left for
  `reviewing-problems` to record rather than silently patched.
- **`flight.tex:74-75`'s `xâu con`** is ambiguous between *substring* and
  *subsequence*. Flagged, never resolved — an editorial call.
- Deferred minors are triaged in each ledger's final-review section.
