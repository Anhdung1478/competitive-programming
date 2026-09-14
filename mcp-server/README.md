# Two MCP servers: `cf-mcp` for Codeforces, `polygon-mcp` for Polygon

One Python project, two console scripts, two independent servers. They share
nothing but the packaging: separate credentials, separate transports, separate
tool namespaces (`cf_*` and `polygon_*`). Read [the Polygon
section](#polygon-mcp--a-polygon-mcp-server) for the second one.

## `cf-mcp` — a Codeforces MCP server

Gives an MCP client (Claude Code, Claude Desktop, …) four things:

1. **Get all problems from a contest** — `cf_list_contest_problems`
2. **Read a problem statement** — `cf_get_problem_statement`
3. **Submit a solution** — `cf_submit_solution`
4. **Read submission status** — `cf_get_submission_status` / `cf_wait_for_verdict`

Codeforces only offers a read-only public API, and it covers none of the
submitting or statement text. So this server uses the API where it exists
(contest metadata, problem lists, verdicts) and drives the website for the rest
(statements, submitting, live-contest status), including the anti-bot `RCPC`
challenge and the `csrf_token` handling that requires.

## Install

Nothing to install by hand. The plugin's `.mcp.json` launches the server with
[`uvx`](https://docs.astral.sh/uv/), which builds it from this directory and
resolves its dependencies on its own:

```bash
uvx --from /path/to/competitive-programming/mcp-server cf-mcp
```

That is also the standalone command, for any MCP client outside the plugin.

## Configure

**Reading contests, statements and public submissions needs no credentials.**
Submitting and reading your own submissions does.

### Authentication: use a session cookie, not a password

Codeforces puts `/enter` behind a Cloudflare browser challenge, so scripted
password login cannot work from a plain HTTP client — verified against the live
site, which answers `403 "Just a moment..."` no matter how browser-like the
request headers are. Every other endpoint (`/contest/…/submit`,
`/contest/…/my`, statements) is *not* challenged, so an existing session cookie
is all that is needed.

To get one:

1. Sign in at <https://codeforces.com> in your browser.
2. Open DevTools → **Application** (Chrome) or **Storage** (Firefox) → Cookies →
   `https://codeforces.com`.
3. Copy the value of **`JSESSIONID`**.
4. Set `CODEFORCES_COOKIE=JSESSIONID=<that value>`.

The cookie is long-lived if you ticked "remember me", but it does expire —
when it does, `cf_whoami` reports `logged_in: false` and you repeat the steps.

| Variable | Required for | Notes |
| --- | --- | --- |
| `CODEFORCES_COOKIE` | submitting, own submissions | `JSESSIONID=<value>`; a bare value works too |
| `CODEFORCES_HANDLE` | recommended | your handle; used for `user.status` lookups |
| `CODEFORCES_PASSWORD` | optional | best-effort login, normally blocked by Cloudflare |
| `CODEFORCES_API_KEY` | private/running-contest API reads | from <https://codeforces.com/settings/api> |
| `CODEFORCES_API_SECRET` | as above | |
| `CF_MCP_DEFAULT_LANGUAGE` | optional | default `GNU G++23` |
| `CF_MCP_STATE_DIR` | optional | cookie cache, default `~/.cache/cf-mcp` |
| `CF_MCP_TIMEOUT` | optional | HTTP timeout in seconds, default `30` |

The five `CODEFORCES_*` names also answer to a `CF_*` shorthand (`CF_HANDLE`,
`CF_PASSWORD`, `CF_COOKIE`, `CF_API_KEY`, `CF_API_SECRET`), and the cookie to
`CODEFORCES_JSESSIONID`; the primary names above are the ones to use in new
config.

The session is cached (mode `0600`) under the state dir, so the server is not
re-authenticating on every call.

### Register with Claude Code

Inside the plugin there is nothing to register: `.mcp.json` at the repository
root already declares the server, reading both variables from the environment
of the shell that launches Claude Code. Registering by hand is only for using
the server outside the plugin — and if you did register one by hand earlier,
remove it, or the two definitions of `codeforces` collide.

```bash
claude mcp add codeforces \
  --env CODEFORCES_HANDLE=your_handle \
  --env CODEFORCES_COOKIE=JSESSIONID=your_cookie_value \
  -- uvx --from /path/to/competitive-programming/mcp-server cf-mcp
```

Or in `claude_desktop_config.json` / `.mcp.json`:

```json
{
  "mcpServers": {
    "codeforces": {
      "command": "uvx",
      "args": ["--from", "/path/to/competitive-programming/mcp-server", "cf-mcp"],
      "env": {
        "CODEFORCES_HANDLE": "your_handle",
        "CODEFORCES_COOKIE": "JSESSIONID=your_cookie_value"
      }
    }
  }
}
```

## Tools

### `cf_whoami()`
Which account the server is configured for, how it authenticates (cookie or
password), and whether the login actually works right now — `logged_in` goes
`false` when the cookie has expired. Call it first when a submit fails.

### `cf_list_contest_problems(contest_id, gym=False, group_id="")`
Contest metadata plus every problem's index, name, rating, tags and points.
Uses the standings API for public contests, and falls back to scraping the
contest page for gyms, group contests and contests that are still running.

### `cf_get_problem_statement(contest_id, index, gym=False, group_id="")`
Full statement as Markdown (math normalised from `$$$x$$$` to `$x$`), time and
memory limits, and every sample test as a separate `{input, output}` pair ready
to pipe into a local run. Also returns `sections` — the statement's titled
blocks (Input, Output, Interaction, Scoring, Note…) in page order — and
`interactive`, true when the problem talks to the judge instead of reading a
fixed input; when it is, flush after every write and treat the sample as a
dialogue transcript, not a runnable test file.

### `cf_list_languages(contest_id, gym=False, group_id="")`
The exact `programTypeId` values that contest's submit form offers. Language
ids change over time, so this reads them live rather than trusting a table.

### `cf_submit_solution(contest_id, index, source_code|source_file, language, gym=False, group_id="", wait_for_verdict=True)`
Submits, then polls until judged. `language` takes an id (`"89"`) or a name
fragment (`"GNU G++23"`, `"Python 3"`). Real submissions against your account.

### `cf_get_submission_status(contest_id=, submission_id=, handle=, count=10, group_id="")`
Verdict, failing test number, time and memory. Reads `/contest/<id>/my` when a
contest is given (works mid-contest), otherwise the public `user.status` API.

### `cf_wait_for_verdict(submission_id, contest_id=, timeout_seconds=120, group_id="")`
Polls a pending submission with backoff until the judge finishes.

Every tool returns `{"ok": false, "error": "..."}` rather than raising, so the
model can read the failure and correct itself.

### Private group contests

Contests inside a group live at
`https://codeforces.com/group/<group_id>/contest/<contest_id>` and are invisible
to the public API — `contest.standings` reports nothing for them regardless of
credentials. Pass the group code from that URL as `group_id` to any tool above
and it scrapes the group pages instead:

```
cf_list_contest_problems(705790, group_id="434yrzK1nB")
cf_get_problem_statement(705790, "A", group_id="434yrzK1nB")
```

This requires being signed in as a member of the group, so `CODEFORCES_COOKIE`
must be set even for reads that are anonymous on the public site. `group_id`
takes precedence over `gym`.

## Typical agent loop

```
cf_list_contest_problems(2000)          → pick problem C
cf_get_problem_statement(2000, "C")     → statement + samples to test against
… write and test a solution locally …
cf_submit_solution(2000, "C", source_file="sol.cpp", language="GNU G++23")
                                        → submits, polls, returns the verdict
```

## Tests

```bash
uv run --extra dev pytest -q
```

148 tests, no network required — 56 for `cf-mcp` and 92 for `polygon-mcp`. On
the Codeforces side: AES against the NIST vectors, statement and status-table
parsing, language resolution, and the whole submit flow against a fake
Codeforces. On the Polygon side, see [its own test notes](#tests-1).

## Implementation notes

Things that are non-obvious about Codeforces and are handled here:

- **Group contests bypass the API entirely.** Every `group_id` call is a page
  scrape against the signed-in session, so it breaks if Codeforces changes its
  markup — unlike the API paths, which are contractual.
- **Standings API is picky.** `contest.standings` only serves non-gym contests
  to anonymous requests carrying *no* extra parameters, so the problem list is
  fetched with a bare query and falls back to scraping for gyms.
- **Unclosed `<tr>`.** Contest tables emit `<tr>` with no `</tr>`, so an HTML
  parser nests every row inside the previous one. Row cells are read with
  `recursive=False` or each problem reports the *last* row's solved count.
- **Two sample-test markups.** Newer problems wrap each sample line in a
  `<div class="test-example-line">`; older ones use plain text in the `<pre>`.
- **Verdicts need the failing test number.** The API reports `passedTestCount`,
  so "Wrong answer" becomes "Wrong answer on test 4".
- **Submission confirmation.** The newest submission id is recorded *before*
  POSTing, and the result must be strictly newer — otherwise a silently dropped
  submission would look like a success.
- Submitting identical source twice is rejected by Codeforces ("You have
  submitted exactly the same code before"); that error is passed through.
- Polling backs off from 2s to 10s, to be considerate to the judge.

---

# `polygon-mcp` — a Polygon MCP server

The other half of the loop. Codeforces is where problems are *solved*;
[Polygon](https://polygon.codeforces.com) is where they are *prepared*, and it
has a real API — no cookies, no scraping, no anti-bot challenge. This server
wraps that API in thirty-six tools, so a package can be uploaded from the working
directory the setting skills built it in: statement, sources, solutions with
their expected verdicts, tests and groups, then commit and build.

## Why this is written here rather than installed

Third-party Polygon MCP servers exist. Handing one an API key means handing
unreviewed code write access to every problem the account can open — and a
Polygon key is not scoped per problem, nor read-only. So the credential-holding
code lives in this repository, where it can be read.

## Configure

Generate a key pair at **Polygon → Settings → API keys**. Each key has a `key`
half and a `secret` half; both are needed. The secret is used to sign requests
and is never transmitted, never logged, never written to disk, and never
present in anything a tool returns — [there is a test for that](#tests-1).

| Variable | Required for | Notes |
| --- | --- | --- |
| `POLYGON_API_KEY` | everything | the `key` half from Polygon → Settings → API keys |
| `POLYGON_API_SECRET` | everything | the `secret` half; used only to sign, never sent |
| `POLYGON_MCP_ROOT` | passing `path=` to a tool | the only directory a tool may read a file from; unset means every path is refused |
| `POLYGON_BASE_URL` | optional | default `https://polygon.codeforces.com/api/` |
| `POLYGON_TIMEOUT` | optional | HTTP timeout in seconds, default `30` |
| `POLYGON_MIN_INTERVAL` | optional | floor on the gap between two requests in seconds, default `0.5` |

```bash
export POLYGON_API_KEY=your_key
export POLYGON_API_SECRET=your_secret
export POLYGON_MCP_ROOT=/path/to/the/problem/you/are/uploading
```

The plugin's `.mcp.json` already declares the server and reads all three from
the environment of the shell that launches Claude Code, so no secret is stored
in this repository. Standalone, it is:

```bash
uvx --from /path/to/competitive-programming/mcp-server polygon-mcp
```

**Troubleshooting: `Incorrect API key` although the key is exported.** The
`.mcp.json` entries are `${POLYGON_API_KEY}`-style placeholders, expanded from
the environment Claude Code was *launched* from. A variable exported later —
in another terminal, or in a `~/.bashrc` the launching shell never read — is
not there, and the server receives the literal text `${POLYGON_API_KEY}`. The
server treats such a value as unset, and `polygon_whoami` lists it under
`unexpanded_variables`. The fix is to export the variables in the shell that
starts Claude Code (or its profile) and restart Claude Code.

## The path guard

Every tool that uploads a file takes either `content=` (the text inline) or
`path=` (a local file to read). The `path=` form is a file-read primitive
handed to a model, so it is fenced:

- With `POLYGON_MCP_ROOT` **unset**, every `path=` is refused and content has
  to be passed inline. That is the default.
- With it set, the path is resolved in full — symlinks followed, `..`
  collapsed — and refused unless the result is inside the equally-resolved
  root. A symlink pointing out of the root fails exactly the way
  `../../.ssh/id_rsa` does.
- Files are read as UTF-8 text, because this server sends uploads as form
  fields, so a binary statement resource has to go through the web interface.
- A file that passes the root check but cannot be read — wrong permissions, a
  dangling mount — comes back as an `{"ok": false}` error like any other
  failure, not as a traceback.

The Codeforces server's `cf_submit_solution(source_file=…)` has no such guard.
This one does, because it is a write API against an account that owns problems.

## Tools

Each tool wraps exactly one Polygon API method and returns a dict carrying
`ok`. A failure comes back as `{"ok": false, "error": "<Polygon's comment>",
"method": "<the API method>"}` rather than as an exception, so the model reads
what went wrong and corrects itself.

| Tool | Polygon method |
| --- | --- |
| `polygon_whoami()` | `problems.list`, as a credential check |
| `polygon_problems_list(show_deleted, problem_id, name, owner)` | `problems.list` |
| `polygon_problem_create(name)` | `problem.create` |
| `polygon_problem_info(problem_id)` | `problem.info` |
| `polygon_problem_update_info(problem_id, input_file, output_file, interactive, well_formed, time_limit_ms, memory_limit_mb)` | `problem.updateInfo` |
| `polygon_accesses(problem_id)` | `problem.accesses` |
| `polygon_set_access(problem_id, login, access)` | `problem.setAccess` |
| `polygon_statements(problem_id)` | `problem.statements` |
| `polygon_save_statement(problem_id, lang, encoding, name, legend, input, output, scoring, interaction, notes, tutorial)` | `problem.saveStatement` |
| `polygon_save_statement_resource(problem_id, name, content\|path)` | `problem.saveStatementResource` |
| `polygon_files(problem_id)` | `problem.files` |
| `polygon_save_file(problem_id, file_type, name, content\|path, source_type)` | `problem.saveFile` |
| `polygon_set_validator(problem_id, name)` | `problem.setValidator` |
| `polygon_set_checker(problem_id, name)` | `problem.setChecker` |
| `polygon_set_interactor(problem_id, name)` | `problem.setInteractor` |
| `polygon_solutions(problem_id)` | `problem.solutions` |
| `polygon_save_solution(problem_id, name, tag, content\|path, source_type)` | `problem.saveSolution` |
| `polygon_script(problem_id, testset)` | `problem.script` |
| `polygon_save_script(problem_id, testset, source)` | `problem.saveScript` |
| `polygon_tests(problem_id, testset, no_inputs)` | `problem.tests` |
| `polygon_save_test(problem_id, testset, test_index, test_input\|path, test_group, test_points, test_description, use_in_statements, input_for_statements, output_for_statements, verify_for_statements)` | `problem.saveTest` |
| `polygon_delete_test(problem_id, testset, test_index)` | `problem.deleteTest` |
| `polygon_enable_groups(problem_id, testset, enable)` | `problem.enableGroups` |
| `polygon_enable_points(problem_id, enable)` | `problem.enablePoints` |
| `polygon_set_test_group(problem_id, testset, test_group, test_indices)` | `problem.setTestGroup` |
| `polygon_test_groups(problem_id, testset, group)` | `problem.viewTestGroup` |
| `polygon_save_test_group(problem_id, testset, group, points_policy, feedback_policy, dependencies)` | `problem.saveTestGroup` |
| `polygon_tags(problem_id)` | `problem.viewTags` |
| `polygon_save_tags(problem_id, tags)` | `problem.saveTags` |
| `polygon_general_description(problem_id)` | `problem.viewGeneralDescription` |
| `polygon_save_general_description(problem_id, description)` | `problem.saveGeneralDescription` |
| `polygon_update_working_copy(problem_id)` | `problem.updateWorkingCopy` |
| `polygon_discard_working_copy(problem_id)` | `problem.discardWorkingCopy` |
| `polygon_commit(problem_id, minor_changes, message)` | `problem.commitChanges` |
| `polygon_build_package(problem_id, full, verify)` | `problem.buildPackage` |
| `polygon_packages(problem_id)` | `problem.packages` |

`file_type` is the API's `type`, renamed only to keep the parameter from
shadowing a Python builtin; the value goes over the wire unchanged.
`polygon_set_checker` passes its name through untouched, so Polygon's standard
checkers work under their own names — `std::wcmp.cpp` for token sequences,
`std::ncmp.cpp` for int64 sequences, `std::rcmp6.cpp` for doubles to 1e-6,
`std::lcmp.cpp` and `std::fcmp.cpp` for line-oriented output.

`polygon_set_access` takes `READ`, `WRITE` or `NONE` — Polygon does not let the
API assign `OWNER`, and `NONE` removes only the *direct* entry, leaving
whatever the user gets through a group. Access changes take effect at once and
need no commit.

Read `polygon_commit`'s `committed`, not its `ok`. A commit with nothing to
commit is a *successful* call reporting `committed: false` and the message
`No changes`, and a working copy that fell behind the repository comes back
with `conflict_occurred: true` — run `polygon_update_working_copy` and commit
again.

`polygon_delete_test` deletes one test per call. Polygon checks before it
deletes, so a refusal changes nothing and the failure carries
`details.failures`, each naming a test `index` and a `reason` of `DUPLICATE`,
`NOT_FOUND`, `FREEMARKER_SCRIPT_TEST` or `DELETE_FAILED`.

Two tools put a test into a group, and they are not interchangeable.
`polygon_set_test_group` names a group and a list of indices and nothing
else, so it cannot touch a test's input — that is the one to use on tests the
script generates. `polygon_save_test`'s `test_group` sets the group of a test
it is also writing, which is the manual-test case. Neither carries points:
`problem.setTestGroup` and `problem.saveTestGroup` have no points parameter,
so per-test points are always `polygon_save_test`'s `test_points`.

## Typical upload loop

```
polygon_whoami()                                   → the key works
polygon_problem_create("candy-shop")               → id 123456
polygon_problem_update_info(123456, time_limit_ms=2000, memory_limit_mb=256)
polygon_save_file(123456, "source", "validator.cpp", path="validator.cpp")
polygon_set_validator(123456, "validator.cpp")
polygon_set_checker(123456, "std::wcmp.cpp")
polygon_save_solution(123456, "sol.cpp", "MA", path="solutions/sol.cpp")
polygon_save_solution(123456, "brute.cpp", "TL", path="solutions/brute.cpp")
polygon_save_script(123456, "tests", "gen_random 1000 1 > $\n…")
polygon_enable_groups(123456, "tests", true)
polygon_enable_points(123456, true)
polygon_set_test_group(123456, "tests", "2", [3, 4, 5])
polygon_save_test_group(123456, "tests", "2", "COMPLETE_GROUP", "ICPC", ["1"])
polygon_save_statement(123456, "english", name="Candy Shop", legend="…")
polygon_commit(123456, message="initial package")
polygon_build_package(123456, verify=true)         → then poll polygon_packages
polygon_set_access(123456, "codeforces", "READ")   → hand it over
```

`polygon_build_package` returns as soon as the build is *queued*. Poll
`polygon_packages` and watch `state` go `PENDING` → `RUNNING` → `READY`, or
`FAILED` with a `comment` saying why.

## Tests

```bash
uv run --extra dev pytest -q tests/test_polygon_offline.py
```

92 tests, no network: nothing leaves `httpx.MockTransport`, so the signature,
the verb split, the pacing and the retry are all the real code and only the
socket is fake. They cover the signature against independently computed SHA-512
hashes, the `FAILED` and HTTP-error mappings, the path guard (inside, outside,
traversal, symlink, unreadable, no root at all), one happy path per tool
asserting the wire method and its parameters, every write proving it went out
as a POST, the three `CommitResult` shapes (committed, "No changes",
conflict), a `400`-with-a-`FAILED`-envelope reaching the caller as Polygon's
comment rather than as "HTTP 400", the structured deletion failures surviving
into `details`, and a grep of every tool's JSON — over the success path *and*
four failure paths — for both halves of the credential.

## Implementation notes

- **The signature is over raw values.** `apiSig` is six arbitrary characters
  followed by the SHA-512 of `<rand>/<method>?k=v&…#<secret>` over every
  parameter including `apiKey` and `time`, sorted by name then value. Polygon
  percent-decodes before it verifies, so signing the *encoded* form would fail
  for any value containing `&`, `=` or a newline — which is to say for every
  statement and every source file.
- **A retry is re-signed, not replayed.** Polygon refuses a request whose
  `time` is more than five minutes off its clock, so the second attempt is
  signed from scratch. One retry, on 5xx and transport failures only — never on
  a 4xx, which would fail identically the second time.
- **Uploads go as form fields, so they are signed.** A solution's whole source
  text is one more `param=value` pair. The API documentation describes `file`
  as an ordinary parameter ("file — file content") and never mentions
  multipart, so this is what it appears to want; it has not been checked
  against the live server.
- **Reads go as GET, writes as POST.** The API documentation fixes no verb; a
  statement's legend does not fit in a query string, so writes are POSTed. This
  split is the one other Polygon clients use, but it is the one thing here that
  no offline test can settle. If a method turns out to want the other verb, it
  is one line in `WRITE_METHODS`.
- **No httpx exception ever reaches a tool result.** httpx spells the request
  URL into the text of everything it raises, and a signed GET's URL carries
  `apiKey`. Every error message here is composed by hand instead.
- **Absent means "leave alone".** `problem.updateInfo`, and the edit mode of
  `problem.saveTest` and `problem.saveSolution`, treat an omitted parameter as
  "keep the old value", so `None` parameters are dropped rather than sent
  empty — otherwise setting a time limit would silently clear `interactive`.
- **Pin-protected problems are not supported.** Polygon takes an extra `pin`
  parameter for those; no tool here sends one.
