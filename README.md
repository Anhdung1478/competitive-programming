# competitive-programming

Claude Code plugin for competitive programming: eleven skills — two for solving
(one problem, one whole contest), seven for setting one (shaping the
constraints, test data, solution validation, statement, package review,
end-to-end orchestration, and the opt-in upload to Polygon), and two optional
skills detached from the pipeline: one that explains a finished problem to the
contestants who could not solve it, and one that estimates what that problem
would be rated — plus two bundled MCP servers, one for Codeforces and one for
Polygon. This repository is also a **marketplace**, so it can be used in place
or installed on another machine.

| Component | Invoked as | What it does |
|---|---|---|
| Skill `solving-problems` | `competitive-programming:solving-problems` | Algorithm design and C++ for one problem on a stdin/stdout judge — constraints → complexity budget → design → edge cases → clean implementation, with stress testing against a brute-force oracle |
| Skill `running-contests` | `competitive-programming:running-contests` | Drives a whole contest on any judge: binds to whatever judge MCP is installed, pulls the problem set, orders it, delegates each problem to `solving-problems`, submits, reads verdicts, and keeps going until every problem is solved |
| Skill `shaping-problems` | `competitive-programming:shaping-problems` | Turns a problem idea into numbers: a novelty check, the intended difficulty, the N that separates the intended solution from the naive one, and a subtask ladder that pays for real partial insight |
| Skill `preparing-tests` | `competitive-programming:preparing-tests` | Builds the test-data contract for a problem being set: checker, validator, generators (random / max-size / boundary / structured-adversarial / hand-written), and sample selection, driven by testlib and `tools/gen_constraints_header.py` / `tools/drift_check.py` |
| Skill `validating-solutions` | `competitive-programming:validating-solutions` | Attacks a problem's test suite with a zoo of deliberately-wrong solutions plus alternative and exhaustive-arbiter `accepted` solutions, runs the invocation matrix (`tools/run_matrix.py`) under `ioi/isolate`, and reports holes and mismatches |
| Skill `writing-statements` | `competitive-programming:writing-statements` | Authors, translates, and reviews problem statements for the vnolymp LaTeX template — the Vietnamese statement package for problems prepared on Polygon |
| Skill `reviewing-problems` | `competitive-programming:reviewing-problems` | Audits a finished problem package before it ships: mechanical checks (drift, unreached bounds, holes, checker/validator disagreement) via `tools/review_checks.py`, plus judgement checks (ambiguity, assumed definitions, unproven invariants) run fresh from the statement, recorded to `flags.json` |
| Skill `creating-problems` | `competitive-programming:creating-problems` | The umbrella over the other five setting skills: drives a problem from an idea, finished or half-formed, to a Polygon-ready package end to end, gated phase by phase with machine-readable evidence from `tools/package_status.py` |
| Skill `writing-editorials` | `competitive-programming:writing-editorials` | Writes a standalone HTML editorial for a solved problem — lore-stripped restatement, the derivation that reaches the intended solution, time complexity — into `$PROBLEM/editorial/editorial.html`. Opt-in and detached from the pipeline: it runs only when a conversation explicitly asks for one |
| Skill `calculating-difficulties` | `competitive-programming:calculating-difficulties` | Estimates what a finished, validated problem would be rated on the Codeforces scale, into `$PROBLEM/difficulty.md`: a prerequisite floor, placement against real rated anchors, an era correction that discounts an old anchor's label onto today's scale, capped adjustments, and a confidence line. Gated on the invocation matrix having run clean; with no such evidence it records `not estimable` rather than guessing. Blind-calibrated, and it emits a `± 300` interval rather than a bare point estimate. Opt-in and detached, and the source `writing-editorials` reads its `Difficulty` field from |
| Skill `uploading-to-polygon` | `competitive-programming:uploading-to-polygon` | Publishes a finished, reviewed package to Codeforces Polygon over the bundled `polygon` server: create, limits, statement, sources, solutions with their measured tags, the generator script and samples, subtask groups and points, commit and verified build, then read access for the coordinators. Opt-in — it runs only when asked for, never off the end of `creating-problems` |
| MCP server `codeforces` | tools `cf_*` | Browse contest problems, read statements, submit solutions, poll verdicts |
| MCP server `polygon` | tools `polygon_*` | Upload a finished package to Polygon: statement and resources, sources, solutions with their expected verdicts, script and manual tests, groups and points, commit and build, then grant a coordinator access to it |

