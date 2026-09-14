"""Load `preferences.toml` — the setter pipeline's standing answers.

The six setting skills keep asking the same handful of judgement questions of
every problem: OI or ICPC, who proposes the subtask ladder, how many test
files a group gets, how many stress rounds to run. Answering them once, in a
file, is the point of this module.

**One file wins whole.** The lookup order is

1. `$CP_PREFERENCES` — an explicit path to a file. If it is set and does not
   load, that is an error; falling through to a different file would make a
   typo in the variable look like a working configuration.
2. `$XDG_CONFIG_HOME/competitive-programming/preferences.toml`, with
   `$XDG_CONFIG_HOME` defaulting to `~/.config`.
3. the `preferences.toml` shipped at the plugin root.

The first file that exists is used **entire** — there is no layering and no
merging in this version, so a user file must carry every key. A missing key
is an error for exactly that reason: with nothing underneath to fall back
to, a silently-defaulted key is drift, which is the thing this file exists
to prevent.

**Strict, in the same spirit as `problem_meta.load`.** An unknown section, an
unknown key, a value of the wrong type, or a value outside the closed set
raises `PreferencesError` naming the file, the `section.key`, and what was
allowed. The shipped file must load with zero errors; a test asserts it.

CLI:

    python3 -m tools.preferences [plugin-root]

prints the effective configuration as JSON with a `"source"` key saying which
file it came from, exit 0. `PreferencesError` goes to stderr with exit 2, the
same package-error code `package_status` uses. The optional `plugin-root`
argument only relocates step 3 — the environment still wins over it.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from tools.problem_meta import FORMAT_VALUES

PREFS_ENV = "CP_PREFERENCES"
XDG_ENV = "XDG_CONFIG_HOME"
CONFIG_DIR_NAME = "competitive-programming"
FILENAME = "preferences.toml"

# `format.default` is `problem.json`'s closed set plus one more answer this
# file can give that the package cannot: "I have not decided, ask me".
FORMAT_DEFAULT_VALUES = FORMAT_VALUES + ("ask",)
SUBTASKS_POLICY_VALUES = ("suggest", "user", "none", "ask")
MULTI_TEST_POLICY_VALUES = ("ask", "never", "always")
SUM_CONSTRAINTS_VALUES = ("ask", "never")
STATEMENT_LANGUAGE_VALUES = ("vietnamese", "english")
# Polygon problem names are lowercase latin letters, digits and dashes. The
# prefix is held to the same alphabet (and may be empty, meaning "no
# convention"), so prefix + problem.json's `name` is a name Polygon accepts
# whenever `name` itself is.
POLYGON_NAME_PREFIX_PATTERN = r"[a-z0-9-]*"


class PreferencesError(ValueError):
    """The preferences file is missing, malformed, or off-schema."""


@dataclass(frozen=True)
class FormatPrefs:
    default: str


@dataclass(frozen=True)
class SubtasksPrefs:
    policy: str


@dataclass(frozen=True)
class TestsPrefs:
    files_per_group: int


@dataclass(frozen=True)
class MultiTestPrefs:
    policy: str
    oi_default_t_max: int
    sum_constraints: str


@dataclass(frozen=True)
class StressPrefs:
    rounds: int


@dataclass(frozen=True)
class ZooPrefs:
    max_accepted: int
    include_presentation_error: bool
    include_obviously_wrong: bool


@dataclass(frozen=True)
class PolygonPrefs:
    statement_language: str
    notify_on_commit: bool
    grant_codeforces_read: bool
    name_prefix: str


@dataclass(frozen=True)
class Preferences:
    format: FormatPrefs
    subtasks: SubtasksPrefs
    tests: TestsPrefs
    multi_test: MultiTestPrefs
    stress: StressPrefs
    zoo: ZooPrefs
    polygon: PolygonPrefs
    source: Path


@dataclass(frozen=True)
class _Key:
    """What one key accepts: a closed set, a bounded integer, a boolean, or a
    free string constrained by a pattern.

    `str` exists for the one answer that is not a choice between a few
    values: `polygon.name_prefix` is whatever naming convention the user's
    Polygon account follows (`qhh-`, `qhhoj-`, ...). It is still validated,
    not taken on trust — the pattern is what Polygon itself accepts in a
    problem name, so a prefix it would refuse is caught when the file loads
    rather than at `problem.create`, half-way through an upload.
    """

    kind: str                    # "enum" | "int" | "bool" | "str"
    values: tuple[str, ...] = ()  # kind == "enum"
    minimum: int = 0              # kind == "int"
    pattern: str = ""             # kind == "str": a `re.fullmatch` pattern
    describe: str = ""            # kind == "str": the pattern, in words

    def allowed(self) -> str:
        if self.kind == "enum":
            return " | ".join(repr(v) for v in self.values)
        if self.kind == "int":
            return f"an integer >= {self.minimum}"
        if self.kind == "str":
            # Words, not the regex: the reader is hand-editing a TOML file,
            # and `^[a-z0-9-]*$` asks them to decode something the sentence
            # can just say.
            return f"a string of {self.describe}"
        return "true or false"


# The schema, and the only place a key name appears. `test_skill_docs` walks
# the shipped file against this and against the skills, so a key added here
# without a skill that reads it fails the suite rather than becoming the dead
# weight the fork accumulated.
SCHEMA: dict[str, tuple[type, dict[str, _Key]]] = {
    "format": (FormatPrefs, {
        "default": _Key("enum", values=FORMAT_DEFAULT_VALUES),
    }),
    "subtasks": (SubtasksPrefs, {
        "policy": _Key("enum", values=SUBTASKS_POLICY_VALUES),
    }),
    "tests": (TestsPrefs, {
        "files_per_group": _Key("int", minimum=1),
    }),
    "multi_test": (MultiTestPrefs, {
        "policy": _Key("enum", values=MULTI_TEST_POLICY_VALUES),
        "oi_default_t_max": _Key("int", minimum=1),
        "sum_constraints": _Key("enum", values=SUM_CONSTRAINTS_VALUES),
    }),
    "stress": (StressPrefs, {
        "rounds": _Key("int", minimum=1),
    }),
    "zoo": (ZooPrefs, {
        "max_accepted": _Key("int", minimum=0),
        "include_presentation_error": _Key("bool"),
        "include_obviously_wrong": _Key("bool"),
    }),
    "polygon": (PolygonPrefs, {
        "statement_language": _Key("enum", values=STATEMENT_LANGUAGE_VALUES),
        "notify_on_commit": _Key("bool"),
        "grant_codeforces_read": _Key("bool"),
        "name_prefix": _Key(
            "str", pattern=POLYGON_NAME_PREFIX_PATTERN,
            describe="lowercase latin letters, digits and dashes "
                     "(empty allowed)"),
    }),
}


def _type_name(value) -> str:
    """TOML's name for a Python value's type, so the message a hand-editor
    reads matches the document they are editing."""
    return {bool: "boolean", int: "integer", float: "float", str: "string",
            list: "array", dict: "table"}.get(type(value), type(value).__name__)


def _value(raw, spec: _Key, path: Path, what: str):
    if spec.kind == "bool":
        if not isinstance(raw, bool):
            raise PreferencesError(
                f"{path}: {what} is {raw!r} (TOML {_type_name(raw)}), "
                f"expected {spec.allowed()}")
        return raw
    if spec.kind == "int":
        # `bool` first: it is an `int` subclass in Python, so `rounds = true`
        # would otherwise load as 1 — the same trap `problem_meta._integer`
        # guards against.
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise PreferencesError(
                f"{path}: {what} is {raw!r} (TOML {_type_name(raw)}), "
                f"expected {spec.allowed()}")
        if raw < spec.minimum:
            raise PreferencesError(
                f"{path}: {what} is {raw}, expected {spec.allowed()}")
        return raw
    if spec.kind == "str":
        if not isinstance(raw, str):
            raise PreferencesError(
                f"{path}: {what} is {raw!r} (TOML {_type_name(raw)}), "
                f"expected {spec.allowed()}")
        # `fullmatch`, not `match` with `^...$`: `$` also matches before a
        # trailing newline, so `"qhh-\n"` would pass a `match` and reach
        # Polygon as a name it rejects.
        if re.fullmatch(spec.pattern, raw) is None:
            raise PreferencesError(
                f"{path}: {what} is {raw!r}, expected {spec.allowed()}")
        return raw
    if not isinstance(raw, str):
        raise PreferencesError(
            f"{path}: {what} is {raw!r} (TOML {_type_name(raw)}), "
            f"expected one of {spec.allowed()}")
    if raw not in spec.values:
        raise PreferencesError(
            f"{path}: {what} is {raw!r}, expected one of {spec.allowed()}")
    return raw


def parse(text: str, path: Path) -> Preferences:
    """Validate one file's text against `SCHEMA`, or raise `PreferencesError`."""
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise PreferencesError(f"{path}: not valid TOML: {exc}") from exc

    unknown = sorted(set(raw) - set(SCHEMA))
    if unknown:
        raise PreferencesError(
            f"{path}: unknown section {unknown[0]!r}; the sections are "
            f"{', '.join(sorted(SCHEMA))}")

    sections = {}
    for name, (cls, keys) in SCHEMA.items():
        table = raw.get(name)
        if table is None:
            raise PreferencesError(
                f"{path}: section [{name}] is missing. One file is used "
                f"whole — there is no layering, so every key must be present.")
        if not isinstance(table, dict):
            raise PreferencesError(
                f"{path}: [{name}] is a TOML {_type_name(table)}, expected a "
                f"table")
        stray = sorted(set(table) - set(keys))
        if stray:
            raise PreferencesError(
                f"{path}: unknown key {name}.{stray[0]!r}; [{name}] accepts "
                f"{', '.join(sorted(keys))}")
        values = {}
        for key, spec in keys.items():
            if key not in table:
                raise PreferencesError(
                    f"{path}: {name}.{key} is missing; expected "
                    f"{spec.allowed()}. One file is used whole — there is no "
                    f"layering, so every key must be present.")
            values[key] = _value(table[key], spec, path, f"{name}.{key}")
        sections[name] = cls(**values)

    return Preferences(source=path, **sections)


