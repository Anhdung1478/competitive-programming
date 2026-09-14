"""MCP server exposing Polygon problem preparation: statements, files, tests, packages.

Every tool wraps exactly one Polygon API method, named in its docstring, and
returns a dict carrying `ok`. Failures come back as
`{"ok": false, "error": ..., "method": ...}` rather than raising, so the model
reads the comment Polygon sent and corrects itself. No tool returns, logs or
writes the API secret.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .api import PolygonApi
from .config import Config, PolygonError, resolve_local_path, unexpanded_explanation

mcp = FastMCP("polygon")

config = Config.from_env()
api = PolygonApi(config)

# The tags Polygon accepts on a solution. Kept here so a typo is caught before
# a request goes out rather than as a FAILED comment afterwards.
SOLUTION_TAGS = ("MA", "OK", "RJ", "TL", "TO", "TM", "WA", "PE", "ML", "NR", "RE")
FILE_TYPES = ("resource", "source", "aux")
POINTS_POLICIES = ("COMPLETE_GROUP", "EACH_TEST")
FEEDBACK_POLICIES = ("NONE", "POINTS", "ICPC", "COMPLETE")
# The three states `problem.setAccess` accepts. OWNER is deliberately absent:
# the API documents that ownership cannot be assigned through this method.
ACCESS_TYPES = ("READ", "WRITE", "NONE")


def _fail(error: Exception, method: str) -> dict[str, Any]:
    """The single failure shape every tool returns.

    Every tool catches `Exception`, not just `PolygonError`: a traceback out of
    a tool reaches the model as a protocol-level error rather than as something
    it can read and correct. `str(error)` is safe here only because nothing in
    this package ever puts an httpx exception into the message — httpx spells
    the request URL into everything it raises, and a signed GET's URL carries
    `apiKey`.
    """
    failure = {
        "ok": False,
        "error": str(error),
        "method": getattr(error, "method", "") or method,
    }
    # Only when Polygon sent structured failure details, so every other tool's
    # failure shape is exactly what it was.
    details = getattr(error, "details", None)
    if details is not None:
        failure["details"] = details
    return failure


def _read_source(
    content: str, path: str, *, what: str = "content", required: bool = True
) -> str | None:
    """Resolve a `content`-or-`path` pair into the text to upload.

    A path is honoured only inside `POLYGON_MCP_ROOT`; see
    `config.resolve_local_path` for why the guard is there at all. Files are
    read as UTF-8 text, because this server sends uploads as form fields —
    which covers every artifact the upload flow needs: source, statement prose,
    test data.

    `required=False` returns None when neither was given, for the methods whose
    edit mode means "change the metadata, leave the body alone".
    """
    if content and path:
        raise PolygonError(f"Pass either {what} or path, not both.")
    if path:
        resolved = resolve_local_path(path, config.root, config.unexpanded)
        try:
            return resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise PolygonError(
                f"{resolved} is not UTF-8 text. This server sends uploads as "
                "form fields, so source, statements and test data go as text; "
                "binary resources have to be uploaded through the web "
                "interface."
            ) from None
        except OSError as error:
            # Passing the root check is not permission to read: the file can be
            # mode 000, or a dangling mount. Without this the tool would raise
            # instead of returning the {"ok": false} shape every other one does.
            raise PolygonError(
                f"Could not read {resolved}: {error.strerror or error}"
            ) from None
    if content:
        return content
    if required:
        raise PolygonError(f"Pass the {what} inline, or a path to a file holding it.")
    return None


def _one_of(name: str, value: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise PolygonError(f"{name} must be one of {', '.join(allowed)}; got {value!r}.")
    return value


# --------------------------------------------------------------------- tools


@mcp.tool()
async def polygon_whoami() -> dict[str, Any]:
    """Check that this server's Polygon credentials work. → `problems.list`

    Lists the problems the key can see and summarises them, which is the
    cheapest call that proves the key, the secret and the clock are all good.
    Call it first when any other tool fails, before re-reading its error.

    `unexpanded_variables` names every variable that reached the server as a
    literal `${NAME}` — the MCP client's placeholder, left in place because
    the variable was missing from the environment Claude Code started in.
    Those count as unset, and the explanation leads the error, because the
    usual fix ("set the variable") is exactly what the operator believes they
    already did.
    """
    unexpanded = list(config.unexpanded)
    status: dict[str, Any] = {
        "ok": True,
        "base_url": config.base_url,
        "credentials_configured": config.has_credentials,
        "path_reads_allowed_under": str(config.root) if config.root else None,
        "unexpanded_variables": unexpanded,
    }
    if not config.has_credentials:
        missing = "No Polygon credentials."
        if unexpanded:
            missing += " " + unexpanded_explanation(unexpanded)
        return {
            **status,
            "ok": False,
            "error": missing + " Generate a key at Polygon → "
            "Settings → API keys and set POLYGON_API_KEY and "
            "POLYGON_API_SECRET for this server.",
            "method": "problems.list",
        }
    if unexpanded:
        # The credentials made it through, so the check can go ahead, but a
        # root or a tuning knob silently falling back to its default is
        # still worth saying out loud.
        status["warning"] = unexpanded_explanation(unexpanded)
    try:
        problems = await api.call("problems.list") or []
    except Exception as error:
        return {**status, **_fail(error, "problems.list")}
    return {
        **status,
        "problem_count": len(problems),
        "first_problems": [
            {"id": p.get("id"), "name": p.get("name"), "owner": p.get("owner")}
            for p in problems[:5]
        ],
    }


@mcp.tool()
async def polygon_problems_list(
    show_deleted: bool = False,
    problem_id: int | None = None,
    name: str = "",
    owner: str = "",
) -> dict[str, Any]:
    """List the problems this account can open. → `problems.list`

    Every filter is optional: `problem_id`, `name` and `owner` narrow the list,
    `show_deleted` brings back deleted problems. Each entry carries the `id`
    that every other tool here takes as `problem_id`, plus `accessType` — WRITE
    or OWNER is required before anything can be saved.
    """
    try:
        result = await api.call(
            "problems.list",
            {
                "showDeleted": show_deleted,
                "id": problem_id,
                "name": name or None,
                "owner": owner or None,
            },
        )
        return {"ok": True, "count": len(result or []), "problems": result or []}
    except Exception as error:
        return _fail(error, "problems.list")


@mcp.tool()
async def polygon_problem_create(name: str) -> dict[str, Any]:
    """Create a new empty problem and return it. → `problem.create`

    The returned `id` is the `problem_id` every other tool takes. The problem
    starts empty: no statement, no checker, no tests.
    """
    try:
        return {"ok": True, "problem": await api.call("problem.create", {"name": name})}
    except Exception as error:
        return _fail(error, "problem.create")


@mcp.tool()
async def polygon_problem_info(problem_id: int) -> dict[str, Any]:
    """Read a problem's input/output files and limits. → `problem.info`

    Returns `inputFile`, `outputFile`, `interactive`, `wellFormed`,
    `timeLimit` (milliseconds) and `memoryLimit` (MB).
    """
    try:
        return {
            "ok": True,
            "info": await api.call("problem.info", {"problemId": problem_id}),
        }
    except Exception as error:
        return _fail(error, "problem.info")


@mcp.tool()
async def polygon_problem_update_info(
    problem_id: int,
    input_file: str = "",
    output_file: str = "",
    interactive: bool | None = None,
    well_formed: bool | None = None,
    time_limit_ms: int | None = None,
    memory_limit_mb: int | None = None,
) -> dict[str, Any]:
    """Set a problem's input/output files and limits. → `problem.updateInfo`

    Every field is optional and an omitted one is left alone, so this is safe
    to call to change a single limit. `time_limit_ms` is milliseconds and
    `memory_limit_mb` is megabytes, matching Polygon's own units — a 2-second,
    256 MB problem is `time_limit_ms=2000, memory_limit_mb=256`.
    """
    try:
        await api.call(
            "problem.updateInfo",
            {
                "problemId": problem_id,
                "inputFile": input_file or None,
                "outputFile": output_file or None,
                "interactive": interactive,
                "wellFormed": well_formed,
                "timeLimit": time_limit_ms,
                "memoryLimit": memory_limit_mb,
            },
        )
        return {"ok": True, "updated": True}
    except Exception as error:
        return _fail(error, "problem.updateInfo")


# -------------------------------------------------------------------- access


@mcp.tool()
async def polygon_accesses(problem_id: int) -> dict[str, Any]:
    """List who has direct access to the problem. → `problem.accesses`

    Each entry is a `login` and an `accessType` of READ, WRITE or OWNER. These
    are the *stored direct* entries, not anyone's effective access: a login
    beginning with `@` is a user group, and its members are not expanded. The
    access list lives at problem level, so it is not part of the working copy
    and needs no commit.

    Reading it needs WRITE or OWNER access on the problem, which access
    inherited through a group satisfies.
    """
    try:
        result = await api.call("problem.accesses", {"problemId": problem_id})
        return {"ok": True, "count": len(result or []), "accesses": result or []}
    except Exception as error:
        return _fail(error, "problem.accesses")


@mcp.tool()
async def polygon_set_access(
    problem_id: int, login: str, access: str
) -> dict[str, Any]:
    """Grant or remove one user's direct access. → `problem.setAccess`

    This is how a finished problem is handed over — `polygon_set_access(id,
    "codeforces", "READ")` gives the Codeforces coordinators a look at it.
    `access` is READ, WRITE or NONE; NONE removes the direct entry and leaves
    any access the user has through a group intact. OWNER is not on the list
    because Polygon does not let this method assign ownership, and a direct
    owner can be neither downgraded nor removed.

    Takes effect immediately — no commit — and `login` must be a real user, not
    a `@group`. Setting the access a user already has is a successful no-op.
    Calling it needs *direct* WRITE or OWNER access; access held only through a
    group is not enough.
    """
    try:
        await api.call(
            "problem.setAccess",
            {
                "problemId": problem_id,
                "login": login,
                "accessType": _one_of("access", access, ACCESS_TYPES),
            },
        )
        return {"ok": True, "login": login, "access": access}
    except Exception as error:
        return _fail(error, "problem.setAccess")


# ---------------------------------------------------------------- statements


@mcp.tool()
async def polygon_statements(problem_id: int) -> dict[str, Any]:
    """Read every language's statement for a problem. → `problem.statements`

    Returns a map from language code to the statement's `name`, `legend`,
    `input`, `output`, `scoring`, `interaction`, `notes` and `tutorial`.
    """
    try:
        result = await api.call("problem.statements", {"problemId": problem_id})
        return {
            "ok": True,
            "languages": sorted((result or {}).keys()),
            "statements": result or {},
        }
    except Exception as error:
        return _fail(error, "problem.statements")


@mcp.tool()
async def polygon_save_statement(
    problem_id: int,
    lang: str,
    encoding: str = "",
    name: str = "",
    legend: str = "",
    input: str = "",
    output: str = "",
    scoring: str = "",
    interaction: str = "",
    notes: str = "",
    tutorial: str = "",
) -> dict[str, Any]:
    """Create or update one language's statement. → `problem.saveStatement`

    Only `lang` is required (`english`, `vietnamese`, …); every section left
    empty is not sent, so an existing one is kept. The text is Polygon's own
    markup, so `$$$x$$$` for inline math and `\\includegraphics` for a figure
    saved with `polygon_save_statement_resource`. `interaction` is accepted
    only for a problem marked interactive.
    """
    try:
        await api.call(
            "problem.saveStatement",
            {
                "problemId": problem_id,
                "lang": lang,
                "encoding": encoding or None,
                "name": name or None,
                "legend": legend or None,
                "input": input or None,
                "output": output or None,
                "scoring": scoring or None,
                "interaction": interaction or None,
                "notes": notes or None,
                "tutorial": tutorial or None,
            },
        )
        return {"ok": True, "saved": True, "lang": lang}
    except Exception as error:
        return _fail(error, "problem.saveStatement")


@mcp.tool()
async def polygon_save_statement_resource(
    problem_id: int, name: str, content: str = "", path: str = ""
) -> dict[str, Any]:
    """Add or replace a statement resource file. → `problem.saveStatementResource`

    These are the files a statement includes — a figure's `.eps`/`.svg` source,
    a `.tex` fragment. Pass the text in `content`, or `path` to a UTF-8 file
    inside `POLYGON_MCP_ROOT`.
    """
    try:
        await api.call(
            "problem.saveStatementResource",
            {"problemId": problem_id, "name": name, "file": _read_source(content, path)},
        )
        return {"ok": True, "saved": True, "name": name}
    except Exception as error:
        return _fail(error, "problem.saveStatementResource")


# --------------------------------------------------------------------- files


@mcp.tool()
async def polygon_files(problem_id: int) -> dict[str, Any]:
    """List a problem's resource, source and aux files. → `problem.files`

    Returns `resourceFiles`, `sourceFiles` and `auxFiles`. Sources are what
    `polygon_set_checker`, `polygon_set_validator` and `polygon_set_interactor`
    choose from, so call this to see what names are already uploaded.
    """
    try:
        return {
            "ok": True,
            "files": await api.call("problem.files", {"problemId": problem_id}),
        }
    except Exception as error:
        return _fail(error, "problem.files")


@mcp.tool()
async def polygon_save_file(
    problem_id: int,
    file_type: str,
    name: str,
    content: str = "",
    path: str = "",
    source_type: str = "",
) -> dict[str, Any]:
    """Add or replace one resource, source or aux file. → `problem.saveFile`

    `file_type` is the API's `type`: `source` for a checker, validator,
    interactor or generator; `resource` for something a compile needs, such as
    `testlib.h`; `aux` for anything else. Pass the text in `content`, or `path`
    to a UTF-8 file inside `POLYGON_MCP_ROOT`. `source_type` is Polygon's
    compiler id (`cpp.g++17`, `cpp.gcc11-64`, …) and can be left empty to let
    Polygon guess from the extension.
    """
    try:
        await api.call(
            "problem.saveFile",
            {
                "problemId": problem_id,
                "type": _one_of("file_type", file_type, FILE_TYPES),
                "name": name,
                "file": _read_source(content, path),
                "sourceType": source_type or None,
            },
        )
        return {"ok": True, "saved": True, "name": name, "type": file_type}
    except Exception as error:
        return _fail(error, "problem.saveFile")


@mcp.tool()
async def polygon_set_validator(problem_id: int, name: str) -> dict[str, Any]:
    """Point the problem at one of its source files as the validator.
    → `problem.setValidator`

    `name` must already be a source file — upload it with
    `polygon_save_file(file_type="source")` first.
    """
    try:
        await api.call(
            "problem.setValidator", {"problemId": problem_id, "validator": name}
        )
        return {"ok": True, "validator": name}
    except Exception as error:
        return _fail(error, "problem.setValidator")


@mcp.tool()
async def polygon_set_checker(problem_id: int, name: str) -> dict[str, Any]:
    """Point the problem at a checker. → `problem.setChecker`

    `name` is either one of the problem's own source files or one of Polygon's
    standard checkers, spelled the way Polygon spells them: `std::wcmp.cpp`
    (sequences of tokens), `std::ncmp.cpp` (sequences of int64), `std::rcmp6.cpp`
    (doubles to 1e-6), `std::fcmp.cpp` (files as lines), `std::lcmp.cpp` (lines
    as token sequences). The name is passed through untouched, so a checker
    Polygon adds later works without a change here.
    """
    try:
        await api.call("problem.setChecker", {"problemId": problem_id, "checker": name})
        return {"ok": True, "checker": name}
    except Exception as error:
        return _fail(error, "problem.setChecker")


@mcp.tool()
async def polygon_set_interactor(problem_id: int, name: str) -> dict[str, Any]:
    """Point the problem at one of its source files as the interactor.
    → `problem.setInteractor`

    Only meaningful once the problem is marked interactive with
    `polygon_problem_update_info(interactive=true)`.
    """
    try:
        await api.call(
            "problem.setInteractor", {"problemId": problem_id, "interactor": name}
        )
        return {"ok": True, "interactor": name}
    except Exception as error:
        return _fail(error, "problem.setInteractor")


# ----------------------------------------------------------------- solutions


@mcp.tool()
async def polygon_solutions(problem_id: int) -> dict[str, Any]:
    """List the problem's solutions and their tags. → `problem.solutions`

    Each entry has `name`, `sourceType`, `length` and `tag`. Exactly one
    solution should carry `MA`.
    """
    try:
        result = await api.call("problem.solutions", {"problemId": problem_id})
        return {"ok": True, "count": len(result or []), "solutions": result or []}
    except Exception as error:
        return _fail(error, "problem.solutions")


@mcp.tool()
async def polygon_save_solution(
    problem_id: int,
    name: str,
    tag: str,
    content: str = "",
    path: str = "",
    source_type: str = "",
) -> dict[str, Any]:
    """Add or replace a solution and set its expected verdict. → `problem.saveSolution`

    `tag` is what the solution is *supposed* to do, and Polygon checks it when
    a package is built with verification: `MA` the main solution, `OK` another
    correct one, `RJ` rejected on some test, `WA`, `PE`, `TL`, `ML`, `RE`,
    `TO` (time limit or accepted), `TM` (time limit or memory limit), `NR` do
    not run. Pass the source in `content`, or `path` to a file inside
    `POLYGON_MCP_ROOT`.
    """
    try:
        await api.call(
            "problem.saveSolution",
            {
                "problemId": problem_id,
                "name": name,
                # Optional: re-tagging a solution that is already uploaded is
                # a save with a name and a tag and nothing else.
                "file": _read_source(content, path, what="source", required=False),
                "tag": _one_of("tag", tag, SOLUTION_TAGS),
                "sourceType": source_type or None,
            },
        )
        return {"ok": True, "saved": True, "name": name, "tag": tag}
    except Exception as error:
        return _fail(error, "problem.saveSolution")


# --------------------------------------------------------------------- tests


@mcp.tool()
async def polygon_script(problem_id: int, testset: str = "tests") -> dict[str, Any]:
    """Read the generator script for a testset. → `problem.script`

    Returns the script as plain text: one generator invocation per line, each
    ending in `> $` for the test it produces.
    """
    try:
        return {
            "ok": True,
            "testset": testset,
            "script": await api.call(
                "problem.script", {"problemId": problem_id, "testset": testset}
            ),
        }
    except Exception as error:
        return _fail(error, "problem.script")


@mcp.tool()
async def polygon_save_script(
    problem_id: int, testset: str, source: str
) -> dict[str, Any]:
    """Replace a testset's generator script. → `problem.saveScript`

    The whole script at once, not a line appended: whatever was there is gone.
    Each line is a generator call ending in `> $`, e.g.
    `gen_random 1000 42 > $`.
    """
    try:
        await api.call(
            "problem.saveScript",
            {"problemId": problem_id, "testset": testset, "source": source},
        )
        return {"ok": True, "saved": True, "testset": testset}
    except Exception as error:
        return _fail(error, "problem.saveScript")


@mcp.tool()
async def polygon_tests(
    problem_id: int, testset: str = "tests", no_inputs: bool = False
) -> dict[str, Any]:
    """List a testset's tests. → `problem.tests`

    Each test has `index`, `manual`, `group`, `points`, `useInStatements` and
    either `input` (manual tests) or `scriptLine` (generated ones). Set
    `no_inputs` to leave the inputs out, which matters for a testset whose
    manual tests are large.
    """
    try:
        result = await api.call(
            "problem.tests",
            {
                "problemId": problem_id,
                "testset": testset,
                "noInputs": no_inputs or None,
            },
        )
        return {
            "ok": True,
            "testset": testset,
            "count": len(result or []),
            "tests": result or [],
        }
    except Exception as error:
        return _fail(error, "problem.tests")


@mcp.tool()
async def polygon_save_test(
    problem_id: int,
    testset: str,
    test_index: int,
    test_input: str = "",
    path: str = "",
    test_group: str = "",
    test_points: float | None = None,
    test_description: str = "",
    use_in_statements: bool | None = None,
    input_for_statements: str = "",
    output_for_statements: str = "",
    verify_for_statements: bool | None = None,
) -> dict[str, Any]:
    """Add or replace one manual test. → `problem.saveTest`

    This is for hand-written tests; generated ones come from the script
    (`polygon_save_script`). Pass the input in `test_input`, or `path` to a
    file inside `POLYGON_MCP_ROOT`. When editing an existing test, everything
    but `testset` and `test_index` is optional and an omitted field is left
    alone.

    `test_group` needs groups enabled for the testset
    (`polygon_enable_groups`) and `test_points` needs points enabled for the
    problem (`polygon_enable_points`). The `*_for_statements` fields are the
    prettified sample shown to contestants, which is not always the literal
    test data.
    """
    try:
        await api.call(
            "problem.saveTest",
            {
                "problemId": problem_id,
                "testset": testset,
                "testIndex": test_index,
                "testInput": _read_source(
                    test_input, path, what="test_input", required=False
                ),
                "testGroup": test_group or None,
                "testPoints": test_points,
                "testDescription": test_description or None,
                "testUseInStatements": use_in_statements,
                "testInputForStatements": input_for_statements or None,
                "testOutputForStatements": output_for_statements or None,
                "verifyInputOutputForStatements": verify_for_statements,
            },
        )
        return {"ok": True, "saved": True, "testset": testset, "test_index": test_index}
    except Exception as error:
        return _fail(error, "problem.saveTest")


@mcp.tool()
async def polygon_delete_test(
    problem_id: int, testset: str, test_index: int
) -> dict[str, Any]:
    """Delete one test from a testset. → `problem.deleteTest`

    Polygon checks the test before deleting anything, so a refusal leaves the
    testset untouched: the failure comes back with `details.failures`, each
    naming the test's `index` and a `reason` of DUPLICATE, NOT_FOUND,
    FREEMARKER_SCRIPT_TEST or DELETE_FAILED. A test the script generates cannot
    be deleted this way — edit the script instead.

    The index goes over the wire as `testIndices`, the API's comma-separated
    form. It is the alternative to repeating `testIndex`, which a signed
    request built from a parameter mapping cannot express; one test per call is
    what this tool offers.
    """
    try:
        await api.call(
            "problem.deleteTest",
            {
                "problemId": problem_id,
                "testset": testset,
                "testIndices": str(test_index),
            },
        )
        return {
            "ok": True,
            "deleted": True,
            "testset": testset,
            "test_index": test_index,
        }
    except Exception as error:
        return _fail(error, "problem.deleteTest")


# --------------------------------------------------------- groups and points


@mcp.tool()
async def polygon_enable_groups(
    problem_id: int, testset: str, enable: bool
) -> dict[str, Any]:
    """Turn test groups on or off for a testset. → `problem.enableGroups`

    Groups have to be enabled before any test can be given a `test_group`, so
    this comes first when building a subtask ladder.
    """
    try:
        await api.call(
            "problem.enableGroups",
            {"problemId": problem_id, "testset": testset, "enable": enable},
        )
        return {"ok": True, "testset": testset, "groups_enabled": enable}
    except Exception as error:
        return _fail(error, "problem.enableGroups")


@mcp.tool()
async def polygon_enable_points(problem_id: int, enable: bool) -> dict[str, Any]:
    """Turn test points on or off for the problem. → `problem.enablePoints`

    Needed before a test or a group can carry points — that is, for any
    IOI-style scored problem.
    """
    try:
        await api.call(
            "problem.enablePoints", {"problemId": problem_id, "enable": enable}
        )
        return {"ok": True, "points_enabled": enable}
    except Exception as error:
        return _fail(error, "problem.enablePoints")


@mcp.tool()
async def polygon_set_test_group(
    problem_id: int, testset: str, test_group: str, test_indices: list[int]
) -> dict[str, Any]:
    """Put one or more tests into a test group. → `problem.setTestGroup`

    The way a *script-generated* test is given its group: it names the group
    and the indices and nothing else, so it cannot disturb a test's input the
    way an edit through `polygon_save_test` could. Groups have to be enabled
    for the testset first (`polygon_enable_groups`), and a group comes into
    existence by a test being put into it.

    The indices go over the wire as `testIndices`, the API's comma-separated
    form. It is the alternative to repeating `testIndex`, which a signed
    request built from a parameter mapping cannot express.

    This method carries no points: `problem.setTestGroup` has no points
    parameter and neither does `problem.saveTestGroup`, so per-test points
    remain `polygon_save_test`'s `test_points`.
    """
    try:
        # Inside the try, like every other guard in this file: a raise out of
        # a tool reaches the model as a protocol error instead of the
        # `{"ok": false}` it can read. An empty list would otherwise send
        # `testIndices=""` and let Polygon answer for it.
        if not test_indices:
            raise PolygonError("test_indices must name at least one test.")
        await api.call(
            "problem.setTestGroup",
            {
                "problemId": problem_id,
                "testset": testset,
                "testGroup": test_group,
                "testIndices": ",".join(str(i) for i in test_indices),
            },
        )
        return {
            "ok": True,
            "testset": testset,
            "test_group": test_group,
            "test_indices": list(test_indices),
        }
    except Exception as error:
        return _fail(error, "problem.setTestGroup")


@mcp.tool()
async def polygon_test_groups(
    problem_id: int, testset: str, group: str = ""
) -> dict[str, Any]:
    """Read a testset's groups. → `problem.viewTestGroup`

    Each group has `name`, `pointsPolicy`, `feedbackPolicy` and
    `dependencies`. Pass `group` to read just one.
    """
    try:
        result = await api.call(
            "problem.viewTestGroup",
            {"problemId": problem_id, "testset": testset, "group": group or None},
        )
        return {
            "ok": True,
            "testset": testset,
            "count": len(result or []),
            "groups": result or [],
        }
    except Exception as error:
        return _fail(error, "problem.viewTestGroup")


@mcp.tool()
async def polygon_save_test_group(
    problem_id: int,
    testset: str,
    group: str,
    points_policy: str = "",
    feedback_policy: str = "",
    dependencies: list[str] | None = None,
) -> dict[str, Any]:
    """Set a group's scoring and feedback policy. → `problem.saveTestGroup`

    This edits an existing group; a group is *created* by giving a test that
    group name with `polygon_save_test`. `points_policy` is `COMPLETE_GROUP`
    (all-or-nothing, the usual subtask) or `EACH_TEST`. `feedback_policy` is
    `NONE`, `POINTS`, `ICPC` (first error) or `COMPLETE`. `dependencies` names
    the groups that must pass before this one is judged; an omitted policy
    keeps its old value.
    """
    try:
        await api.call(
            "problem.saveTestGroup",
            {
                "problemId": problem_id,
                "testset": testset,
                "group": group,
                "pointsPolicy": _one_of(
                    "points_policy", points_policy, POINTS_POLICIES
                )
                if points_policy
                else None,
                "feedbackPolicy": _one_of(
                    "feedback_policy", feedback_policy, FEEDBACK_POLICIES
                )
                if feedback_policy
                else None,
                # Polygon takes the dependency list as one comma-separated
                # string, not as a repeated parameter.
                "dependencies": ",".join(dependencies) if dependencies else None,
            },
        )
        return {"ok": True, "saved": True, "testset": testset, "group": group}
    except Exception as error:
        return _fail(error, "problem.saveTestGroup")


# ---------------------------------------------------------------------- meta


@mcp.tool()
async def polygon_tags(problem_id: int) -> dict[str, Any]:
    """Read the problem's tags. → `problem.viewTags`"""
    try:
        result = await api.call("problem.viewTags", {"problemId": problem_id})
        return {"ok": True, "tags": result or []}
    except Exception as error:
        return _fail(error, "problem.viewTags")


