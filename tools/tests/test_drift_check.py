import dataclasses
import tempfile
import unittest
from pathlib import Path

from tools.drift_check import DriftCheckError, check, main, parse_tex
from tools.problem_meta import Constraint, Problem, Subtask

TEX = r"""
\documentclass[11pt, a4paper, oneside]{article}
\usepackage[vietnamese, color, standalone]{vnolymp}
\begin{document}
\begin{problem}[
  input  = stdin, output = stdout,
  time   = 1, memory = 256,
]{Chuyến bay đầu tiên}
Nội dung.
\begin{subtasks}
  \subtask{40}{$|A| \le 6$ và $|B| \le 6$}
  \subtask{60}{Không có ràng buộc gì thêm}
\end{subtasks}
\end{problem}
\end{document}
"""

PROBLEM = Problem(
    name="flight", title={}, tags=[], time_ms_published=1000, time_ms_computed=740,
    memory_mb=256, input="stdin", output="stdout",
    checker_kind="stock", checker_name="rcmp6",
    constraints=[Constraint(id="len_a", expr="x", min=1, max=20)],
    subtasks=[Subtask(id="g1", points=40), Subtask(id="g2", points=60)],
    examples=[],
    format="oi",
)


class TestParseTex(unittest.TestCase):
    def test_reads_the_problem_key_list(self):
        parsed = parse_tex(TEX)
        self.assertEqual(parsed["time"], 1)
        self.assertEqual(parsed["memory"], 256)
        self.assertEqual(parsed["input"], "stdin")
        self.assertEqual(parsed["output"], "stdout")

    def test_reads_subtask_percentages_in_order(self):
        self.assertEqual(parse_tex(TEX)["subtask_points"], [40, 60])

    def test_a_fractional_time_limit_is_read_as_a_float(self):
        # `time = 1.5` is a routine limit. `int("1.5")` raises, and the old
        # code swallowed that into None — which check() then reported as
        # "no `time` key in \begin{problem}", naming a key that is present
        # and correct.
        self.assertEqual(parse_tex(TEX.replace("time   = 1,", "time = 1.5,"))["time"],
                         1.5)

    def test_a_braced_decimal_comma_time_is_read_as_a_float(self):
        # Field report: `time = {2,5}` is how a statement renders "2,5 giây".
        # The brace-aware splitter keeps it whole as "2,5", and
        # `float("2,5")` raised — false drift "no `time` key".
        self.assertEqual(
            parse_tex(TEX.replace("time   = 1,", "time = {2,5},"))["time"], 2.5)

    def test_only_the_single_comma_decimal_form_is_read(self):
        for value in ("{2,5,1}", "{1,000,000}", "{,5}", "{2,}"):
            with self.subTest(value=value):
                self.assertIsNone(parse_tex(
                    TEX.replace("time   = 1,", f"time = {value},"))["time"])

    def test_the_decimal_comma_is_read_only_for_time(self):
        # memory is whole megabytes; `{256,5}` is not a limit.
        self.assertIsNone(parse_tex(
            TEX.replace("memory = 256,", "memory = {256,5},"))["memory"])

    def test_a_non_numeric_time_is_still_none(self):
        self.assertIsNone(parse_tex(TEX.replace("time   = 1,", "time = soon,"))["time"])

    def test_a_fractional_memory_is_rejected_not_truncated(self):
        # memory is whole megabytes; 256.5 must not be silently read as 256.
        self.assertIsNone(
            parse_tex(TEX.replace("memory = 256,", "memory = 256.5,"))["memory"])


