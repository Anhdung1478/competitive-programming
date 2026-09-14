# Changelog

All notable changes to this plugin are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `LICENSE` (MIT). The plugin and marketplace manifests and the MCP server's `pyproject.toml` now declare it too.
- `NOTICE`, crediting the space-dark editorial theme to nudetiger.

### Changed

- The Polygon MCP server retries HTTP 429 with backoff, honouring
  `Retry-After`. `polygon_whoami` reports environment variables that reached
  the server as literal `${NAME}` placeholders, which means they were unset
  when Claude Code launched.

## [0.7.0] - 2026-09-06

Nine pull requests (#11-#19) adopted ideas from the
[nudetiger/competitive-programming-problem-preparer](https://github.com/nudetiger/competitive-programming-problem-preparer)
fork, re-expressed in this repo's own prose and tooling. PR #10 is not part
of that series; it fixes how memory-limit verdicts are judged.

### Added

- **`writing-editorials` skill** (#15): writes a standalone HTML editorial for
  a solved problem into `$PROBLEM/editorial/editorial.html`, or for a whole
  contest into `$CONTEST/editorial/editorial.html` with one section per
  problem. Opt-in: it runs only when you explicitly ask for an editorial,
  writeup, or tutorial page; it never runs at the end of `creating-problems`.
  Try it: invoke `competitive-programming:writing-editorials`.
- **`uploading-to-polygon` skill** (#19): publishes a reviewed package to
  Codeforces Polygon through the bundled `polygon` MCP server. It uploads the
  problem, limits, statement, sources, solutions, script and tests, groups
  and points, then commits and grants coordinators read access. Opt-in: it
  runs only when asked, never automatically. Try it: invoke
  `competitive-programming:uploading-to-polygon`.
- **Bundled `polygon` MCP server** (#18): our own code wrapping the
  Codeforces Polygon API, not a third-party package, so no third-party server
  ever holds your Polygon credentials. Needs `POLYGON_API_KEY` and
  `POLYGON_API_SECRET` in the server's environment. Set `POLYGON_MCP_ROOT`
  too if a tool needs to read a local file; without it, any local path is
  refused. See `mcp-server/README.md` and `mcp-server/.env.example` for setup.
- **`preferences.toml` + `tools/preferences.py`** (#16): a user-editable
  defaults file for the judgement calls the setting skills otherwise ask
  about every time. It covers problem format, subtask policy, how many
  files a test group gets, multi-test policy, stress rounds, zoo
  composition, and Polygon defaults. The shipped file lives at the plugin
  root. Override it with `$CP_PREFERENCES` pointing at your own file, or
  drop one at `$XDG_CONFIG_HOME/competitive-programming/preferences.toml`
  (default `~/.config/competitive-programming/preferences.toml`). The first
  file found wins whole. Try it: from the plugin root, run
  `python3 -m tools.preferences` to print the effective config as JSON.
- **`format` field in `problem.json`** (#13): an optional top-level
  `"format": "oi"` or `"format": "icpc"` that records whether a problem scores
  by subtasks or all-or-nothing. If you omit it, it is inferred: `oi` when
  more than one subtask is declared, else `icpc`. Try it: add `"format": "oi"`
  (or `"icpc"`) to a problem's `problem.json`.
- **`preparing-tests` now designs test families from a written doctrine**
  (#14). The new `skills/preparing-tests/references/test-generation.md`
  covers kill policy by format, subtask separation, parameter saturation, a
  brute-kill size table, a shape catalogue, corner cases, and multi-test `T`
  policy. It is read automatically; nothing to invoke separately.
- **The testlib bootstrap now works on Windows** (#12): fetching and caching
  the `testlib.h` checkout is portable stdlib Python
  (`tools/bootstrap_testlib.py`) instead of shell. Try it: set
  `CP_TESTLIB=<dir>` to point at your own `testlib.h` checkout instead of the
  cached clone.

### Changed

- **Multi-test `T` protocol and kill policy by format** (#17): `shaping-problems`
  now records a maximum `T` (test cases per file) as a judged constraint.
  `creating-problems`' zoo expectations also differ by format: every wrong
  solution must fail somewhere under `icpc`. Under `oi`, a solution correct
  through subtask k is expected to pass up to k and fail on stronger groups.
  No new command; this changes what the setting skills ask and expect.
- **Three setter-prose fixes** (#11): `preparing-tests` now tells you to make
  a validator accept both the `g1` and the bare-number spelling of a group,
  and to keep the package's Polygon group names identical to
  `problem.json`'s. `writing-statements` keeps sample explanations from
  arguing why an alternative is worse: that is editorial content leaking
  into the statement. `validating-solutions` requires each new zoo entry to
  be the strongest wrong solution of its kind, not a weaker duplicate. Try
  it: read the validator section in `skills/preparing-tests/SKILL.md` the
  next time you write a group check, and the zoo rules in
  `skills/validating-solutions/SKILL.md` before adding a wrong solution.

### Fixed

- **Memory-limit verdicts now judged from peak RSS** (#10): the old cgroup
  memory counter also charges dirty page-cache pages. On cgroup v2, a
  solution that wrote output faster than the disk flusher could drain it was
  being OOM-killed even with a tiny real memory footprint. That produced a
  false ML verdict. `run_matrix` now judges ML from isolate's `max-rss`
  (which excludes page cache) or an actual cgroup OOM kill, and sizes the
  cgroup cap with slack for permitted output size. No user action needed;
  existing invocations benefit automatically.
- A flaky `test_package_status` exit-code test that depended on all evidence
  files landing in the same mtime tick (#10).
- Example problem citations that implied a `flight` package on disk
  retargeted to `tools/tests/fixtures/mini` or reworded as illustrative, in
  `shaping-problems`, `preparing-tests`, `reviewing-problems` and
  `validating-solutions` (#10).

## [0.6.0]

The version number was set to `0.6.0` at #3 (2026-08-01), which added the
problem-setting pipeline: testlib tooling, sandboxed verification, and the
first two setter skills. PRs #4 and #5 (both 2026-08-01) shipped the
remaining stage-2 setting skills and file-based IO support with the
writing-statements routing table. PRs #6 and #7 (both 2026-08-09) made the
invocation matrix run in parallel and added crash/stale-evidence guards. PR
#9 (2026-09-04) synced the docs with the code and guarded the two places they
had drifted. None of these bumped the version, so `0.6.0` covers all of them.