@mcp.tool()
async def polygon_save_tags(problem_id: int, tags: list[str]) -> dict[str, Any]:
    """Replace the problem's tags. → `problem.saveTags`

    The whole set at once — the tags given here replace whatever was there, so
    read `polygon_tags` first if you mean to add one.
    """
    try:
        await api.call(
            "problem.saveTags",
            {"problemId": problem_id, "tags": ",".join(tags)},
        )
        return {"ok": True, "saved": True, "tags": tags}
    except Exception as error:
        return _fail(error, "problem.saveTags")


@mcp.tool()
async def polygon_general_description(problem_id: int) -> dict[str, Any]:
    """Read the problem's general description. → `problem.viewGeneralDescription`

    This is the setter-facing note on the problem, not the statement.
    """
    try:
        result = await api.call(
            "problem.viewGeneralDescription", {"problemId": problem_id}
        )
        return {"ok": True, "description": result or ""}
    except Exception as error:
        return _fail(error, "problem.viewGeneralDescription")


@mcp.tool()
async def polygon_save_general_description(
    problem_id: int, description: str
) -> dict[str, Any]:
    """Replace the problem's general description. → `problem.saveGeneralDescription`

    An empty string is accepted and clears it.
    """
    try:
        await api.call(
            "problem.saveGeneralDescription",
            {"problemId": problem_id, "description": description},
        )
        return {"ok": True, "saved": True}
    except Exception as error:
        return _fail(error, "problem.saveGeneralDescription")


