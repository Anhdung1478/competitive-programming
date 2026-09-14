"""Configuration, read from the environment the MCP client launches us with.

The credentials live only here. Nothing in this package writes them to disk,
puts them in a log line, or lets them out through a tool's return value —
`PolygonError` messages are composed by hand rather than stringified from an
exception, because the signed query string carries `apiKey` and httpx embeds
the request URL in the text of every error it raises.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

BASE_URL = "https://polygon.codeforces.com/api/"

# Polygon rejects a request whose `time` is more than five minutes off its own
# clock, so a slow retry has to be re-signed rather than replayed.
MAX_CLOCK_SKEW_SECONDS = 300


class PolygonError(Exception):
    """Anything a tool should report as `{"ok": false, "error": ...}`.

    Carries the API method so a failure names what was being attempted, which
    matters when a tool call is one step of a long upload flow. `details` holds
    whatever structured `result` a FAILED envelope carried alongside its
    comment — `problem.deleteTest` says which tests it refused that way, and a
    comment reading "Some tests can not be deleted." on its own is not enough
    for the caller to act on.
    """

    def __init__(self, message: str, method: str = "", details: object = None):
        super().__init__(message)
        self.method = method
        self.details = details


# A value that is nothing but `${NAME}` is a placeholder the MCP client failed
# to expand, not a value. The plugin's `.mcp.json` passes
# `"POLYGON_API_KEY": "${POLYGON_API_KEY}"`, and when that variable is absent
# from the environment Claude Code was started in — exported later, or in
# another terminal, or in a profile the launching shell never read — the
# server receives the eleven literal characters instead. Taken at face value
# that string counts as a configured key, whoami says so, and Polygon answers
# every call with "Incorrect API key", which points nowhere near the cause.
_PLACEHOLDER = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")


def is_unexpanded(value: str) -> bool:
    return bool(_PLACEHOLDER.match(value.strip()))


def _env(name: str, default: str = "", unexpanded: list[str] | None = None) -> str:
    """Read one variable, treating a blank or an unexpanded placeholder as unset.

    The name of a variable that arrived as a placeholder is appended to
    `unexpanded`, so the one tool that reports configuration can say *why*
    something looks unset rather than just that it is.
    """
    value = (os.environ.get(name) or "").strip()
    if is_unexpanded(value):
        if unexpanded is not None:
            unexpanded.append(name)
        return default
    return value or default


def unexpanded_explanation(names: tuple[str, ...] | list[str]) -> str:
    """The plain-language fix for variables that arrived as `${NAME}`.

    Only names are ever mentioned; a placeholder carries no secret, but this
    is the message a real value would be printed into by mistake, so it takes
    none.
    """
    listed = ", ".join(names)
    literal = ", ".join(f"${{{n}}}" for n in names)
    return (
        f"{listed} reached this server literally as {literal}: the MCP client "
        "could not expand them because they were not set in the environment "
        "Claude Code was launched from. Export them in that shell (or in the "
        "profile it reads) and restart Claude Code. Exporting them in another "
        "terminal, or after Claude Code started, changes nothing for the "
        "running server."
    )


@dataclass
class Config:
    api_key: str = ""
    api_secret: str = ""
    base_url: str = BASE_URL
    timeout: float = 30.0
    # The only directory a `path=` argument may point into. Unset means paths
    # are refused outright and content must be passed inline.
    root: Path | None = None
    # Floor on the gap between two requests, so a scripted upload of a few
    # hundred tests does not hammer Polygon.
    min_interval: float = 0.5
    # Names of the variables that arrived as a literal `${NAME}` and were
    # therefore treated as unset. Reported by whoami; never holds a value.
    unexpanded: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "Config":
        unexpanded: list[str] = []
        root = _env("POLYGON_MCP_ROOT", unexpanded=unexpanded)
        return cls(
            api_key=_env("POLYGON_API_KEY", unexpanded=unexpanded),
            api_secret=_env("POLYGON_API_SECRET", unexpanded=unexpanded),
            base_url=_env("POLYGON_BASE_URL", BASE_URL, unexpanded),
            timeout=float(_env("POLYGON_TIMEOUT", "30", unexpanded)),
            root=Path(root).expanduser() if root else None,
            min_interval=float(_env("POLYGON_MIN_INTERVAL", "0.5", unexpanded)),
            unexpanded=tuple(unexpanded),
        )

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key and self.api_secret)


def resolve_local_path(
    raw: str, root: Path | None, unexpanded: tuple[str, ...] = ()
) -> Path:
    """Resolve a caller-supplied path, or refuse it.

    A tool that accepts `path=` is a file-read primitive handed to a model, so
    it is confined to one directory the operator names with `POLYGON_MCP_ROOT`.
    Both sides are fully resolved before the comparison, so a symlink pointing
    out of the root is caught the same way `../..` is. With no root configured
    there is nothing to confine the read to, so every path is refused and the
    caller has to pass the content inline instead.

    `unexpanded` is `Config.unexpanded`: when the root is missing because it
    arrived as `${POLYGON_MCP_ROOT}`, "not set" alone would send the operator
    to check a variable they are sure they exported.
    """
    if root is None and "POLYGON_MCP_ROOT" in unexpanded:
        raise PolygonError(
            "Reading from a path is disabled: POLYGON_MCP_ROOT is not set. "
            + unexpanded_explanation(["POLYGON_MCP_ROOT"])
            + " Until then, pass the content inline instead."
        )
    if root is None:
        raise PolygonError(
            "Reading from a path is disabled: POLYGON_MCP_ROOT is not set. "
            "Set it to the problem directory this server may read, or pass the "
            "content inline instead."
        )
    resolved = Path(raw).expanduser()
    try:
        base = root.resolve(strict=True)
    except OSError:
        raise PolygonError(
            f"POLYGON_MCP_ROOT does not exist: {root}"
        ) from None
    try:
        resolved = resolved.resolve(strict=True)
    except OSError:
        raise PolygonError(f"File not found: {raw}") from None
    if resolved != base and base not in resolved.parents:
        raise PolygonError(
            f"Refusing to read {resolved}: it is outside POLYGON_MCP_ROOT "
            f"({base})."
        )
    if not resolved.is_file():
        raise PolygonError(f"Not a regular file: {resolved}")
    return resolved