class TestCheck(unittest.TestCase):
    def test_clean_document_reports_nothing(self):
        self.assertEqual(check(PROBLEM, TEX), [])

    def test_detects_time_mismatch(self):
        problems = check(PROBLEM, TEX.replace("time   = 1", "time   = 2"))
        self.assertEqual(len(problems), 1)
        self.assertIn("time", problems[0])

    def test_a_matching_fractional_time_limit_is_not_drift(self):
        # The whole-branch review's finding: a 1.5 s limit made this tool
        # emit `statement: no \`time\` key in \begin{problem}` — false
        # drift, with a message naming a key that was present and correct.
        problem = dataclasses.replace(PROBLEM, time_ms_published=1500)
        self.assertEqual(check(problem, TEX.replace("time   = 1,", "time = 1.5,")), [])

    def test_a_mismatched_fractional_time_limit_is_real_drift(self):
        problem = dataclasses.replace(PROBLEM, time_ms_published=2500)
        issues = check(problem, TEX.replace("time   = 1,", "time = 1.5,"))
        self.assertEqual(len(issues), 1)
        self.assertIn("2.5 s", issues[0])
        self.assertIn("1.5 s", issues[0])

    def test_a_matching_decimal_comma_time_limit_is_not_drift(self):
        problem = dataclasses.replace(PROBLEM, time_ms_published=2500)
        self.assertEqual(
            check(problem, TEX.replace("time   = 1,", "time = {2,5},")), [])

    def test_time_drift_names_the_edit_on_both_sides(self):
        # Field report: 2000 -> 2500 in problem.json, and the finding said
        # nothing about which file to change.
        problem = dataclasses.replace(PROBLEM, time_ms_published=2500)
        issue, = check(problem, TEX.replace("time   = 1,", "time = 2,"))
        self.assertTrue(issue.startswith(
            "time: problem.json publishes 2.5 s, statement says 2 s"), issue)
        self.assertIn("`time = 2.5`", issue)
        self.assertIn("\\begin{problem}", issue)
        self.assertIn("`limits.time_ms_published` to 2000", issue)

    def test_a_whole_second_suggestion_is_written_bare(self):
        issue, = check(PROBLEM, TEX.replace("time   = 1,", "time = 2,"))
        self.assertIn("`time = 1`", issue)
        self.assertIn("`limits.time_ms_published` to 2000", issue)

    def test_detects_memory_mismatch(self):
        problems = check(PROBLEM, TEX.replace("memory = 256", "memory = 512"))
        self.assertIn("memory", problems[0])
        self.assertTrue(problems[0].startswith(
            "memory: problem.json says 256 MB, statement says 512 MB"))
        self.assertIn("`memory = 256`", problems[0])
        self.assertIn("`limits.memory_mb` to 512", problems[0])

    def test_detects_subtask_points_mismatch(self):
        problems = check(PROBLEM, TEX.replace(r"\subtask{40}", r"\subtask{30}"))
        self.assertIn("subtask", problems[0].lower())

    def test_detects_subtask_count_mismatch(self):
        stripped = TEX.replace(
            "  \\subtask{60}{Không có ràng buộc gì thêm}\n", "")
        problems = check(PROBLEM, stripped)
        self.assertTrue(problems)

    def test_detects_io_mismatch(self):
        problems = check(PROBLEM, TEX.replace("input  = stdin", "input  = flight.inp"))
        self.assertIn("input", problems[0])

    def test_detects_output_mismatch(self):
        problems = check(PROBLEM, TEX.replace("output = stdout", "output = flight.out"))
        self.assertIn("output", problems[0])

    def test_matching_file_based_io_is_not_reported(self):
        # A file-IO problem (Task 1's io.input/io.output sentinel-or-bare-
        # filename validation) whose statement names the same files must not
        # drift, even though neither side is "stdin"/"stdout".
        problem = dataclasses.replace(PROBLEM, input="flight.inp", output="flight.out")
        tex = TEX.replace("input  = stdin, output = stdout",
                           "input  = flight.inp, output = flight.out")
        self.assertEqual(check(problem, tex), [])

    def test_mismatched_file_based_io_is_reported(self):
        # The motivating case: the statement promises a filename but
        # problem.json still says stdin/stdout (or a different filename) —
        # this sends every solution to NO_OUTPUT with no explanation, so it
        # must surface here rather than at grading time.
        tex = TEX.replace("input  = stdin, output = stdout",
                           "input  = flight.inp, output = flight.out")
        issues = check(PROBLEM, tex)
        self.assertTrue(any("input" in d for d in issues), issues)
        self.assertTrue(any("output" in d for d in issues), issues)


