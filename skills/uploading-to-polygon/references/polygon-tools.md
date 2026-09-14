# Polygon tool registry

Every tool the bundled `polygon` MCP server exposes, paired with the one
Polygon API method it wraps, for [uploading-to-polygon](../SKILL.md). Grouped
by the upload phase that reaches for it, so the question this file answers is
"what do I call in phase 5" rather than "what does the server have".

**The loaded tool schema always wins over this file.** Load the real
definitions with `ToolSearch` and read their parameter names before calling
anything — the same rule
[running-contests](../../running-contests/references/judges.md) states for
judge MCPs, and for the same reason: a registry file can go stale, a loaded
schema cannot. Parameter names below carry `=` when they have a default.

A tool never raises. Every call returns a dict carrying `ok`; a failure comes
back as `{"ok": false, "error": "<Polygon's own comment>", "method": "<the
API method>"}`, and sometimes a `details` object. Read the comment and
correct the call — do not retry the identical request.

The credentials live in the server's own environment and never reach this
skill. Setup is in [`mcp-server/README.md`](../../../mcp-server/README.md).

## Credentials and inventory

| Tool | Polygon method |
| --- | --- |
| `polygon_whoami()` | `problems.list` |
| `polygon_problems_list(show_deleted=, problem_id=, name=, owner=)` | `problems.list` |

`polygon_whoami()` is the cheapest proof that the key, the secret and the
clock are all good. Call it first when any other tool fails.

## Create, limits, meta

| Tool | Polygon method |
| --- | --- |
| `polygon_problem_create(name)` | `problem.create` |
| `polygon_problem_info(problem_id)` | `problem.info` |
| `polygon_problem_update_info(problem_id, input_file=, output_file=, interactive=, well_formed=, time_limit_ms=, memory_limit_mb=)` | `problem.updateInfo` |
| `polygon_tags(problem_id)` | `problem.viewTags` |
| `polygon_save_tags(problem_id, tags)` | `problem.saveTags` |
| `polygon_general_description(problem_id)` | `problem.viewGeneralDescription` |
| `polygon_save_general_description(problem_id, description)` | `problem.saveGeneralDescription` |

`problem.create` returns `id`, `owner`, `name`, `deleted`, `favourite` and
`accessType` — and **no address**. The problem's page is
`https://polygon.codeforces.com/edit-start?problemId=<id>`, which is the URL
the skill records.

`polygon_save_tags` replaces the whole set, so read `polygon_tags` first if
you mean to add one.

## Access

| Tool | Polygon method |
| --- | --- |
| `polygon_accesses(problem_id)` | `problem.accesses` |
| `polygon_set_access(problem_id, login, access)` | `problem.setAccess` |

`access` is `READ`, `WRITE` or `NONE`; `OWNER` is deliberately absent because
the API does not let this method assign ownership. Access lives at problem
level, so it takes effect immediately and needs no commit. `problem.setAccess`
needs **direct** WRITE or OWNER — access held only through a user group is
not enough, and that is the one failure worth predicting here.

## Statement

| Tool | Polygon method |
| --- | --- |
| `polygon_statements(problem_id)` | `problem.statements` |
| `polygon_save_statement(problem_id, lang, encoding=, name=, legend=, input=, output=, scoring=, interaction=, notes=, tutorial=)` | `problem.saveStatement` |
| `polygon_save_statement_resource(problem_id, name, content=, path=)` | `problem.saveStatementResource` |

Only `lang` is required; every section left empty is not sent, so an existing
one survives. `interaction` is accepted only for a problem already marked
interactive.

The API accepts any text and reports nothing about how it will render. What
the Codeforces HTML converter accepts — `$x$`, not `$$$x$$$`, and the
text-mode command whitelist — is in
[polygon-statement-markup.md](polygon-statement-markup.md).

## Sources, checker, validator

| Tool | Polygon method |
| --- | --- |
| `polygon_files(problem_id)` | `problem.files` |
| `polygon_save_file(problem_id, file_type, name, content=, path=, source_type=)` | `problem.saveFile` |
| `polygon_set_validator(problem_id, name)` | `problem.setValidator` |
| `polygon_set_checker(problem_id, name)` | `problem.setChecker` |
| `polygon_set_interactor(problem_id, name)` | `problem.setInteractor` |

`file_type` is `source` (a checker, validator, interactor or generator),
`resource` (something a compile needs beside a source, such as a shared
header) or `aux`. `source_type` is Polygon's compiler id and may be left
empty for Polygon to guess from the extension.

`path=` is honoured only under `POLYGON_MCP_ROOT` and read as UTF-8 text.