def shipped_path(plugin_root=None) -> Path:
    """The `preferences.toml` this repository ships, step 3 of the lookup."""
    root = Path(plugin_root) if plugin_root is not None \
        else Path(__file__).resolve().parents[1]
    return root / FILENAME


def _xdg_path() -> Path:
    base = os.environ.get(XDG_ENV) or ""
    root = Path(base) if base else Path.home() / ".config"
    return root / CONFIG_DIR_NAME / FILENAME


def resolve_path(plugin_root=None) -> Path:
    """The file `load` would read, without parsing it.

    Raises `PreferencesError` if `$CP_PREFERENCES` names something unreadable,
    or if nothing is found at all — never falls back past an explicit request.
    """
    explicit = os.environ.get(PREFS_ENV) or ""
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise PreferencesError(
                f"{path}: no such file (named by ${PREFS_ENV})")
        return path
    xdg = _xdg_path()
    if xdg.is_file():
        return xdg
    shipped = shipped_path(plugin_root)
    if shipped.is_file():
        return shipped
    raise PreferencesError(
        f"{shipped}: no such file — the shipped preferences are missing and "
        f"neither ${PREFS_ENV} nor {xdg} supplied one")


def load(plugin_root=None) -> Preferences:
    """The effective preferences, from the first file the lookup order finds."""
    path = resolve_path(plugin_root)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PreferencesError(f"{path}: cannot be read: {exc}") from exc
    return parse(text, path)


def as_json_object(prefs: Preferences) -> dict:
    obj = {name: asdict(getattr(prefs, name)) for name in SCHEMA}
    obj["source"] = str(prefs.source)
    return obj


def main(argv: list[str]) -> int:
    if len(argv) > 2:
        print("usage: preferences.py [plugin-root]", file=sys.stderr)
        return 2
    try:
        prefs = load(argv[1] if len(argv) == 2 else None)
    except PreferencesError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(as_json_object(prefs), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
