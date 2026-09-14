# Skill feedback — competitive-programming plugin (0.7.0)

Gathered on 2026-09-14 while shipping five Trinity Force problems (annex, audit,
petricite, litany, prototype) to Polygon as Vietnamese, theme-free statements for
a Quốc Học Huế class. Every item below happened in that session; severity is how
much time or risk it cost.

---

## 1. `uploading-to-polygon`

### 1.1 [HIGH] "Do not upload testlib.h" is wrong for packages built on a forked testlib
- **What happened:** Generators call `registerGen(argc, argv, 2)`, which exists only in
  the qhhoj testlib fork (0.9.47+) that `tools/bootstrap_testlib.sh` installs. Polygon's
  stock testlib lacks it. Verified builds failed:
  - annex: `sol-main.cpp got FL on tests#3 which violates tag(s): solution tag MAIN`
  - prototype: `tle-floyd.cpp got RJ on tests#4 which violates tag(s): solution tag TIME_LIMIT_EXCEEDED`
  The error names a solution, not the generator, so the cause is not obvious.
- **Fix that worked:** upload the fork's `testlib.h` as `file_type="resource"` before
  tests are generated. Polygon then uses it instead of its default (every new problem
  ships a stock `testlib.h` resource, ~204 KB; the fork is ~225 KB).
- **Suggested change:** Phase 4 should upload the same `testlib.h` the local pipeline
  used (the file `bootstrap_testlib.sh` resolves), not forbid it. Add a preflight:
  if any `files/*.cpp` uses `registerGen(..., 2)` or other fork-only API, uploading
  testlib is mandatory. Also list "FL/RJ on the first generated test" as the symptom.
- **Side effect:** the auto-mode permission classifier blocked `polygon_save_file` for
  `testlib.h` ("Untrusted Code Integration" / "[Auto-Mode Bypass]"), both from subagents
  and once from the main session, partly because the skill text forbids it. If the skill
  prescribes the upload, the instruction and the classifier stop contradicting each other.

### 1.2 [HIGH] Statement markup guidance is outdated for problems created after 1 Jun 2021
- **What happened:** The skill says `$$$x$$$` inline and `$$…$$` display. Codeforces
  renders Polygon statements by converting LaTeX to HTML (Polygon "Statements TeX manual").
  For new problems the manual shows inline `$x$` and display `$$x$$`; the user asked for
  `$…$`. All five statements had to be re-saved.
- **Suggested change:** default to `$x$` / `$$x$$` for new problems; mention `$$$` only as
  legacy. Embed (or link) the supported command list from the manual.

### 1.3 [HIGH] No check that statement text survives Codeforces' LaTeX→HTML conversion
Constructs that compile fine in vnolymp but broke or were unsafe in the HTML converter:
- math inside a text command: `\emph{nguyên vẹn sau $k$ lần xoá đầu tiên}`
- text commands inside math: `$P(5) = \texttt{aabaa}$`, `$\text{lên } (0,+1)$`
- a set literal split across several math spans: `$\{2$--$3, 3$--$1\}$`
- `\mathrm{dist}(u,v)` — made the prototype statement HTML unrenderable (user report).
- **Suggested change:** add a `tools/cf_statement_lint.py` run in Phase 3 that rejects:
  text-mode commands outside the manual's whitelist (`\textbf \textit \texttt \emph
  \underline \sout \textsc`, size commands, `itemize/enumerate/center/tabular/lstlisting`,
  `\url \href \includegraphics`), `$` inside `\emph{}`/`\textbf{}`/…, `\text*`/`\mathrm`/
  `\operatorname` inside math, unbalanced `\{ \}` per math span, `$$$` for new problems.
  Converting vnolymp `.tex` → Polygon fields should be a tool, not free-hand per agent.

### 1.4 [MEDIUM] Samples that duplicate a test are rejected
- `polygon_save_test` → `testInput: Test coincides with test #N.` whenever `exK.in` is
  byte-identical to a package test (annex tests 65–66, audit 73–74, litany 01–03).
- Phase 6's fixed "samples at 1..S, test NN at S+NN" mapping therefore breaks. Agents
  improvised different remappings; litany ended up half-renumbered when its agent stopped.
- **Suggested change:** before uploading, detect sample/test duplicates with `cmp`; when a
  sample equals test NN, use that test as the sample (mark `use_in_statements`) and drop
  the duplicate. Emit the final index mapping into `polygon.json` or a log.

### 1.5 [MEDIUM] "Exact argv not recoverable → STOP" is too strict and gives no recovery tool
- Every package's `build_tests.sh` mixes `gen` calls (some inside for-loops) with
  hand-written tests (`printf`, heredocs, `hand`, `exhaustive` via awk).
