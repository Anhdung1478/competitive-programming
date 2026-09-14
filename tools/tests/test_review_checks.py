import json, os, shutil, tempfile, unittest
from pathlib import Path

from tools.review_checks import KINDS, run

# Anchored to this file rather than to the working directory — see the same
# note in test_package_status.py.
FIXTURE = Path(__file__).parent / "fixtures" / "mini"


class TestRun(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp()) / "p"
        shutil.copytree(FIXTURE, self.dir,
                        ignore=shutil.ignore_patterns(
                            ".build", "invocation.json", "solutions.json",
                            "flags.json", "*.a"))

    def kinds(self, **kw):
        return {f.kind for f in run(self.dir, **kw)}

    def only(self, kind, target=None, **kw):
        """The findings of one `kind`, asserting at least one exists.

        Every hostile test below used to assert nothing but `assertTrue(run(...))`
        — "it returned a non-empty list". That is satisfied unconditionally by
        the `incomplete-package` finding the fixture always produces, so those
        tests passed whether or not the check they were named after ran at all.
        Gutting five of the six check functions to `return []` left 13 of 18
        tests green. Naming the kind is what makes them able to fail.
        """
        findings = [f for f in run(target if target is not None else self.dir, **kw)
                    if f.kind == kind]
        self.assertTrue(
            findings, f"expected a {kind!r} finding, got "
            f"{[(f.kind, f.what) for f in run(target if target is not None else self.dir, **kw)]}")
        return findings

    def test_every_finding_uses_a_declared_kind_and_severity(self):
        for finding in run(self.dir):
            self.assertIn(finding.kind, KINDS)
            self.assertIn(finding.severity, ("high", "medium", "low"))

    def test_an_unfinished_package_reports_incomplete(self):
        self.assertIn("incomplete-package", self.kinds())

    def test_a_malformed_problem_json_does_not_raise(self):
        (self.dir / "problem.json").write_text("{ not json", encoding="utf-8")
        findings = self.only("incomplete-package")
        self.assertIn("problem_json", findings[0].what)
        self.assertIn("not valid JSON", findings[0].what)

    def test_holes_in_invocation_json_are_reported(self):
        (self.dir / "invocation.json").write_text(json.dumps(
            {"schema": 1, "holes": [{"solution": "sol-wrong.cpp", "group": "g1",
                                     "expected": "WA", "actual": "OK"}],
             "mismatches": []}), encoding="utf-8")
        findings = [f for f in run(self.dir) if f.kind == "matrix-hole"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "high")
        self.assertIn("sol-wrong.cpp", findings[0].what)

    def test_mismatches_are_reported_separately_from_holes(self):
        (self.dir / "invocation.json").write_text(json.dumps(
            {"schema": 1, "holes": [],
             "mismatches": [{"solution": "sol-alt.cpp", "group": "g2",
                             "expected": "OK", "actual": "WA"}]}), encoding="utf-8")
        self.assertIn("matrix-mismatch", self.kinds())
        self.assertNotIn("matrix-hole", self.kinds())

    def test_a_solution_file_absent_from_the_scan_is_an_orphan(self):
        (self.dir / "solutions" / "notes.txt").write_text("x", encoding="utf-8")
        self.assertNotIn("orphan-solution", self.kinds())
        (self.dir / "solutions" / "sol-orphan.cpp").write_text(
            "int main(){}\n", encoding="utf-8")
        findings = [f for f in run(self.dir) if f.kind == "orphan-solution"]
        self.assertEqual(len(findings), 1)
        self.assertIn("sol-orphan.cpp", findings[0].what)

    def test_a_stale_constraints_header_is_reported(self):
        # Write a header that doesn't match render(problem)
        header = self.dir / "files" / "constraints.h"
        header.parent.mkdir(exist_ok=True)
        header.write_text("// wrong content\n", encoding="utf-8")
        self.assertIn("stale-constraints-header", self.kinds())

    def test_a_matching_constraints_header_is_not_reported(self):
        # Write the correct rendered header
        from tools.gen_constraints_header import render
        from tools.problem_meta import load
        problem = load(self.dir / "problem.json")
        header = self.dir / "files" / "constraints.h"
        header.parent.mkdir(exist_ok=True)
        header.write_text(render(problem), encoding="utf-8")
        self.assertNotIn("stale-constraints-header", self.kinds())

    def test_statement_drift_is_reported_when_a_tex_is_given(self):
        tex = self.dir / "mini.tex"
        tex.write_text(
            "\\begin{problem}[input = stdin, output = stdout,\n"
            "  time = 9, memory = 256,\n]{Mini}\n"
            "\\begin{subtasks}\\subtask{100}{x}\\end{subtasks}\n"
            "\\end{problem}\n", encoding="utf-8")
        findings = [f for f in run(self.dir, tex_path=tex)
                    if f.kind == "constraint-drift"]
        self.assertTrue(findings)
        self.assertEqual(findings[0].severity, "high")

    def test_time_drift_finding_says_which_file_to_edit(self):
        # Field report: after raising the TL in problem.json the finding
        # named the disagreement but not the edit. Both sides are named,
        # since which one is intended is the setter's call.
        tex = self.dir / "mini.tex"
        tex.write_text(
            "\\begin{problem}[input = stdin, output = stdout,\n"
            "  time = 9, memory = 256,\n]{Mini}\n"
            "\\begin{subtasks}\\subtask{100}{x}\\end{subtasks}\n"
            "\\end{problem}\n", encoding="utf-8")
        time_findings = [f for f in run(self.dir, tex_path=tex)
                         if f.kind == "constraint-drift"
                         and f.what.startswith("time:")]
        self.assertEqual(len(time_findings), 1)
        what = time_findings[0].what
        self.assertIn("statement says 9 s", what)
        self.assertIn("\\begin{problem}", what)
        self.assertIn("limits.time_ms_published", what)

    def test_invocation_json_with_holes_as_string_does_not_raise(self):
        (self.dir / "invocation.json").write_text(json.dumps(
            {"schema": 1, "holes": "not_a_list", "mismatches": []}), encoding="utf-8")
        findings = self.only("matrix-hole")
        self.assertEqual(findings[0].severity, "low")
        self.assertIn("malformed", findings[0].what)

    def test_invocation_json_with_holes_as_int_does_not_raise(self):
        (self.dir / "invocation.json").write_text(json.dumps(
            {"schema": 1, "holes": 123, "mismatches": []}), encoding="utf-8")
        findings = self.only("matrix-hole")
        self.assertEqual(findings[0].severity, "low")
        self.assertIn("malformed", findings[0].what)

    def test_invocation_json_with_top_level_list_does_not_raise(self):
        (self.dir / "invocation.json").write_text(json.dumps(
            [{"holes": []}]), encoding="utf-8")
        findings = self.only("matrix-hole")
        self.assertEqual(findings[0].severity, "low")
        self.assertIn("top level is not an object", findings[0].what)

    def test_nonexistent_problem_directory_does_not_raise(self):
        nonexistent = Path(tempfile.mkdtemp()) / "nonexistent"
        findings = self.only("incomplete-package", target=nonexistent)
        self.assertIn("problem_json", findings[0].what)
        self.assertIn("no such file", findings[0].what)

    def test_solutions_as_file_not_directory_does_not_raise(self):
        # Remove the solutions directory and replace with a file
        shutil.rmtree(self.dir / "solutions")
        (self.dir / "solutions").write_text("not a directory", encoding="utf-8")
        findings = self.only("orphan-solution")
        self.assertEqual(findings[0].severity, "low")
        self.assertIn("solution scan failed", findings[0].what)

    def test_tex_path_as_directory_does_not_raise(self):
        tex_dir = self.dir / "tex_dir"
        tex_dir.mkdir(parents=True, exist_ok=True)
        findings = self.only("constraint-drift", tex_path=tex_dir)
        self.assertEqual(findings[0].severity, "low")
        self.assertIn("statement unreadable", findings[0].what)

    def test_tex_path_with_invalid_utf8_does_not_raise(self):
        tex_path = self.dir / "bad.tex"
        tex_path.write_bytes(b"\xff\xfe")
        findings = self.only("constraint-drift", tex_path=tex_path)
        self.assertEqual(findings[0].severity, "low")
        self.assertIn("statement unreadable", findings[0].what)

    def test_constraints_h_without_problem_json_does_not_raise(self):
        # The comment here used to say "problem.json was not copied" while
        # setUp copies it — so `problem` was never None and the guard at
        # `review_checks._stale_header`'s `if problem is None` was untested.
        # Remove the file for real.
        (self.dir / "problem.json").unlink()
        (self.dir / "files").mkdir(exist_ok=True)
        (self.dir / "files" / "constraints.h").write_text("test", encoding="utf-8")
        kinds = self.kinds()
        # The guard's whole job: a header that cannot be compared to anything
        # is not reported as stale.
        self.assertNotIn("stale-constraints-header", kinds)
        findings = self.only("incomplete-package")
        self.assertIn("problem_json", findings[0].what)

    def test_a_constraint_id_that_is_not_a_string_does_not_raise(self):
        # `gen_constraints_header.identifier()` calls `re.sub` on this, which
        # raises TypeError on a number — from inside a module that promises
        # `run()` never raises. The loader rejects it now.
        problem = json.loads((self.dir / "problem.json").read_text(encoding="utf-8"))
        problem["constraints"][0]["id"] = 3
        (self.dir / "problem.json").write_text(json.dumps(problem), encoding="utf-8")
        findings = self.only("incomplete-package")
        self.assertIn("constraints[0].id", findings[0].what)

    def test_two_constraint_ids_colliding_after_uppercasing_is_a_finding(self):
        # `load()` accepts "n" and "N" as distinct; `render()` uppercases both
        # into `N_MIN` and raises ProblemMetaError. That escaped `run()` as a
        # traceback until `_stale_header` widened its except clause.
        problem = json.loads((self.dir / "problem.json").read_text(encoding="utf-8"))
        problem["constraints"] = [
            {"id": "n", "expr": "1 \\le n \\le 10", "min": 1, "max": 10},
            {"id": "N", "expr": "1 \\le N \\le 10", "min": 1, "max": 10},
        ]
        (self.dir / "problem.json").write_text(json.dumps(problem), encoding="utf-8")
        (self.dir / "files").mkdir(exist_ok=True)
        (self.dir / "files" / "constraints.h").write_text("// any\n", encoding="utf-8")
        findings = self.only("stale-constraints-header")
        self.assertEqual(findings[0].severity, "low")
        self.assertIn("Identifier collision", findings[0].what)

    # --- coordinator review round: `_matrix()` here is the sibling of
    # `package_status._matrix()` and had the identical staleness hole —
    # fixed by sharing `package_status.newest_source_mtime` rather than
    # duplicating it, so the two checks cannot silently drift apart again.

    def test_a_stale_matrix_is_reported(self):
        (self.dir / "invocation.json").write_text(json.dumps(
            {"schema": 1, "holes": [], "mismatches": []}), encoding="utf-8")
        later = (self.dir / "invocation.json").stat().st_mtime + 10
        os.utime(self.dir / "solutions" / "sol-main.cpp", (later, later))
        findings = self.only("stale-matrix")
        self.assertEqual(findings[0].severity, "high")

    def test_a_stale_matrix_suppresses_hole_findings(self):
        # Staleness is reported instead of holes/mismatches, not alongside
        # them: a stale invocation.json's holes describe a package state
        # that no longer exists, and surfacing them here would be citing
        # evidence about a different tree as though it were current.
        (self.dir / "invocation.json").write_text(json.dumps(
            {"schema": 1, "holes": [{"solution": "sol-wrong.cpp", "group": "g1",
                                     "expected": "WA", "actual": "OK"}],
             "mismatches": []}), encoding="utf-8")
        later = (self.dir / "invocation.json").stat().st_mtime + 10
        os.utime(self.dir / "solutions" / "sol-main.cpp", (later, later))
        kinds = self.kinds()
        self.assertIn("stale-matrix", kinds)
        self.assertNotIn("matrix-hole", kinds)

    def test_a_fresh_matrix_with_holes_is_not_reported_as_stale(self):
        # Contrast case: a genuinely current invocation.json with real
        # holes must still surface `matrix-hole`, not `stale-matrix` — the
        # staleness check must not fire just because holes are present.
        (self.dir / "invocation.json").write_text(json.dumps(
            {"schema": 1, "holes": [{"solution": "sol-wrong.cpp", "group": "g1",
                                     "expected": "WA", "actual": "OK"}],
             "mismatches": []}), encoding="utf-8")
        kinds = self.kinds()
        self.assertIn("matrix-hole", kinds)
        self.assertNotIn("stale-matrix", kinds)

    def test_a_stale_custom_checker_is_reported(self):
        # The custom checker decides every cell's verdict and lives under
        # `files/`, outside `problem.json`/`solutions/`/`tests/` entirely
        # -- declare one, then edit it after invocation.json is written.
        problem = json.loads((self.dir / "problem.json").read_text(encoding="utf-8"))
        problem["checker"] = {"kind": "custom", "name": "checker.cpp"}
        (self.dir / "problem.json").write_text(json.dumps(problem), encoding="utf-8")
        checker = self.dir / "files" / "checker.cpp"
        checker.parent.mkdir(exist_ok=True)
        checker.write_text("// checker\n", encoding="utf-8")
        (self.dir / "invocation.json").write_text(json.dumps(
            {"schema": 1, "holes": [], "mismatches": []}), encoding="utf-8")
        later = (self.dir / "invocation.json").stat().st_mtime + 10
        os.utime(checker, (later, later))
        self.assertIn("stale-matrix", self.kinds())