class TestMainErrorHandling(unittest.TestCase):
    def test_main_raises_drift_check_error_on_missing_statement_file(self):
        """R1: Missing file must raise DriftCheckError, not FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            problem_dir = Path(tmpdir) / "problem"
            problem_dir.mkdir()
            statement_file = problem_dir / "missing.tex"
            # Create a minimal problem.json
            problem_json = problem_dir / "problem.json"
            problem_json.write_text('{"schema": 1, "name": "test", "limits": {"time_ms_published": 1000, "memory_mb": 256}, "io": {"input": "stdin", "output": "stdout"}, "checker": {"kind": "stock", "name": "rcmp6"}, "subtasks": [{"id": "g1", "points": 100}], "constraints": []}')

            with self.assertRaises(DriftCheckError) as cm:
                main(["drift_check.py", str(problem_dir), str(statement_file)])
            # Verify the cause is a FileNotFoundError, which is an OSError
            self.assertIsInstance(cm.exception.__cause__, FileNotFoundError)

    def test_main_raises_drift_check_error_on_non_utf8_statement(self):
        """R1: Non-UTF-8 file must raise DriftCheckError, not UnicodeDecodeError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            problem_dir = Path(tmpdir) / "problem"
            problem_dir.mkdir()
            statement_file = problem_dir / "statement.tex"
            # Write non-UTF-8 bytes
            statement_file.write_bytes(b'\xff\xfe invalid utf-8')
            # Create a minimal problem.json
            problem_json = problem_dir / "problem.json"
            problem_json.write_text('{"schema": 1, "name": "test", "limits": {"time_ms_published": 1000, "memory_mb": 256}, "io": {"input": "stdin", "output": "stdout"}, "checker": {"kind": "stock", "name": "rcmp6"}, "subtasks": [{"id": "g1", "points": 100}], "constraints": []}')

            with self.assertRaises(DriftCheckError) as cm:
                main(["drift_check.py", str(problem_dir), str(statement_file)])
            # Verify the cause is a UnicodeDecodeError
            self.assertIsInstance(cm.exception.__cause__, UnicodeDecodeError)

    def test_main_raises_drift_check_error_on_directory_as_statement(self):
        """Finding 1: A directory path raises DriftCheckError, not IsADirectoryError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            problem_dir = Path(tmpdir) / "problem"
            problem_dir.mkdir()
            statement_dir = problem_dir / "statement.tex"
            statement_dir.mkdir()
            # Create a minimal problem.json
            problem_json = problem_dir / "problem.json"
            problem_json.write_text('{"schema": 1, "name": "test", "limits": {"time_ms_published": 1000, "memory_mb": 256}, "io": {"input": "stdin", "output": "stdout"}, "checker": {"kind": "stock", "name": "rcmp6"}, "subtasks": [{"id": "g1", "points": 100}], "constraints": []}')

            with self.assertRaises(DriftCheckError) as cm:
                main(["drift_check.py", str(problem_dir), str(statement_dir)])
            # Verify the wrapped cause is IsADirectoryError (which is an OSError)
            self.assertIsInstance(cm.exception.__cause__, IsADirectoryError)


class TestRegression(unittest.TestCase):
    """Regression tests for Finding 2 and 3."""

    def test_commented_out_subtask_is_ignored(self):
        """Finding 2: Commented-out \\subtask{30} should not be counted."""
        tex = r"""
\documentclass{article}
\usepackage{vnolymp}
\begin{document}
\begin{problem}[
  input  = stdin, output = stdout,
  time   = 1, memory = 256,
]{Title}
Text.
\begin{subtasks}
  % \subtask{30}{nhóm cũ, đã gộp}
  \subtask{40}{a}
  \subtask{60}{b}
\end{subtasks}
\end{problem}
\end{document}
"""
        parsed = parse_tex(tex)
        self.assertEqual(parsed["subtask_points"], [40, 60],
                        "Commented subtask should not be counted")

    def test_subtask_outside_environment_is_ignored(self):
        """Finding 2: \\subtask mentioned outside \\begin{subtasks}...\\end{subtasks} is ignored."""
        tex = r"""
\documentclass{article}
\begin{document}
\begin{problem}[
  input  = stdin, output = stdout,
  time   = 1, memory = 256,
]{Title}
Some text mentioning \subtask{25} as an example.
\begin{subtasks}
  \subtask{40}{a}
  \subtask{60}{b}
\end{subtasks}
Text after mentioning \subtask{35} again.
\end{problem}
\end{document}
"""
        parsed = parse_tex(tex)
        self.assertEqual(parsed["subtask_points"], [40, 60],
                        "Subtask outside environment should not be counted")

    def test_origin_key_with_bracketed_value(self):
        """Finding 3: origin = {Đề chọn [Vòng 2]} should parse time/memory correctly."""
        tex = r"""
\documentclass{article}
\begin{document}
\begin{problem}[
  origin = {Đề chọn đội tuyển [Vòng 2]}, input = stdin, output = stdout,
  time = 1, memory = 256,
]{Title}
Text.
\begin{subtasks}
  \subtask{40}{a}
  \subtask{60}{b}
\end{subtasks}
\end{problem}
\end{document}
"""
        parsed = parse_tex(tex)
        self.assertEqual(parsed["time"], 1, "time key should parse correctly with origin before it")
        self.assertEqual(parsed["memory"], 256, "memory key should parse correctly with origin before it")
        self.assertEqual(parsed["input"], "stdin", "input key should parse correctly")
        self.assertEqual(parsed["output"], "stdout", "output key should parse correctly")

    def test_author_key_with_comma_in_braced_value(self):
        """Finding 3: author = {Lâm, VOI 2026} with comma inside braces should not break parsing."""
        tex = r"""
