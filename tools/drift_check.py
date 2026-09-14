#!/usr/bin/env python3
"""Compare problem.json against the vnolymp statement.

The statement is not generated — templating the .tex would fight vnolymp — so
this is the guard that stops the two from disagreeing. Parsing is brace-aware
and comment-aware for robustness against well-formed LaTeX statements.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from tools.problem_meta import Problem, load

_SUBTASK = re.compile(r"\\subtask\{(?P<points>\d+)\}")


class DriftCheckError(ValueError):
    """Statement file is malformed, unreadable, or inconsistent with problem.json."""


def _strip_comments(text: str) -> str:
    """Remove LaTeX comments (% to EOL) but preserve escaped percents (\\%)."""
    result = []
    i = 0
    while i < len(text):
        if i + 1 < len(text) and text[i] == '\\' and text[i + 1] == '%':
            # Escaped percent - keep both characters
            result.append('\\%')
            i += 2
        elif text[i] == '%':
            # Unescaped percent - skip to EOL
            while i < len(text) and text[i] != '\n':
                i += 1
            # Keep the newline if present
            if i < len(text):
                result.append('\n')
                i += 1
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)


def _extract_subtasks_body(text: str) -> str:
    """Extract the content between \\begin{subtasks} and \\end{subtasks}."""
    begin_idx = text.find(r'\begin{subtasks}')
    if begin_idx == -1:
        return ""
    end_idx = text.find(r'\end{subtasks}', begin_idx)
    if end_idx == -1:
        return text[begin_idx + len(r'\begin{subtasks}'):]
    return text[begin_idx + len(r'\begin{subtasks}'):end_idx]


def _parse_keylist_braceaware(text: str) -> dict[str, str]:
    """Parse the vnolymp problem key list with brace-aware scanning.

    Handles keys like origin = {Đề chọn [Vòng 2]} correctly by tracking
    brace depth and only splitting on commas at depth 0.
    """
    # Find \begin{problem}[
    start = text.find(r'\begin{problem}[')
    if start == -1:
        return {}

    i = start + len(r'\begin{problem}[')
    depth = 0
    keylist_text = []

    # Scan forward until we find ] at depth 0
    while i < len(text):
        ch = text[i]
        if ch == '{':
            depth += 1
            keylist_text.append(ch)
        elif ch == '}':
            depth -= 1
            keylist_text.append(ch)
        elif ch == ']' and depth == 0:
            # End of key list
            break
        else:
            keylist_text.append(ch)
        i += 1

    # Parse the keylist, splitting on commas at depth 0
    keys: dict[str, str] = {}
    keylist = ''.join(keylist_text)

    depth = 0
    pairs = []
    current_pair = []

    for ch in keylist:
        if ch == '{':
            depth += 1
            current_pair.append(ch)
        elif ch == '}':
            depth -= 1
            current_pair.append(ch)
        elif ch == ',' and depth == 0:
            pairs.append(''.join(current_pair))
            current_pair = []
        else:
            current_pair.append(ch)

    if current_pair:
        pairs.append(''.join(current_pair))

    for pair in pairs:
        if "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        keys[name.strip()] = value.strip().strip("{}")

    return keys


def parse_tex(text: str) -> dict:
    # Strip comments first
    text_no_comments = _strip_comments(text)

    # Parse key list with brace awareness
    keys = _parse_keylist_braceaware(text_no_comments)

    def as_number(name, cast):
        try:
            return cast(keys[name])
        except (KeyError, ValueError, TypeError):
            return None

    def as_seconds(raw):
        # A Vietnamese statement writes 2.5 s as "2,5 giây", and an author
        # who wants that rendered writes `time = {2,5}` — the braces are
        # required, because keyval splits the key list on a bare comma.
        # `_parse_keylist_braceaware` keeps the braced value whole and
        # strips the braces, so what arrives here is "2,5"; `float("2,5")`
        # raises, and `check()` then reported "no `time` key", false drift
        # naming the wrong cause for a key that was present and correct.
        # Only the one-comma decimal form is read: "2,5,1" or "1,000" are not
        # a decimal comma anyone means, and guessing at them would let a
        # malformed limit through.
        #
        # The *unbraced* `time = 2,5` cannot be rescued here and is not
        # tried: the splitter (like keyval itself, in LaTeX) has already
        # read it as `time = 2` plus a stray `5`, so the value is "2" by the
        # time it arrives — and the statement LaTeX renders is wrong too.
        if raw is not None and re.fullmatch(r"\d+,\d+", raw.strip()):
            raw = raw.strip().replace(",", ".")
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None

    # Extract subtasks body and find subtask points only within it
    subtasks_body = _extract_subtasks_body(text_no_comments)
    subtask_points = [int(m.group("points")) for m in _SUBTASK.finditer(subtasks_body)]

    return {
        # `time` is a float, not an int. A 1.5 s or 2.5 s limit is routine,
        # and `int("1.5")` raises — which this function used to swallow into
        # `None`, making `check()` report "statement: no `time` key in
        # \begin{problem}" for a key that was present, correct, and read.
        # A drift guard emitting false drift, naming the wrong cause, is
        # the one failure mode this tool cannot have. `check()` was already
        # comparing against a float with a 1e-9 tolerance, so the float was
        # what the rest of the module expected all along.
        "time": as_seconds(keys.get("time")),
        # `memory` stays an int: vnolymp's memory key is whole megabytes,
        # and accepting "256.5 MB" would let a meaningless value through
        # rather than catching it.
        "memory": as_number("memory", int),
        "input": keys.get("input"),
        "output": keys.get("output"),
        "subtask_points": subtask_points,
    }


def _tex_seconds(seconds: float) -> str:
    """How to write `seconds` as a vnolymp `time` value.

    Always bare, with a decimal point for a fractional limit: `2.5`, not
    `{2,5}`. `writing-statements` recommends the bare form, because it is the
    one every reader of the key list — this module, a reviewer, the next
    tool — parses without special-casing. `parse_tex` still accepts the
    braced decimal comma an author may already have written, but the fix it
    suggests should not steer anyone back toward it.
    """
    return f"{seconds:g}"


def check(problem: Problem, tex_text: str) -> list[str]:
    tex = parse_tex(tex_text)
    issues: list[str] = []

    # The limit drifts are the ones that arise from an *edit* — a TL raised
    # in problem.json after a timing run, a statement retyped by hand — so
    # the finding says which of the two files to change. Without that, the
    # reader of "problem.json publishes 2.5 s, statement says 2 s" has to
    # already know that the statement's side is the `time` key of
    # `\begin{problem}` and problem.json's is `limits.time_ms_published`
    # (not `time_ms_computed`, which is the measured figure and is never
    # what the statement shows). Which side is *right* is not something
    # this tool can know, so both edits are named, each conditioned on it.
    # Appended after the existing text so the "time: problem.json publishes
    # ..." prefix callers match on is unchanged.
    published_s = problem.time_ms_published / 1000
    if tex["time"] is None:
        issues.append("statement: no `time` key in \\begin{problem}")
    elif abs(tex["time"] - published_s) > 1e-9:
        issues.append(
            f"time: problem.json publishes {published_s:g} s, "
            f"statement says {tex['time']:g} s — if problem.json is right, "
            f"set `time = {_tex_seconds(published_s)}` in the statement's "
            f"\\begin{{problem}} key list; if the statement is right, set "
            f"`limits.time_ms_published` to {round(tex['time'] * 1000)} in "
            f"problem.json"
        )

    if tex["memory"] != problem.memory_mb:
        issues.append(
            f"memory: problem.json says {problem.memory_mb} MB, "
            f"statement says {tex['memory']} MB — if problem.json is right, "
            f"set `memory = {problem.memory_mb}` in the statement's "
            f"\\begin{{problem}} key list"
            + (f"; if the statement is right, set `limits.memory_mb` to "
               f"{tex['memory']} in problem.json"
               if tex["memory"] is not None else "")
        )

    if tex["input"] != problem.input:
        issues.append(
            f"input: problem.json says {problem.input!r}, "
            f"statement says {tex['input']!r}"
        )
    if tex["output"] != problem.output:
        issues.append(
            f"output: problem.json says {problem.output!r}, "
            f"statement says {tex['output']!r}"
        )

    expected = [s.points for s in problem.subtasks]
    if tex["subtask_points"] != expected:
        issues.append(
            f"subtask points: problem.json says {expected}, "
            f"statement says {tex['subtask_points']}"
        )

    return issues


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: drift_check.py <problem-dir> <statement.tex>", file=sys.stderr)
        return 2
    problem = load(Path(argv[1]) / "problem.json")
    try:
        tex_text = Path(argv[2]).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DriftCheckError(f"statement file error: {exc}") from exc
    issues = check(problem, tex_text)
    if not issues:
        print("no drift between problem.json and the statement")
        return 0
    for issue in issues:
        print(f"DRIFT  {issue}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