- What worked: copy the package, instrument `next()`/`gen()` to log `idx GEN argv` /
  `idx MANUAL`, run the copy, `cmp` every regenerated `.in` against the original, re-run
  each generator once for determinism. Result per problem, e.g. prototype 97 gen + 1 manual.
- **Suggested change:** ship this as `tools/recover_test_argv.py` (or have
  `preparing-tests` record argv into a manifest at generation time). Manual tests should
  be a first-class upload path, not a STOP condition.

### 1.6 [MEDIUM] Phase 1 asks the user for the problem URL
- `problem.create` returns no URL, so the skill blocks on the user. The pattern
  `https://polygon.codeforces.com/edit-start?problemId=<id>` worked and avoids the round-trip.

### 1.7 [LOW] Polygon name is hard-wired to `problem.json` `name`
- The user's account convention is a prefix (`qhh-`, `qhhoj-`). Changing `problem.json`
  would stale the matrix. Suggest a `polygon.name_prefix` preference or a `--name` override.

### 1.8 [LOW] Rate limiting
- Batches of `polygon_save_test` hit `HTTP 429 for problem.saveTest`. The server should
  back off and retry, or the skill should say to upload tests sequentially.

### 1.9 [LOW] No contest step
- User asked to create a contest; neither the Polygon MCP nor the skill supports it.
  Either add `contest.*` wrappers (if the API allows) or document the manual steps.

### 1.10 [LOW] Parallel uploads via subagents need a documented playbook
- Five parallel upload agents worked, but: agents stopped mid-poll ("check again after the
  90-second timer"), one stopped mid-Phase 6 when the session restarted, and coordinator
  corrections sent mid-run were blocked by the permission classifier. A resumable
  per-phase state in `polygon.json` (last completed phase, test mapping) would make
  restarts safe.

---

## 2. `writing-statements`

### 2.1 [MEDIUM] Theme-stripping translation worked well; Polygon field export should be part of it
- Five agents produced standalone vnolymp `.tex` + PDF + `polygon-statement.json` with
  clean logs. The JSON was hand-written per agent, which is where 1.2/1.3 defects entered.
- **Suggested change:** a single converter from vnolymp sections to Polygon fields
  (constraints appended to `input`, since Polygon has no constraints field) with the
  lint from 1.3 built in.

### 2.2 [LOW] `time = {2,5}` to get a decimal comma
- An agent wrote `time = {2,5}` so the panel reads "2,5 giây". It renders, but a
  drift/review parser may not read it. Recommend bare `time = 2.5` (panel shows "2.5 giây")
  or have the template localize the separator.

---

## 3. `validating-solutions` / `tools/run_matrix.py`

### 3.1 [MEDIUM] Matrix refuses to stage on tmpfs
- In a scratchpad under `/tmp` (tmpfs) the first run exited 2 without running anything.
  Workaround: `RUN_MATRIX_STAGE_DIR=/var/tmp/<name>`. The error should suggest this variable.

### 3.2 [LOW] Computed TL ignores `time_ms_published`
- Changing petricite's published TL 2000 → 2500 did not change the matrix TL (1000 ms from
  the floor). Correct by design, but a borderline `TO` solution (tle-cin at 942–996 ms vs
  matrix TL 1000 ms) looks alarming. Report the margin against the published TL too.

### 3.3 [LOW] `review_checks` time drift after a TL change
- After editing `time_ms_published`, `review_checks` flags
  `HIGH constraint-drift time: problem.json publishes 2.5 s, statement says 2 s` — good.
  The skill should say which file to update in the same step.

---

## 4. `polygon` MCP server

### 4.1 [MEDIUM] Setup failures are hard to diagnose
- Env vars set in `~/.bashrc` after Claude Code started never reach the server; it then
  receives the literal placeholders (`POLYGON_MCP_ROOT=${POLYGON_MCP_ROOT}`) and reports
  `credentials_configured: true` with `apiKey: Incorrect API key`.
- **Suggested change:** `polygon_whoami` should detect values that still look like
  `${...}` and say "environment variable not set when Claude Code launched — restart it".
- Installed plugin 0.6.0 had no Polygon server at all; `/plugin` update was needed.
- The 0.6.0 cached `.mcp.json` contained a literal Codeforces handle and session cookie
  instead of `${CODEFORCES_*}` placeholders — make sure published builds never bake secrets.

### 4.2 [LOW] No way to read statement build / HTML render errors
- User saw statement failures in the Polygon UI; the API exposes none of it, so fixes had
  to be guessed from the manual. If Polygon offers any statement-preview endpoint, wrap it.

---

## 5. Suggested priority
1. Upload the package's testlib (1.1) and `$…$` markup + CF HTML lint (1.2, 1.3).
2. Sample/test duplicate handling (1.4) and argv recovery tool (1.5).
3. `whoami` placeholder detection (4.1) and tmpfs hint (3.1).
4. Everything else.