\documentclass{article}
\begin{document}
\begin{problem}[
  author = {Phan Bình Nguyên Lâm, VOI}, input = stdin, output = stdout,
  time = 1, memory = 256,
]{Title}
Text.
\begin{subtasks}
  \subtask{40}{a}
  \subtask{60}{b}
\end{subtasks}
\end{problem}
\end{document}
"""
        parsed = parse_tex(tex)
        self.assertEqual(parsed["time"], 1, "time should parse correctly despite author comma")
        self.assertEqual(parsed["memory"], 256, "memory should parse correctly despite author comma")

    def test_escaped_percent_is_not_a_comment(self):
        """Finding 2: \\% literal percent should not start a comment."""
        tex = r"""
\documentclass{article}
\begin{document}
\begin{problem}[
  input  = stdin, output = stdout,
  time   = 1, memory = 256,
]{Title}
Text with 100\% accuracy.
\begin{subtasks}
  \subtask{40}{40\% of cases}
  \subtask{60}{60\% accuracy}
\end{subtasks}
\end{problem}
\end{document}
"""
        parsed = parse_tex(tex)
        # Should not find fake subtasks from the \% in text
        self.assertEqual(parsed["subtask_points"], [40, 60],
                        "Escaped \\% should not be treated as comment")

    def test_commented_out_input_key_is_ignored(self):
        """In the spirit of Finding 2 (commented-out \\subtask): a
        commented-out override line, superseded by a real one, must not
        leak a stale `input`/`output` value into the parsed keys.

        The `%` must precede a throwaway token with no `=` ("superseded")
        so that, once `_strip_comments` removes the whole line, nothing is
        left behind — but if stripping were a no-op, the comma right after
        "superseded" would hand the brace-aware comma-splitter a *clean*
        standalone `input = flight.inp` token (no `%` glued to it, unlike
        `% input = ...` where the `%` sticks to the key name and never
        collides with `"input"` at all). That clean token would then
        overwrite the real pair, since dict assignment is last-pair-wins.
        Only real comment-stripping prevents that collision — so this test
        is red exactly when `_strip_comments` is broken, not incidentally.
        """
        tex = r"""
\documentclass{article}
\begin{document}
\begin{problem}[
  input  = stdin, output = stdout,
  % superseded, input = flight.inp, output = flight.out,
  time   = 1, memory = 256,
]{Title}
Text.
\begin{subtasks}
  \subtask{40}{a}
  \subtask{60}{b}
\end{subtasks}
\end{problem}
\end{document}
"""
        parsed = parse_tex(tex)
        self.assertEqual(parsed["input"], "stdin")
        self.assertEqual(parsed["output"], "stdout")
        self.assertEqual(check(PROBLEM, tex), [])

    def test_input_word_inside_another_keys_value_is_ignored(self):
        """In the spirit of Finding 3 (origin's bracketed value): a comma
        *inside* another key's braced value — the character brace-depth
        tracking exists to protect — must not be treated as a top-level
        separator, even when the text on either side of it reads exactly
        like a real `input =` / `output =` pair.

        Without brace-depth tracking, the comma-splitter would cut
        `note = {bản nháp: input = flight.inp, output = flight.out, đã sửa}`
        into pieces at every comma, including the ones inside the braces.
        The piece right after each such internal comma —
        ` input = flight.inp` and ` output = flight.out` — has no `%` or
        `note =` prefix glued to it (that contamination lands on the
        *previous* piece instead, split at the same broken comma), so it
        parses as a clean, standalone `input`/`output` pair and overwrites
        the real one below it. Only correct brace-depth tracking keeps the
        whole `{...}` a single value and prevents that collision — so this
        test is red exactly when brace-awareness is broken, not
        incidentally (there is no top-level `]` inside the braces for the
        *other* loop to trip on, unlike `test_origin_key_with_bracketed_value`).
        """
        tex = r"""
\documentclass{article}
\begin{document}
\begin{problem}[
  input  = stdin, output = stdout,
  note = {bản nháp: input = flight.inp, output = flight.out, đã sửa},
  time   = 1, memory = 256,
]{Title}
Text.
\begin{subtasks}
  \subtask{40}{a}
  \subtask{60}{b}
\end{subtasks}
\end{problem}
\end{document}
"""
        parsed = parse_tex(tex)
        self.assertEqual(parsed["input"], "stdin")
        self.assertEqual(parsed["output"], "stdout")
        self.assertEqual(check(PROBLEM, tex), [])


if __name__ == "__main__":
    unittest.main()