## Layout

```
competitive-programming/
├── .claude-plugin/
│   ├── plugin.json           # plugin manifest ("skills": ["./skills"])
│   └── marketplace.json      # lets this repo be installed as a marketplace
├── .mcp.json                 # registers the bundled codeforces and polygon servers
├── preferences.toml          # standing answers the setting skills read first
├── skills/
│   ├── solving-problems/SKILL.md  (+ references/black-magic.md)
│   ├── running-contests/SKILL.md   (+ references/judges.md)
│   ├── shaping-problems/SKILL.md
│   ├── preparing-tests/SKILL.md  (+ references/test-generation.md)
│   ├── validating-solutions/SKILL.md
│   ├── writing-statements/SKILL.md
│   ├── reviewing-problems/SKILL.md
│   ├── creating-problems/SKILL.md
│   ├── uploading-to-polygon/SKILL.md (+ references/polygon-tools.md,
│   │                                    references/polygon-statement-markup.md)
│   ├── writing-editorials/SKILL.md  (+ references/vi-glossary.md,
│   │                                    references/themes/space-dark.html)
│   └── calculating-difficulties/SKILL.md  (+ references/tag-floors.md,
│                                             references/anchors.md,
│                                             calibration/)
├── tools/                    # Python pipeline the setting skills drive
│   ├── problem_meta.py  flags.py  gen_constraints_header.py  drift_check.py
│   ├── scan_solutions.py  matrix_core.py  run_matrix.py  box_pool.py
│   ├── package_status.py  review_checks.py  bootstrap_testlib.py  preferences.py
│   ├── polygon_ref.py          # polygon.json: which Polygon problem a package owns
│   ├── cf_statement_lint.py    # rejects TeX the Codeforces HTML statement renderer breaks on
│   ├── recover_test_argv.py    # proves each test's generator argv, for the Polygon script
│   ├── bootstrap_testlib.sh   # thin wrapper: cd's to the plugin root, execs the .py
│   └── tests/                # unittest suite, see Checks below
└── mcp-server/               # both MCP servers (one Python project, two scripts)
    ├── pyproject.toml  uv.lock
    ├── src/cf_mcp/           # the Codeforces server, launched as cf-mcp
    ├── src/polygon_mcp/      # the Polygon server, launched as polygon-mcp
    └── tests/
```

## Setup