# ----------------------------------------------------------------- lifecycle


@mcp.tool()
async def polygon_update_working_copy(problem_id: int) -> dict[str, Any]:
    """Pull the latest revision into the working copy. → `problem.updateWorkingCopy`

    Needed when someone else committed while this one was open; a working copy
    behind the repository is what makes `polygon_commit` come back with
    `conflict_occurred`.
    """
    try:
        await api.call("problem.updateWorkingCopy", {"problemId": problem_id})
        return {"ok": True, "problem_id": problem_id}
    except Exception as error:
        return _fail(error, "problem.updateWorkingCopy")


@mcp.tool()
async def polygon_discard_working_copy(problem_id: int) -> dict[str, Any]:
    """Throw away every uncommitted change. → `problem.discardWorkingCopy`

    Destructive and not undoable: everything saved since the last commit is
    gone. This is the way out of a working copy that will not commit, and the
    way to start a re-upload from the last known-good revision.
    """
    try:
        await api.call("problem.discardWorkingCopy", {"problemId": problem_id})
        return {"ok": True, "problem_id": problem_id}
    except Exception as error:
        return _fail(error, "problem.discardWorkingCopy")


@mcp.tool()
async def polygon_commit(
    problem_id: int, minor_changes: bool = False, message: str = ""
) -> dict[str, Any]:
    """Commit the working copy. → `problem.commitChanges`

    Nothing saved by the tools above is visible to anyone else until this runs.
    `minor_changes=true` suppresses the email notification to the problem's
    other authors.

    Read `committed` rather than `ok`. Polygon answers a no-op with a
    *successful* envelope carrying `committed=false` and the message "No
    changes", and it reports a working copy that fell behind the repository as
    `conflict_occurred=true` — so `ok: true` means the call went through, not
    that a revision was created. On a conflict, `polygon_update_working_copy`
    and then commit again. A missing field is reported false: this tool does
    not claim a commit Polygon did not confirm.
    """
    try:
        result = await api.call(
            "problem.commitChanges",
            {
                "problemId": problem_id,
                "minorChanges": minor_changes,
                "message": message or None,
            },
        )
        commit_result = result if isinstance(result, dict) else {}
        return {
            "ok": True,
            "committed": bool(commit_result.get("committed")),
            "conflict_occurred": bool(commit_result.get("conflictOccurred")),
            "message": str(commit_result.get("message") or ""),
            "commit_result": result,
        }
    except Exception as error:
        return _fail(error, "problem.commitChanges")