## Solutions

| Tool | Polygon method |
| --- | --- |
| `polygon_solutions(problem_id)` | `problem.solutions` |
| `polygon_save_solution(problem_id, name, tag, content=, path=, source_type=)` | `problem.saveSolution` |

`tag` is what the solution is *supposed* to do, and a verified package build
checks that the claim holds: `MA`, `OK`, `RJ`, `TL`, `TO`, `TM`, `WA`, `PE`,
`ML`, `NR`, `RE`. Exactly one solution carries `MA`, and Polygon computes
every test's answer by running it.

## Tests, groups, points

| Tool | Polygon method |
| --- | --- |
| `polygon_script(problem_id, testset=)` | `problem.script` |
| `polygon_save_script(problem_id, testset, source)` | `problem.saveScript` |
| `polygon_tests(problem_id, testset=, no_inputs=)` | `problem.tests` |
| `polygon_save_test(problem_id, testset, test_index, test_input=, path=, test_group=, test_points=, test_description=, use_in_statements=, input_for_statements=, output_for_statements=, verify_for_statements=)` | `problem.saveTest` |
| `polygon_delete_test(problem_id, testset, test_index)` | `problem.deleteTest` |
| `polygon_enable_groups(problem_id, testset, enable)` | `problem.enableGroups` |
| `polygon_enable_points(problem_id, enable)` | `problem.enablePoints` |
| `polygon_set_test_group(problem_id, testset, test_group, test_indices)` | `problem.setTestGroup` |
| `polygon_test_groups(problem_id, testset, group=)` | `problem.viewTestGroup` |
| `polygon_save_test_group(problem_id, testset, group, points_policy=, feedback_policy=, dependencies=)` | `problem.saveTestGroup` |

`polygon_save_script` replaces the whole script — it is not a line appended.

`polygon_save_test` with a `test_input` or `path` byte-identical to an
existing test fails with `testInput: Test coincides with test #N.` — which is
how a sample that duplicates a package test first shows up. Mark test `N`
with `use_in_statements` instead of uploading the sample again.

Polygon rate-limits an account. The server backs off and retries an HTTP 429
a few times, but a batch of calls fired in parallel can still exhaust that,
so save tests one at a time.

Two tools carry three routes into a test's group and points, and they are
not interchangeable:

- `polygon_set_test_group` names a group and a list of indices and **nothing
  else**, so there is no field through which it could disturb a test's input.
  It is the route for tests the *script* generates.
- `polygon_save_test`'s `test_group` sets the group of a test it is also
  writing — the manual-test case, samples included.
- `polygon_save_test`'s `test_points` is the **only** route to per-test
  points: neither `problem.setTestGroup` nor `problem.saveTestGroup` has a
  points parameter, so an OI ladder's points can arrive no other way. Sent on
  its own, with no `test_group` and no `test_input`, it is a points update
  and the server omits every parameter left unset. Expect it to leave the
  group and the input alone; it is not documented in so many words for a
  script-generated index, so confirm it against `manual` and `scriptLine` in
  the readback rather than assuming it — and a refusal comes back as
  `{"ok": false}`, which is a stop, not something to work around.

`polygon_save_test_group` only *edits* a group. A group is **created** by a
test being put into it — so tests get their groups first and policies second,
never the other way round.

## Commit and build

| Tool | Polygon method |
| --- | --- |
| `polygon_update_working_copy(problem_id)` | `problem.updateWorkingCopy` |
| `polygon_discard_working_copy(problem_id)` | `problem.discardWorkingCopy` |
| `polygon_commit(problem_id, minor_changes=, message=)` | `problem.commitChanges` |
| `polygon_build_package(problem_id, full=, verify=)` | `problem.buildPackage` |
| `polygon_packages(problem_id)` | `problem.packages` |

**Read `committed`, not `ok`.** Polygon answers a no-op commit with a
*successful* envelope carrying `committed=false` and the message "No changes",
and reports a working copy that fell behind the repository as
`conflict_occurred=true`. `ok: true` means the call went through, not that a
revision exists. On a conflict, `polygon_update_working_copy` and commit
again.

`minor_changes=true` suppresses the notification mail to the problem's other
authors.

`polygon_build_package` returns as soon as the build is *queued*. Poll
`polygon_packages` and watch `state` go `PENDING` → `RUNNING` → `READY`, or
`FAILED` with a `comment` saying why.

`polygon_discard_working_copy` is destructive and not undoable — it is the
way out of a working copy that will not commit, and it throws away everything
saved since the last revision.