**Prerequisite:** [`uv`](https://docs.astral.sh/uv/) — both servers are launched
with `uvx`, which builds them from `mcp-server/` and resolves dependencies on its
own, so there is no virtualenv to manage:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Codeforces credentials.** Codeforces guards its login with a Cloudflare
challenge, so the server authenticates with a session cookie rather than a
password. Sign in at codeforces.com, then DevTools → Application → Cookies →
copy `JSESSIONID`. Export both variables in the shell that launches Claude Code
(`.mcp.json` reads them via `${…}`, so **no secret is ever stored in this
repo**):

```bash
export CODEFORCES_HANDLE=your_handle
export CODEFORCES_COOKIE=JSESSIONID=your_cookie_value
```

**Polygon credentials.** Polygon has a real API, so no cookie is involved:
generate a key pair at Polygon → Settings → API keys and export both halves.
`POLYGON_MCP_ROOT` is the one directory the Polygon server may read a file from
when a tool is called with `path=` instead of inline content; leave it unset and
every path is refused, which is the safe default:

```bash
export POLYGON_API_KEY=your_key
export POLYGON_API_SECRET=your_secret
export POLYGON_MCP_ROOT=/path/to/the/problem/you/are/uploading
```

Every other variable either server reads — Codeforces API key, default language,
state dir; Polygon base URL, timeout, pacing — is documented in
[`mcp-server/README.md`](mcp-server/README.md), which owns those tables;
`mcp-server/.env.example` mirrors them as a fill-in template.

**Prerequisite:** [`ioi/isolate`](https://github.com/ioi/isolate) —
`tools/run_matrix.py` runs every *solution* sandboxed under isolate, never a bare
`fork`/`exec`, and refuses to start rather than falling back to something
unsandboxed. Generators, validators and checkers are not sandboxed; nothing in
`tools/` executes a generator at all. This is a one-time machine setup, not a
per-problem one:

```bash
sudo apt install build-essential pkg-config libcap-dev libseccomp-dev libsystemd-dev
git clone https://github.com/ioi/isolate.git && cd isolate
make && sudo make install
```

Then create the system user isolate expects, register its subuid/subgid range, and
start the cgroup keeper daemon:

```bash
sudo useradd -r isolate   # if it doesn't already exist
echo "isolate:200000:65536" | sudo tee -a /etc/subuid /etc/subgid
sudo systemctl enable --now isolate.service
```

Verify with `isolate --version`; if `--init` still fails, the likely cause is a
missing subuid/subgid range or `isolate.service` not running — both above.

**Both IO modes are supported.** A problem's `problem.json` sets
`io.input` / `io.output` either to the sentinels `"stdin"` / `"stdout"` or to a
pair of bare filenames (`flight.inp` / `flight.out`, the shape most VOI-style
packages use); anything else — a path separator, a dot-segment, the two names
being equal — is refused at load. In file-IO mode `run_matrix.py` stages the
test into the sandbox's one writable mount under `io.input`, `--chdir`s there,
and reads the answer back from `io.output`. **Generators and validators are
unaffected**: they are stdin/stdout testlib tools in both modes, and nothing in
`tools/` executes either one. **The checker is unaffected too** — testlib
checkers already take three file paths (`checker <input> <output> <answer>`),
which is what `run_matrix.py` has always handed them. The one genuinely new
outcome is the verdict `NO_OUTPUT`: a solution that exits cleanly and never
creates `io.output`, almost always because it wrote the wrong filename. Like
`FAIL`, it is discovered by the harness and can never be declared in a
solution's `@expect`.

**Preferences.** The judgement calls the setting pipeline would otherwise ask
about on every problem — OI or ICPC, who proposes the subtask ladder, how many
files a test group gets, how many stress rounds — have standing answers in
`preferences.toml` at the repository root. Six of the seven setting skills
read it before asking anything it already answers — writing-statements has
no Bootstrap block and does not read the file; a value of `"ask"` means the
file declines to decide and the question is put to you. One file is used **whole**,
with no layering: `$CP_PREFERENCES` if set (an explicit path, and an error if
it does not load), else
`$XDG_CONFIG_HOME/competitive-programming/preferences.toml` (default
`~/.config/…`), else the shipped file. So a copy you put in your config
directory has to keep every key. `tools/preferences.py` is the only parser —
an unknown section or key, a wrong type, or a value outside the closed set is
an error naming the file, the `section.key` and what was allowed, rather than
a silent default:

```bash
python3 -m tools.preferences          # the effective config as JSON, plus "source"
```

## Installing

See `CHANGELOG.md` for what changed since the last version you had.

**Same machine** — clone into `~/.claude/skills/`. Anything there with a
`.claude-plugin/plugin.json` auto-loads as `<name>@skills-dir`; no install step:

```bash
git clone <repo-url> ~/.claude/skills/competitive-programming
# then, in Claude Code:  /reload-plugins
```

**Elsewhere** — install it as a marketplace:

```
/plugin marketplace add <repo-url>
/plugin install competitive-programming@competitive-programming
```

If you previously registered a `codeforces` server by hand in `~/.claude.json`,
remove that entry — the plugin now provides it, and two definitions of the same
server name will collide.

## How skill discovery works here (read before adding skills)

Claude Code discovers personal skills at exactly **`~/.claude/skills/<skill>/SKILL.md`**
— one level. A bare subfolder is *not* scanned: a skill at
`~/.claude/skills/<category>/<skill>/SKILL.md` returns `Unknown skill`.

Grouping into a folder works only because that folder is a **plugin**: the
`.claude-plugin/plugin.json` here is what makes `skills/*` visible, and it is
also what supplies the `competitive-programming:` namespace.

To add a skill, create `skills/<new-skill>/SKILL.md` with frontmatter whose `name:`
matches the directory. Do not nest deeper, and do not remove the manifest.

## Checks

Each line names its own working directory: the tools suite imports `tools.*`
and only resolves from the repository root, and the previous version of this
block put it after a `cd mcp-server`, where it fails with `ImportError: Start
directory is not importable`.

```bash
cd <this repo>
claude plugin validate . --strict                 # manifests
claude plugin details competitive-programming     # inventory: 11 skills, 2 MCP servers

python3 -m unittest discover -s tools/tests -t . -v    # tools suite (repo root)
(cd mcp-server && uv run --extra dev pytest -q)        # server suite (subshell)

# end-to-end: each server should answer an MCP handshake
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}' \
  | uvx --from ./mcp-server cf-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}' \
  | uvx --from ./mcp-server polygon-mcp
```

**The tools suite is parallel-safe.** `run_matrix.py` leases every isolate
box id from a per-user `flock` pool (`/run/user/<uid>/run_matrix-boxes`,
falling back to `/tmp/run_matrix-boxes-<uid>`, overridable with
`$RUN_MATRIX_BOX_LOCK_DIR`), so several invocations — or several
`dispatching-parallel-agents` subagents, or two copies of the test suite —
can run at once without colliding. That guarantee is about correctness —
no two of this user's invocations can land on the same box or clobber
each other's staged output — not about timing isolation: a sibling invocation's
sandboxes still compete for the same CPUs while yours run. Pass 2 also runs
on that same pool, so the pool size is simultaneously the box allocator and
this user's CPU
admission control. Measured, not projected: `goldenseed` (13 solutions, 42
graded tests, 546 results) ran in 182.4s serial vs. 65.4s at 4 workers — 2.79x —
with verdicts, holes, mismatches, and TL/kill limits identical between the
two runs, and 1 of 546 results re-timed serially.

The pool is per-user, and that bound is worth knowing: two *different*
users running `run_matrix` on the same machine can still land on the same
isolate box id. That collision is caught loudly by isolate's own lock — the
driver names it and stops, rather than reporting a wrong verdict — but it
is not prevented.

`$RUN_MATRIX_BOX_POOL` sets the pool size; it defaults to half the CPUs.
That default is a correctness bound, not a throughput setting: CPU time
inflates under contention (measured on an 8-thread box, 1.15–1.21x at 4
concurrent sandboxes and up to 1.92x at 8), and the driver's ambiguity rule
is only sound while inflation stays below 2x. `pool_size()` accepts any
value up to isolate's own box-id ceiling with no check against the core
count, so raising it past `nproc` is an operator hazard, not a safety net —
nothing bounds wall-time inflation the way `CONTENTION_BOUND` bounds CPU
time, so oversubscription is where wall-clock kills start showing up. The
same is true of memory: each sandbox's cgroup is capped via `--cg-mem` at
the problem's `memory_mb` plus a fixed 256 MB output allowance (on cgroup
v2 a solution's dirty output pages are charged to its cgroup until written
back, so the cap must leave room for them; ML itself is judged from the
child's peak RSS against `memory_mb`), but `pool_size()` sandboxes run at
once, so this driver's own peak memory footprint from live sandboxes is
`workers × (memory_mb + 256 MB)`, with nothing here checking that sum
against the machine's physical RAM — raising `$RUN_MATRIX_BOX_POOL`
multiplies memory pressure exactly as it multiplies CPU pressure. Raise
it only on a machine with the resources to match, and set it to `1` for a
fully quiesced authoritative run *provided this is the only `run_matrix`
invocation on the machine* — a sibling invocation running at
`RUN_MATRIX_BOX_POOL=4` will happily sweep the other three lease ids while
yours holds the one it was given, so `POOL=1` only quiesces the machine
when nothing else is drawing from the same pool.

Pass 1 — the model solution's timings, from which TL is derived — is
always serial regardless of the pool size *within this invocation*: this
process never runs more than one pass-1 timing at a time. That does not
mean the core it runs on is otherwise idle — a sibling `run_matrix`
invocation can still be running its own boxes concurrently and inflating
this process's measured `t_main`. That is the safe direction to be wrong
in, though: an inflated TL makes a genuinely-too-slow solution measure
under a looser limit and pass, and `compare()` records exactly that
pattern — `@expect TL` met by an `OK` result — as a **hole**. It is a
false alarm worth double-checking (the solution may not actually be too
slow; contention noise can produce the same signature), not a silent
failure: it lands in `invocation.json`'s `holes` list and trips exit code
1, so it gets looked at rather than passing unseen.

The tools suite **fails** rather than skips when `g++`, `isolate`, or the
testlib cache is missing: `run_matrix.py` is the one module with no fallback
runner, so gating its tests on the presence of that same dependency meant a
fresh clone printed a green `OK` over a driver it had never executed. Set
`CP_ALLOW_SANDBOX_SKIP=1` to opt back into skipping them.

That testlib cache is populated by `tools/bootstrap_testlib.sh`, which every
skill's Bootstrap block and the tools suite itself shell out to. It clones or
refreshes `qhhoj/testlib` into `$XDG_CACHE_HOME/testlib` (`~/.cache/testlib`
if unset) and prints the path; set `CP_TESTLIB` to an existing directory
containing `testlib.h` to skip that entirely — no network, no `git` needed.
`python3 -m tools.bootstrap_testlib` is the portable entry point that
actually does the work; the `.sh` is a thin `cd`-then-`exec` wrapper around
it, kept so every existing caller's `bash tools/bootstrap_testlib.sh` keeps
working unchanged.

After editing a skill or `.mcp.json`, run `/reload-plugins` (or start a new session).

> **Note on the `mcp` pin.** `pyproject.toml` requires `mcp>=1.2,<2`. Both servers
> use `mcp.server.fastmcp`, which 2.0 removed — an unpinned `>=1.2.0` resolves to
> 2.0 and fails at import. Keep the upper bound until they are ported.

> **Note on `flags.json.lock`.** `tools/flags.py` takes an advisory `flock` on a
> separate lock file beside every problem package's `flags.json`, so concurrent
> writers (several `dispatching-parallel-agents` subagents appending flags at once)
> don't race each other's read-modify-write. That lock file — `flags.json.lock` —
> is never unlinked: `flags.json` itself is replaced with `os.replace` on every
> write, so a lock held on it would be a lock on an unlinked inode the moment the
> first writer finished, and `flock` is released by `os.close` (or process death)
> regardless of whether the file is ever removed. It is left on disk deliberately
> rather than cleaned up, which means it is a **permanent** byproduct of running
> this pipeline. Problem repositories (e.g. the one `creating-problems` and its
> siblings write packages into) should gitignore `flags.json.lock`; this repo
> itself never creates one, since no problem package lives here.

> **Note on `polygon.json`.** `uploading-to-polygon` records which Polygon
> problem a package owns in `polygon.json` at the package root — id, owner, URL
> and the timestamp of the last revision it committed, read and written by
> `tools/polygon_ref.py`. Unlike `flags.json.lock` it belongs in the problem
> repository's history: **commit it, do not gitignore it.** It is the only
> record of which Polygon problem a package is, and losing it makes the next
> upload look like a first one. It deliberately is *not* a key in
> `problem.json`: that file is matrix evidence (`tools/package_status.py` walks
> it to decide whether `invocation.json` has gone stale), so a record written
> into it would fail the very gates the upload skill has to pass before
> writing it.

## Author

LamTer <lamtercqh@gmail.com>

## License

MIT; see `LICENSE`. `NOTICE` credits the space-dark editorial theme.
