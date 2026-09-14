import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.cf_statement_lint import (
    ENVIRONMENTS,
    TEXT_COMMANDS,
    TEXT_COMMANDS_FORBIDDEN_IN_MATH,
    Finding,
    lint,
    main,
)


def kinds(text: str) -> list[str]:
    return [f.kind for f in lint(text)]


CLEAN_STATEMENT = r"""Cho một dãy gồm $n$ số nguyên $a_1, a_2, \ldots, a_n$ với
$1 \le n \le 2 \cdot 10^5$ và $|a_i| \le 10^9$. Hãy tính
$$\sum a_i$$
theo modulo $10^9 + 7$. Chi phí là 50\% tổng, giá \$5 --- rẻ.

\textbf{Lưu ý:} một thao tác gồm các bước sau:
\begin{itemize}
  \item chọn chỉ số $i$ sao cho $a_i > 0$;
  \item giảm $a_i$ đi \emph{đúng một} đơn vị.
\end{itemize}

\begin{center}
\includegraphics[width=6cm]{hinh1.png}
\end{center}

\begin{tabular}{|c|c|c|}
\hline
Nhóm & Điểm & Ràng buộc \\ \hline
1 & 40 & $n \le 10$ \\ \hline
2 & 60 & Không có ràng buộc gì thêm \\ \hline
\end{tabular}

Xem thêm tại \url{https://example.com/a_b%20c#x}.
"""


class TestConstants(unittest.TestCase):
    def test_exported_sets(self):
        for name in ("textbf", "texttt", "emph", "includegraphics", "item"):
            self.assertIn(name, TEXT_COMMANDS)
        self.assertEqual(ENVIRONMENTS, frozenset(
            {"itemize", "enumerate", "lstlisting", "center", "tabular"}))
        for name in ("text", "textrm", "textbf", "textit", "texttt", "emph",
                     "mathrm", "operatorname", "mbox"):
            self.assertIn(name, TEXT_COMMANDS_FORBIDDEN_IN_MATH)

    def test_finding_is_frozen(self):
        f = Finding("error", "k", 1, 1, "m")
        with self.assertRaises(Exception):
            f.line = 2  # type: ignore[misc]


class TestKinds(unittest.TestCase):
    def test_legacy_dollars(self):
        self.assertEqual(kinds("so $$$x$$$ la"), ["legacy-dollars"])
        self.assertEqual(kinds("so $x$ la"), [])

    def test_display_bracket(self):
        self.assertEqual(kinds(r"\[x^2\]"), ["display-bracket", "display-bracket"])
        self.assertEqual(kinds(r"\(x\)"), ["display-bracket", "display-bracket"])
        self.assertEqual(kinds(r"$$x^2$$"), [])

    def test_unbalanced_dollar(self):
        found = lint("dong 1 $x + y\n")
        self.assertEqual([f.kind for f in found], ["unbalanced-dollar"])
        self.assertEqual((found[0].line, found[0].col), (1, 8))
        self.assertEqual(kinds("mo $$x$ chua dong"), ["unbalanced-dollar"])
        self.assertEqual(kinds("$x$ va $$y$$"), [])

    def test_unbalanced_dollar_stops_at_paragraph_break(self):
        text = "Doan $x\n\nDoan sau $y$ va \\textbf{dam}."
        self.assertEqual(kinds(text), ["unbalanced-dollar"])

    def test_adjacent_inline_spans(self):
        self.assertEqual(kinds("$a$$b$"), [])

    def test_escaped_dollar_is_fine(self):
        self.assertEqual(kinds(r"gia \$5 va \$7"), [])

    def test_math_in_text_command(self):
        self.assertEqual(kinds(r"\textbf{gia tri $x$}"), ["math-in-text-command"])
        self.assertEqual(kinds(r"\texttt{a {b $x$}}"), ["math-in-text-command"])
        self.assertEqual(kinds(r"{\bf dam $x$}"), ["math-in-text-command"])
        self.assertEqual(kinds(r"\textbf{gia tri} $x$ {nhom $y$}"), [])

    def test_text_command_in_math(self):
        found = lint(r"$\operatorname{lcm}(a, b)$")
        self.assertEqual([f.kind for f in found], ["text-command-in-math"])
        self.assertIn("Codeforces", found[0].message)
        self.assertIn("split", found[0].message)
        self.assertEqual(kinds(r"$\max(a, b) + \sum_{i} x_i$"), [])

    def test_unbalanced_brace_in_math(self):
        self.assertEqual(kinds(r"$\{1, 2$"), ["unbalanced-brace-in-math"])
        self.assertEqual(kinds(r"$x^{2$"), ["unbalanced-brace-in-math"])
        self.assertEqual(kinds(r"$x}{$"), ["unbalanced-brace-in-math"])
        self.assertEqual(kinds(r"$\{1, 2\}$ va $x^{2}$"), [])

    def test_unsupported_command(self):
        found = lint(r"\InputFile Dong dau \exmpfile{a.in}{a.out} \Examples")
        self.assertEqual([f.kind for f in found], ["unsupported-command"] * 3)
        self.assertIn("\\InputFile", found[0].message)
        self.assertIn("\\exmpfile", found[1].message)
        self.assertEqual(kinds(r"\textit{nghieng} \\ \small nho \% \_ \# \& \{ \}"), [])

    def test_def_names_are_accepted(self):
        self.assertEqual(kinds(r"\def\N{10} gia tri \N"), [])

    def test_unsupported_environment(self):
        found = lint("\\begin{problem}\nx\n\\end{problem}")
        self.assertEqual([f.kind for f in found], ["unsupported-environment"])
        self.assertIn("problem", found[0].message)
        self.assertEqual(kinds("\\begin{enumerate}\\item a\\end{enumerate}"), [])

    def test_line_break_with_skip_is_not_bracket(self):
        self.assertEqual(kinds(r"dong 1 \\[2mm] dong 2"), [])

    def test_url_argument_is_verbatim(self):
        self.assertEqual(kinds(r"\url{http://x/a_b%20c#y} \href{http://x/%41}{day}"), [])

    def test_comments_are_skipped(self):
        self.assertEqual(kinds("dong % \\InputFile $\nhet"), [])


