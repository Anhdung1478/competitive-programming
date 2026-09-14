#!/usr/bin/env python3
"""Lint Polygon statement fields against what Codeforces can actually render.

Codeforces turns a Polygon statement into HTML with its own, deliberately
small TeX converter: text mode understands only the commands listed in
Polygon's "Statements TeX manual", and math spans are handed to MathJax. A
statement that compiles cleanly under LaTeX can still come out broken on
the problem page, and nothing on the upload path says so — the statement
saves fine and only looks wrong once someone opens it. This linter is the
check that runs *before* `polygon_save_statement`, so the breakage is caught
while the text is still in front of the setter.

Every construct it flags was seen breaking a real upload:

* math inside a text command — `\\emph{nguyên vẹn sau $k$ lần xoá}`;
* text commands inside math — `$P(5) = \\texttt{aabaa}$`,
  `$\\text{lên } (0,+1)$`, and `$\\mathrm{dist}(u,v)$`, which made a whole
  statement unrenderable;
* a set literal split over several math spans — `$\\{2$--$3, 3$--$1\\}$`,
  where each span on its own has an unmatched brace;
* the legacy `$$$x$$$` delimiter, which problems created after 1 June 2021
  (rendered with MathJax) replace with `$x$` inline and `$$x$$` display;
* vnolymp macros such as `\\exmpfile` or `\\InputFile` that only mean
  something to the LaTeX template.

**It is a scanner, not a pile of regexes.** Brace nesting decides whether a
`$` sits inside `\\emph{...}`, and a single missed `$` flips the meaning of
everything after it, so the text is walked once, character by character,
with an explicit stack of open brace groups and a text/math mode. To stop
one missing `$` from inverting a whole field, a blank line (a paragraph
break, which math cannot span) closes a dangling math span and reports it.

**Decisions the manual leaves open.** `%` starts a comment to end of line,
as in LaTeX and MathJax, so commented-out macros are not reported; the first
argument of `\\url` and `\\href` is skipped verbatim because URLs carry `%`,
`#` and `_`. Bodies of `\\verb|...|` and `lstlisting` are never linted.
Names introduced by `\\def\\name` are accepted afterwards.

CLI:

    python3 -m tools.cf_statement_lint FILE...

A `.json` FILE must hold an object; each string value is linted as its own
field (non-string values are skipped). Any other file is linted whole. One
line per finding: `<file>[:<field>]:<line>:<col>: <severity>: <kind>: <msg>`.
Exit 0 with no errors (warnings allowed), 1 with any error, 2 on a usage
error, an unreadable file, or JSON that is not an object.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

# Text-mode commands the Polygon TeX manual lists, as bare names.
TEXT_COMMANDS: frozenset[str] = frozenset({
    "bf", "textbf", "it", "textit", "t", "tt", "texttt", "verb", "emph",
    "underline", "sout", "textsc",
    "tiny", "scriptsize", "small", "normalsize", "large", "Large", "LARGE",
    "huge", "Huge",
    "begin", "end", "item",
    "hline", "cline", "multicolumn", "multirow",
    "url", "href", "includegraphics", "def", "htmlPixelsInCm", "epigraph",
})

# Environments `\begin{...}` may open.
ENVIRONMENTS: frozenset[str] = frozenset({
    "itemize", "enumerate", "lstlisting", "center", "tabular",
})

# Control symbols (backslash + one non-letter) allowed in text mode.
TEXT_CONTROL_SYMBOLS: frozenset[str] = frozenset({"\\", "%", "$", "&", "_", "#", "{", "}"})

# Commands whose braced argument is styled text: a `$` inside it breaks.
TEXT_STYLE_COMMANDS: frozenset[str] = frozenset({
    "textbf", "textit", "texttt", "emph", "underline", "sout", "textsc",
})

# Declarations that restyle the rest of the enclosing group, `{\bf ...}`.
TEXT_STYLE_DECLARATIONS: frozenset[str] = frozenset({"bf", "it", "tt"})

# Seen breaking Codeforces' HTML rendering when used inside a math span.
TEXT_COMMANDS_FORBIDDEN_IN_MATH: frozenset[str] = frozenset({
    "text", "textrm", "textbf", "textit", "texttt", "textsf", "textsc",
    "emph", "underline", "mathrm", "operatorname", "mbox",
})

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    severity: str  # "error" | "warning"
    kind: str
    line: int
    col: int
    message: str


def _is_letter(ch: str) -> bool:
    return ("a" <= ch <= "z") or ("A" <= ch <= "Z")


@dataclass
class _MathSpan:
    start: int        # offset of the opening `$`
    width: int        # 1 inline, 2 display, 3 legacy
    plain: int = 0    # open minus close of `{` `}`
    plain_neg: bool = False  # a `}` arrived before its `{`
    escaped: int = 0  # `\{` minus `\}`


class _Scanner:
    def __init__(self, text: str) -> None:
        self.text = text
        self.n = len(text)
        self.findings: list[Finding] = []
        self.line_starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                self.line_starts.append(i + 1)
        # Text-mode brace groups; each entry is the owning style command or None.
        self.groups: list[str | None] = []
        self.pending_owner: str | None = None
        self.math: _MathSpan | None = None
        self.defined: set[str] = set()

    # -- reporting ------------------------------------------------------

    def _pos(self, offset: int) -> tuple[int, int]:
        lo, hi = 0, len(self.line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.line_starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1, offset - self.line_starts[lo] + 1

    def report(self, offset: int, kind: str, message: str, severity: str = ERROR) -> None:
        line, col = self._pos(offset)
        self.findings.append(Finding(severity, kind, line, col, message))

    # -- helpers --------------------------------------------------------

    def _skip_to_eol(self, i: int) -> int:
        end = self.text.find("\n", i)
        return self.n if end == -1 else end

    def _skip_spaces(self, i: int) -> int:
        while i < self.n and self.text[i] in " \t":
            i += 1
        return i

    def _read_braced(self, i: int) -> tuple[str, int] | None:
        """If text[i] (after spaces) is `{`, return (content, offset past `}`)."""
        j = self._skip_spaces(i)
        if j >= self.n or self.text[j] != "{":
            return None
        depth, k = 0, j
        while k < self.n:
            ch = self.text[k]
            if ch == "\\":
                k += 2
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return self.text[j + 1:k], k + 1
            k += 1
        return self.text[j + 1:], self.n

    def _blank_line_at(self, i: int) -> bool:
        """True when text[i] is a newline that starts a blank line."""
        j = i + 1
        while j < self.n and self.text[j] in " \t\r":
            j += 1
        return j < self.n and self.text[j] == "\n"

    def _in_styled_group(self) -> str | None:
        for owner in reversed(self.groups):
            if owner is not None:
                return owner
        return None

    # -- math spans -----------------------------------------------------

    def _open_math(self, i: int, width: int) -> None:
        owner = self._in_styled_group()
        if owner is not None:
            self.report(
                i, "math-in-text-command",
                f"math span inside the argument of \\{owner}; Codeforces does "
                f"not render math inside text commands — close \\{owner}{{...}} "
                "before the `$` and reopen it after",
            )
        self.math = _MathSpan(start=i, width=width)
        self.pending_owner = None

    def _close_math(self) -> None:
        span = self.math
        assert span is not None
        if span.escaped != 0:
            self.report(
                span.start, "unbalanced-brace-in-math",
                "`\\{` and `\\}` counts differ inside this math span; a set "
                "literal split across several `$...$` spans breaks on "
                "Codeforces — write it as one span",
            )
        if span.plain != 0 or span.plain_neg:
            self.report(
                span.start, "unbalanced-brace-in-math",
                "unbalanced `{`/`}` inside this math span",
            )
        self.math = None

    def _abandon_math(self) -> None:
        span = self.math
        assert span is not None
        delim = "$" * span.width
        self.report(
            span.start, "unbalanced-dollar",
            f"math span opened with `{delim}` is never closed",
        )
        self._close_math()

    def _scan_math_char(self, i: int) -> int:
        t, span = self.text, self.math
        assert span is not None
        ch = t[i]
        if ch == "$":
            run = 1
            while i + run < self.n and t[i + run] == "$":
                run += 1
            if span.width == 1:
                self._close_math()
                return i + 1
            if run >= span.width:
                self._close_math()
                return i + span.width
            return i + run
        if ch == "%":
            return self._skip_to_eol(i)
        if ch == "\n" and self._blank_line_at(i):
            self._abandon_math()
            return i + 1
        if ch == "{":
            span.plain += 1
            return i + 1
        if ch == "}":
            span.plain -= 1
            if span.plain < 0:
                span.plain_neg = True
            return i + 1
        if ch == "\\":
            if i + 1 >= self.n:
                return i + 1
            nxt = t[i + 1]
            if nxt == "{":
                span.escaped += 1
                return i + 2
            if nxt == "}":
                span.escaped -= 1
                return i + 2
            if not _is_letter(nxt):
                return i + 2
            j = i + 1
            while j < self.n and _is_letter(t[j]):
                j += 1
            name = t[i + 1:j]
            if name in TEXT_COMMANDS_FORBIDDEN_IN_MATH:
                self.report(
                    i, "text-command-in-math",
                    f"\\{name} inside a math span was observed to break "
                    "Codeforces' HTML rendering; use plain letters or italic "
                    "math, move \\textbf/\\texttt outside the span, or split "
                    "the span around the text",
                )
            return j
        return i + 1

    # -- text mode ------------------------------------------------------

    def _scan_command(self, i: int) -> int:
        t = self.text
        if i + 1 >= self.n:
            self.report(i, "unsupported-command", "lone backslash at end of text")
            return i + 1
        nxt = t[i + 1]
        if nxt in "[]()":
            self.report(
                i, "display-bracket",
                f"`\\{nxt}` math delimiter is not supported; use `$...$` "
                "inline or `$$...$$` display",
            )
            return i + 2
        if not _is_letter(nxt):
            if nxt == "\\":
                return i + 2  # line break; also covers `\\[2mm]`
            if nxt not in TEXT_CONTROL_SYMBOLS:
                self.report(
                    i, "unsupported-command",
                    f"`\\{nxt}` is not supported in Codeforces statement text",
                )
            return i + 2
        j = i + 1
        while j < self.n and _is_letter(t[j]):
            j += 1
        name = t[i + 1:j]

        if name == "verb":
            if j < self.n and t[j] == "*":
                j += 1
            if j >= self.n:
                return j
            delim = t[j]
            end = t.find(delim, j + 1)
            eol = self._skip_to_eol(j + 1)
            return eol if end == -1 or end > eol else end + 1

        if name in ("begin", "end"):
            arg = self._read_braced(j)
            if arg is None:
                return j
            env, after = arg
            env = env.strip()
            if name == "begin" and env not in ENVIRONMENTS:
                self.report(
                    i, "unsupported-environment",
                    f"environment `{env}` is not supported by Codeforces; "
                    f"allowed: {', '.join(sorted(ENVIRONMENTS))}",
                )
            if name == "begin" and env == "lstlisting":
                end = t.find(r"\end{lstlisting}", after)
                return self.n if end == -1 else end + len(r"\end{lstlisting}")
            return after

        if name in ("url", "href"):
            arg = self._read_braced(j)
            return j if arg is None else arg[1]

        if name == "def":
            k = self._skip_spaces(j)
            if k + 1 < self.n and t[k] == "\\":
                m = k + 1
                while m < self.n and _is_letter(t[m]):
                    m += 1
                if m > k + 1:
                    self.defined.add(t[k + 1:m])
                    return m
            return j

        if name not in TEXT_COMMANDS and name not in self.defined:
            self.report(
                i, "unsupported-command",
                f"\\{name} is not supported in Codeforces statement text",
            )
            return j

        if name in TEXT_STYLE_COMMANDS:
            self.pending_owner = name
        elif name in TEXT_STYLE_DECLARATIONS and self.groups and self.groups[-1] is None:
            self.groups[-1] = name
        return j

    def _scan_text_char(self, i: int) -> int:
        t = self.text
        ch = t[i]
        if ch == "\\":
            return self._scan_command(i)
        if ch == "%":
            return self._skip_to_eol(i)
        if ch == "$":
            run = 1
            while i + run < self.n and t[i + run] == "$":
                run += 1
            if run >= 3:
                self.report(
                    i, "legacy-dollars",
                    "`$$$` is the legacy delimiter; use `$x$` inline and "
                    "`$$x$$` display",
                )
                self._open_math(i, 3)
                return i + 3
            self._open_math(i, run)
            return i + run
        if ch == "{":
            self.groups.append(self.pending_owner)
            self.pending_owner = None
            return i + 1
        if ch == "}":
            if self.groups:
                self.groups.pop()
            return i + 1
        if ch not in " \t\r\n":
            self.pending_owner = None
        return i + 1

    def run(self) -> list[Finding]:
        i = 0
        while i < self.n:
            if self.math is not None:
                i = self._scan_math_char(i)
            else:
                i = self._scan_text_char(i)
        if self.math is not None:
            self._abandon_math()
        return sorted(self.findings, key=lambda f: (f.line, f.col))


def lint(text: str) -> list[Finding]:
    """Return every finding in one statement field, ordered by position."""
    return _Scanner(text).run()


def _lint_file(path: Path) -> list[tuple[str, Finding]]:
    """Lint one file; raise ValueError on unreadable input or a non-object JSON."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"{path}: cannot read: {exc}") from exc
    if path.suffix.lower() != ".json":
        return [(str(path), f) for f in lint(text)]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object of statement fields")
    out = []
    for field, value in data.items():
        if isinstance(value, str):
            out.extend((f"{path}:{field}", f) for f in lint(value))
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: cf_statement_lint.py FILE...", file=sys.stderr)
        return 2
    results: list[tuple[str, Finding]] = []
    for arg in argv[1:]:
        try:
            results.extend(_lint_file(Path(arg)))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    for where, f in results:
        print(f"{where}:{f.line}:{f.col}: {f.severity}: {f.kind}: {f.message}")
    return 1 if any(f.severity == ERROR for _, f in results) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