@mcp.tool()
async def polygon_build_package(
    problem_id: int, full: bool = False, verify: bool = True
) -> dict[str, Any]:
    """Start building a package. → `problem.buildPackage`

    Returns as soon as the build is queued, not when it finishes — poll
    `polygon_packages` for the `state` to go `PENDING` → `RUNNING` → `READY`
    or `FAILED`. `verify=true` runs every solution on every test and checks
    the tags actually hold, which is the point of building one at all. `full`
    additionally produces the linux and windows packages, not just the
    standard one.
    """
    try:
        await api.call(
            "problem.buildPackage",
            {"problemId": problem_id, "full": full, "verify": verify},
        )
        return {"ok": True, "build_started": True, "full": full, "verify": verify}
    except Exception as error:
        return _fail(error, "problem.buildPackage")


@mcp.tool()
async def polygon_packages(problem_id: int) -> dict[str, Any]:
    """List the problem's packages. → `problem.packages`

    Each has `id`, `revision`, `creationTimeSeconds`, `state`
    (PENDING/RUNNING/READY/FAILED), `comment` and `type`. This is how a build
    started by `polygon_build_package` is followed to its end; a FAILED
    package's `comment` says why.
    """
    try:
        result = await api.call("problem.packages", {"problemId": problem_id})
        return {"ok": True, "count": len(result or []), "packages": result or []}
    except Exception as error:
        return _fail(error, "problem.packages")


def run() -> None:
    mcp.run()