class TestFieldReport(unittest.TestCase):
    def test_math_inside_emph(self):
        self.assertIn("math-in-text-command",
                      kinds(r"\emph{nguyên vẹn sau $k$ lần xoá}"))

    def test_texttt_inside_math(self):
        self.assertIn("text-command-in-math", kinds(r"$P(5) = \texttt{aabaa}$"))

    def test_text_inside_math(self):
        self.assertIn("text-command-in-math", kinds(r"$\text{lên } (0,+1)$"))

    def test_mathrm_inside_math(self):
        self.assertIn("text-command-in-math", kinds(r"$\mathrm{dist}(u,v)$"))

    def test_set_literal_split_across_spans(self):
        found = kinds(r"$\{2$--$3, 3$--$1\}$")
        self.assertEqual(found, ["unbalanced-brace-in-math"] * 2)


class TestVerbatim(unittest.TestCase):
    def test_verb_contents_ignored(self):
        self.assertEqual(kinds(r"go \verb|$x \InputFile \[| roi"), [])
        self.assertEqual(kinds(r"go \verb+{$+ roi"), [])

    def test_lstlisting_body_ignored(self):
        text = ("\\begin{lstlisting}\nint main() { printf(\"$$$\\n\"); \\foo }\n"
                "\\end{lstlisting}\nsau $x$")
        self.assertEqual(kinds(text), [])


class TestCleanStatement(unittest.TestCase):
    def test_realistic_vietnamese_statement_has_no_findings(self):
        self.assertEqual(lint(CLEAN_STATEMENT), [])


class TestCli(unittest.TestCase):
    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["cf_statement_lint.py", *args])
        return code, out.getvalue(), err.getvalue()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, content):
        path = self.dir / name
        path.write_text(content, encoding="utf-8")
        return str(path)

    def test_clean_file_exits_zero(self):
        code, out, _ = self.run_main(self.write("legend.tex", CLEAN_STATEMENT))
        self.assertEqual((code, out), (0, ""))

    def test_errors_exit_one_with_formatted_lines(self):
        path = self.write("legend.tex", "dong 1\nmot $$$x$$$\n")
        code, out, _ = self.run_main(path)
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith(f"{path}:2:5: error: legacy-dollars: "), out)

    def test_json_fields_are_named(self):
        path = self.write("statement.json", json.dumps({
            "name": "Dãy số",
            "legend": "ok $x$",
            "input": r"\InputFile",
            "points": 100,
        }))
        code, out, _ = self.run_main(path)
        self.assertEqual(code, 1)
        lines = out.splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith(
            f"{path}:input:1:1: error: unsupported-command: "), lines[0])

    def test_usage_error_exits_two(self):
        self.assertEqual(self.run_main()[0], 2)

    def test_unreadable_file_exits_two(self):
        self.assertEqual(self.run_main(str(self.dir / "missing.tex"))[0], 2)

    def test_json_not_object_exits_two(self):
        self.assertEqual(self.run_main(self.write("s.json", "[1, 2]"))[0], 2)
        self.assertEqual(self.run_main(self.write("t.json", "{not json"))[0], 2)


if __name__ == "__main__":
    unittest.main()