class TestCleanPackageReturnsNoFindings(unittest.TestCase):
    """A known-good, complete package should produce zero findings."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp()) / "p"
        # Copy the fixture, excluding incomplete phases
        shutil.copytree(FIXTURE, self.dir,
                        ignore=shutil.ignore_patterns(".build", ".pycache"))

    def test_fixture_with_legitimate_completions_has_no_findings(self):
        """Fixture with examples and samples added should produce zero findings.

        The fixture is committed with a valid generated constraints.h and valid
        invocation.json. We only add the missing examples and sample files that
        Stage 1 never provided, then verify the audit is clean.
        """
        import json
        # Add examples to problem.json (fixture intentionally ships without these)
        problem_path = self.dir / "problem.json"
        problem = json.loads(problem_path.read_text(encoding="utf-8"))
        problem["examples"] = [{"test": "01"}]
        problem_path.write_text(json.dumps(problem, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")

        # Create the sample files (fixture intentionally ships without these)
        (self.dir / "01.in").write_text("1 2\n", encoding="utf-8")
        (self.dir / "01.a").write_text("3\n", encoding="utf-8")

        # Write valid invocation.json with no holes/mismatches (fixture is incomplete without this)
        (self.dir / "invocation.json").write_text(
            json.dumps({"schema": 1, "holes": [], "mismatches": []}),
            encoding="utf-8")

        findings = run(self.dir)
        if findings:
            msg = "Fixture with legitimate completions has findings:\n"
            for f in findings:
                msg += f"  {f.severity.upper()} {f.kind}: {f.what}\n"
            self.fail(msg)
        self.assertEqual(findings, [])
