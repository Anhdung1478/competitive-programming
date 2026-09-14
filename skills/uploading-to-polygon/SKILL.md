---
name: uploading-to-polygon
description: >
  Use ONLY when the user explicitly asks to upload, push, ship or re-sync a
  finished problem package to Codeforces Polygon — upload this to polygon,
  push the package to polygon, sync it to polygon, put it on polygon. Drives
  the plugin's own bundled `polygon` MCP server (tools `polygon_*`): create
  the problem, set limits, write the statement, push validator, generators
  and checker, upload every solution with its expected verdict, save the
  generator script and the samples, wire subtasks into groups and points,
  commit, and grant the coordinators read access. It is the one opt-in step
  of the setting pipeline and never runs on its own — not at the end of
  competitive-programming:creating-problems, not after a review. It uploads
  a package that is already finished and never regenerates, repairs or
  re-reviews one.
---

# Uploading to Polygon

Ship a finished package to [Polygon](https://polygon.codeforces.com) through
this plugin's **own** bundled MCP server. The upload mirrors what
`problem.json` and the files on disk already say, and a package that is not
finished goes back to a sibling skill rather than being patched up on the way
out. **The one file this skill writes into the package is `polygon.json`** — the
record of which Polygon problem the package owns. What it assembles on the
way lives in `$SCRATCH`, or in a staging directory under the server's
readable root that is removed after the run. Nothing in it edits
`problem.json`, the statement, the tests or the solutions.

**This skill runs only when asked for.** Every other setting skill is part of
a pipeline that reaches an end; this one starts after that end, publishes to
an account that owns real problems, and is not something to do helpfully.

## Am I the right skill?

| If it's really about | Use |
|---|---|
| Finishing the package first — any phase still incomplete | `competitive-programming:creating-problems` |
| Auditing a package that has not been signed off yet | `competitive-programming:reviewing-problems` |
| The statement prose itself, in the `.tex` | `competitive-programming:writing-statements` |
| Test data, groups, the generator families | `competitive-programming:preparing-tests` |
| Publishing a package the user has explicitly asked to upload | this skill |

## Bootstrap

`$BASE` is not an environment variable the harness sets — it is not exported
into a shell, only into MCP config. What you actually have is the line **"Base
directory for this skill" printed in this skill's own invocation preamble.
Substitute that literal path for `BASE` below:

```bash
BASE="<the path from this skill's own 'Base directory for this skill' line>"
PLUGIN_ROOT="$BASE/../.."
PROBLEM="<absolute path to the problem directory you are uploading>"
TESTLIB="$(bash "$PLUGIN_ROOT/tools/bootstrap_testlib.sh")"
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/polygon-upload.XXXXXX")"
cd "$PLUGIN_ROOT"
PREFS="$(python3 -m tools.preferences)"
```

`$SCRATCH` holds everything this run assembles that is not package data —
the statement fields, the recovered test manifest. It is outside `$PROBLEM`
on purpose. When the harness already gives you a scratch directory, a fresh
subdirectory of it works just as well.

`$PREFS` is the effective `preferences.toml` as JSON — the standing answers
to the questions this pipeline would otherwise put to a human on every
problem. Read it before asking anything it already answers, and treat a
value of `"ask"` as the file declining to decide: that one is genuinely
open, so ask it. Anything said in this conversation still wins over the
file, for this problem only.

The keys this skill reads: `polygon.name_prefix` (prepended to
`problem.json`'s `name` to form the Polygon problem name),
`polygon.statement_language` (the language the statement is expected to be
in; Phase 3 asks when the `.tex` is in another),
`polygon.notify_on_commit` (whether the commit emails the problem's other
authors), `polygon.grant_codeforces_read` (whether to hand the `codeforces`
login read access at the end).

Every `python3 -m tools.*` command below is a module inside `tools/`, only
importable with `PLUGIN_ROOT` as the working directory — `cd` there first, or
every invocation fails with `ModuleNotFoundError` before it does anything.
**The working directory stays `$PLUGIN_ROOT` for everything below**, and
`$PROBLEM` is passed as an argument, never `cd`'d into.

## Secrets never reach you

The server reads its credentials from its own environment and signs every
request itself. **Never** read a config file for them, print them, ask the
user to paste them into the conversation, or reimplement the signature. If a
tool reports the credentials are missing, stop and point the user at
[`mcp-server/README.md`](../../mcp-server/README.md) — that is the whole of
your setup advice.

## Bind the tools before you call one

The server's tools are not in your catalogue until you load them: call
`ToolSearch` with a `select:` list of the names each phase needs, and **read
the loaded schema**, which always wins over anything written down.
[`references/polygon-tools.md`](references/polygon-tools.md) lists all
thirty-six with the API method each wraps and the failure shape they share;
it is a map, not an authority.

Never retry an identical request, and never invent a tool the server does not
have. If the server is not connected, say so and stop: there is no degraded
mode here, because a half-uploaded problem is worse than none.

## Phase 0 — preflight, and the one blocking gate

**Both preconditions, run fresh, in this conversation.** Not remembered from
earlier in the session:

```bash
python3 -m tools.package_status "$PROBLEM" "$TESTLIB"
python3 -m tools.review_checks "$PROBLEM" "$PROBLEM/<name>.tex" "$TESTLIB"
```

`tools.package_status` must print `complete` — every phase `[x]`, no `next:`
line — and `tools.review_checks` must exit 0. Either one short of that and
you **stop**: send the package back to `creating-problems` or
`reviewing-problems`. Upload is not a way to finish a package, and a Polygon
problem built from one that drifted carries the drift into a contest.
**REQUIRED:** invoke `superpowers:verification-before-completion` and show
both commands' output and exit codes.

Then read `problem.json`, the single source of truth for every number below.

**Already on Polygon?** Read the package's Polygon record:

```bash
python3 -c "import sys;from tools.polygon_ref import load;print(load(sys.argv[1]))" "$PROBLEM"
```

`None` means the package has never been uploaded — go on to Phase 1. Anything
else means it has. Ask, and do not proceed until answered:
**re-sync** the problem the record names — uploading only the files whose
mtime is newer than its `committed_at`, the RFC 3339 timestamp of the last
revision this skill committed, then committing again — or **stop**. There is
no third answer. On a re-sync, **skip Phase 1 entirely**: the problem already
exists, and `problem_id` for every phase below is the record's `id`. **Never
create a second Polygon problem for a package that already has one**: no
tidying afterwards undoes the id the user's collaborators have already
bookmarked. A record that fails to load is a `PolygonRefError` naming the
field — report it and stop; do not guess around it.

The record is `polygon.json`, beside `problem.json` rather than inside it,
and that placement is load-bearing. `problem.json` is matrix evidence: the
two gates above compare it against `invocation.json` and call the matrix
stale when it is newer. A Polygon id written into `problem.json` would fail
the gate this phase has just passed, on every run after the first, over a
package nothing had changed. `polygon.json` is not walked by either gate, so
writing it costs nothing.

## Phase 1 — create, and record where it went

The **Polygon name** is `polygon.name_prefix` followed by `problem.json`'s
`name` (the ASCII slug): with a prefix of `qhh-` and a name of `annex`, it
is `qhh-annex`. It is computed here and never written back into
`problem.json`. The human title is the statement's `name` in Phase 3, and
the two are not the same thing.

1. `polygon_whoami()` — proves the key, the secret and the clock. Note its
   `path_reads_allowed_under`: every `path=` below must lie under it.
2. `polygon_problems_list(name=<Polygon name>)`. A live problem with that
   name and no `polygon.json` in the package means someone else already
   created it, or a previous run failed after create and before recording.
   **Stop and report the id** — do not adopt it silently and do not create a
   second.
3. `polygon_problem_create(name=<Polygon name>)`.
4. **Record it, immediately.** `problem.create` returns `id` and `owner` and
   no address. The problem's page is
   `https://polygon.codeforces.com/edit-start?problemId=<id>`, so build the
   URL from the id — there is no need to ask the user — and write all three
   to `$PROBLEM/polygon.json`:

```bash
python3 -c "import sys;from tools.polygon_ref import PolygonRef,save;save(sys.argv[1],PolygonRef(int(sys.argv[2]),sys.argv[3],sys.argv[4]))" \
  "$PROBLEM" 123456 "<owner, from the create result>" "https://polygon.codeforces.com/edit-start?problemId=123456"
```

`owner` is whatever the create result says — never a name from this skill,
this repository, or a previous problem. Write it before anything else goes
up: a create that is not recorded is the state Phase 1 step 2 has to stop
on next time. `committed_at` stays unset until Phase 8; the module refuses
anything it could not read back, so a `PolygonRefError` here means the
values are wrong, not the file.

## Phase 2 — limits

`polygon_problem_update_info(problem_id, time_limit_ms=<limits.time_ms_published>,
memory_limit_mb=<limits.memory_mb>)`. The published time limit, not
`time_ms_computed` — the statement's promise is what contestants are judged
against.

For `io.input == "stdin"`, **leave `input_file` and `output_file` unset**: a
new Polygon problem is stdin/stdout already, an empty argument means "leave
it alone", and passing the literal string would create a file named `stdin`.
For file IO, pass `io.input` and `io.output` verbatim.

## Phase 3 — statement

`polygon_save_statement(problem_id, lang=<the .tex's language>, …)`, with the
text taken from the package's `.tex` and rewritten into Polygon's markup.
The `.tex` language is the option vnolymp was loaded with, such as
`[english]` or `[vietnamese]`. It should equal `polygon.statement_language`.
**When the two differ, ask before saving anything.** The choice is to upload
the `.tex` as it stands, in its own language, or to stop so
`writing-statements` can translate it. This skill never translates, just as
it never repairs a package.

`format` is the value `tools.problem_meta` resolves: the explicit key, or,
without one, more than one subtask reads as `"oi"` and one (or none) reads
as `"icpc"`.

### Statement markup on Polygon

**Read [`references/polygon-statement-markup.md`](references/polygon-statement-markup.md)
before writing a field.** It is the upload convention. Codeforces renders
the statement to HTML with a converter that supports a short fixed list of
text-mode commands, so a statement whose PDF builds can still render broken
in the HTML. The essentials:

- **Delimiters:** `$x$` inline, `$$x$$` display. `$$$x$$$` belongs to
  problems created before 1 Jun 2021 — never write it for a new one — and
  `\[…\]` is never supported.
- **No formula inside a text command** (`\emph{… $k$ …}`) and **no text
  command inside a formula** (`$\texttt{…}$`, `$\text{…}$`, `$\mathrm{…}$`,
  `$\operatorname{…}$`). Each formula is balanced on its own.
- **`\emph` renders as underline** on Polygon, and vnolymp's `\emph` means
  italics. Convert every `\emph{…}` to `\textit{…}` as part of the rewrite;
  the linter accepts `\emph`, so it will not prompt you to.

| package | Polygon field |
|---|---|
| the title in the statement's language | `name` |
| story and task | `legend` |
| `\InputFile` | `input` |
| `\Constraints` | `input`, appended after a blank line — Polygon has no constraints field |
| `\OutputFile` | `output` |
| the subtask table, `format == "oi"` only | `scoring`, as a `tabular` built from `problem.json` |
| `\Explanation`, then `\Note` | `notes` |

Samples do **not** go in any field; they arrive in Phase 6 as tests marked
for the statement. For `format == "icpc"`, leave `scoring` out entirely.
Figures go up first with `polygon_save_statement_resource` and are then
referenced by name.

Write the fields as one JSON object to `$SCRATCH/polygon-statement.json`.
Its keys are exactly the `polygon_save_statement` sections the package fills
(`name`, `legend`, `input`, `output`, `scoring`, `notes`) and nothing else;
`name` is plain text with no `\` and no `$`. Then lint it:

```bash
python3 -m tools.cf_statement_lint "$SCRATCH/polygon-statement.json"
```

It must exit 0 before `polygon_save_statement` is called. On exit 1, fix
the field it names and run it again. Fix the JSON, not the package's `.tex`
— the PDF is reviewed and correct. Once it lints clean, the strings go to
the tool unchanged: no edit after the last lint.

**On a re-sync**, rebuild the JSON from the `.tex` every time and save it
again. It is cheap, and a statement that has not changed simply becomes part
of a commit that reports "No changes".

## Phase 4 — checker, validator, generators

`polygon_save_file` takes `path=`, resolved under `POLYGON_MCP_ROOT`, and a
`path=` outside that root is refused by design. The server reads the root from
the environment of the shell that **launched Claude Code**, so if it is unset
the fix is to export it there and restart — exporting it in some other
terminal mid-session changes nothing, because the server process is already
running without it. Pass `content=` inline only for something genuinely small
— a few KB — never as a way around the guard.

**When `$PROBLEM` is not under `path_reads_allowed_under`** (a root of `/tmp`,
say), every `path=` in Phases 4–6 is refused. The one-time fix is to point
`POLYGON_MCP_ROOT` at a directory that contains your problems, then restart
Claude Code. Until then, stage each file under the root for its call and
remove the staging directory when the run ends:

```bash
ROOT="<path_reads_allowed_under, from polygon_whoami>"
STAGE="$(mktemp -d "$ROOT/polygon-upload.XXXXXX")"
cp "<file>" "$STAGE/"      # then call the tool with path="$STAGE/<basename>"
rm -rf "$STAGE"            # once, after the last upload
```

1. **`testlib.h`, first, always** — as `file_type="resource"`,
   `name="testlib.h"`, from the exact file the local pipeline compiled
   against: `$TESTLIB/testlib.h`. Every new Polygon problem ships a stock
   `testlib.h` resource. The package's generators call
   `registerGen(argc, argv, 2)`, which preparing-tests requires and which
   exists only in the fork `bootstrap_testlib.sh` installs. A problem left
   on Polygon's copy fails its verified build, and the error names a
   solution rather than the generator —
   `sol-main.cpp got FL on tests#3 which violates tag(s): solution tag MAIN`,
   or `RJ on tests#4` for a time-limit solution. **FL or RJ on the first
   generated tests of a verified build means this step was skipped.**
   Uploading it replaces Polygon's copy, so validator, checker, generators
   and Polygon's answers all build against the header the matrix was run
   with. The file is ~225 KB, far past what `content=` is for, and it lives
   in the cache, outside the readable root, so it always goes through the
   staging directory above:

   ```bash
   STAGE="${STAGE:-$(mktemp -d "$ROOT/polygon-upload.XXXXXX")}"
   cp "$TESTLIB/testlib.h" "$STAGE/testlib.h"
   # polygon_save_file(problem_id, file_type="resource", name="testlib.h", path="$STAGE/testlib.h")
   ```

2. **Checker.** `checker.kind == "stock"` → `polygon_set_checker(problem_id,
   "std::<checker.name>.cpp")`; the package spells stock names bare (`ncmp`,
   `wcmp`, `rcmp6`) and Polygon spells them `std::ncmp.cpp`. `custom` →
   `polygon_save_file(file_type="source", name=<checker.name>, path=…)`
   first, then `polygon_set_checker` with that same name.
3. **`files/constraints.h`** as `file_type="resource"` — the generated header
   the validator includes. A resource file is placed beside the sources at
   compile time, which is exactly what `#include "constraints.h"` needs.
   Upload it **before** the validator so that compile finds it, and never
   edit the package's own `files/validator.cpp` to work around it.
4. **Validator.** `polygon_save_file(file_type="source",
   name="validator.cpp", path=…)`, then
   `polygon_set_validator(problem_id, "validator.cpp")`.
5. **Generators.** Every `files/gen-*.cpp` as `file_type="source"` under its
   own name. Nothing binds them; the script names them.

## Phase 5 — solutions, with the tags they were measured at

**The model solution goes up first, before any test.** Polygon computes every
test's answer by running the `MA` solution, so `tests/*/*.a` is never
uploaded — those are local evidence, and uploading one would stand a second,
unchecked answer beside the one Polygon derives.

Then every other `solutions/*.cpp`, one
`polygon_save_solution(problem_id, name=<basename>, tag=…, path=…)` apiece,
with the Polygon tag its own `@tag` metadata block maps to:

| `@tag` | Polygon |
|---|---|
| `main` | `MA` |
| `accepted` | `OK` |
| `wrong-answer` | `WA` |
| `time-limit-exceeded` | `TL` |
| `time-limit-exceeded-or-accepted` | `TO` |
| `memory-limit-exceeded` | `ML` |
| `presentation-error` | `PE` |
| `failed` | `RJ` |

The mapping is total over the package's tag set (`scan_solutions.TAGS`) —
never invent a tag, and never promote a measured verdict. A solution that is
correct but only just fits the limit is `TO`, not `OK`: a verified build runs
every solution and fails when `OK` times out. Exactly one solution carries
`MA`; `tools.review_checks` has already guaranteed that.

## Phase 6 — tests, then samples last

Polygon's indices follow the package: groups in `problem.json` subtask
order, `NN.in` in numeric order within each group, after the samples.
**Generated tests go up as script lines, and hand-made tests as manual
uploads of the package's own files.** A script line is the exact `argv` that
produced its `tests/<group>/NN.in`: generators are pure functions of their
command line, so the same invocation reproduces the same bytes forever.

1. **Samples that duplicate a test.** Polygon refuses a second test with the
   same input (`testInput: Test coincides with test #N.`). Check every
   sample against the suite:

   ```bash
   for s in "$PROBLEM"/ex*.in; do
     dup=""; for t in "$PROBLEM"/tests/*/*.in; do cmp -s "$s" "$t" && { dup="$t"; break; }; done
     echo "$(basename "$s") ${dup:-unique}"
   done
   ```

   A **unique** sample is uploaded as its own manual test. A **duplicate** is
   not uploaded at all: the test it equals is marked for the statement
   instead, in step 5. Count the unique samples, `S`. They take indices
   `1..S`, and the package's tests start at `S+1`.

2. **Recover every test's origin:**

   ```bash
   python3 -m tools.recover_test_argv "$PROBLEM" "$SCRATCH/argv" --offset <S>
   ```

   The tool copies the package into `$SCRATCH`, runs `build_tests.sh` there
   with the generators wrapped, and keeps an invocation only if it
   reproduces the original bytes twice. It never writes into `$PROBLEM` and
   never changes what gets uploaded. It writes
   `$SCRATCH/argv/tests-manifest.json`, one entry per test (`index`,
   `group`, `file`, `kind` of `gen` or `manual`, and the generator and args
   for `gen`), and `$SCRATCH/argv/script.txt`, already offset by `S`.
   **Exit 1 is a STOP:** `build_tests.sh` does not reproduce the suite on
   disk, so the package is not what its own script says. Send it back to
   `preparing-tests`, and do not regenerate or patch anything here.
   Exit 0 with `manual` entries is normal.

3. `polygon_save_script(problem_id, "tests", source=<script.txt, verbatim>)`.
   It replaces the script entirely; there is no appending. Every line ends
   in an explicit index, never `> $`, and there are no `#` comment lines,
   which Polygon's script parser rejects.

4. **Hand-made tests**, one call each, for every manifest entry of kind
   `manual`:
   `polygon_save_test(problem_id, "tests", test_index=<index + S>,
   path=<$PROBLEM/<file>>)`. A manual test is a first-class test, not a
   gap: it is the package's own validated file, uploaded byte for byte.

5. **Samples last.** Each unique sample:
   `polygon_save_test(problem_id, "tests", test_index=i, path=<the .in>,
   use_in_statements=true)` for `i` in `1..S`. Each duplicate: mark the
   test it equals, and send nothing else —
   `polygon_save_test(problem_id, "tests", test_index=<that test's index + S>,
   use_in_statements=true)`. Leave `output_for_statements` unset — the shown
   answer is then the one Polygon computes from `MA`, which is the point of
   Phase 5's ordering. Unique samples carry no group and no points.

   Polygon shows statement samples in index order. When a duplicate makes a
   sample appear in a different position than its `exK` number, the
   `notes` field must refer to samples in Polygon's order. Re-save the
   statement if Phase 3 numbered them the vnolymp way.

6. Read back with `polygon_tests(problem_id, no_inputs=true)`, one index
   per line of the manifest plus `S`. Script tests come back
   `manual: false` with a `scriptLine`, and hand-made tests come back
   `manual: true`, at exactly the manifest's indices. `useInStatements` is
   set on the `S` unique samples and on each duplicate's test. Polygon does not document marking a
   script-generated test for the statement, so the readback decides, not
   the call's `ok`. If a duplicate's test flipped to `manual: true` or lost
   its `scriptLine`, repair it before committing:
   - drop that test's line from `script.txt` and save the script again;
   - upload the sample itself as the manual test at that index, with
     `use_in_statements=true`. Its bytes equal the test's, so it is the same
     test;
   - for `oi`, give it that test's group and points in Phase 7;
   - read back again.

**One call at a time.** Tests go up sequentially, never as a parallel
batch. The server paces its requests and backs off on HTTP 429, but calls
fired together against one account still hit Polygon's rate limit.

## Phase 7 — groups and points, `format == "oi"` only

For `format == "icpc"`, skip this phase: groups and points stay disabled and
the problem is scored all-or-nothing.

For `format == "oi"`:

1. `polygon_enable_groups(problem_id, "tests", true)` and
   `polygon_enable_points(problem_id, true)`. Both come first — a test
   cannot carry a group or points until they are on.
2. **One group per subtask, named with the subtask's own id** (`g1`, `g2`, …
   from `problem.json`). Polygon hands the group name to the validator, so
   the validator must recognise the spelling it receives — both `g1` and the
   bare number — and a mismatch does not reliably fail loud; see
   preparing-tests' "Accept the group name Polygon actually sends" for why
   an unmatched `if` with no `else` silently skips the subtask-specific
   bound instead of rejecting the test.
3. **Points first**, one call per test:
   `polygon_save_test(problem_id, "tests", test_index=…, test_points=…)` —
   `test_points` and nothing else. `subtasks[].points` is split across that
   subtask's tests — the manifest entries of that `group`, at Polygon index
   `index + S` — to sum **exactly** to the subtask's points. This is the
   only route to per-test points: neither `problem.setTestGroup` nor
   `problem.saveTestGroup` takes any.
4. **Then the groups**, one call per subtask:
   `polygon_set_test_group(problem_id, "tests", test_group=<subtask id>,
   test_indices=[…])`, with the same manifest indices, `index + S`. It names a group and indices and nothing else, so
   there is no field through which it could disturb a script-generated
   test's input — which is why groups go through it rather than through
   `polygon_save_test`. Groups **after** points, deliberately: this call
   cannot touch points, so a points update that cleared a group is repaired
   here rather than left standing — which the other order would not be. A
   group comes into existence by a test being put into it.
5. Then the policies:
   `polygon_save_test_group(problem_id, "tests", group=<subtask id>,
   points_policy="COMPLETE_GROUP", dependencies=<subtasks[].depends_on>)` —
   only after the tests are in the group, because it edits a group rather
   than creating one.
6. **Read back before committing**, and treat it as a gate, not a glance.
   `polygon_tests(problem_id, no_inputs=true)` — `no_inputs` because a real
   suite's inputs are megabytes and none of this needs them. Every index the
   script produced must still come back with **`manual: false` and its
   `scriptLine`**, and every hand-made test with `manual: true`, alongside
   the `group` and `points` you set. Those two
   fields are the discriminator: a generated test that an edit clobbered
   into a manual *add* flips `manual` to true and loses its `scriptLine`, and
   nothing later in the run would say so. If one has, **stop** — do not
   commit over it. Then `polygon_test_groups(problem_id, "tests")`: every
   group present with the dependencies `problem.json` declares, points
   summing to 100 across the ladder.

## Phase 8 — commit

`polygon_commit(problem_id, minor_changes=<not polygon.notify_on_commit>,
message="<problem name>: uploaded from competitive-programming")`. Note the
inversion: `notify_on_commit = false` means `minor_changes = true`, which is
how Polygon commits without mailing the problem's other authors.

**Read `committed`, not `ok`.** `ok: true` only means the call went through:
`committed: false` with the message "No changes" means nothing was saved, and
`conflict_occurred: true` means the working copy fell behind — then
`polygon_update_working_copy` and commit again.

After a commit that really happened — and only then — stamp the record. The
next re-sync compares file mtimes against `committed_at`, so a timestamp
written for a commit that did not happen skips files that had in fact
changed:

```bash
python3 -c "import sys;from dataclasses import replace;from tools.polygon_ref import load,save;save(sys.argv[1],replace(load(sys.argv[1]),committed_at=sys.argv[2]))" \
  "$PROBLEM" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

Then `polygon_build_package(problem_id, verify=true)` and poll
`polygon_packages` until `state` leaves `PENDING`/`RUNNING`. `verify=true` is
what makes the Phase 5 tags mean something — it runs every solution on every
test and checks each claim holds. A build takes minutes: **keep polling
inside this run** until the state is final. Do not end the turn with "check
again later" — a run that stops there leaves an upload nobody verified. A
`FAILED` package's `comment` says why; report it rather than committing
again over the top, and read an FL or RJ on the first generated tests as
Phase 4 step 1.

The API cannot show how the statement rendered. After a `READY` build, give
the user the problem's URL and ask them to open the statement preview once.
The linter catches the constructs known to break, not every one.

## Phase 9 — access

When `polygon.grant_codeforces_read` is true:
`polygon_set_access(problem_id, "codeforces", "READ")` — this is what makes
the problem importable into a Codeforces contest. It takes effect
immediately and needs no commit.

Report exactly what came back; `polygon_accesses(problem_id)` confirms it.
The method needs **direct** WRITE or OWNER access on the problem — access
held through a user group is not enough — so a refusal here is about who the
key belongs to, not about the package. Say that and stop; do not describe a
sequence of clicks in a web UI you cannot see. When the preference is false,
say the step was skipped and which preference skipped it.

## Several problems, and contests

**Several problems at once.** One agent per problem is fine. Each agent
works on its own package and its own `polygon.json`, and none of them
touches another's problem. Every agent still shares one account's rate
limit, so each one uploads its tests sequentially (Phase 6). An agent that
stops part-way leaves a problem with a `polygon.json` and no
`committed_at`. The next run finds that record in Phase 0 and re-syncs it,
rather than creating a second problem.

**Contests are not part of this skill.** The server wraps no contest method,
and the public Polygon API has none that creates a contest or adds problems
to one, as far as this skill knows. When
the user asks for a contest, finish uploading the problems. Report each
Polygon name, id and URL, and say the contest itself is assembled by hand
in Polygon's web UI.

## Done

- [ ] Both preconditions run fresh in this conversation: `tools.package_status`
      printed `complete`, `tools.review_checks` exited 0
- [ ] `$PROBLEM/polygon.json` carries the id and owner the server reported
      and the `edit-start?problemId=<id>` URL, and `polygon_ref.load` reads
      it back
- [ ] Statement uploaded in the `.tex`'s language (asked first if it differs
      from the preference), fields linted clean by `tools.cf_statement_lint`
      before they were saved, and the user asked to open the preview
- [ ] The package's `testlib.h` uploaded as a resource before any source;
      the staging directory under the server's root removed afterwards
- [ ] Limits, statement, checker, validator, generators and every solution
      uploaded, each solution tagged from its own `@tag`, exactly one `MA`
- [ ] Tests follow `tools.recover_test_argv`'s manifest: script lines for
      `gen`, manual uploads for `manual`; unique samples at `1..S` and
      duplicate samples marked on the test they equal, all with no uploaded
      answers
- [ ] Groups and points enabled iff `format == "oi"`, one group per subtask
      id, points summing to 100
- [ ] `polygon_commit` reported `committed: true`; `committed_at` recorded in
      `polygon.json`; the verified build reached `READY`
- [ ] The access step reported: granted, or skipped with the preference that
      skipped it, or refused with the reason
