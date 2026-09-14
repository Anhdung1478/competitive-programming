"""Exercise the Polygon server against a fake Polygon, without network access.

Everything here runs through `httpx.MockTransport`, so the whole client — the
signature, the read/write verb split, the pacing, the one retry — is the real
code, and only the socket is fake.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

import httpx
import pytest

from polygon_mcp import server
from polygon_mcp.api import PLAIN_TEXT_METHODS, PolygonApi, WRITE_METHODS, sign
from polygon_mcp.config import Config, PolygonError, resolve_local_path

API_KEY = "polygon-key-11112222"
API_SECRET = "polygon-secret-33334444"

# A reply that makes the fake transport raise instead of answering.
TIMEOUT = "<<timeout>>"


# ----------------------------------------------------------------- the fake


@dataclass
class Call:
    method: str
    params: dict[str, str]
    verb: str


def ok(result: Any) -> tuple[int, Any]:
    return 200, {"status": "OK", "result": result}


def failed(comment: str) -> tuple[int, Any]:
    return 200, {"status": "FAILED", "comment": comment}


class FakePolygon:
    """Replays canned replies and records what was sent.

    Replies are consumed in order and the last one repeats, so a retry test
    reads `FakePolygon((503, "busy"), ok({}))` as "fails once, then works".
    """

    def __init__(self, *replies: tuple[int, Any]):
        self.replies = list(replies) or [ok(None)]
        self.calls: list[Call] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            params = dict(request.url.params)
        else:
            params = dict(parse_qsl(request.content.decode(), keep_blank_values=True))
        self.calls.append(
            Call(
                method=request.url.path.rsplit("/", 1)[-1],
                params=params,
                verb=request.method,
            )
        )
        status, payload = (
            self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        )
        if payload is TIMEOUT:
            raise httpx.ReadTimeout("timed out", request=request)
        if isinstance(payload, (dict, list)):
            return httpx.Response(status, json=payload)
        return httpx.Response(status, text=str(payload))

    @property
    def last(self) -> Call:
        return self.calls[-1]


def make_api(fake: FakePolygon, sleeps: list[float] | None = None, **overrides):
    overrides.setdefault("min_interval", 0.0)
    config = Config(
        api_key=API_KEY,
        api_secret=API_SECRET,
        base_url="https://polygon.test/api/",
        **overrides,
    )

    async def record_sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    return config, PolygonApi(
        config, transport=httpx.MockTransport(fake), sleep=record_sleep
    )


@pytest.fixture
def polygon(monkeypatch):
    """Wire one fake Polygon into the server module for a single test."""

    def install(*replies, **overrides) -> FakePolygon:
        fake = FakePolygon(*replies)
        config, api = make_api(fake, **overrides)
        monkeypatch.setattr(server, "config", config)
        monkeypatch.setattr(server, "api", api)
        return fake

    return install


# ------------------------------------------------------------------- signing


def test_signature_has_the_documented_shape():
    signed = sign(
        "problem.info",
        {"problemId": 42},
        api_key=API_KEY,
        secret=API_SECRET,
        rand="123456",
        now=1700000000,
    )
    assert signed["apiSig"][:6] == "123456"
    assert len(signed["apiSig"]) == 6 + 128
    int(signed["apiSig"][6:], 16)  # the tail is hexadecimal
    assert signed["apiKey"] == API_KEY
    assert signed["time"] == "1700000000"


def test_signature_matches_an_independently_computed_hash():
    # The documented string: <rand>/<method>?k=v&…#<secret>, every parameter
    # including apiKey and time, sorted by name then value.
    signed = sign(
        "problem.saveTest",
        {"problemId": 42, "testset": "tests", "testIndex": 1},
        api_key="KEY",
        secret="SEC",
        rand="abcdef",
        now=1000,
    )
    query = "apiKey=KEY&problemId=42&testIndex=1&testset=tests&time=1000"
    expected = hashlib.sha512(
        f"abcdef/problem.saveTest?{query}#SEC".encode()
    ).hexdigest()
    assert signed["apiSig"] == "abcdef" + expected


def test_signature_sorts_parameters_regardless_of_insertion_order():
    forward = sign(
        "problems.list",
        {"name": "a", "owner": "b", "showDeleted": False},
        api_key="K", secret="S", rand="000000", now=1,
    )
    backward = sign(
        "problems.list",
        {"showDeleted": False, "owner": "b", "name": "a"},
        api_key="K", secret="S", rand="000000", now=1,
    )
    assert forward["apiSig"] == backward["apiSig"]


def test_signature_is_deterministic_for_a_fixed_rand_and_time():
    kwargs = dict(api_key="K", secret="S", rand="aaaaaa", now=7)
    assert sign("problem.info", {"problemId": 1}, **kwargs) == sign(
        "problem.info", {"problemId": 1}, **kwargs
    )


def test_a_different_secret_changes_the_signature():
    kwargs = dict(api_key="K", rand="aaaaaa", now=7)
    one = sign("problem.info", {"problemId": 1}, secret="S1", **kwargs)
    two = sign("problem.info", {"problemId": 1}, secret="S2", **kwargs)
    assert one["apiSig"] != two["apiSig"]


def test_a_whole_numbered_float_is_sent_as_an_integer():
    # `test_points: float | None` means an argument of 10 arrives as 10.0 once
    # the tool call has been coerced to its annotated type.
    signed = sign(
        "problem.saveTest",
        {"testPoints": 10.0, "testIndex": 1},
        api_key="K", secret="S", rand="000000", now=1,
    )
    assert signed["testPoints"] == "10"
    assert signed["testIndex"] == "1"


def test_a_fractional_float_keeps_its_fraction():
    signed = sign(
        "problem.saveTest",
        {"testPoints": 2.5},
        api_key="K", secret="S", rand="000000", now=1,
    )
    assert signed["testPoints"] == "2.5"


def test_booleans_are_signed_as_they_are_sent():
    signed = sign(
        "problem.enablePoints",
        {"enable": True},
        api_key="K", secret="S", rand="000000", now=1,
    )
    assert signed["enable"] == "true"
    query = "apiKey=K&enable=true&time=1"
    expected = hashlib.sha512(
        f"000000/problem.enablePoints?{query}#S".encode()
    ).hexdigest()
    assert signed["apiSig"] == "000000" + expected


async def test_the_file_content_is_signed_like_any_other_parameter():
    # Polygon takes uploads as ordinary form fields, not multipart parts, so
    # the whole source text participates in the hash.
    fake = FakePolygon(ok(None))
    _, api = make_api(fake)
    source = "int main() { return 0; }\n"
    await api.call(
        "problem.saveSolution",
        {"problemId": 1, "name": "sol.cpp", "file": source, "tag": "MA"},
    )
    sent = fake.last.params
    assert sent["file"] == source
    unsigned = {k: v for k, v in sent.items() if k != "apiSig"}
    query = "&".join(f"{k}={v}" for k, v in sorted(unsigned.items()))
    rand = sent["apiSig"][:6]
    expected = hashlib.sha512(
        f"{rand}/problem.saveSolution?{query}#{API_SECRET}".encode()
    ).hexdigest()
    assert sent["apiSig"] == rand + expected


# ---------------------------------------------------------------- transport


async def test_reads_go_as_get_and_writes_as_post():
    fake = FakePolygon(ok([]))
    _, api = make_api(fake)
    await api.call("problem.info", {"problemId": 1})
    assert fake.last.verb == "GET"
    await api.call("problem.enablePoints", {"problemId": 1, "enable": True})
    assert fake.last.verb == "POST"


def test_every_write_method_is_a_save_set_or_lifecycle_call():
    # A read wrongly listed as a write would put a statement in a query string;
    # a write wrongly left out would do the same to a solution's source.
    assert not (WRITE_METHODS & PLAIN_TEXT_METHODS)
    for method in WRITE_METHODS:
        tail = method.split(".", 1)[1]
        assert tail.startswith(("save", "set", "enable", "update", "edit")) or tail in {
            "create",
            "commitChanges",
            "discardWorkingCopy",
            "buildPackage",
            "deleteTest",
        }, method


async def test_none_parameters_are_dropped_rather_than_sent_empty():
    fake = FakePolygon(ok(None))
    _, api = make_api(fake)
    await api.call(
        "problem.updateInfo",
        {"problemId": 1, "timeLimit": 2000, "interactive": None, "inputFile": None},
    )
    assert "interactive" not in fake.last.params
    assert "inputFile" not in fake.last.params
    assert fake.last.params["timeLimit"] == "2000"


async def test_a_failed_status_becomes_an_error_naming_the_method():
    fake = FakePolygon(failed("problemId: Problem not found"))
    _, api = make_api(fake)
    with pytest.raises(PolygonError) as caught:
        await api.call("problem.info", {"problemId": 9})
    assert "Problem not found" in str(caught.value)
    assert caught.value.method == "problem.info"


async def test_a_4xx_is_not_retried():
    fake = FakePolygon((403, "<html>Forbidden</html>"))
    _, api = make_api(fake)
    with pytest.raises(PolygonError, match="HTTP 403"):
        await api.call("problem.info", {"problemId": 1})
    assert len(fake.calls) == 1


async def test_a_503_is_retried_once_and_then_succeeds():
    sleeps: list[float] = []
    fake = FakePolygon((503, "<html>busy</html>"), ok({"timeLimit": 2000}))
    _, api = make_api(fake, sleeps=sleeps)
    assert await api.call("problem.info", {"problemId": 1}) == {"timeLimit": 2000}
    assert len(fake.calls) == 2
    assert sleeps == [1.0]


async def test_the_retry_is_signed_again_rather_than_replayed():
    # The signature commits to `time`, and Polygon refuses a request whose time
    # is more than five minutes off its clock, so a replay would eventually 403.
    fake = FakePolygon((503, "busy"), ok(None))
    _, api = make_api(fake)
    await api.call("problem.info", {"problemId": 1})
    first, second = fake.calls
    assert first.params["apiSig"] != second.params["apiSig"]


async def test_a_second_503_gives_up():
    fake = FakePolygon((503, "<html>busy</html>"))
    _, api = make_api(fake)
    with pytest.raises(PolygonError, match="HTTP 503"):
        await api.call("problem.info", {"problemId": 1})
    assert len(fake.calls) == 2


async def test_a_timeout_is_retried_once():
    sleeps: list[float] = []
    fake = FakePolygon((0, TIMEOUT), ok("fine"))
    _, api = make_api(fake, sleeps=sleeps)
    assert await api.call("problem.info", {"problemId": 1}) == "fine"
    assert len(fake.calls) == 2 and sleeps == [1.0]


async def test_a_persistent_timeout_reports_without_the_request_url():
    fake = FakePolygon((0, TIMEOUT))
    _, api = make_api(fake)
    with pytest.raises(PolygonError) as caught:
        await api.call("problem.info", {"problemId": 1})
    # httpx spells the request URL into its own exceptions, and a signed GET's
    # URL carries apiKey — so the message must be ours, not httpx's.
    assert API_KEY not in str(caught.value)
    assert "did not answer" in str(caught.value)


async def test_an_unreachable_host_reports_without_the_request_url():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    config = Config(
        api_key=API_KEY,
        api_secret=API_SECRET,
        base_url="https://polygon.test/api/",
        min_interval=0.0,
    )

    async def no_sleep(seconds: float) -> None:
        return None

    api = PolygonApi(
        config, transport=httpx.MockTransport(refuse), sleep=no_sleep
    )
    with pytest.raises(PolygonError) as caught:
        await api.call("problem.info", {"problemId": 1})
    assert API_KEY not in str(caught.value)
    assert "Could not reach Polygon" in str(caught.value)


async def test_requests_are_paced_by_the_minimum_interval():
    sleeps: list[float] = []
    fake = FakePolygon(ok(None))
    _, api = make_api(fake, sleeps=sleeps, min_interval=0.5)
    await api.call("problem.info", {"problemId": 1})
    await api.call("problem.info", {"problemId": 1})
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 0.5


async def test_a_plain_text_method_returns_its_body_verbatim():
    fake = FakePolygon((200, "gen_random 100 1 > $\ngen_max 200000 > $\n"))
    _, api = make_api(fake)
    script = await api.call("problem.script", {"problemId": 1, "testset": "tests"})
    assert script.startswith("gen_random 100 1")


async def test_a_plain_text_method_that_fails_still_reads_the_json_envelope():
    fake = FakePolygon(failed("testset: No such testset"))
    _, api = make_api(fake)
    with pytest.raises(PolygonError, match="No such testset"):
        await api.call("problem.script", {"problemId": 1, "testset": "nope"})


async def test_a_one_line_test_input_is_not_mistaken_for_json():
    fake = FakePolygon((200, "5"))
    _, api = make_api(fake)
    assert await api.call(
        "problem.testInput", {"problemId": 1, "testset": "tests", "testIndex": 1}
    ) == "5"


async def test_a_429_is_retried_with_a_doubling_backoff_and_then_succeeds():
    sleeps: list[float] = []
    fake = FakePolygon((429, "slow down"), (429, "slow down"), ok("fine"))
    _, api = make_api(fake, sleeps=sleeps)
    assert await api.call("problem.saveTest", {"problemId": 1}) == "fine"
    assert len(fake.calls) == 3
    assert sleeps == [2.0, 4.0]
    # Each attempt is signed afresh, as with the 5xx retry.
    assert len({c.params["apiSig"] for c in fake.calls}) == 3


async def test_a_429_honours_retry_after_and_caps_it():
    sleeps: list[float] = []
    replies = [
        httpx.Response(429, headers={"Retry-After": "7"}, text="slow down"),
        httpx.Response(429, headers={"Retry-After": "3600"}, text="slow down"),
        httpx.Response(200, json={"status": "OK", "result": None}),
    ]
    config = Config(
        api_key=API_KEY,
        api_secret=API_SECRET,
        base_url="https://polygon.test/api/",
        min_interval=0.0,
    )

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    api = PolygonApi(
        config,
        transport=httpx.MockTransport(lambda request: replies.pop(0)),
        sleep=record_sleep,
    )
    await api.call("problem.saveTest", {"problemId": 1})
    assert sleeps == [7.0, 60.0]


async def test_a_persistent_429_gives_up_saying_it_was_rate_limited():
    sleeps: list[float] = []
    fake = FakePolygon((429, "slow down"))
    _, api = make_api(fake, sleeps=sleeps)
    with pytest.raises(PolygonError) as caught:
        await api.call("problem.info", {"problemId": 1})
    message = str(caught.value)
    assert len(fake.calls) == 4 and sleeps == [2.0, 4.0, 8.0]
    assert caught.value.method == "problem.info"
    assert "problem.info" in message and "rate-limited" in message
    assert API_KEY not in message and "polygon.test" not in message


async def test_a_429_does_not_use_up_the_retry_a_503_is_owed():
    fake = FakePolygon((429, "slow"), (503, "busy"), ok("fine"))
    _, api = make_api(fake)
    assert await api.call("problem.info", {"problemId": 1}) == "fine"
    assert len(fake.calls) == 3


async def test_a_call_without_credentials_never_reaches_the_network():
    fake = FakePolygon(ok(None))
    config, api = make_api(fake)
    config.api_key = ""
    with pytest.raises(PolygonError, match="POLYGON_API_KEY"):
        await api.call("problem.info", {"problemId": 1})
    assert fake.calls == []


# ------------------------------------------------------------- the path guard


def test_a_path_inside_the_root_is_accepted(tmp_path: Path):
    target = tmp_path / "sol.cpp"
    target.write_text("int main(){}")
    assert resolve_local_path(str(target), tmp_path) == target.resolve()


def test_a_path_outside_the_root_is_refused(tmp_path: Path):
    root = tmp_path / "problem"
    root.mkdir()
    outside = tmp_path / "secrets.txt"
    outside.write_text("nope")
    with pytest.raises(PolygonError, match="outside POLYGON_MCP_ROOT"):
        resolve_local_path(str(outside), root)


def test_a_traversal_out_of_the_root_is_refused(tmp_path: Path):
    root = tmp_path / "problem"
    root.mkdir()
    (tmp_path / "secrets.txt").write_text("nope")
    with pytest.raises(PolygonError, match="outside POLYGON_MCP_ROOT"):
        resolve_local_path(str(root / ".." / "secrets.txt"), root)


def test_a_symlink_pointing_out_of_the_root_is_refused(tmp_path: Path):
    root = tmp_path / "problem"
    root.mkdir()
    (tmp_path / "secrets.txt").write_text("nope")
    (root / "link.txt").symlink_to(tmp_path / "secrets.txt")
    with pytest.raises(PolygonError, match="outside POLYGON_MCP_ROOT"):
        resolve_local_path(str(root / "link.txt"), root)


def test_no_root_refuses_every_path(tmp_path: Path):
    target = tmp_path / "sol.cpp"
    target.write_text("int main(){}")
    with pytest.raises(PolygonError, match="POLYGON_MCP_ROOT is not set"):
        resolve_local_path(str(target), None)


def test_an_unexpanded_root_is_refused_with_the_reason(tmp_path: Path):
    target = tmp_path / "sol.cpp"
    target.write_text("int main(){}")
    with pytest.raises(PolygonError, match=r"literally as \$\{POLYGON_MCP_ROOT\}"):
        resolve_local_path(str(target), None, ("POLYGON_MCP_ROOT",))


# ------------------------------------------- placeholders the client left in


def test_a_placeholder_key_counts_as_unset_and_is_recorded(monkeypatch):
    monkeypatch.setenv("POLYGON_API_KEY", "${POLYGON_API_KEY}")
    monkeypatch.setenv("POLYGON_API_SECRET", " ${POLYGON_API_SECRET} ")
    monkeypatch.delenv("POLYGON_MCP_ROOT", raising=False)
    config = Config.from_env()
    assert config.api_key == "" and config.api_secret == ""
    assert config.has_credentials is False
    assert config.unexpanded == ("POLYGON_API_KEY", "POLYGON_API_SECRET")


def test_a_placeholder_root_becomes_none(monkeypatch):
    monkeypatch.setenv("POLYGON_API_KEY", API_KEY)
    monkeypatch.setenv("POLYGON_API_SECRET", API_SECRET)
    monkeypatch.setenv("POLYGON_MCP_ROOT", "${POLYGON_MCP_ROOT}")
    monkeypatch.setenv("POLYGON_TIMEOUT", "${POLYGON_TIMEOUT}")
    config = Config.from_env()
    assert config.root is None
    assert config.timeout == 30.0
    assert config.has_credentials is True
    assert config.unexpanded == ("POLYGON_MCP_ROOT", "POLYGON_TIMEOUT")


def test_a_value_merely_containing_a_dollar_brace_is_kept(monkeypatch):
    monkeypatch.setenv("POLYGON_API_KEY", "abc${X}def")
    config = Config.from_env()
    assert config.api_key == "abc${X}def"
    assert "POLYGON_API_KEY" not in config.unexpanded


async def test_whoami_explains_placeholders_the_client_left_in(polygon):
    fake = polygon(ok([]))
    server.config.api_key = ""
    server.config.api_secret = ""
    server.config.unexpanded = ("POLYGON_API_KEY", "POLYGON_API_SECRET")
    result = await server.polygon_whoami()
    assert result["ok"] is False
    assert result["credentials_configured"] is False
    assert result["unexpanded_variables"] == ["POLYGON_API_KEY", "POLYGON_API_SECRET"]
    assert "literally as ${POLYGON_API_KEY}, ${POLYGON_API_SECRET}" in result["error"]
    assert "restart Claude Code" in result["error"]
    assert "another terminal" in result["error"]
    assert fake.calls == []


async def test_whoami_warns_about_a_placeholder_root_but_still_checks(polygon):
    fake = polygon(ok([]))
    server.config.unexpanded = ("POLYGON_MCP_ROOT",)
    result = await server.polygon_whoami()
    assert result["ok"] is True
    assert result["unexpanded_variables"] == ["POLYGON_MCP_ROOT"]
    assert "${POLYGON_MCP_ROOT}" in result["warning"]
    assert len(fake.calls) == 1


def test_a_missing_file_inside_the_root_says_so(tmp_path: Path):
    with pytest.raises(PolygonError, match="File not found"):
        resolve_local_path(str(tmp_path / "absent.cpp"), tmp_path)


async def test_a_tool_uploads_the_file_the_path_points_at(polygon, tmp_path: Path):
    source = tmp_path / "sol.cpp"
    source.write_text("int main(){ return 0; }\n")
    fake = polygon(ok(None), root=tmp_path)
    result = await server.polygon_save_solution(
        problem_id=1, name="sol.cpp", tag="MA", path=str(source)
    )
    assert result["ok"] is True
    assert fake.last.params["file"] == "int main(){ return 0; }\n"


async def test_a_tool_refuses_a_path_outside_the_root(polygon, tmp_path: Path):
    root = tmp_path / "problem"
    root.mkdir()
    outside = tmp_path / "id_rsa"
    outside.write_text("PRIVATE KEY")
    fake = polygon(ok(None), root=root)
    result = await server.polygon_save_solution(
        problem_id=1, name="sol.cpp", tag="MA", path=str(outside)
    )
    assert result["ok"] is False
    assert "outside POLYGON_MCP_ROOT" in result["error"]
    assert fake.calls == []  # nothing was sent, and nothing was read


async def test_an_unreadable_file_inside_the_root_is_a_failure_not_a_traceback(
    polygon, tmp_path: Path, monkeypatch
):
    # Passing the root check is not permission to read. Running as root makes
    # chmod 000 unenforceable, so the failure is injected at the read instead.
    source = tmp_path / "sol.cpp"
    source.write_text("int main(){}")

    def refuse(self, *args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "read_text", refuse)
    fake = polygon(ok(None), root=tmp_path)
    result = await server.polygon_save_solution(
        problem_id=1, name="sol.cpp", tag="MA", path=str(source)
    )
    assert result["ok"] is False
    assert "Permission denied" in result["error"]
    assert fake.calls == []


async def test_a_tool_refuses_content_and_path_together(polygon, tmp_path: Path):
    source = tmp_path / "sol.cpp"
    source.write_text("x")
    polygon(ok(None), root=tmp_path)
    result = await server.polygon_save_solution(
        problem_id=1, name="s.cpp", tag="OK", content="y", path=str(source)
    )
    assert result["ok"] is False and "not both" in result["error"]


# ------------------------------------------------------------ tool behaviour


async def test_whoami_summarises_the_visible_problems(polygon):
    polygon(ok([{"id": 1, "name": "a-plus-b", "owner": "me"}]))
    result = await server.polygon_whoami()
    assert result["ok"] is True
    assert result["problem_count"] == 1
    assert result["first_problems"][0]["name"] == "a-plus-b"


async def test_whoami_without_credentials_explains_what_to_set(polygon):
    fake = polygon(ok([]))
    server.config.api_secret = ""
    result = await server.polygon_whoami()
    assert result["ok"] is False
    assert "POLYGON_API_SECRET" in result["error"]
    assert fake.calls == []


async def test_a_failed_reply_becomes_the_documented_failure_shape(polygon):
    polygon(failed("problemId: Problem not found"))
    result = await server.polygon_problem_info(problem_id=9)
    assert result == {
        "ok": False,
        "error": "problemId: Problem not found",
        "method": "problem.info",
    }


async def test_an_http_error_becomes_the_same_shape(polygon):
    polygon((404, "<html>nope</html>"))
    result = await server.polygon_problem_info(problem_id=9)
    assert result["ok"] is False
    assert "HTTP 404" in result["error"]
    assert result["method"] == "problem.info"


async def test_an_unknown_solution_tag_is_refused_before_a_request(polygon):
    fake = polygon(ok(None))
    result = await server.polygon_save_solution(
        problem_id=1, name="s.cpp", tag="AC", content="x"
    )
    assert result["ok"] is False and "must be one of" in result["error"]
    assert fake.calls == []


async def test_an_unknown_file_type_is_refused_before_a_request(polygon):
    fake = polygon(ok(None))
    result = await server.polygon_save_file(
        problem_id=1, file_type="binary", name="x", content="y"
    )
    assert result["ok"] is False and "must be one of" in result["error"]
    assert fake.calls == []


async def test_update_info_leaves_omitted_fields_alone(polygon):
    # Naming one limit must not silently clear `interactive` or the file names.
    fake = polygon(ok(None))
    await server.polygon_problem_update_info(problem_id=1, time_limit_ms=2000)
    sent = fake.last.params
    assert sent["timeLimit"] == "2000"
    assert not {"interactive", "wellFormed", "inputFile", "outputFile"} & sent.keys()


async def test_tags_and_dependencies_are_comma_joined(polygon):
    fake = polygon(ok(None))
    await server.polygon_save_tags(problem_id=1, tags=["dp", "graphs"])
    assert fake.last.params["tags"] == "dp,graphs"

    fake = polygon(ok(None))
    await server.polygon_save_test_group(
        problem_id=1,
        testset="tests",
        group="3",
        points_policy="COMPLETE_GROUP",
        feedback_policy="ICPC",
        dependencies=["1", "2"],
    )
    assert fake.last.params["dependencies"] == "1,2"
    assert fake.last.params["pointsPolicy"] == "COMPLETE_GROUP"


async def test_set_test_group_sends_one_comma_separated_index_list(polygon):
    # The API's alternative to repeating `testIndex`, which a signed request
    # built from a parameter mapping cannot express — the same form
    # `polygon_delete_test` already uses.
    fake = polygon(ok(None))
    await server.polygon_set_test_group(
        problem_id=1, testset="tests", test_group="g1", test_indices=[7]
    )
    assert fake.last.params["testIndices"] == "7"
    assert fake.last.params["testGroup"] == "g1"
    # It names a group and indices and nothing else: there is no way for it
    # to disturb a script-generated test's input, which is the whole reason
    # the upload skill assigns groups with this rather than with `saveTest`.
    assert "testInput" not in fake.last.params


async def test_set_test_group_refuses_an_empty_index_list_before_the_request(polygon):
    fake = polygon(ok(None))
    result = await server.polygon_set_test_group(
        problem_id=1, testset="tests", test_group="g1", test_indices=[]
    )
    assert result["ok"] is False
    assert "at least one test" in result["error"]
    assert fake.calls == []


async def test_a_standard_checker_name_is_passed_through_untouched(polygon):
    fake = polygon(ok(None))
    await server.polygon_set_checker(problem_id=1, name="std::rcmp6.cpp")
    assert fake.last.params["checker"] == "std::rcmp6.cpp"


async def test_the_script_tool_returns_the_plain_text_body(polygon):
    polygon((200, "gen 1 2 > $\n"))
    result = await server.polygon_script(problem_id=1)
    assert result["ok"] is True and result["script"] == "gen 1 2 > $\n"


# ------------------------------------------------------------ commit results


async def test_a_real_commit_is_reported_as_committed(polygon):
    polygon(ok({"committed": True, "conflictOccurred": False, "message": "Committed"}))
    result = await server.polygon_commit(problem_id=1, message="tests")
    assert result["ok"] is True
    assert result["committed"] is True
    assert result["conflict_occurred"] is False
    assert result["message"] == "Committed"


async def test_a_no_op_commit_is_not_reported_as_a_commit(polygon):
    # The envelope is OK, so `ok` stays true — but nothing was committed, and
    # a caller that reads only `ok` would go on to build a package from the
    # previous revision.
    polygon(
        ok({"committed": False, "conflictOccurred": False, "message": "No changes"})
    )
    result = await server.polygon_commit(problem_id=1)
    assert result["ok"] is True
    assert result["committed"] is False
    assert result["message"] == "No changes"


async def test_a_conflict_during_commit_is_surfaced(polygon):
    polygon(
        ok(
            {
                "committed": False,
                "conflictOccurred": True,
                "message": "Conflict occurred while updating working copy",
            }
        )
    )
    result = await server.polygon_commit(problem_id=1)
    assert result["ok"] is True
    assert result["committed"] is False
    assert result["conflict_occurred"] is True
    assert "Conflict" in result["message"]


async def test_a_commit_result_polygon_did_not_send_is_not_invented(polygon):
    # An OK envelope with no CommitResult in it says nothing about whether a
    # revision was created, so nothing is claimed.
    polygon(ok(None))
    result = await server.polygon_commit(problem_id=1)
    assert result["ok"] is True
    assert result["committed"] is False
    assert result["commit_result"] is None


# ------------------------------------------------------------------- access


async def test_set_access_rejects_owner_before_a_request(polygon):
    # Polygon does not let this method assign ownership, so the tool offers
    # READ, WRITE and NONE only.
    fake = polygon(ok(None))
    result = await server.polygon_set_access(
        problem_id=1, login="codeforces", access="OWNER"
    )
    assert result["ok"] is False and "must be one of" in result["error"]
    assert fake.calls == []


async def test_a_400_carrying_a_failed_envelope_reports_polygons_comment(polygon):
    # setAccess answers an unknown user with HTTP 400 *and* a FAILED envelope.
    # The envelope has to be read before the status code, or the caller gets
    # "HTTP 400" instead of the reason.
    polygon((400, {"status": "FAILED", "comment": "login: No such user"}))
    result = await server.polygon_set_access(
        problem_id=1, login="nosuchuser", access="READ"
    )
    assert result["ok"] is False
    assert result["error"] == "login: No such user"
    assert result["method"] == "problem.setAccess"


# ----------------------------------------------------------- test deletion


async def test_a_refused_deletion_keeps_polygons_structured_details(polygon):
    # deleteTest reports *which* tests it refused inside a FAILED envelope's
    # `result`. Dropping it would leave the caller with only the comment.
    polygon(
        (
            200,
            {
                "status": "FAILED",
                "comment": "Some tests can not be deleted.",
                "result": {
                    "failures": [
                        {
                            "index": 4,
                            "reason": "FREEMARKER_SCRIPT_TEST",
                            "message": "Test 4 is generated by the script.",
                        }
                    ]
                },
            },
        )
    )
    result = await server.polygon_delete_test(
        problem_id=1, testset="tests", test_index=4
    )
    assert result["ok"] is False
    assert result["error"] == "Some tests can not be deleted."
    assert result["details"]["failures"][0]["reason"] == "FREEMARKER_SCRIPT_TEST"


async def test_a_failure_without_details_carries_no_details_key(polygon):
    polygon(failed("testset: No such testset"))
    result = await server.polygon_delete_test(
        problem_id=1, testset="nope", test_index=1
    )
    assert result["ok"] is False and "details" not in result


# One happy path per tool, so every tool is known to reach the method its
# docstring names with the parameters Polygon documents.
TOOL_CASES: list[tuple[str, dict[str, Any], Any, str, dict[str, str]]] = [
    ("polygon_whoami", {}, [], "problems.list", {}),
    (
        "polygon_problems_list",
        {"owner": "me", "show_deleted": True},
        [{"id": 1}],
        "problems.list",
        {"owner": "me", "showDeleted": "true"},
    ),
    (
        "polygon_problem_create",
        {"name": "a-plus-b"},
        {"id": 7},
        "problem.create",
        {"name": "a-plus-b"},
    ),
    (
        "polygon_problem_info",
        {"problem_id": 7},
        {"timeLimit": 2000},
        "problem.info",
        {"problemId": "7"},
    ),
    (
        "polygon_problem_update_info",
        {"problem_id": 7, "time_limit_ms": 2000, "memory_limit_mb": 256},
        None,
        "problem.updateInfo",
        {"timeLimit": "2000", "memoryLimit": "256"},
    ),
    (
        "polygon_accesses",
        {"problem_id": 7},
        [{"login": "alice", "accessType": "READ"}],
        "problem.accesses",
        {"problemId": "7"},
    ),
    (
        "polygon_set_access",
        {"problem_id": 7, "login": "codeforces", "access": "READ"},
        None,
        "problem.setAccess",
        {"login": "codeforces", "accessType": "READ"},
    ),
    (
        "polygon_statements",
        {"problem_id": 7},
        {"english": {"name": "A plus B"}},
        "problem.statements",
        {"problemId": "7"},
    ),
    (
        "polygon_save_statement",
        {"problem_id": 7, "lang": "english", "legend": "Add $$$a$$$ and $$$b$$$."},
        None,
        "problem.saveStatement",
        {"lang": "english", "legend": "Add $$$a$$$ and $$$b$$$."},
    ),
    (
        "polygon_save_statement_resource",
        {"problem_id": 7, "name": "fig.svg", "content": "<svg/>"},
        None,
        "problem.saveStatementResource",
        {"name": "fig.svg", "file": "<svg/>"},
    ),
    (
        "polygon_files",
        {"problem_id": 7},
        {"sourceFiles": [], "resourceFiles": [], "auxFiles": []},
        "problem.files",
        {"problemId": "7"},
    ),
    (
        "polygon_save_file",
        {"problem_id": 7, "file_type": "source", "name": "val.cpp", "content": "x"},
        None,
        "problem.saveFile",
        {"type": "source", "name": "val.cpp", "file": "x"},
    ),
    (
        "polygon_set_validator",
        {"problem_id": 7, "name": "val.cpp"},
        None,
        "problem.setValidator",
        {"validator": "val.cpp"},
    ),
    (
        "polygon_set_checker",
        {"problem_id": 7, "name": "std::wcmp.cpp"},
        None,
        "problem.setChecker",
        {"checker": "std::wcmp.cpp"},
    ),
    (
        "polygon_set_interactor",
        {"problem_id": 7, "name": "inter.cpp"},
        None,
        "problem.setInteractor",
        {"interactor": "inter.cpp"},
    ),
    (
        "polygon_solutions",
        {"problem_id": 7},
        [{"name": "sol.cpp", "tag": "MA"}],
        "problem.solutions",
        {"problemId": "7"},
    ),
    (
        "polygon_save_solution",
        {"problem_id": 7, "name": "sol.cpp", "tag": "MA", "content": "int main(){}"},
        None,
        "problem.saveSolution",
        {"name": "sol.cpp", "tag": "MA", "file": "int main(){}"},
    ),
    (
        "polygon_script",
        {"problem_id": 7, "testset": "tests"},
        "gen 1 > $\n",
        "problem.script",
        {"testset": "tests"},
    ),
    (
        "polygon_save_script",
        {"problem_id": 7, "testset": "tests", "source": "gen 1 > $\n"},
        None,
        "problem.saveScript",
        {"testset": "tests", "source": "gen 1 > $\n"},
    ),
    (
        "polygon_tests",
        {"problem_id": 7, "testset": "tests"},
        [{"index": 1, "manual": True}],
        "problem.tests",
        {"testset": "tests"},
    ),
    (
        "polygon_save_test",
        {
            "problem_id": 7,
            "testset": "tests",
            "test_index": 3,
            "test_input": "1 2\n",
            "test_group": "2",
            "test_points": 10.0,  # what pydantic hands a `float | None` given 10
            "use_in_statements": True,
        },
        None,
        "problem.saveTest",
        {
            "testIndex": "3",
            "testInput": "1 2\n",
            "testGroup": "2",
            "testPoints": "10",
            "testUseInStatements": "true",
        },
    ),
    (
        "polygon_delete_test",
        {"problem_id": 7, "testset": "tests", "test_index": 3},
        None,
        "problem.deleteTest",
        {"testset": "tests", "testIndices": "3"},
    ),
    (
        "polygon_enable_groups",
        {"problem_id": 7, "testset": "tests", "enable": True},
        None,
        "problem.enableGroups",
        {"testset": "tests", "enable": "true"},
    ),
    (
        "polygon_enable_points",
        {"problem_id": 7, "enable": True},
        None,
        "problem.enablePoints",
        {"enable": "true"},
    ),
    (
        "polygon_set_test_group",
        {
            "problem_id": 7,
            "testset": "tests",
            "test_group": "g2",
            "test_indices": [3, 4, 5],
        },
        None,
        "problem.setTestGroup",
        {"testset": "tests", "testGroup": "g2", "testIndices": "3,4,5"},
    ),
    (
        "polygon_test_groups",
        {"problem_id": 7, "testset": "tests"},
        [{"name": "1", "pointsPolicy": "COMPLETE_GROUP"}],
        "problem.viewTestGroup",
        {"testset": "tests"},
    ),
    (
        "polygon_save_test_group",
        {
            "problem_id": 7,
            "testset": "tests",
            "group": "2",
            "points_policy": "EACH_TEST",
            "feedback_policy": "NONE",
        },
        None,
        "problem.saveTestGroup",
        {"group": "2", "pointsPolicy": "EACH_TEST", "feedbackPolicy": "NONE"},
    ),
    ("polygon_tags", {"problem_id": 7}, ["dp"], "problem.viewTags", {"problemId": "7"}),
    (
        "polygon_save_tags",
        {"problem_id": 7, "tags": ["dp", "trees"]},
        None,
        "problem.saveTags",
        {"tags": "dp,trees"},
    ),
    (
        "polygon_general_description",
        {"problem_id": 7},
        "Prepared for round 42.",
        "problem.viewGeneralDescription",
        {"problemId": "7"},
    ),
    (
        "polygon_save_general_description",
        {"problem_id": 7, "description": "Prepared for round 42."},
        None,
        "problem.saveGeneralDescription",
        {"description": "Prepared for round 42."},
    ),
    (
        "polygon_update_working_copy",
        {"problem_id": 7},
        None,
        "problem.updateWorkingCopy",
        {"problemId": "7"},
    ),
    (
        "polygon_discard_working_copy",
        {"problem_id": 7},
        None,
        "problem.discardWorkingCopy",
        {"problemId": "7"},
    ),
    (
        "polygon_commit",
        {"problem_id": 7, "minor_changes": True, "message": "tests"},
        # A real CommitResult: with `None` here the row would pass while the
        # tool claimed a commit Polygon never reported.
        {"committed": True, "conflictOccurred": False, "message": "Committed"},
        "problem.commitChanges",
        {"minorChanges": "true", "message": "tests"},
    ),
    (
        "polygon_build_package",
        {"problem_id": 7, "full": False, "verify": True},
        None,
        "problem.buildPackage",
        {"full": "false", "verify": "true"},
    ),
    (
        "polygon_packages",
        {"problem_id": 7},
        [{"id": 1, "state": "READY"}],
        "problem.packages",
        {"problemId": "7"},
    ),
]


@pytest.mark.parametrize(
    "tool_name,kwargs,result,method,expected",
    TOOL_CASES,
    ids=[case[0] for case in TOOL_CASES],
)
async def test_each_tool_calls_its_documented_method(
    polygon, tool_name, kwargs, result, method, expected
):
    reply = (200, result) if method in PLAIN_TEXT_METHODS else ok(result)
    fake = polygon(reply)
    answer = await getattr(server, tool_name)(**kwargs)
    assert answer["ok"] is True, answer
    assert fake.last.method == method
    assert fake.last.verb == ("POST" if method in WRITE_METHODS else "GET")
    for key, value in expected.items():
        assert fake.last.params[key] == value, (key, fake.last.params)


# A tool changes something if its name says so. The three that mutate without
# a verb in their name are listed instead.
_MUTATING_MARKERS = ("_save_", "_set_", "_enable_", "_delete_", "_update_", "_discard_")
_MUTATING_TOOLS = {"polygon_problem_create", "polygon_commit", "polygon_build_package"}


def test_every_tool_that_changes_something_is_declared_a_write():
    """A write missing from `WRITE_METHODS` silently goes out as GET.

    Nothing in the client catches that — it reads the same set to pick the
    verb — so the check has to come from outside it: from what the tool is
    called. A `polygon_set_access` left off the list would put a login in a
    URL, and a `polygon_save_solution` would put a whole source file there.
    """
    for tool_name, _, _, method, _ in TOOL_CASES:
        mutates = tool_name in _MUTATING_TOOLS or any(
            marker in tool_name for marker in _MUTATING_MARKERS
        )
        assert (method in WRITE_METHODS) is mutates, (tool_name, method)


def test_every_tool_registered_on_the_server_has_a_happy_path_test():
    registered = {
        name for name in dir(server) if name.startswith("polygon_")
    }
    covered = {case[0] for case in TOOL_CASES}
    assert registered - covered == set(), sorted(registered - covered)


# ------------------------------------------------------- credentials never leak


async def test_no_result_from_any_tool_contains_the_key_or_the_secret(polygon):
    """Grep every tool's JSON, on the happy path and on each failure path.

    The happy path is the least likely leak site; the dangerous one is an error
    that stringifies an httpx exception, because a signed GET's URL carries
    `apiKey`. So each tool is run against a canned success, a FAILED envelope,
    a 4xx, an exhausted 5xx and a timeout, and every result is searched.
    """

    failures: list[tuple[int, Any]] = [
        failed("Access denied: you need WRITE access"),
        (403, "<html>Forbidden</html>"),
        (503, "<html>Service Unavailable</html>"),
        (0, TIMEOUT),
    ]

    results: list[dict[str, Any]] = []
    for tool_name, kwargs, result, method, _ in TOOL_CASES:
        success = (200, result) if method in PLAIN_TEXT_METHODS else ok(result)
        for reply in [success, *failures]:
            polygon(reply)
            results.append(await getattr(server, tool_name)(**kwargs))

    blob = json.dumps(results)
    assert API_KEY not in blob
    assert API_SECRET not in blob
    # And the sentinels really would have been found had they been there.
    assert API_KEY in json.dumps({"leak": API_KEY})
    # Every failure path did produce a failure, so the grep was not vacuous.
    assert sum(1 for r in results if r["ok"] is False) == 4 * len(TOOL_CASES)


async def test_whoami_reports_the_credentials_without_showing_them(polygon):
    """whoami is the one tool whose whole job is to talk about the credentials."""
    polygon(ok([]))
    result = await server.polygon_whoami()
    blob = json.dumps(result)
    assert result["credentials_configured"] is True
    assert API_KEY not in blob and API_SECRET not in blob
