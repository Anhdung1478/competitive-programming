"""Integration test for run_matrix.py against the mini fixture.

This wraps the fixture run described in Task 9's brief: build every
solution, run the matrix, and confirm both a clean pass (no holes, no
mismatches) and — the actual point of the tool — that the hole detector
fires when a test can no longer distinguish the wrong solution from the
model solution. It also pins down the fixes made during review: the
child's own peak RSS (not the driver's), the timing-band re-run path, the
checker timeout, and — since Stage 3 — both IO modes end to end.

Task 9b migrated the runner from `os.posix_spawn` + `/proc` polling to the
ioi/isolate sandbox — there is no fallback runner any more, so the tests
below exercise the real thing: the peak-RSS test now pins isolate's own
cgroup accounting rather than `VmHWM`, and new tests below cover
isolate-specific outcomes a posix_spawn driver could never produce
(`status:TO`, `cg-oom-killed`) plus the refuse-to-run and box-cleanup
guarantees task 9b added.

**Missing tooling fails this suite; it does not skip it.** g++, isolate,
and the testlib cache are hard requirements of the module under test, and
`run_matrix.py` is the one module in this pipeline with no fallback path —
gating its only 20 tests on the presence of the very dependency that has
no fallback meant a fresh clone, or CI without isolate, printed a green
`OK` for a 1000-line driver that had not been executed at all. Set
`CP_ALLOW_SANDBOX_SKIP=1` to opt back into skipping, for the one case that
justifies it: working on an unrelated module on a machine where the
sandbox genuinely cannot be installed.

Scratch trees live under `<plugin root>/.test-scratch/`, not `/tmp`, and
that is load-bearing rather than tidiness: `/tmp` is tmpfs, `run()` stages
sandbox output next to the problem directory, and tmpfs pages are charged
to the writing cgroup — so a fixture under `/tmp` would put the driver's
staging directory back on exactly the memory-backed filesystem
`_stage_base()` now refuses. The refusal would fail every test here with
a message about staging rather than about the thing under test.
"""

from __future__ import annotations

import contextlib
import dataclasses
import inspect
import io
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from tools import box_pool, flags, matrix_core, run_matrix
from tools.matrix_core import Limits

FIXTURE = Path(__file__).parent / "fixtures" / "mini"
PLUGIN_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_SCRIPT = PLUGIN_ROOT / "tools" / "bootstrap_testlib.sh"

# Scratch trees go here rather than /tmp — see the module docstring: /tmp is
# tmpfs, and the driver refuses to stage sandbox output on a memory-backed
# filesystem because that charges a solution's stdout against its own
# memory limit. This directory is gitignored and each test removes its own
# subtree in tearDown.
SCRATCH_ROOT = PLUGIN_ROOT / ".test-scratch"

# Set CP_ALLOW_SANDBOX_SKIP=1 to turn missing tooling back into a skip.
SKIP_ENV = "CP_ALLOW_SANDBOX_SKIP"


def _missing_dependency(reason: str):
    """Fail — not skip — when a hard dependency of run_matrix is absent.

    Returns an exception for the caller to raise. `unittest.SkipTest` only
    when the caller explicitly opted in via $CP_ALLOW_SANDBOX_SKIP;
    otherwise an `AssertionError`, so a fresh clone or a CI runner without
    isolate reports a failure instead of a green suite over a driver that
    was never executed.
    """
    if os.environ.get(SKIP_ENV) == "1":
        return unittest.SkipTest(f"{reason} (skipping: ${SKIP_ENV}=1)")
    return AssertionError(
        f"{reason}. This is a hard dependency of run_matrix.py, which has no "
        f"fallback runner — the tests covering it must not pass silently "
        f"without it. Install the dependency, or set {SKIP_ENV}=1 to skip "
        f"these tests deliberately.")

# scan_solutions requires every solution file to carry this metadata block
# (@tag/@expect/...); tests that overwrite sol-main.cpp's body with a
# throwaway misbehaving program must keep it, or scan() fails before
# run_matrix ever gets to compile anything.
_MAIN_HEADER = (
    "/**\n"
    " * @tag        main\n"
    " * @expect     g1=OK\n"
    " * @algorithm  Deliberately misbehaving stand-in for a test.\n"
    " * @complexity O(1)\n"
    " */\n"
)


# The file-IO variant of the mini fixture's two solutions: the same
# arithmetic, but reading `t.inp` and writing `t.out` by *relative* name and
# never touching stdin or stdout. Used by `_make_file_io_package` to drive
# `run()` end to end in file-IO mode. The nonzero returns are diagnostics:
# any of them surfaces as `crashed`/RE rather than as a mystery WA.
_FILE_IO_MAIN = (
    "/**\n"
    " * @tag        main\n"
    " * @expect     g1=OK\n"
    " * @algorithm  Reads two integers from t.inp, writes their sum to t.out.\n"
    " * @complexity O(1)\n"
    " */\n"
    "#include <cstdio>\n"
    'int main(){ FILE *fi = fopen("t.inp", "r"); if (!fi) return 3;\n'
    '  long long a, b; if (fscanf(fi, "%lld %lld", &a, &b) != 2) return 4;\n'
    "  fclose(fi);\n"
    '  FILE *fo = fopen("t.out", "w"); if (!fo) return 5;\n'
    '  fprintf(fo, "%lld\\n", a + b); fclose(fo); return 0; }\n'
)

_FILE_IO_WRONG = (
    "/**\n"
    " * @tag        wrong-answer\n"
    " * @expect     g1=WA\n"
    " * @algorithm  Writes the difference instead of the sum.\n"
    " * @why-wrong  Wrong operator; every test with a != 0 catches it.\n"
    " * @complexity O(1)\n"
    " */\n"
    "#include <cstdio>\n"
    'int main(){ FILE *fi = fopen("t.inp", "r"); if (!fi) return 3;\n'
    '  long long a, b; if (fscanf(fi, "%lld %lld", &a, &b) != 2) return 4;\n'
    "  fclose(fi);\n"
    '  FILE *fo = fopen("t.out", "w"); if (!fo) return 5;\n'
    '  fprintf(fo, "%lld\\n", a - b); fclose(fo); return 0; }\n'
)


def _compile(src_text: str, out_path: Path, tmp_dir: Path) -> Path:
    """Compile a throwaway C++ source string, for tests that need a binary
    with a specific misbehavior (busy-looping, memory-hogging) that has no
    place in the checked-in fixture."""
    src = tmp_dir / f"{out_path.name}.cpp"
    src.write_text(src_text, encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-O2", str(src), "-o", str(out_path)],
                    check=True, capture_output=True)
    return out_path


def _fixed_lease(box_id: int):
    """Stand in for `box_pool.lease`, always handing out the same id.

    Box ids now come from `box_pool`'s per-user lease pool rather than a
    value this module derives itself, so tests that need a *specific* box
    id (an out-of-range one to force a real `--init` failure, or a known
    one to check its box directory is gone afterward) patch
    `run_matrix.box_pool.lease` with this rather than a function this
    module no longer has. Only safe for an id no real lease would ever
    hand out (`box_pool`'s pool never exceeds 65536 ids) — anything within
    the real range must go through `_track_leased_box_ids` instead, or two
    copies of this suite running at once will genuinely collide on it,
    since this bypasses the real `flock` entirely.
    """
    return contextlib.nullcontext(box_id)


@contextlib.contextmanager
def _track_leased_box_ids():
    """Record, for every box id `box_pool.lease` hands out during the
    block, whether its isolate box directory still existed at the moment
    the real lease released it — checked while the real `flock` is still
    held, not after.

    `test_boxes_are_cleaned_up_after_*` need to know that every box a
    `run()` (or `_run_once`) call touched was torn down before that call's
    lease let go of it. Two earlier approaches both got this wrong:

    Snapshotting the whole of `/var/local/lib/isolate/` before and after
    assumed this process was the only thing using isolate for the whole
    window, which a second copy of this suite running at the same time
    (Task 2's own acceptance criterion) violates: `pool_size()` is as low
    as 4 on a real machine, so a sibling suite's `BoxLeasingTest` draws
    from the *same* few ids, not merely "other" ones, and can legitimately
    hold one live at whatever instant the snapshot is taken.

    Recording the ids and checking `box_dir.exists()` only *after* this
    context manager (and so after `real_lease`) has released every flock
    has the identical race in miniature: nothing stops a sibling process
    from re-leasing one of those same ids the instant this process's flock
    lets go of it, and then this test would see *the sibling's* live box
    and misreport it as ours never having been cleaned up.

    So the check has to happen inside the spy's own `finally`, which runs
    after the caller's `with box_pool.lease() as box_id:` body returns
    (i.e. after `_init_box`/the sandboxed run/`_cleanup_box` has already
    completed — see `_run_once` and `open_isolate_box`) but *before*
    `real_lease`'s own `__exit__` releases the flock. That is also the only
    way this test can actually enforce "the lease wraps the whole
    `--init`/`--run`/`--cleanup` cycle": an assertion made after release
    cannot tell "cleaned up before the lease let go" from "cleaned up
    whenever, by whoever, since" — moving `_cleanup_box` outside the
    `with box_pool.lease()` in `run_matrix.py` must make this fail, and it
    does (verified; see the task report).
    """
    records: list[tuple[int, bool]] = []
    real_lease = run_matrix.box_pool.lease

    @contextlib.contextmanager
    def _spy(**kwargs):
        with real_lease(**kwargs) as box_id:
            try:
                yield box_id
            finally:
                box_dir = Path(f"/var/local/lib/isolate/{box_id}")
                records.append((box_id, box_dir.exists()))

    with mock.patch.object(run_matrix.box_pool, "lease", _spy):
        yield records


def _testlib_dir() -> Path:
    """Resolve the cached testlib checkout, failing if it cannot be reached.

    Delegates to bootstrap_testlib.sh (the same script the driver's users run
    by hand) rather than hardcoding ~/.cache/testlib, so this still works if
    the cache lives somewhere else. An unreachable cache is a failure, not a
    skip, unless $CP_ALLOW_SANDBOX_SKIP=1 — see `_missing_dependency`.
    """
    try:
        done = subprocess.run(
            ["bash", str(BOOTSTRAP_SCRIPT)],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _missing_dependency(f"bootstrap_testlib.sh could not run: {exc}")
    if done.returncode != 0:
        raise _missing_dependency(f"testlib cache unavailable: {done.stderr.strip()}")
    path = Path(done.stdout.strip())
    if not (path / "testlib.h").exists():
        raise _missing_dependency(f"testlib cache at {path} has no testlib.h")
    return path


class PackageFixture(unittest.TestCase):
    """Shared setup for tests that need a scratch copy of the `mini` problem
    package: the hard-dependency skip guard, testlib cache resolution, and
    the package-editing helpers built on top of them.

    Deliberately carries **no** `test_*` methods of its own. `unittest`
    collects inherited test methods, so a fixture class that also held
    tests would have every one of them silently re-run by each subclass
    that reuses this setup — see `TestRunMatrixFixture` and
    `ParallelPassTest` below, which both subclass this rather than one
    subclassing the other, for exactly that reason.
    """

    def setUp(self):
        if shutil.which("g++") is None:
            raise _missing_dependency("g++ not found on PATH")
        if shutil.which("isolate") is None:
            raise _missing_dependency("isolate not found on PATH")
        self.testlib_dir = _testlib_dir()

        # Copy the fixture into a scratch dir so the run's build artifacts
        # (.build/, *.a, invocation.json, flags.json, solutions.json) never
        # touch the checked-in fixture and each test starts from the same
        # pristine tree. `ignore` is not decoration: a working copy of this
        # repo accumulates untracked `.build/` binaries and `.a` answer
        # files under the fixture from earlier manual runs, and copying
        # those in reproduces the sandbox permission failure they were
        # created with — this test errored on isolate's "Permission denied"
        # before its own assertions were ever evaluated.
        SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(prefix="run_matrix_test_", dir=SCRATCH_ROOT))
        self.problem_dir = self.tmp / "mini"
        shutil.copytree(
            FIXTURE, self.problem_dir,
            ignore=shutil.ignore_patterns(".build", "invocation.json",
                                          "solutions.json", "flags.json", "*.a"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_file_io_package(self, *, extra_solution=None, main_source=None):
        """Turn the scratch copy of the mini fixture into a file-IO package.

        `problem.json`'s `io` block names real files and both checked-in
        solutions are replaced by ones that read `t.inp` and write `t.out`.
        Everything else — the checker (stock `ncmp`, which already takes
        three paths), the validator, the generator, the tests — is untouched,
        which is the point: only `problem.json` and the solutions differ
        between the two IO modes.

        `extra_solution` is an `(filename, source)` pair added to
        `solutions/`; `main_source` overrides the model solution.
        """
        meta_path = self.problem_dir / "problem.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["io"] = {"input": "t.inp", "output": "t.out"}
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        solutions = self.problem_dir / "solutions"
        (solutions / "sol-main.cpp").write_text(
            main_source if main_source is not None else _FILE_IO_MAIN,
            encoding="utf-8")
        (solutions / "sol-wrong.cpp").write_text(_FILE_IO_WRONG, encoding="utf-8")
        if extra_solution is not None:
            name, source = extra_solution
            (solutions / name).write_text(source, encoding="utf-8")
        return self.problem_dir

    def _assert_boxes_gone(self, records) -> None:
        """Consumes `_track_leased_box_ids()`'s output: `(box_id,
        still_present_when_its_lease_released)` pairs. The "still present"
        half was recorded while that lease's flock was still held, so this
        does not re-check the filesystem itself — doing so here, after
        every lease in `records` has already been released, would reopen
        the exact race `_track_leased_box_ids` exists to avoid (a sibling
        process may have re-leased and be legitimately using that id by
        now)."""
        self.assertTrue(records, "no box id was leased at all — sanity check")
        for box_id, still_present in records:
            self.assertFalse(
                still_present,
                f"/var/local/lib/isolate/{box_id} still present when its "
                "lease released — the lease did not wrap the whole "
                "--init/--run/--cleanup cycle")

    @staticmethod
    def _mounted_host_dirs(cmd) -> set[str]:
        """The host paths in an isolate `--dir=<label>=<host>[:rw]` argv."""
        found = set()
        for arg in cmd:
            if not isinstance(arg, str) or not arg.startswith("--dir="):
                continue
            host = arg.split("=", 2)[2]
            found.add(host[:-3] if host.endswith(":rw") else host)
        return found

    def _isolate_run_argv(self, call):
        """Run `call()` with `subprocess.run` spied on; return the `--run` argv.

        `_run_once` shells out three times per call (`--init`, `--run`,
        `--cleanup`); only the middle one carries the mounts.
        """
        seen = []
        real = subprocess.run

        def spy(cmd, *args, **kwargs):
            seen.append(cmd)
            return real(cmd, *args, **kwargs)

        with mock.patch.object(run_matrix.subprocess, "run", spy):
            call()
        runs = [cmd for cmd in seen
                if isinstance(cmd, list) and "--run" in cmd]
        self.assertEqual(len(runs), 1,
                         f"expected exactly one isolate --run, saw {seen!r}")
        return runs[0]


class TestRunMatrixFixture(PackageFixture):
    def test_clean_matrix_has_no_holes_or_mismatches(self):
        payload = run_matrix.run(self.problem_dir, self.testlib_dir)

        self.assertEqual(payload["holes"], [])
        self.assertEqual(payload["mismatches"], [])
        self.assertEqual(payload["limits"]["tl_ms"], 1000)  # floor binds, t_main is ~ms
        self.assertEqual(payload["limits"]["kill_ms"], 2000)

        by_solution = {r["solution"]: r for r in payload["results"]
                       if r["group"] == "g1" and r["test"] == "01"}
        self.assertEqual(by_solution["sol-main.cpp"]["verdict"], "OK")
        # sol-wrong.cpp must land on WA for g1, matching its @expect.
        self.assertEqual(by_solution["sol-wrong.cpp"]["verdict"], "WA")

        # Peak RSS must be a real, positive reading, not a zeroed-out stub.
        # (The regression-proof that it is the *child's* figure, not the
        # driver's, is a separate test below — this assertion alone would
        # pass even with the pre-review bug, since that bug over-reports
        # rather than reporting zero.)
        for record in payload["results"]:
            self.assertGreater(record["peak_kb"], 0)

    def test_hole_detector_fires_when_a_test_cannot_distinguish(self):
        # a - b == a + b when a == b == 0, so sol-wrong.cpp's (buggy)
        # subtraction coincides with the model solution's (correct) sum on
        # this one input. With only this test in g1, nothing catches it:
        # the tool must report this as a hole, not pass silently.
        (self.problem_dir / "tests" / "g1" / "01.in").write_text("0 0\n", encoding="utf-8")

        payload = run_matrix.run(self.problem_dir, self.testlib_dir)

        self.assertEqual(len(payload["holes"]), 1)
        hole = payload["holes"][0]
        self.assertEqual(hole["solution"], "sol-wrong.cpp")
        self.assertEqual(hole["group"], "g1")
        self.assertEqual(hole["expected"], "WA")
        self.assertEqual(hole["actual"], "OK")
        self.assertEqual(payload["mismatches"], [])

    def test_peak_kb_is_the_childs_own_footprint_not_the_drivers(self):
        # Regression pin, originally for the posix_spawn-era finding that
        # `ru_maxrss` after fork+exec is max(driver RSS at spawn, child's
        # real peak): deliberately balloon *this test process's* own RSS
        # well past anything the tiny fixture binaries could plausibly use,
        # then confirm the reported peak_kb does not track it. Now that
        # peak_kb comes from isolate's own cgroup accounting (`max-rss` in
        # its meta file, read from a namespace the driver process isn't
        # even part of) there is no shared-address-space mechanism left
        # that *could* leak the driver's RSS into this reading — this test
        # stays as a regression pin against that entire failure class
        # reappearing, e.g. if a future change ever reintroduced measuring
        # from the driver's own process instead of isolate's report.
        ballast = bytearray(250 * 1024 * 1024)
        for i in range(0, len(ballast), 4096):
            ballast[i] = 1  # touch every page so it is really resident
        try:
            payload = run_matrix.run(self.problem_dir, self.testlib_dir)
        finally:
            del ballast

        for record in payload["results"]:
            # sol-main.cpp/sol-wrong.cpp are static-ish iostream binaries
            # that in practice use a few MB; 30 MB is a generous ceiling
            # that a correct reading will clear easily while a
            # driver-tracking regression (hundreds of MB once ballooned)
            # would blow through immediately.
            self.assertLess(
                record["peak_kb"], 30_000,
                f"{record['solution']} reported {record['peak_kb']} KB peak "
                "RSS while the driver process was deliberately ballooned to "
                "~250 MB; this should be a few MB, not tracking the driver")
            self.assertGreater(record["peak_kb"], 0)

    def test_band_result_is_reached_and_flagged_with_accurate_wording(self):
        # Force every test into the (TL, kill] band deterministically by
        # patching compute_limits (imported by name into run_matrix, hence
        # patchable as run_matrix.compute_limits) rather than engineering a
        # sleep-based solution. tl_ms=-1 guarantees classify()'s `time_ms >
        # limits.tl_ms` fires even for a fixture solution measured at 0ms
        # (millisecond rounding on a trivial binary genuinely can read 0);
        # kill_ms=5000 is nowhere near reached, so the branch fires with no
        # flakiness regardless of how fast the machine running this is.
        forced = Limits(t_main_ms=2, tl_ms=-1, kill_ms=5000)
        with mock.patch.object(run_matrix, "compute_limits", return_value=forced):
            payload = run_matrix.run(self.problem_dir, self.testlib_dir)

        self.assertTrue(payload["results"])
        for record in payload["results"]:
            self.assertTrue(record["banded"], record)

        recorded = flags.read(self.problem_dir)
        band_flags = [f for f in recorded if f["kind"] == "timing-band"]
        self.assertGreaterEqual(len(band_flags), 1)
        for flag in band_flags:
            for field in ("phase", "severity", "kind", "what", "assumed",
                          "changes_if_wrong"):
                self.assertTrue(str(flag.get(field, "")).strip(), (flag, field))
            # Review finding: the old wording claimed reclassification to
            # "time-limit-exceeded-or-accepted", a verdict that does not
            # exist — the recorded verdict is always a real one.
            self.assertNotIn("time-limit-exceeded-or-accepted", flag["assumed"])

    def test_checker_timeout_reports_fail_instead_of_hanging(self):
        # A custom checker is externally-authored data; one that hangs
        # forever must not hang the whole pipeline. Build a literal
        # infinite loop and confirm _check() bounds it (using a short
        # timeout directly rather than the real CHECKER_TIMEOUT_S=10, so
        # this test stays fast).
        hang_src = self.tmp / "hang_checker.cpp"
        hang_src.write_text("int main(){ for(;;) {} }\n", encoding="utf-8")
        hang_bin = self.tmp / "hang_checker"
        subprocess.run(["g++", "-std=c++17", "-O2", str(hang_src), "-o", str(hang_bin)],
                        check=True, capture_output=True)
        dummy = self.tmp / "dummy.txt"
        dummy.write_text("x\n", encoding="utf-8")

        started = time.monotonic()
        verdict = run_matrix._check(hang_bin, dummy, dummy, dummy, timeout_s=1)
        elapsed_s = time.monotonic() - started

        self.assertEqual(verdict, "FAIL")
        self.assertLess(elapsed_s, 5)

    def test_isolate_missing_binary_refuses_with_a_named_fix(self):
        # Task 9b ruling: no fallback runner. A missing isolate must not
        # surface as a bare FileNotFoundError/CalledProcessError (R1) — it
        # must raise MatrixError naming the fix, and that message must be
        # distinguishable from the "installed but unconfigured" case below.
        with mock.patch.dict(os.environ, {"ISOLATE_BIN": "/no/such/isolate"}):
            with self.assertRaises(run_matrix.MatrixError) as ctx:
                run_matrix.open_isolate_box(self.tmp)
        self.assertIn("not found", str(ctx.exception))

    def test_isolate_init_failure_is_diagnosed_distinctly_from_missing(self):
        # The other failure family R1 requires: isolate present on PATH but
        # `--init` failing (real cause on this machine: an out-of-range
        # box id: isolate's own box-id range is 0-65535, see `isolate
        # --cg --box-id=999999 --init`, which fails distinctly from a
        # missing binary). Standing in for the "installed but
        # unconfigured" case this driver must diagnose separately, since a
        # genuinely unconfigured sandbox cannot be produced on this
        # already-configured machine without root to break it.
        with mock.patch.object(run_matrix.box_pool, "lease",
                               lambda **kw: _fixed_lease(999_999)):
            with self.assertRaises(run_matrix.MatrixError) as ctx:
                run_matrix.open_isolate_box(self.tmp)
        message = str(ctx.exception)
        self.assertIn("--init", message)
        self.assertNotIn("not found", message)

    def test_run_once_reports_a_real_tle_as_status_to(self):
        # A genuine busy loop, run through the real sandbox with a 1s CPU
        # cap, must come back with isolate's own status:TO — not a driver-
        # side wait-loop deadline, which no longer exists.
        binary = _compile("int main(){ volatile long i=0; for(;;) i++; }\n",
                          self.tmp / "spin", self.tmp)
        os.chmod(self.tmp, 0o777)
        stdin_path = self.tmp / "in.txt"
        stdin_path.write_text("\n", encoding="utf-8")
        out_path = self.tmp / "spin.out"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            r = run_matrix._run_once(isolate, binary, stdin_path, out_path,
                                     cpu_limit_s=1.0, wall_limit_s=3.0,
                                     mem_limit_kb=256 * 1024)
        finally:
            run_matrix.close_isolate_box(isolate)

        self.assertTrue(r.killed, r)
        self.assertFalse(r.oom, r)
        self.assertGreaterEqual(r.cpu_ms, 900)

    def test_run_once_reports_a_real_oom_as_cg_oom_killed_and_classifies_ml(self):
        # A throwaway memory hog (never added to the fixture, per the task's
        # evidence standard) run under a tight --cg-mem must come back with
        # cg-oom-killed, and that must classify as ML directly — not RE,
        # which is the trap this driver has to avoid (a memory kill arrives
        # as status:SG, indistinguishable from a bare crash by status text
        # alone; cg-oom-killed is what disambiguates it).
        binary = _compile(
            "#include <cstring>\n#include <cstdlib>\n"
            "int main(){ for(;;){ char*p=(char*)malloc(8*1024*1024); "
            "if(!p) return 1; memset(p,1,8*1024*1024); } }\n",
            self.tmp / "hog", self.tmp)
        os.chmod(self.tmp, 0o777)
        stdin_path = self.tmp / "in.txt"
        stdin_path.write_text("\n", encoding="utf-8")
        out_path = self.tmp / "hog.out"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            r = run_matrix._run_once(isolate, binary, stdin_path, out_path,
                                     cpu_limit_s=5.0, wall_limit_s=15.0,
                                     mem_limit_kb=64 * 1024)
        finally:
            run_matrix.close_isolate_box(isolate)

        # The unbounded hog runs past `memory_mb + OUTPUT_SLACK_KB` (the
        # cgroup cap `_run_once` actually applies — see that constant), so
        # this is the genuine-OOM path to ML, as distinct from the max-rss
        # path `test_rss_over_the_limit_but_under_the_cgroup_cap_is_ml`
        # pins below.
        self.assertTrue(r.oom, r)
        self.assertFalse(r.killed, r)

        outcome = run_matrix._classify(r, checker=Path("/bin/true"),
                                       test=stdin_path, out=out_path,
                                       ans=stdin_path, limits=Limits(
                                           t_main_ms=1, tl_ms=1000, kill_ms=2000),
                                       mem_limit_kb=64 * 1024)
        self.assertEqual(outcome.verdict, "ML")

    def test_rss_over_the_limit_but_under_the_cgroup_cap_is_ml(self):
        # `--cg-mem` is `memory_mb + OUTPUT_SLACK_KB`, not `memory_mb`: on
        # cgroup v2 the page cache a solution dirties while writing its
        # output is charged to its cgroup until writeback drains it, so a
        # cap set exactly at `memory_mb` OOM-kills a solution for its
        # *output* (measured: anon 160 KB, file 32 MB all dirty/writeback,
        # OOM under a 32 MB cap). The cap therefore carries slack, and ML
        # is judged from `max-rss` against the *unslacked* limit. A
        # solution that touches 64 MB under a 32 MB limit must be ML
        # without ever being OOM-killed — this is the path that did not
        # exist before: pre-fix, `oom` is True here (the cap was 32 MB).
        # Same `volatile` pattern as `test_peak_kb_does_not_carry_over`,
        # so the allocation cannot be constant-folded away.
        binary = _compile(
            "#include <cstdlib>\n#include <cstdio>\n"
            "int main(){ size_t n = 64*1024*1024; "
            "volatile char *p = (volatile char*)malloc(n); if(!p) return 1; "
            "for (size_t i = 0; i < n; i += 4096) p[i] = (char)(i & 0xFF); "
            "printf(\"%d\\n\", (int)p[n-4096]); return 0; }\n",
            self.tmp / "overshoot", self.tmp)
        os.chmod(self.tmp, 0o777)
        stdin_path = self.tmp / "in.txt"
        stdin_path.write_text("\n", encoding="utf-8")
        out_path = self.tmp / "overshoot.out"
        mem_limit_kb = 32 * 1024

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            r = run_matrix._run_once(isolate, binary, stdin_path, out_path,
                                     cpu_limit_s=5.0, wall_limit_s=15.0,
                                     mem_limit_kb=mem_limit_kb)
        finally:
            run_matrix.close_isolate_box(isolate)

        self.assertFalse(r.oom, r)
        self.assertFalse(r.crashed, r)
        self.assertFalse(r.killed, r)
        self.assertGreater(r.peak_kb, mem_limit_kb, r)

        outcome = run_matrix._classify(r, checker=Path("/bin/true"),
                                       test=stdin_path, out=out_path,
                                       ans=stdin_path, limits=Limits(
                                           t_main_ms=1, tl_ms=1000, kill_ms=2000),
                                       mem_limit_kb=mem_limit_kb)
        self.assertEqual(outcome.verdict, "ML")

    def test_run_once_applies_the_output_slack_to_cg_mem(self):
        # The slack is a policy with a number attached, so pin the argv:
        # `--cg-mem` must be the limit plus `OUTPUT_SLACK_KB`, and the slack
        # must be exactly `--fsize` — the largest single file the sandbox
        # permits, so any output the harness allows can sit fully dirty in
        # the page cache without tripping the cap.
        binary = _compile("int main(){ return 0; }\n", self.tmp / "argv", self.tmp)
        os.chmod(self.tmp, 0o777)
        stdin_path = self.tmp / "in.txt"
        stdin_path.write_text("\n", encoding="utf-8")
        mem_limit_kb = 32 * 1024

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            argv = self._isolate_run_argv(lambda: run_matrix._run_once(
                isolate, binary, stdin_path, self.tmp / "argv.out",
                cpu_limit_s=5.0, wall_limit_s=15.0, mem_limit_kb=mem_limit_kb))
        finally:
            run_matrix.close_isolate_box(isolate)

        self.assertEqual(run_matrix.OUTPUT_SLACK_KB, run_matrix.OUTPUT_LIMIT_KB)
        self.assertIn(f"--cg-mem={mem_limit_kb + run_matrix.OUTPUT_SLACK_KB}", argv)
        self.assertIn(f"--fsize={run_matrix.OUTPUT_LIMIT_KB}", argv)

    def test_oom_does_not_leak_into_the_next_run_in_the_same_handle(self):
        # Task 9c: the `flight` dogfood found that isolate's cgroup counters
        # are NOT reset between `--run`s in the same box — reproduced with
        # bare isolate, no involvement from this module. A hog that OOMs
        # followed by a trivial, memory-innocent program in the SAME box
        # reported the hog's cg-oom-killed for the trivial program too.
        # Since ML outranks WA in _SEVERITY, that doesn't just add a wrong
        # row to invocation.json — it overwrites a correct verdict with a
        # wrong one. This test must FAIL against the single-persistent-box
        # code this task replaces (confirmed: see the task report for the
        # actual failing-before transcript) and PASS now that every
        # `_run_once` call leases its own fresh box from `box_pool`.
        hog = _compile(
            "#include <cstring>\n#include <cstdlib>\n"
            "int main(){ for(;;){ char*p=(char*)malloc(8*1024*1024); "
            "if(!p) return 1; memset(p,1,8*1024*1024); } }\n",
            self.tmp / "hog2", self.tmp)
        tiny = _compile("int main(){ return 0; }\n", self.tmp / "tiny", self.tmp)
        os.chmod(self.tmp, 0o777)
        stdin_path = self.tmp / "in.txt"
        stdin_path.write_text("\n", encoding="utf-8")

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            r_hog = run_matrix._run_once(
                isolate, hog, stdin_path, self.tmp / "hog2.out",
                cpu_limit_s=5.0, wall_limit_s=15.0, mem_limit_kb=64 * 1024)
            self.assertTrue(r_hog.oom, r_hog)  # sanity: the hog did OOM

            r_tiny = run_matrix._run_once(
                isolate, tiny, stdin_path, self.tmp / "tiny.out",
                cpu_limit_s=5.0, wall_limit_s=15.0, mem_limit_kb=64 * 1024)
        finally:
            run_matrix.close_isolate_box(isolate)

        self.assertFalse(r_tiny.oom, r_tiny)
        self.assertLess(r_tiny.peak_kb, 10_000, r_tiny)

    def test_peak_kb_does_not_carry_over_between_runs(self):
        # The other half of the same box-lifetime bug: `cg-mem` is a
        # box-lifetime high-water mark, so a solution that allocates
        # substantially followed by one that does not must not have the
        # second's peak_kb inflated by the first's — with or without an
        # OOM involved.
        # `p` is `volatile` and written a non-constant value per page: a
        # plain malloc+memset+read-one-byte with no other use of `p` is
        # legal for GCC to constant-fold away *entirely* (it can prove the
        # byte printed back is always 1 and eliminate the allocation with
        # it) — which the first version of this test learned the hard way
        # (objdump showed no call to malloc/memset at all, and peak_kb came
        # back at ~1.6 MB instead of ~200 MB). `volatile` forces every
        # access to actually happen.
        big = _compile(
            "#include <cstdlib>\n#include <cstdio>\n"
            "int main(){ size_t n = 200*1024*1024; "
            "volatile char *p = (volatile char*)malloc(n); if(!p) return 1; "
            "for (size_t i = 0; i < n; i += 4096) p[i] = (char)(i & 0xFF); "
            "printf(\"%d\\n\", (int)p[n-4096]); return 0; }\n",
            self.tmp / "big", self.tmp)
        small = _compile("int main(){ return 0; }\n", self.tmp / "small", self.tmp)
        os.chmod(self.tmp, 0o777)
        stdin_path = self.tmp / "in.txt"
        stdin_path.write_text("\n", encoding="utf-8")

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            r_big = run_matrix._run_once(
                isolate, big, stdin_path, self.tmp / "big.out",
                cpu_limit_s=5.0, wall_limit_s=15.0, mem_limit_kb=256 * 1024)
            r_small = run_matrix._run_once(
                isolate, small, stdin_path, self.tmp / "small.out",
                cpu_limit_s=5.0, wall_limit_s=15.0, mem_limit_kb=256 * 1024)
        finally:
            run_matrix.close_isolate_box(isolate)

        self.assertFalse(r_big.oom, r_big)
        self.assertGreater(r_big.peak_kb, 100_000, r_big)
        self.assertLess(r_small.peak_kb, 10_000, r_small)
        self.assertNotEqual(r_big.peak_kb, r_small.peak_kb)

    def test_box_is_cleaned_up_after_a_single_run_that_raises(self):
        # Task 9c: cleanup is now per-`--run` (a box lives from just before
        # one _run_once call to just after it), not per-run() — so the
        # exception-safety guarantee has to be re-pinned at that smaller
        # scope. Force _run_once itself to raise partway through (after the
        # sandboxed process has already run and a box exists) by making
        # meta parsing blow up, and confirm that specific box is still
        # torn down by _run_once's own `finally`.
        binary = _compile("int main(){ return 0; }\n", self.tmp / "ok", self.tmp)
        os.chmod(self.tmp, 0o777)
        stdin_path = self.tmp / "in.txt"
        stdin_path.write_text("\n", encoding="utf-8")
        out_path = self.tmp / "ok.out"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            # `_run_once` leases its own box id now (no more
            # `box_id_counter` to seed) — record whichever id the real
            # `box_pool.lease` hands out (still under its real flock, so
            # this test does not collide with a concurrently running
            # second copy of this same suite the way a hardcoded id with
            # no locking would) and check that one's directory afterward.
            with _track_leased_box_ids() as leased:
                with mock.patch.object(run_matrix, "_parse_meta",
                                       side_effect=RuntimeError("boom")):
                    with self.assertRaises(RuntimeError):
                        run_matrix._run_once(isolate, binary, stdin_path, out_path,
                                             cpu_limit_s=1.0, wall_limit_s=3.0,
                                             mem_limit_kb=256 * 1024)
            self._assert_boxes_gone(leased)
        finally:
            run_matrix.close_isolate_box(isolate)

    def test_boxes_are_cleaned_up_after_a_real_run(self):
        # A box leaked under /var/local/lib/isolate/<id> is exactly the
        # failure mode a `finally`-guarded `--cleanup` exists to prevent —
        # confirm it is actually gone after a clean run and after a
        # hole-firing one. Neither of these actually *raises* out of
        # run() (the hole-firing input still returns a payload, it just
        # reports a hole) — see
        # test_boxes_are_cleaned_up_after_run_raises below for the path
        # that does raise, which review found this test's old comment
        # claimed to cover but did not.
        #
        # Task 9c: `run()` now opens and closes a *different* box for every
        # single sandboxed execution, each leased from `box_pool`, so
        # checking only one fixed id would only ever pin the first of
        # several boxes a real run opens. `_track_leased_box_ids` records
        # every id this invocation actually leased so all of them are
        # checked, not just the first — and, unlike snapshotting the whole
        # of `/var/local/lib/isolate/`, does not misreport a leak when a
        # concurrently running second copy of this suite is using the same
        # small pool of ids (`pool_size()` is 4 here, so "other" ids are
        # not guaranteed): each `(box_id, exists)` is recorded while this
        # invocation still holds that id's flock, so no sibling can have
        # taken it yet at the moment of observation. See
        # `_track_leased_box_ids`'s own docstring for the full reasoning.
        with _track_leased_box_ids() as leased:
            run_matrix.run(self.problem_dir, self.testlib_dir)
        self._assert_boxes_gone(leased)

        (self.problem_dir / "tests" / "g1" / "01.in").write_text(
            "0 0\n", encoding="utf-8")
        with _track_leased_box_ids() as leased:
            payload = run_matrix.run(self.problem_dir, self.testlib_dir)
        self.assertEqual(len(payload["holes"]), 1)  # sanity: still ran
        self._assert_boxes_gone(leased)

    def test_boxes_are_cleaned_up_after_run_raises(self):
        # Task 9b review finding D: the test above never actually drives
        # run() through its exception path (`finally: close_isolate_box`
        # in run()) — both of its calls return normally. Force a genuine
        # raise by replacing the model solution with a source that
        # segfaults, so pass 1's `r.crashed` branch raises MatrixError
        # out of the middle of the `try`, and confirm cleanup still fired.
        (self.problem_dir / "solutions" / "sol-main.cpp").write_text(
            _MAIN_HEADER + "int main(){ int *p = nullptr; *p = 1; return 0; }\n",
            encoding="utf-8")
        with _track_leased_box_ids() as leased:
            with self.assertRaises(run_matrix.MatrixError):
                run_matrix.run(self.problem_dir, self.testlib_dir)
        self._assert_boxes_gone(leased)

    def test_crashing_model_solution_is_diagnosed_as_crashed_not_exited_0(self):
        # Task 9b review finding A: a signal death (status SG) carries no
        # `exitcode` line in isolate's meta file, so defaulting exit_code
        # to 0 and reporting "exited 0" reads like a bug in the check
        # itself rather than a crashing model solution. The message must
        # name the crash, not claim a clean exit.
        (self.problem_dir / "solutions" / "sol-main.cpp").write_text(
            _MAIN_HEADER + "int main(){ int *p = nullptr; *p = 1; return 0; }\n",
            encoding="utf-8")
        with self.assertRaises(run_matrix.MatrixError) as ctx:
            run_matrix.run(self.problem_dir, self.testlib_dir)
        message = str(ctx.exception)
        self.assertIn("crashed", message)
        self.assertNotIn("exited 0", message)

    def test_pass1_wall_clock_kill_names_the_wall_limit_not_cpu(self):
        # Task 9b review finding B: isolate reports status:TO for both a
        # CPU-time kill and a wall-time kill, and the old diagnostic
        # always blamed MODEL_SAFETY_CPU_S regardless of which one
        # actually fired. A model solution that sleeps (near-zero CPU
        # time, real wall time) must be blamed for the wall-clock ceiling,
        # not told it burned 60 seconds of CPU it never used. Patches the
        # wall ceiling down to make this fast and deterministic rather
        # than sleeping for the real 90s default.
        (self.problem_dir / "solutions" / "sol-main.cpp").write_text(
            _MAIN_HEADER + "#include <unistd.h>\nint main(){ sleep(3); return 0; }\n",
            encoding="utf-8")
        with mock.patch.object(run_matrix, "MODEL_SAFETY_WALL_S", 1.0):
            with self.assertRaises(run_matrix.MatrixError) as ctx:
                run_matrix.run(self.problem_dir, self.testlib_dir)
        message = str(ctx.exception)
        self.assertIn("wall-clock", message)
        self.assertNotIn("CPU time", message)

    def test_solution_output_lands_in_repo_owned_by_us_not_a_subuid(self):
        # Task 9b review's Critical finding: an earlier version of this
        # driver bind-mounted tests/<group>/ and .build/ read-write, so
        # every file the sandbox created there (the regenerated .a answer
        # file, a solution's .out) came back owned by the mapped subuid —
        # not us, not writable or chmod-able by us afterward — and the
        # directory itself was left permanently o+w. Confirm both halves
        # are fixed: ownership and mode.
        payload = run_matrix.run(self.problem_dir, self.testlib_dir)
        self.assertTrue(payload["results"])

        my_uid = os.getuid()
        answer_files = list((self.problem_dir / "tests" / "g1").glob("*.a"))
        self.assertTrue(answer_files)
        for answer in answer_files:
            st = answer.stat()
            self.assertEqual(st.st_uid, my_uid,
                             f"{answer} is owned by uid {st.st_uid}, not ours "
                             f"({my_uid}) — the ownership-transfer bug")
            self.assertTrue(os.access(answer, os.W_OK),
                            f"{answer} is not writable by us")

        out_files = list((self.problem_dir / ".build").glob("*.out"))
        self.assertTrue(out_files)
        for out in out_files:
            st = out.stat()
            self.assertEqual(st.st_uid, my_uid,
                             f"{out} is owned by uid {st.st_uid}, not ours")

        tests_mode = stat.S_IMODE((self.problem_dir / "tests" / "g1").stat().st_mode)
        self.assertFalse(tests_mode & stat.S_IWOTH,
                         "tests/g1 was left world-writable by run()")
        build_mode = stat.S_IMODE((self.problem_dir / ".build").stat().st_mode)
        self.assertFalse(build_mode & stat.S_IWOTH,
                         ".build was left world-writable by run()")

    def test_run_heals_a_directory_damaged_by_the_old_read_write_mount(self):
        # Simulate exactly the damage the old behaviour left behind (a
        # stray o+w bit on tests/<group>/, verified for real on this
        # machine's own fixture prior to this fix — see the task report)
        # and confirm a fresh run() strips it back off rather than
        # perpetuating or ignoring it.
        group_dir = self.problem_dir / "tests" / "g1"
        group_dir.chmod(stat.S_IMODE(group_dir.stat().st_mode) | stat.S_IWOTH)
        self.assertTrue(stat.S_IMODE(group_dir.stat().st_mode) & stat.S_IWOTH)

        run_matrix.run(self.problem_dir, self.testlib_dir)

        healed_mode = stat.S_IMODE(group_dir.stat().st_mode)
        self.assertFalse(healed_mode & stat.S_IWOTH,
                         "run() did not heal a pre-existing o+w directory")

    def test_large_output_is_not_charged_against_the_memory_limit(self):
        # Final-review Critical: the staging directory was a bare
        # `tempfile.mkdtemp()`, i.e. `/tmp`, i.e. tmpfs. `--stdout` pointed
        # into it while `--cg-mem` capped the same cgroup, and tmpfs pages
        # are charged to the writing cgroup and are not reclaimable — so a
        # solution's own output counted as its memory. Reproduced with bare
        # isolate before the fix: a 1.6 MB program writing 70 MB to stdout
        # under a 64 MB limit came back
        # `max-rss:1668 cg-mem:65536 cg-oom-killed:1 status:SG`, a false ML
        # on a program using 2.5% of its limit.
        #
        # This test FAILS against the pre-fix driver (verified: see the
        # final fix report for the transcript) — 48 MB of output under a
        # 32 MB limit is an OOM there and an ordinary OK here.
        #
        # The buffer is `static` and the program's own footprint is ~1-2 MB,
        # so any memory reading above a few MB is coming from the output,
        # not from the process.
        mb_out = 48
        binary = _compile(
            "#include <cstdio>\n"
            "int main(){ static char buf[1<<16];\n"
            "  for (int i = 0; i < (1<<16); i++) buf[i] = 'x';\n"
            f"  for (int k = 0; k < {mb_out} * 16; k++) fwrite(buf, 1, 1<<16, stdout);\n"
            "  return 0; }\n",
            self.tmp / "loud", self.tmp)
        os.chmod(self.tmp, 0o777)
        stdin_path = self.tmp / "in.txt"
        stdin_path.write_text("\n", encoding="utf-8")
        out_path = self.tmp / "loud.out"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            r = run_matrix._run_once(isolate, binary, stdin_path, out_path,
                                     cpu_limit_s=10.0, wall_limit_s=30.0,
                                     mem_limit_kb=32 * 1024)
        finally:
            run_matrix.close_isolate_box(isolate)

        self.assertFalse(r.oom, r)
        self.assertFalse(r.crashed, r)
        self.assertFalse(r.killed, r)
        self.assertLess(r.peak_kb, 10_000, r)
        self.assertEqual(out_path.stat().st_size, mb_out * 1024 * 1024)

        outcome = run_matrix._classify(r, checker=Path("/bin/true"),
                                       test=stdin_path, out=out_path,
                                       ans=stdin_path, limits=Limits(
                                           t_main_ms=1, tl_ms=1000, kill_ms=2000),
                                       mem_limit_kb=32 * 1024)
        self.assertEqual(outcome.verdict, "OK")

    def test_output_is_bounded_by_fsize_and_surfaces_as_a_crash_not_an_ml(self):
        # The other half of the same fix. Once staging is disk-backed,
        # nothing accidentally caps output any more — a `while(1)
        # putchar()` solution would write until the disk filled and then
        # have the whole file read into the driver's RAM by
        # `staged_out.read_bytes()`. `--fsize` is the deliberate ceiling.
        # OUTPUT_LIMIT_KB is patched down to 1 MB so this stays fast; the
        # real 256 MB constant is exercised by the same code path.
        binary = _compile(
            "#include <cstdio>\n"
            "int main(){ for(;;) putchar('x'); }\n",
            self.tmp / "runaway", self.tmp)
        os.chmod(self.tmp, 0o777)
        stdin_path = self.tmp / "in.txt"
        stdin_path.write_text("\n", encoding="utf-8")
        out_path = self.tmp / "runaway.out"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            with mock.patch.object(run_matrix, "OUTPUT_LIMIT_KB", 1024):
                r = run_matrix._run_once(isolate, binary, stdin_path, out_path,
                                         cpu_limit_s=10.0, wall_limit_s=30.0,
                                         mem_limit_kb=256 * 1024)
        finally:
            run_matrix.close_isolate_box(isolate)

        # SIGXFSZ, so: a signal death with no cg-oom-killed. It must be RE
        # (the solution's output ran away), never ML (the solution used too
        # much memory) — those are different findings for the setter.
        self.assertTrue(r.crashed, r)
        self.assertFalse(r.oom, r)
        self.assertLessEqual(out_path.stat().st_size, 1024 * 1024)

        outcome = run_matrix._classify(r, checker=Path("/bin/true"),
                                       test=stdin_path, out=out_path,
                                       ans=stdin_path, limits=Limits(
                                           t_main_ms=1, tl_ms=1000, kill_ms=2000),
                                       mem_limit_kb=256 * 1024)
        self.assertEqual(outcome.verdict, "RE")

    # ------------------------------------------------------------------
    # File-based IO (`io.input`/`io.output` naming real files rather than
    # the `stdin`/`stdout` sentinels). Every test below drives `_run_once`
    # directly: `run()` still refuses file IO one level up, and wiring that
    # is a later task — this one is only about the sandboxed execution.
    # ------------------------------------------------------------------

    def test_file_io_solution_reads_its_inp_and_writes_its_out(self):
        # A solution that never touches stdin or stdout at all: it opens
        # "t.inp" and "t.out" by *relative* name, so this passes only if the
        # sandbox's cwd is the one `:rw` mount (the staging directory). It
        # fails two distinct ways against the pre-fix driver: `--chdir` used
        # to point at the binary's read-only mount, where fopen("t.inp") is
        # NULL (exit 3, `crashed`) and where "t.out" could not be created at
        # all even if the input had been found.
        binary = _compile(
            '#include <cstdio>\n'
            'int main(){ FILE *fi = fopen("t.inp", "r"); if (!fi) return 3;\n'
            '  int a, b; if (fscanf(fi, "%d %d", &a, &b) != 2) return 4;\n'
            '  fclose(fi);\n'
            '  FILE *fo = fopen("t.out", "w"); if (!fo) return 5;\n'
            '  fprintf(fo, "%d\\n", a + b); fclose(fo); return 0; }\n',
            self.tmp / "fileio", self.tmp)
        os.chmod(self.tmp, 0o777)
        test_in = self.tmp / "01.in"
        test_in.write_text("2 3\n", encoding="utf-8")
        dest = self.tmp / "01.produced"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            r = run_matrix._run_once(isolate, binary, test_in, dest,
                                     cpu_limit_s=2.0, wall_limit_s=6.0,
                                     mem_limit_kb=256 * 1024,
                                     io_input="t.inp", io_output="t.out")
        finally:
            run_matrix.close_isolate_box(isolate)

        self.assertFalse(r.crashed, r)   # exit 3/4/5 above would show up here
        self.assertEqual(r.exit_code, 0, r)
        self.assertFalse(r.no_output, r)
        self.assertEqual(dest.read_text(encoding="utf-8").strip(), "5")

    def test_file_io_missing_output_file_is_reported_not_crashed(self):
        # Exits 0 and writes nothing — an outcome a stdin/stdout problem
        # cannot have (isolate always creates the stdout file), so it needs
        # its own signal rather than being folded into `crashed`.
        binary = _compile("int main(){ return 0; }\n", self.tmp / "silent", self.tmp)
        os.chmod(self.tmp, 0o777)
        test_in = self.tmp / "01.in"
        test_in.write_text("2 3\n", encoding="utf-8")
        dest = self.tmp / "01.produced"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            r = run_matrix._run_once(isolate, binary, test_in, dest,
                                     cpu_limit_s=2.0, wall_limit_s=6.0,
                                     mem_limit_kb=256 * 1024,
                                     io_input="t.inp", io_output="t.out")
        finally:
            run_matrix.close_isolate_box(isolate)

        self.assertTrue(r.no_output, r)
        self.assertFalse(r.crashed, r)   # a clean exit is not a crash
        self.assertFalse(r.killed, r)
        self.assertFalse(r.oom, r)
        self.assertEqual(r.exit_code, 0, r)

    def test_stdin_mode_never_reports_no_output(self):
        # Pins the `no_output` docstring claim that it is only reachable in
        # file-IO mode: the *same* silent binary, run through the default
        # path, has a stdout file (empty) and must report no_output=False.
        # Without this, "only reachable in file-IO mode" is an untested
        # claim about a field a later task classifies as a verdict.
        binary = _compile("int main(){ return 0; }\n", self.tmp / "silent_std", self.tmp)
        os.chmod(self.tmp, 0o777)
        test_in = self.tmp / "01.in"
        test_in.write_text("2 3\n", encoding="utf-8")
        dest = self.tmp / "01.produced"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            r = run_matrix._run_once(isolate, binary, test_in, dest,
                                     cpu_limit_s=2.0, wall_limit_s=6.0,
                                     mem_limit_kb=256 * 1024)
        finally:
            run_matrix.close_isolate_box(isolate)

        self.assertFalse(r.no_output, r)
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_bytes(), b"")

    def test_file_io_output_does_not_leak_between_runs(self):
        # The same contamination shape as the three memory bugs, one level
        # down: `_time_median` calls `_run_once` three times and every
        # solution reuses the same handle — hence the same staging
        # directory. Run 1 writes "first"; run 2 writes nothing at all. If
        # the pre-run unlink of the output file is removed, run 2 reads run
        # 1's file and is reported as a solution that produced "first".
        writer = _compile(
            '#include <cstdio>\n'
            'int main(){ FILE *f = fopen("t.out", "w"); if (!f) return 5;\n'
            '  fprintf(f, "first\\n"); fclose(f); return 0; }\n',
            self.tmp / "writer", self.tmp)
        silent = _compile("int main(){ return 0; }\n", self.tmp / "silent2", self.tmp)
        os.chmod(self.tmp, 0o777)
        test_in = self.tmp / "01.in"
        test_in.write_text("x\n", encoding="utf-8")
        d1, d2 = self.tmp / "a.produced", self.tmp / "b.produced"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            r1 = run_matrix._run_once(isolate, writer, test_in, d1,
                                      cpu_limit_s=2.0, wall_limit_s=6.0,
                                      mem_limit_kb=256 * 1024,
                                      io_input="t.inp", io_output="t.out")
            r2 = run_matrix._run_once(isolate, silent, test_in, d2,
                                      cpu_limit_s=2.0, wall_limit_s=6.0,
                                      mem_limit_kb=256 * 1024,
                                      io_input="t.inp", io_output="t.out")
        finally:
            run_matrix.close_isolate_box(isolate)

        self.assertFalse(r1.no_output, r1)
        self.assertEqual(d1.read_text(encoding="utf-8").strip(), "first")
        self.assertTrue(r2.no_output, r2)
        # The destination is rewritten every run too, so a stale `.out` in
        # the repository cannot be read as this run's answer either.
        self.assertEqual(d2.read_bytes(), b"")

    def test_a_stray_file_from_one_run_does_not_break_the_next(self):
        # Found by the Task 6 dogfood, not by reasoning. The three targeted
        # unlinks this driver used to do (`run.out`, io_input, io_output)
        # covered only the names it knows. A solution that writes any OTHER
        # filename — `output.txt` here, which is precisely the
        # wrong-output-filename mistake the NO_OUTPUT verdict exists to
        # diagnose — leaves that file behind owned by the mapped subuid of
        # its own box, and every `_run_once` claims a fresh box id, hence a
        # different subuid. The next run's `fopen(..., "w")` on it then
        # fails EACCES, the solution exits 4, and the driver reports RE.
        #
        # So the *same binary on the same input* used to return no_output on
        # its first run and crashed/RE on its second: a verdict that
        # depended on execution order. Both runs below must be identical.
        stray = _compile(
            '#include <cstdio>\n'
            'int main(){ FILE *f = fopen("output.txt", "w"); if (!f) return 4;\n'
            '  fprintf(f, "answer\\n"); fclose(f); return 0; }\n',
            self.tmp / "stray", self.tmp)
        os.chmod(self.tmp, 0o777)
        test_in = self.tmp / "01.in"
        test_in.write_text("2 3\n", encoding="utf-8")

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            first = run_matrix._run_once(isolate, stray, test_in,
                                         self.tmp / "a.produced",
                                         cpu_limit_s=2.0, wall_limit_s=6.0,
                                         mem_limit_kb=256 * 1024,
                                         io_input="t.inp", io_output="t.out")
            second = run_matrix._run_once(isolate, stray, test_in,
                                          self.tmp / "b.produced",
                                          cpu_limit_s=2.0, wall_limit_s=6.0,
                                          mem_limit_kb=256 * 1024,
                                          io_input="t.inp", io_output="t.out")
        finally:
            run_matrix.close_isolate_box(isolate)

        for label, r in (("first", first), ("second", second)):
            with self.subTest(run=label):
                # It wrote the wrong filename: no output file, clean exit.
                self.assertTrue(r.no_output, r)
                self.assertFalse(r.crashed, r)
                self.assertEqual(r.exit_code, 0, r)

    def test_file_io_output_is_not_charged_against_the_memory_limit(self):
        # Risk 1 — the tmpfs bug, a fourth time. The first three times the
        # contaminated write was the driver's own staging of *stdout*; the
        # solution's own output file is a new writable file inside the box
        # and is the same shape again. 48 MB written under a 32 MB
        # `--cg-mem` is an OK on a disk-backed staging directory and an OOM
        # on a memory-backed one, so this fails immediately if the output
        # file ever moves onto tmpfs or into a second, memory-backed mount.
        # The buffer is `static` and the program's own footprint is ~1-2 MB.
        mb_out = 48
        binary = _compile(
            "#include <cstdio>\n"
            'int main(){ static char buf[1<<16];\n'
            "  for (int i = 0; i < (1<<16); i++) buf[i] = 'x';\n"
            '  FILE *f = fopen("t.out", "w"); if (!f) return 5;\n'
            f"  for (int k = 0; k < {mb_out} * 16; k++) fwrite(buf, 1, 1<<16, f);\n"
            "  fclose(f); return 0; }\n",
            self.tmp / "bigout", self.tmp)
        os.chmod(self.tmp, 0o777)
        test_in = self.tmp / "01.in"
        test_in.write_text("x\n", encoding="utf-8")
        dest = self.tmp / "big.produced"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            r = run_matrix._run_once(isolate, binary, test_in, dest,
                                     cpu_limit_s=10.0, wall_limit_s=30.0,
                                     mem_limit_kb=32 * 1024,
                                     io_input="t.inp", io_output="t.out")
        finally:
            run_matrix.close_isolate_box(isolate)

        self.assertFalse(r.oom, r)
        self.assertFalse(r.crashed, r)
        self.assertFalse(r.killed, r)
        self.assertFalse(r.no_output, r)
        self.assertLess(r.peak_kb, 10_000, r)
        self.assertEqual(dest.stat().st_size, mb_out * 1024 * 1024)

    def test_file_io_name_colliding_with_the_staged_stdout_is_refused(self):
        # `--stdout` still points at the staging directory's fixed `run.out`
        # in file-IO mode (see `_run_once`). A problem whose own io.output
        # is literally that name would have isolate and the solution writing
        # the same file — garbage, silently. Task 1 accepts any bare
        # filename, so this collision is reachable and must be refused
        # rather than run.
        binary = _compile("int main(){ return 0; }\n", self.tmp / "collide", self.tmp)
        os.chmod(self.tmp, 0o777)
        test_in = self.tmp / "01.in"
        test_in.write_text("x\n", encoding="utf-8")

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            with self.assertRaises(run_matrix.MatrixError) as ctx:
                run_matrix._run_once(isolate, binary, test_in,
                                     self.tmp / "c.produced",
                                     cpu_limit_s=2.0, wall_limit_s=6.0,
                                     mem_limit_kb=256 * 1024,
                                     io_input="t.inp",
                                     io_output=run_matrix.STAGED_STDOUT_NAME)
        finally:
            run_matrix.close_isolate_box(isolate)
        self.assertIn(run_matrix.STAGED_STDOUT_NAME, str(ctx.exception))

    def test_file_io_same_name_for_input_and_output_is_refused(self):
        # Measured, not theorised (review finding): with both names equal,
        # the staged input IS the file read back as the answer, so a
        # solution that writes nothing returns the test data as its output
        # and the checker accepts it — a silent, confident wrong verdict on
        # every test. `problem_meta` refuses this at load time as well;
        # this pins the check at the point of use, since `_run_once` is
        # called directly.
        binary = _compile("int main(){ return 0; }\n", self.tmp / "samename", self.tmp)
        os.chmod(self.tmp, 0o777)
        test_in = self.tmp / "01.in"
        test_in.write_text("SECRET-TEST-INPUT\n", encoding="utf-8")
        dest = self.tmp / "same.produced"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            with self.assertRaises(run_matrix.MatrixError) as ctx:
                run_matrix._run_once(isolate, binary, test_in, dest,
                                     cpu_limit_s=2.0, wall_limit_s=6.0,
                                     mem_limit_kb=256 * 1024,
                                     io_input="t.txt", io_output="t.txt")
        finally:
            run_matrix.close_isolate_box(isolate)
        self.assertIn("t.txt", str(ctx.exception))
        # The specific damage: the test input must never reach `dest`.
        self.assertFalse(dest.exists(), dest)

    def test_file_io_staged_input_is_readable_under_a_strict_umask(self):
        # Review finding: `run()` grants the real test file the "other" read
        # bit the mapped subuid needs (`_ensure_sandbox_readable`), and
        # `shutil.copyfile` recreates the staged copy at `0666 & ~umask`,
        # throwing that heal away. At umask 077 the sandbox could not open
        # its own input and the failure surfaced as isolate `status:XX`
        # ("Permission denied") — i.e. the driver blaming isolate for a
        # permission bit it set itself, on every file-IO run, for anyone
        # with a hardened umask.
        #
        # The umask is set only around the `_run_once` call: the binary and
        # the test file are created before it (as `run()` would, already
        # healed), so the only file this window affects is the staged copy.
        binary = _compile(
            '#include <cstdio>\n'
            'int main(){ FILE *fi = fopen("t.inp", "r"); if (!fi) return 3;\n'
            '  int a, b; if (fscanf(fi, "%d %d", &a, &b) != 2) return 4;\n'
            '  fclose(fi);\n'
            '  FILE *fo = fopen("t.out", "w"); if (!fo) return 5;\n'
            '  fprintf(fo, "%d\\n", a + b); fclose(fo); return 0; }\n',
            self.tmp / "umask_io", self.tmp)
        os.chmod(self.tmp, 0o777)
        test_in = self.tmp / "01.in"
        test_in.write_text("2 3\n", encoding="utf-8")
        run_matrix._ensure_sandbox_readable(test_in)
        dest = self.tmp / "01.produced"

        isolate = run_matrix.open_isolate_box(self.tmp)
        previous_umask = os.umask(0o077)
        try:
            r = run_matrix._run_once(isolate, binary, test_in, dest,
                                     cpu_limit_s=2.0, wall_limit_s=6.0,
                                     mem_limit_kb=256 * 1024,
                                     io_input="t.inp", io_output="t.out")
        finally:
            os.umask(previous_umask)
            run_matrix.close_isolate_box(isolate)

        self.assertFalse(r.crashed, r)
        self.assertFalse(r.no_output, r)
        self.assertEqual(dest.read_text(encoding="utf-8").strip(), "5")

    def test_file_io_unreadable_output_is_a_matrix_error_not_a_bare_oserror(self):
        # The other permission direction, and the other half of the same
        # review finding. The solution owns its output file, so it can leave
        # it -rw------- under the sandbox's subuid; we own only the staging
        # directory, so we can neither read nor chmod it. Left bare, the
        # PermissionError escaped `_run_once` and aborted the whole matrix
        # mid-run on one careless solution (R1: no bare stdlib exception on
        # solution-controlled state). It must NOT be reported as
        # `no_output`: "unreadable" and "never written" are different facts.
        binary = _compile(
            '#include <cstdio>\n#include <sys/stat.h>\n'
            'int main(){ umask(077);\n'
            '  FILE *f = fopen("t.out", "w"); if (!f) return 5;\n'
            '  fprintf(f, "hidden\\n"); fclose(f); return 0; }\n',
            self.tmp / "secretive", self.tmp)
        os.chmod(self.tmp, 0o777)
        test_in = self.tmp / "01.in"
        test_in.write_text("x\n", encoding="utf-8")
        dest = self.tmp / "secret.produced"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            with self.assertRaises(run_matrix.MatrixError) as ctx:
                run_matrix._run_once(isolate, binary, test_in, dest,
                                     cpu_limit_s=2.0, wall_limit_s=6.0,
                                     mem_limit_kb=256 * 1024,
                                     io_input="t.inp", io_output="t.out")
        finally:
            run_matrix.close_isolate_box(isolate)

        message = str(ctx.exception)
        self.assertIn("t.out", message)          # names the file
        self.assertIn("secretive", message)      # names the solution
        self.assertIn("not readable", message)   # not "produced no output"

    def test_stdin_mode_is_unchanged(self):
        # The default path must behave exactly as before: this test passes
        # both before and after the file-IO change, and is here so that a
        # regression in the sentinel path shows up as a failure about the
        # sentinel path rather than as a puzzling fixture failure.
        binary = _compile(
            '#include <cstdio>\n'
            'int main(){ int a, b; scanf("%d %d", &a, &b);\n'
            '  printf("%d\\n", a + b); return 0; }\n',
            self.tmp / "stdio_sum", self.tmp)
        os.chmod(self.tmp, 0o777)
        test_in = self.tmp / "01.in"
        test_in.write_text("7 8\n", encoding="utf-8")
        dest = self.tmp / "s.produced"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            r = run_matrix._run_once(isolate, binary, test_in, dest,
                                     cpu_limit_s=2.0, wall_limit_s=6.0,
                                     mem_limit_kb=256 * 1024)
        finally:
            run_matrix.close_isolate_box(isolate)

        self.assertFalse(r.crashed, r)
        self.assertEqual(dest.read_text(encoding="utf-8").strip(), "15")

    # ------------------------------------------------------------------
    # What the solution may leave at `io.output`. File IO handed the
    # *solution* the choice of what kind of filesystem object sits at that
    # name, and the driver then reads it as its own uid, OUTSIDE the
    # sandbox. In stdin mode this surface does not exist at all: isolate
    # creates `run.out` itself. All three shapes below must be reported
    # (`MatrixError`), never read, never hung on, and never folded into
    # `no_output` — "the solution substituted a pipe for its output" is not
    # "the solution produced no output".
    # ------------------------------------------------------------------

    def test_file_io_symlinked_output_is_refused_instead_of_read(self):
        # The exfiltration half. `symlink(<any absolute path>, "t.out")`
        # needs no mount and no privilege — the sandbox only has to create
        # the link; the *driver* is what dereferences it, running as the
        # user who started the pipeline, with that user's whole filesystem
        # in range. Whatever came back was handed to the checker as this
        # solution's answer, and on the model solution's pass 1 it was
        # written into the jury's `.a` answer key.
        #
        # The target here is a file next to the tests, standing in for a
        # jury answer, with a marker that must never reach `dest`.
        secret = self.tmp / "jury-answer.a"
        secret.write_text("JURY-ANSWER-42\n", encoding="utf-8")
        binary = _compile(
            "#include <unistd.h>\n"
            "int main(){ if (symlink(\"%s\", \"t.out\") != 0) return 6;\n"
            "  return 0; }\n" % secret,
            self.tmp / "symlinker", self.tmp)
        os.chmod(self.tmp, 0o777)
        test_in = self.tmp / "01.in"
        test_in.write_text("x\n", encoding="utf-8")
        dest = self.tmp / "sym.produced"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            with self.assertRaises(run_matrix.MatrixError) as ctx:
                run_matrix._run_once(isolate, binary, test_in, dest,
                                     cpu_limit_s=2.0, wall_limit_s=6.0,
                                     mem_limit_kb=256 * 1024,
                                     io_input="t.inp", io_output="t.out")
        finally:
            run_matrix.close_isolate_box(isolate)

        message = str(ctx.exception)
        self.assertIn("t.out", message)                 # names the file
        self.assertIn("symlinker", message)             # names the solution
        self.assertIn("not a regular file", message)
        # The damage the guard exists to prevent: the target's contents must
        # not have been read, and above all must not have reached the file
        # the checker (and, in pass 1, the answer key) is built from.
        self.assertFalse(dest.exists(), dest)

    def test_file_io_fifo_output_does_not_hang_the_driver(self):
        # The denial-of-service half, and the reason the guard cannot be a
        # `try: read / except: report`: `open()` on a FIFO with no writer
        # blocks forever. Nothing times that read out, it sits *inside*
        # `_run_once`'s `try`, so the `finally` never runs and the box leaks
        # on top of the hang. SIGALRM below is the regression signal: a
        # driver that goes back to reading blindly fails this test in 30
        # seconds instead of wedging CI until someone kills it.
        binary = _compile(
            "#include <sys/types.h>\n#include <sys/stat.h>\n"
            'int main(){ if (mkfifo("t.out", 0666) != 0) return 6;\n'
            "  return 0; }\n",
            self.tmp / "fifomaker", self.tmp)
        os.chmod(self.tmp, 0o777)
        test_in = self.tmp / "01.in"
        test_in.write_text("x\n", encoding="utf-8")
        dest = self.tmp / "fifo.produced"

        def _too_slow(signum, frame):
            raise TimeoutError(
                "_run_once blocked reading the solution's FIFO — the "
                "regular-file guard is gone and the whole matrix would hang")

        isolate = run_matrix.open_isolate_box(self.tmp)
        previous = signal.signal(signal.SIGALRM, _too_slow)
        signal.alarm(30)
        try:
            with self.assertRaises(run_matrix.MatrixError) as ctx:
                run_matrix._run_once(isolate, binary, test_in, dest,
                                     cpu_limit_s=2.0, wall_limit_s=6.0,
                                     mem_limit_kb=256 * 1024,
                                     io_input="t.inp", io_output="t.out")
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
            run_matrix.close_isolate_box(isolate)

        message = str(ctx.exception)
        self.assertIn("t.out", message)
        self.assertIn("not a regular file", message)
        self.assertFalse(dest.exists(), dest)

    def test_file_io_directory_in_place_of_the_output_is_refused(self):
        # The third shape, and the one with no exotic mechanism behind it:
        # `read_bytes()` on a directory raises `IsADirectoryError`, an
        # `OSError` — so before this guard it was reported through the
        # *permissions* branch, whose message tells the setter their
        # solution restricted its output's permissions. It did not. A
        # directory is refused on its own terms.
        binary = _compile(
            "#include <sys/types.h>\n#include <sys/stat.h>\n"
            'int main(){ if (mkdir("t.out", 0755) != 0) return 6;\n'
            "  return 0; }\n",
            self.tmp / "dirmaker", self.tmp)
        os.chmod(self.tmp, 0o777)
        test_in = self.tmp / "01.in"
        test_in.write_text("x\n", encoding="utf-8")
        dest = self.tmp / "dir.produced"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            with self.assertRaises(run_matrix.MatrixError) as ctx:
                run_matrix._run_once(isolate, binary, test_in, dest,
                                     cpu_limit_s=2.0, wall_limit_s=6.0,
                                     mem_limit_kb=256 * 1024,
                                     io_input="t.inp", io_output="t.out")
        finally:
            run_matrix.close_isolate_box(isolate)

        message = str(ctx.exception)
        self.assertIn("t.out", message)
        self.assertIn("not a regular file", message)
        self.assertNotIn("umask", message)   # not the permissions diagnostic
        self.assertFalse(dest.exists(), dest)

    def test_a_regular_output_file_still_passes_the_shape_guard(self):
        # The control for all three above: the guard must refuse only what
        # is not a regular file. A guard that refused everything would make
        # every test in this section pass and the feature useless.
        binary = _compile(
            "#include <cstdio>\n"
            'int main(){ FILE *f = fopen("t.out", "w"); if (!f) return 5;\n'
            '  fprintf(f, "42\\n"); fclose(f); return 0; }\n',
            self.tmp / "regular", self.tmp)
        os.chmod(self.tmp, 0o777)
        test_in = self.tmp / "01.in"
        test_in.write_text("x\n", encoding="utf-8")
        dest = self.tmp / "reg.produced"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            r = run_matrix._run_once(isolate, binary, test_in, dest,
                                     cpu_limit_s=2.0, wall_limit_s=6.0,
                                     mem_limit_kb=256 * 1024,
                                     io_input="t.inp", io_output="t.out")
        finally:
            run_matrix.close_isolate_box(isolate)

        self.assertFalse(r.no_output, r)
        self.assertEqual(dest.read_text(encoding="utf-8").strip(), "42")

    # ------------------------------------------------------------------
    # Which host directories reach the box. (`_mounted_host_dirs` and
    # `_isolate_run_argv` live on `PackageFixture`.)
    # ------------------------------------------------------------------

    def test_the_test_directory_is_not_mounted_in_file_io_mode(self):
        # Pre-existing and correctly not a blocker, but free to remove here:
        # the directory holding the tests also holds the jury's `.a` answer
        # files, and mounting it lets a solution open `/host1/01.a` and print
        # it back. stdin mode has to mount it — `--stdin` must name a path
        # inside the box. File-IO mode does not: `--stdin` points at the
        # staged copy in the staging directory, so the mount is referenced
        # nowhere and buys nothing.
        #
        # The binary and the test live in *different* directories here on
        # purpose: `_label` de-duplicates by resolved path, so a fixture
        # with both in one directory would keep the mount alive through the
        # binary and make this test vacuous.
        bin_dir, test_dir = self.tmp / "bin", self.tmp / "tests"
        bin_dir.mkdir()
        test_dir.mkdir()
        for d in (self.tmp, bin_dir, test_dir):
            os.chmod(d, 0o777)
        binary = _compile(
            "#include <cstdio>\n"
            'int main(){ FILE *fi = fopen("t.inp", "r"); if (!fi) return 3;\n'
            "  int a, b; if (fscanf(fi, \"%d %d\", &a, &b) != 2) return 4;\n"
            "  fclose(fi);\n"
            '  FILE *fo = fopen("t.out", "w"); if (!fo) return 5;\n'
            '  fprintf(fo, "%d\\n", a + b); fclose(fo); return 0; }\n',
            bin_dir / "mountcheck", self.tmp)
        test_in = test_dir / "01.in"
        test_in.write_text("2 3\n", encoding="utf-8")
        # The jury's answer, sitting where it always sits.
        (test_dir / "01.a").write_text("5\n", encoding="utf-8")
        dest = self.tmp / "m.produced"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            argv = self._isolate_run_argv(
                lambda: run_matrix._run_once(
                    isolate, binary, test_in, dest,
                    cpu_limit_s=2.0, wall_limit_s=6.0,
                    mem_limit_kb=256 * 1024,
                    io_input="t.inp", io_output="t.out"))
            mounted = self._mounted_host_dirs(argv)
            stage_root = isolate.stage_root.resolve()
        finally:
            run_matrix.close_isolate_box(isolate)

        self.assertNotIn(
            str(test_dir.resolve()), mounted,
            f"the test directory is still mounted in file-IO mode, so a "
            f"solution can read the jury's answers: {sorted(mounted)}")
        # ...and the two mounts that *are* load-bearing survive, so this is
        # not passing because mounting broke altogether.
        self.assertIn(str(bin_dir.resolve()), mounted, sorted(mounted))
        # The rw mount is a fresh per-call directory under `stage_root`
        # (Task 3), not `stage_root` itself, and its name isn't known ahead
        # of the call — assert it's a direct child of `stage_root` instead
        # of an exact path, and that `stage_root` itself was never handed to
        # isolate (it is never a `--dir=` target on its own).
        rw_mounts = [m for m in mounted if Path(m).parent == stage_root]
        self.assertEqual(len(rw_mounts), 1,
                         f"expected exactly one per-run mount under "
                         f"{stage_root}, got {sorted(mounted)}")
        self.assertNotIn(str(stage_root), mounted, sorted(mounted))

    def test_the_test_directory_is_still_mounted_in_stdin_mode(self):
        # The control, and the reason the change above is scoped to file-IO
        # mode: in stdin mode `--stdin` names a path inside the box, so this
        # mount is what makes the run possible at all. Dropping it there
        # would be a regression, not a fix.
        bin_dir, test_dir = self.tmp / "bin", self.tmp / "tests"
        bin_dir.mkdir()
        test_dir.mkdir()
        for d in (self.tmp, bin_dir, test_dir):
            os.chmod(d, 0o777)
        binary = _compile(
            "#include <cstdio>\n"
            'int main(){ int a, b; scanf("%d %d", &a, &b);\n'
            '  printf("%d\\n", a + b); return 0; }\n',
            bin_dir / "stdincheck", self.tmp)
        test_in = test_dir / "01.in"
        test_in.write_text("2 3\n", encoding="utf-8")
        dest = self.tmp / "s2.produced"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            argv = self._isolate_run_argv(
                lambda: run_matrix._run_once(
                    isolate, binary, test_in, dest,
                    cpu_limit_s=2.0, wall_limit_s=6.0,
                    mem_limit_kb=256 * 1024))
            mounted = self._mounted_host_dirs(argv)
        finally:
            run_matrix.close_isolate_box(isolate)

        self.assertIn(str(test_dir.resolve()), mounted, sorted(mounted))
        self.assertEqual(dest.read_text(encoding="utf-8").strip(), "5")

    # ------------------------------------------------------------------
    # `_remove_run_dir`'s two paths (formerly `_clear_stage_dir`'s, before
    # Task 3 moved cleanup from the top of the *next* run to the `finally`
    # of the run that made the mess). Both are reachable and neither is
    # skipped: the review of the old code confirmed that turning the
    # `except OSError` into a `continue` left the whole suite green. An
    # error path nothing has ever triggered is not a handled error path.
    # Covered in the lighter `ReentrancyTest` fixture, which needs no
    # package copy to exercise `_run_once` directly —
    # `test_an_unremovable_run_directory_warns_and_keeps_the_verdict`
    # and `test_a_removable_foreign_subdirectory_does_not_block_cleanup`.
    # ------------------------------------------------------------------

    def test_close_isolate_box_warns_about_a_staging_directory_it_cannot_remove(self):
        # `shutil.rmtree(..., ignore_errors=True)` is right — teardown must
        # never mask the error already propagating — but on its own it left
        # a subuid-owned directory sitting in the user's repository, needing
        # root to delete, with nothing said anywhere. The user learned
        # nothing. Now it warns, on stderr, naming the path, and still does
        # not raise.
        #
        # The obstruction here is built by hand and owned by *us*, so this
        # test leaves nothing behind: a mode-0000 directory blocks its owner
        # too, which is all `rmtree` needs, and unlike a real subuid-owned
        # one it can be chmod'ed back.
        isolate = run_matrix.open_isolate_box(self.tmp)
        stage = isolate.stage_root
        blocked = stage / "unremovable"
        blocked.mkdir()
        (blocked / "x").write_text("x", encoding="utf-8")
        os.chmod(blocked, 0o000)

        captured = io.StringIO()
        try:
            with contextlib.redirect_stderr(captured):
                run_matrix.close_isolate_box(isolate)   # must not raise
            survived = stage.exists()
        finally:
            os.chmod(blocked, 0o700)
            shutil.rmtree(stage, ignore_errors=True)

        self.assertTrue(survived,
                        "the staging directory was removable after all — this "
                        "test no longer reproduces the case it describes")
        warning = captured.getvalue()
        self.assertIn(str(stage), warning,
                      "close_isolate_box left an undeletable staging "
                      "directory behind without naming it")
        self.assertEqual(len(warning.strip().splitlines()), 1,
                         f"expected a one-line warning, got: {warning!r}")

        # The control: a staging directory that comes away cleanly must say
        # nothing at all, or the warning is noise on every single run.
        clean = run_matrix.open_isolate_box(self.tmp)
        quiet = io.StringIO()
        with contextlib.redirect_stderr(quiet):
            run_matrix.close_isolate_box(clean)
        self.assertEqual(quiet.getvalue(), "",
                         "close_isolate_box warns even when teardown worked")

    # ------------------------------------------------------------------
    # `_time_median` in file-IO mode. It calls `_run_once` `runs` times and
    # rebuilds a RunResult from the samples, and every field it forgets to
    # carry is silently lost. `no_output` was dropped there — unreachable
    # while nothing passed IO names down, live the moment `run()` did.
    # ------------------------------------------------------------------

    def test_time_median_carries_no_output_from_any_run_not_just_the_last(self):
        # The mutation test for the sticky-OR *and* for the rebuilt
        # RunResult. The first of three runs writes no `t.out`; runs 2 and 3
        # do. Only a flag OR-ed across runs *and* passed to the RunResult
        # built below the loop reports the first run's silence.
        #
        # Three ways to break the driver, all caught here: not threading the
        # IO names through `_time_median` (the runs execute in stdin mode,
        # where `no_output` is never set), not OR-ing `r.no_output` into the
        # accumulator (the last run wins and reports False), and not passing
        # `no_output` to the RunResult built below the loop (computed, then
        # thrown away).
        #
        # The "first run differs" mechanism is supplied by this test — the
        # binary on disk is swapped between calls — and deliberately not by
        # a marker file the solution leaves in the staging directory. That
        # earlier mechanism relied on the staging directory *keeping* a
        # solution's stray files between runs, which Task 6's dogfood proved
        # is a defect, not a feature: the leftover is owned by one box's
        # subuid and no later box can reopen it, so it turned NO_OUTPUT into
        # RE. Every `_run_once` call now gets its own fresh directory
        # (Task 3), so that leak is unreachable rather than merely cleared,
        # and this test must not be the reason to reintroduce it.
        silent = _compile("int main(){ return 0; }\n",
                          self.tmp / "silent_first", self.tmp)
        writer = _compile(
            '#include <cstdio>\n'
            'int main(){ FILE *f = fopen("t.out", "w"); if (!f) return 5;\n'
            '  fprintf(f, "later\\n"); fclose(f); return 0; }\n',
            self.tmp / "later_writer", self.tmp)
        binary = self.tmp / "swapped"
        shutil.copyfile(silent, binary)
        os.chmod(binary, 0o755)
        os.chmod(self.tmp, 0o777)
        test_in = self.tmp / "01.in"
        test_in.write_text("x\n", encoding="utf-8")
        dest = self.tmp / "late.produced"

        real_run_once = run_matrix._run_once
        seen = []

        def _swap_after_the_first_run(*args, **kwargs):
            result = real_run_once(*args, **kwargs)
            seen.append(result)
            if len(seen) == 1:
                shutil.copyfile(writer, binary)
                os.chmod(binary, 0o755)
            return result

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            with mock.patch.object(run_matrix, "_run_once",
                                   _swap_after_the_first_run):
                r = run_matrix._time_median(isolate, binary, test_in, dest,
                                            2.0, 6.0, 256 * 1024, 3,
                                            io_input="t.inp", io_output="t.out")
        finally:
            run_matrix.close_isolate_box(isolate)

        # Exactly one silent run out of three — asserted per run, so "every
        # run was silent" can never masquerade as a working sticky-OR.
        self.assertEqual([x.no_output for x in seen], [True, False, False],
                         [str(x) for x in seen])
        # Runs 2 and 3 really did write, and the last one's output is what
        # landed in the repository.
        self.assertEqual(dest.read_text(encoding="utf-8").strip(), "later")
        self.assertFalse(r.crashed, r)
        self.assertFalse(r.killed, r)
        self.assertTrue(
            r.no_output,
            "the first of three runs created no output file; _time_median "
            f"reported no_output=False ({r})")

    def test_time_median_does_not_invent_no_output_when_every_run_writes(self):
        # The other direction: a solution that writes its output file on
        # every run must come back clean. Without this, `no_output=True`
        # hardcoded in the rebuilt RunResult would pass the test above.
        binary = _compile(
            '#include <cstdio>\n'
            'int main(){ FILE *fi = fopen("t.inp", "r"); if (!fi) return 3;\n'
            '  int a, b; if (fscanf(fi, "%d %d", &a, &b) != 2) return 4;\n'
            '  fclose(fi);\n'
            '  FILE *fo = fopen("t.out", "w"); if (!fo) return 5;\n'
            '  fprintf(fo, "%d\\n", a + b); fclose(fo); return 0; }\n',
            self.tmp / "median_writer", self.tmp)
        os.chmod(self.tmp, 0o777)
        test_in = self.tmp / "01.in"
        test_in.write_text("2 3\n", encoding="utf-8")
        dest = self.tmp / "median.produced"

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            r = run_matrix._time_median(isolate, binary, test_in, dest,
                                        2.0, 6.0, 256 * 1024, 3,
                                        io_input="t.inp", io_output="t.out")
        finally:
            run_matrix.close_isolate_box(isolate)

        self.assertFalse(r.no_output, r)
        self.assertEqual(dest.read_text(encoding="utf-8").strip(), "5")

    # ------------------------------------------------------------------
    # `run()` end to end in file-IO mode, and `_classify`'s ordering.
    # ------------------------------------------------------------------

    def test_run_accepts_a_file_io_problem(self):
        # The refusal is gone: a vnolymp-style package (io.input/io.output
        # naming real files) now produces a real matrix rather than a
        # MatrixError. Same fixture, same tests, same checker as the
        # stdin/stdout run above — only the IO mode differs, so the two
        # runs must agree verdict for verdict.
        self._make_file_io_package()

        payload = run_matrix.run(self.problem_dir, self.testlib_dir)

        self.assertEqual(payload["holes"], [])
        self.assertEqual(payload["mismatches"], [])
        by_solution = {r["solution"]: r for r in payload["results"]
                       if r["group"] == "g1" and r["test"] == "01"}
        self.assertEqual(by_solution["sol-main.cpp"]["verdict"], "OK")
        self.assertEqual(by_solution["sol-wrong.cpp"]["verdict"], "WA")

        # Pass 1 wrote the jury's answer from the model solution's *file*
        # output, not from an empty stdout: 2 + 3 = 5. An empty `.a` here
        # would mean the matrix judged everything against nothing.
        answer = self.problem_dir / "tests" / "g1" / "01.a"
        self.assertEqual(answer.read_text(encoding="utf-8").strip(), "5")

        # And the artifact on disk is a normal one, not a special case.
        written = json.loads(
            (self.problem_dir / "invocation.json").read_text(encoding="utf-8"))
        self.assertEqual(written["holes"], [])
        self.assertEqual(written["results"], payload["results"])

    def test_solution_that_never_writes_output_is_NO_OUTPUT(self):
        # The verdict a stdin/stdout problem cannot produce. `silent.cpp`
        # exits 0 and writes nothing — the classic "wrote the wrong
        # filename" mistake — and must be reported as NO_OUTPUT rather than
        # checked (an empty file against the jury's answer would read as WA
        # and hide the real defect).
        silent = (
            "/**\n"
            " * @tag        wrong-answer\n"
            " * @expect     g1=WA\n"
            " * @algorithm  Writes nothing at all.\n"
            " * @why-wrong  Never creates t.out; stands in for a wrong filename.\n"
            " * @complexity O(1)\n"
            " */\n"
            "int main(){ return 0; }\n"
        )
        self._make_file_io_package(extra_solution=("silent.cpp", silent))

        payload = run_matrix.run(self.problem_dir, self.testlib_dir)

        verdicts = {r["solution"]: r["verdict"] for r in payload["results"]
                    if r["group"] == "g1" and r["test"] == "01"}
        self.assertEqual(verdicts["silent.cpp"], "NO_OUTPUT")
        # The other two are unaffected by its presence.
        self.assertEqual(verdicts["sol-main.cpp"], "OK")
        self.assertEqual(verdicts["sol-wrong.cpp"], "WA")

        # NO_OUTPUT is not declarable, so `silent.cpp` had to declare WA;
        # the disagreement is a mismatch, never a hole. The hole rule is
        # unchanged: a hole is a solution declared wrong that got OK.
        self.assertEqual(payload["holes"], [])
        mismatch = [m for m in payload["mismatches"]
                    if m["solution"] == "silent.cpp"]
        self.assertEqual(len(mismatch), 1, payload["mismatches"])
        self.assertEqual(mismatch[0]["expected"], "WA")
        self.assertEqual(mismatch[0]["actual"], "NO_OUTPUT")

    def test_wrong_filename_solution_is_NO_OUTPUT_on_every_test_not_just_the_first(self):
        # The `run()`-level half of the stray-file leak, and the exact shape
        # the Task 6 dogfood hit: a solution writing `output.txt` was
        # NO_OUTPUT on the first test it ran and RE on every test after it,
        # because its own leftover file — owned by a box subuid no later box
        # shares — could not be reopened for writing.
        #
        # A second test input is what makes this test able to fail at all:
        # with one test per group the wrong-filename solution never gets a
        # second run, and the bug is invisible.
        wrong_name = (
            "/**\n"
            " * @tag        wrong-answer\n"
            " * @expect     g1=WA\n"
            " * @algorithm  Correct sum, written to output.txt.\n"
            " * @why-wrong  Writes output.txt, not the t.out problem.json declares.\n"
            " * @complexity O(1)\n"
            " */\n"
            "#include <cstdio>\n"
            'int main(){ FILE *fi = fopen("t.inp", "r"); if (!fi) return 3;\n'
            '  long long a, b; if (fscanf(fi, "%lld %lld", &a, &b) != 2) return 4;\n'
            "  fclose(fi);\n"
            '  FILE *fo = fopen("output.txt", "w"); if (!fo) return 5;\n'
            '  fprintf(fo, "%lld\\n", a + b); fclose(fo); return 0; }\n'
        )
        self._make_file_io_package(extra_solution=("wrongname.cpp", wrong_name))
        (self.problem_dir / "tests" / "g1" / "02.in").write_text(
            "4 5\n", encoding="utf-8")

        payload = run_matrix.run(self.problem_dir, self.testlib_dir)

        got = {r["test"]: r["verdict"] for r in payload["results"]
               if r["solution"] == "wrongname.cpp"}
        self.assertEqual(got, {"01": "NO_OUTPUT", "02": "NO_OUTPUT"},
                         "the wrong-filename solution's verdict changed with "
                         "run order — its own leftover file poisoned the "
                         "later run")
        # And it did not poison the honest solutions sharing the staging
        # directory either: both still get their real verdicts on both tests.
        self.assertEqual(
            {r["test"]: r["verdict"] for r in payload["results"]
             if r["solution"] == "sol-main.cpp"},
            {"01": "OK", "02": "OK"})

    def test_model_solution_that_writes_no_output_file_is_refused(self):
        # Pass 1 turns the model solution's output into the jury's `.a`
        # answer file. In file-IO mode a model solution that writes nothing
        # would hand pass 2 an EMPTY answer to judge every submission
        # against — a whole matrix of confident, wrong verdicts. It must
        # refuse, naming the filename problem.json declares. (This also
        # exercises the median path: pass 1 runs the model solution `runs`
        # times through `_time_median`.)
        silent_main = (
            "/**\n"
            " * @tag        main\n"
            " * @expect     g1=OK\n"
            " * @algorithm  Writes nothing — a model solution with the wrong filename.\n"
            " * @complexity O(1)\n"
            " */\n"
            "int main(){ return 0; }\n"
        )
        self._make_file_io_package(main_source=silent_main)

        with self.assertRaises(run_matrix.MatrixError) as ctx:
            run_matrix.run(self.problem_dir, self.testlib_dir)

        message = str(ctx.exception)
        self.assertIn("t.out", message)          # names the file it wanted
        self.assertIn("model solution", message)
        # It must refuse, not leave a blank answer behind as if it were jury
        # truth — and it must not have written invocation.json either.
        self.assertFalse((self.problem_dir / "invocation.json").exists())

    def test_classify_checks_killed_and_crashed_before_no_output(self):
        # Ordering, stated in `_classify`'s docstring and load-bearing: a
        # segfault and a time-limit kill both leave no output file, and
        # reporting either as NO_OUTPUT names the symptom instead of the
        # cause. Pure — no sandbox needed. `_check` is patched to fail
        # loudly, pinning the other half of the claim: the checker is never
        # invoked on a run that produced no output file.
        limits = Limits(t_main_ms=10, tl_ms=1000, kill_ms=2000)
        missing = self.tmp / "does-not-exist.out"

        def _never(*args, **kwargs):
            raise AssertionError("the checker must not run on a no-output run")

        cases = {
            "RE": dict(crashed=True),
            "TL": dict(killed=True),
            "ML": dict(oom=True),
            "NO_OUTPUT": dict(),
        }
        with mock.patch.object(run_matrix, "_check", _never):
            for expected, extra in cases.items():
                base = dict(cpu_ms=5, wall_ms=5, killed=False, oom=False,
                            crashed=False, exit_code=0, peak_kb=100,
                            status="", message="", no_output=True)
                base.update(extra)
                outcome = run_matrix._classify(
                    run_matrix.RunResult(**base), self.tmp / "no-checker",
                    self.tmp / "01.in", missing, self.tmp / "01.a", limits,
                    mem_limit_kb=1024)
                self.assertEqual(outcome.verdict, expected, base)

        # And time still beats correctness: a run over the limit that also
        # wrote nothing is TL, not NO_OUTPUT (matrix_core decides time
        # first). 2500 ms is past kill_ms, so it is not merely banded.
        over = run_matrix.RunResult(
            cpu_ms=2500, wall_ms=2500, killed=False, oom=False, crashed=False,
            exit_code=0, peak_kb=100, status="", message="", no_output=True)
        with mock.patch.object(run_matrix, "_check", _never):
            outcome = run_matrix._classify(
                over, self.tmp / "no-checker", self.tmp / "01.in", missing,
                self.tmp / "01.a", limits, mem_limit_kb=1024)
        self.assertEqual(outcome.verdict, "TL")

    def test_classify_judges_ml_from_peak_kb_against_the_memory_limit(self):
        # ML is no longer only `cg-oom-killed`: the cgroup cap carries
        # `OUTPUT_SLACK_KB` of headroom for dirty page cache (see
        # `_run_once`), so a solution can overshoot `memory_mb` without
        # ever being OOM-killed. `_classify` must then read the overshoot
        # off `max-rss` — strictly greater than the limit, so a run exactly
        # at the limit is *not* ML, mirroring the time rule. Pure, no
        # sandbox; `_check` is patched to fail loudly so this also pins
        # that an ML run never reaches the checker, and that ML still
        # outranks a TL kill exactly as the OOM path always has.
        limits = Limits(t_main_ms=10, tl_ms=1000, kill_ms=2000)
        mem_limit_kb = 65536
        present = self.tmp / "present.out"
        present.write_text("1\n", encoding="utf-8")

        def _never(*args, **kwargs):
            raise AssertionError("the checker must not run on an ML run")

        def outcome_for(**extra):
            base = dict(cpu_ms=5, wall_ms=5, killed=False, oom=False,
                        crashed=False, exit_code=0, peak_kb=100,
                        status="", message="", no_output=False)
            base.update(extra)
            return run_matrix._classify(
                run_matrix.RunResult(**base), self.tmp / "no-checker",
                self.tmp / "01.in", present, self.tmp / "01.a", limits,
                mem_limit_kb=mem_limit_kb)

        with mock.patch.object(run_matrix, "_check", _never):
            self.assertEqual(outcome_for(peak_kb=mem_limit_kb + 1).verdict, "ML")
            self.assertEqual(outcome_for(oom=True, peak_kb=100).verdict, "ML")
            # Over memory *and* killed for time: ML, as the OOM path did.
            self.assertEqual(outcome_for(peak_kb=mem_limit_kb + 1,
                                         killed=True).verdict, "ML")
            self.assertEqual(outcome_for(peak_kb=mem_limit_kb + 1,
                                         crashed=True).verdict, "ML")
        # Exactly at the limit is not over it: the checker runs.
        with mock.patch.object(run_matrix, "_check", lambda *a, **k: "OK"):
            self.assertEqual(outcome_for(peak_kb=mem_limit_kb).verdict, "OK")

    def test_stage_dir_is_not_on_a_memory_backed_filesystem(self):
        isolate = run_matrix.open_isolate_box(self.problem_dir)
        try:
            fstype = run_matrix._filesystem_type(isolate.stage_root)
            self.assertNotIn(fstype, run_matrix.MEMORY_BACKED_FSTYPES,
                             f"staging landed on {fstype} at {isolate.stage_root}")
            self.assertTrue(isolate.stage_root.is_dir())
        finally:
            run_matrix.close_isolate_box(isolate)
        self.assertFalse(isolate.stage_root.exists(),
                         "the staging directory outlived close_isolate_box")
        self.assertFalse(isolate.meta_dir.exists(),
                         "the meta directory outlived close_isolate_box")

    def test_matrix_error_exits_2_so_it_is_not_read_as_a_hole(self):
        # `validating-solutions` tells the agent that exit 1 means holes or
        # mismatches. An uncaught MatrixError used to exit 1 as well, so a
        # compile failure or a refused package read as a finding about the
        # test suite. The trigger used to be the blanket file-IO refusal,
        # which this task deleted; the surviving refusal in the same family
        # is an `io.output` colliding with the name the driver stages the
        # sandboxed process's stdout under.
        meta_path = self.problem_dir / "problem.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["io"] = {"input": "mini.inp",
                      "output": run_matrix.STAGED_STDOUT_NAME}
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        code = run_matrix.main(["run_matrix.py", str(self.problem_dir),
                                str(self.testlib_dir)])
        self.assertEqual(code, 2)

    def test_a_malformed_box_pool_env_exits_2_not_1(self):
        # `box_pool.BoxPoolError` is a bare RuntimeError with no dependency
        # on this module's error type, so it does not automatically become
        # a MatrixError the way every other externally-authored failure in
        # this file does (R1). Left unconverted it would escape main()'s
        # `except MatrixError` entirely, crash with a traceback, and exit
        # 1 — the exact code `validating-solutions` reads as "the matrix
        # ran and found holes", reopening the crash-read-as-a-finding
        # defect `main()`'s own docstring says it exists to prevent. This
        # is the interface contract (`main()`'s exit code), so it is
        # tested at `main()`, not at `run()` or `open_isolate_box()`
        # directly — a MatrixError raised deep inside proves nothing about
        # what actually reaches the caller.
        captured = io.StringIO()
        with mock.patch.dict(os.environ, {"RUN_MATRIX_BOX_POOL": "not-a-number"}):
            with contextlib.redirect_stderr(captured):
                code = run_matrix.main(["run_matrix.py", str(self.problem_dir),
                                        str(self.testlib_dir)])
        self.assertEqual(code, 2)
        self.assertIn("RUN_MATRIX_BOX_POOL", captured.getvalue())

    def test_invocation_json_pins_the_testlib_revision(self):
        payload = run_matrix.run(self.problem_dir, self.testlib_dir)
        machine = payload["machine"]
        self.assertIn("testlib", machine)
        self.assertRegex(machine["testlib"] or "", r"^[0-9a-f]{40}$")
        # `cg` was a hardcoded True presented as an observation of the
        # machine; it is a declaration and is now named as one.
        self.assertNotIn("cg", machine)
        self.assertTrue(machine["cg_requested"])

    def test_invocation_json_records_the_cgroup_cap_actually_applied(self):
        # Evidence must show the cap that was enforced, not just the
        # problem's `memory_mb`: the two differ by `OUTPUT_SLACK_KB` (the
        # page-cache headroom `_run_once` adds to `--cg-mem`), and a reader
        # of a recorded ML needs to know whether it was a max-rss judgement
        # against `memory_mb` or a kernel kill at the cap.
        payload = run_matrix.run(self.problem_dir, self.testlib_dir)
        machine = payload["machine"]
        memory_mb = json.loads((self.problem_dir / "problem.json")
                               .read_text(encoding="utf-8"))["limits"]["memory_mb"]
        self.assertEqual(machine["output_slack_kb"], run_matrix.OUTPUT_SLACK_KB)
        self.assertEqual(machine["cg_mem_kb"],
                         memory_mb * 1024 + run_matrix.OUTPUT_SLACK_KB)
        self.assertGreater(machine["cg_mem_kb"], memory_mb * 1024)

    def test_model_solution_over_the_memory_limit_but_under_the_cap_aborts(self):
        # Pass 1's "model solution exceeded the memory limit" abort used to
        # fire only on `cg-oom-killed`. With the cap raised by the slack, a
        # model solution that overshoots `memory_mb` but stays under the cap
        # is never OOM-killed, and without a max-rss check it would sail
        # through pass 1 and define the answers while breaking its own
        # limit. It must still abort, naming the limit.
        meta_path = self.problem_dir / "problem.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["limits"]["memory_mb"] = 16
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        (self.problem_dir / "solutions" / "sol-main.cpp").write_text(
            _MAIN_HEADER +
            "#include <cstdlib>\n#include <cstdio>\n"
            "int main(){ size_t n = 48*1024*1024; "
            "volatile char *p = (volatile char*)malloc(n); if(!p) return 1; "
            "for (size_t i = 0; i < n; i += 4096) p[i] = (char)(i & 0xFF); "
            "long long a, b; if (scanf(\"%lld %lld\", &a, &b) != 2) return 2; "
            "printf(\"%lld\\n\", a + b + (p[n-4096] - p[n-4096])); return 0; }\n",
            encoding="utf-8")
        with self.assertRaises(run_matrix.MatrixError) as ctx:
            run_matrix.run(self.problem_dir, self.testlib_dir)
        self.assertIn("memory limit", str(ctx.exception))
        self.assertIn("16 MB", str(ctx.exception))
        self.assertFalse((self.problem_dir / "invocation.json").exists())


class ParallelPassTest(PackageFixture):
    def tearDown(self):
        os.environ.pop("RUN_MATRIX_BOX_POOL", None)
        super().tearDown()

    def test_invocation_json_records_the_worker_count_and_bound(self):
        payload = run_matrix.run(self.problem_dir, self.testlib_dir)
        self.assertIn("workers", payload["machine"])
        self.assertGreaterEqual(payload["machine"]["workers"], 1)
        self.assertEqual(payload["machine"]["contention_bound"],
                         matrix_core.CONTENTION_BOUND)

    def test_every_result_declares_whether_it_was_retimed_serially(self):
        payload = run_matrix.run(self.problem_dir, self.testlib_dir)
        for record in payload["results"]:
            self.assertIn("retimed_serially", record)
            self.assertIsInstance(record["retimed_serially"], bool)

    def test_one_worker_produces_the_same_verdicts_as_many(self):
        # The property that matters: parallelism must not change a verdict.
        os.environ["RUN_MATRIX_BOX_POOL"] = "1"
        serial = run_matrix.run(self.problem_dir, self.testlib_dir)
        os.environ["RUN_MATRIX_BOX_POOL"] = "4"
        parallel = run_matrix.run(self.problem_dir, self.testlib_dir)

        def verdicts(payload):
            return {(r["solution"], r["group"], r["test"]): r["verdict"]
                    for r in payload["results"]}

        self.assertEqual(verdicts(serial), verdicts(parallel))
        self.assertEqual(serial["holes"], parallel["holes"])
        self.assertEqual(serial["mismatches"], parallel["mismatches"])

    def test_pass_one_is_never_run_concurrently(self):
        # t_main defines TL. Running it under contention inflates TL and lets
        # genuinely-TLE solutions through, which manufactures holes. Asserted
        # behaviourally — by watching how many runs are actually in flight —
        # rather than by scraping the source for "ThreadPoolExecutor", so a
        # refactor that keeps the property passes and one that loses it fails.
        os.environ["RUN_MATRIX_BOX_POOL"] = "4"
        real_run_once = run_matrix._run_once
        lock = threading.Lock()
        state = {"live": 0, "peak_pass1": 0, "peak_pass2": 0}
        limits_known = threading.Event()

        def watched(*args, **kwargs):
            with lock:
                state["live"] += 1
                key = "peak_pass2" if limits_known.is_set() else "peak_pass1"
                state[key] = max(state[key], state["live"])
            try:
                return real_run_once(*args, **kwargs)
            finally:
                with lock:
                    state["live"] -= 1

        real_compute = run_matrix.compute_limits

        def marking(*args, **kwargs):
            # Pass 1 ends exactly here: compute_limits is what consumes it.
            result = real_compute(*args, **kwargs)
            limits_known.set()
            return result

        with mock.patch.object(run_matrix, "_run_once", watched), \
             mock.patch.object(run_matrix, "compute_limits", marking):
            run_matrix.run(self.problem_dir, self.testlib_dir)

        self.assertEqual(state["peak_pass1"], 1,
                         "pass 1 must measure the model solution alone")
        self.assertGreater(state["peak_pass2"], 1,
                           "pass 2 did not actually run in parallel")

    def test_a_retimed_result_is_flagged_with_the_worker_count(self):
        # The band is unreachable on the `mini` fixture — two trivial
        # solutions, TL pinned to the 1000 ms floor, so nothing can land in
        # (1000, 2000]. Rather than assert inside a loop that never runs
        # (a test that asserts nothing), the near-TL measurement is
        # fabricated by stubbing the runner.
        os.environ["RUN_MATRIX_BOX_POOL"] = "4"
        real_run_once = run_matrix._run_once
        seen = {"pass2": False}

        def near_tl(*args, **kwargs):
            r = real_run_once(*args, **kwargs)
            if seen["pass2"]:
                return dataclasses.replace(r, cpu_ms=1200)  # TL < 1200 <= 1.5*TL
            return r

        real_compute = run_matrix.compute_limits

        def marking(*args, **kwargs):
            result = real_compute(*args, **kwargs)
            seen["pass2"] = True
            return result

        with mock.patch.object(run_matrix, "_run_once", near_tl), \
             mock.patch.object(run_matrix, "compute_limits", marking):
            payload = run_matrix.run(self.problem_dir, self.testlib_dir)

        self.assertTrue(any(r["retimed_serially"] for r in payload["results"]))
        register = json.loads(
            (self.problem_dir / "flags.json").read_text(encoding="utf-8"))
        banded = [f for f in register["flags"] if f["kind"] == "timing-band"]
        self.assertTrue(banded, "a near-TL measurement produced no flag")
        self.assertTrue(any("worker" in f["assumed"] or "worker" in f["what"]
                            for f in banded))

    def test_a_wall_clock_kill_is_retimed_serially_but_a_cpu_kill_is_not(self):
        # needs_serial_retime's short-circuit on `killed` is justified by
        # CPU-time arithmetic (kill_ms/bound > tl_ms): it says nothing about
        # wall time. A descheduled process accrues wall time without
        # accruing CPU time, so a wall-clock kill under contention is not
        # bounded by CONTENTION_BOUND at all. Left unhandled, a solution
        # that genuinely finishes under TL could be wall-killed under
        # contention, land on TL, match an `@expect TL` declaration, and
        # silently mask a real hole. The fix: `_run_pass2` re-times a
        # wall-clock kill unconditionally, while a CPU-time kill keeps
        # `needs_serial_retime`'s existing (correct, never-ambiguous)
        # short-circuit — that contrast is the point, and preserving it is
        # what keeps the speedup, since ordinary CPU-time TLs are the bulk
        # of the wall clock.
        #
        # Fabricated by stubbing the runner, the same way the near-TL test
        # above does: the `mini` fixture's two trivial solutions never
        # actually get killed by either clock, so both kill kinds are
        # injected on each solution's first pass-2 call only — a later call
        # for the same binary is the serial re-time itself and must see a
        # real (non-killed) measurement, or `retimed_serially` could never
        # be observed to make a difference to the recorded verdict.
        os.environ["RUN_MATRIX_BOX_POOL"] = "4"
        real_run_once = run_matrix._run_once
        seen = {"pass2": False}
        fabricated_once = set()

        def killed_after_pass1(isolate, binary, *rest, **kwargs):
            r = real_run_once(isolate, binary, *rest, **kwargs)
            if not seen["pass2"] or binary.stem in fabricated_once:
                return r
            fabricated_once.add(binary.stem)
            if binary.stem == "sol-main":
                # A wall-clock kill: cpu_ms stays low (the process was
                # descheduled, not slow), only wall time blew past the
                # ceiling.
                return dataclasses.replace(
                    r, killed=True, cpu_ms=50,
                    message="Time limit exceeded (wall clock)")
            # A CPU-time kill on the other solution: never ambiguous, must
            # not be re-timed.
            return dataclasses.replace(r, killed=True,
                                       message="Time limit exceeded")

        real_compute = run_matrix.compute_limits

        def marking(*args, **kwargs):
            result = real_compute(*args, **kwargs)
            seen["pass2"] = True
            return result

        with mock.patch.object(run_matrix, "_run_once", killed_after_pass1), \
             mock.patch.object(run_matrix, "compute_limits", marking):
            payload = run_matrix.run(self.problem_dir, self.testlib_dir)

        by_solution = {r["solution"]: r for r in payload["results"]}
        wall = by_solution["sol-main.cpp"]
        cpu = by_solution["sol-wrong.cpp"]

        self.assertTrue(wall["retimed_serially"],
                        "a wall-clock kill under contention must be re-timed")
        self.assertFalse(cpu["retimed_serially"],
                         "a CPU-time kill is never ambiguous and must not "
                         "be re-timed")
        # The re-time used the real (fast, non-killed) measurement, so the
        # wall-killed solution's TL is corrected — exactly the masked hole
        # this fix closes. The CPU kill, never re-timed, stays TL.
        self.assertFalse(wall["killed"])
        self.assertEqual(cpu["verdict"], "TL")

        register = json.loads(
            (self.problem_dir / "flags.json").read_text(encoding="utf-8"))
        banded = [f for f in register["flags"] if f["kind"] == "timing-band"]
        self.assertTrue(
            any("wall-clock" in f["what"] and "sol-main.cpp" in f["what"]
                for f in banded),
            "the wall-clock kill produced no flag naming it")

    def test_the_wall_kill_flag_records_the_original_wall_reading(self):
        # `first_run_ms` (the CPU-time reading) was already recorded before
        # this fix. But for a *wall-clock* kill, `cpu_ms` does not explain
        # the kill -- the process was descheduled, not slow -- so the
        # number a reader of flags.json actually needs is the original
        # *wall* reading, and nothing carried it. Same stub harness as the
        # wall-vs-CPU-kill test above, narrowed to just the wall-kill case,
        # with a distinctive fabricated `wall_ms` so this assertion can
        # only pass if that specific original reading survived into the
        # flag's `what` text (not just the re-timed one, which is a
        # different, real measurement of the same run).
        FABRICATED_WALL_MS = 918273
        os.environ["RUN_MATRIX_BOX_POOL"] = "4"
        real_run_once = run_matrix._run_once
        seen = {"pass2": False}
        fabricated_once = set()

        def killed_after_pass1(isolate, binary, *rest, **kwargs):
            r = real_run_once(isolate, binary, *rest, **kwargs)
            if not seen["pass2"] or binary.stem in fabricated_once:
                return r
            fabricated_once.add(binary.stem)
            if binary.stem == "sol-main":
                return dataclasses.replace(
                    r, killed=True, cpu_ms=50, wall_ms=FABRICATED_WALL_MS,
                    message="Time limit exceeded (wall clock)")
            return r

        real_compute = run_matrix.compute_limits

        def marking(*args, **kwargs):
            result = real_compute(*args, **kwargs)
            seen["pass2"] = True
            return result

        with mock.patch.object(run_matrix, "_run_once", killed_after_pass1), \
             mock.patch.object(run_matrix, "compute_limits", marking):
            run_matrix.run(self.problem_dir, self.testlib_dir)

        register = json.loads(
            (self.problem_dir / "flags.json").read_text(encoding="utf-8"))
        banded = [f for f in register["flags"] if f["kind"] == "timing-band"]
        self.assertTrue(
            any(str(FABRICATED_WALL_MS) in f["what"] for f in banded),
            "the wall-kill flag does not record the original wall reading")

    def test_a_matrix_error_in_one_worker_surfaces_from_run(self):
        # A worker's MatrixError must propagate out of the pool, not be
        # swallowed into a verdict. Forced directly, by stubbing `_run_once`
        # to raise `MatrixError` after pass 1 has finished with it — this
        # exercises the propagation path itself (pool.map -> run()) rather
        # than any specific real-world trigger of a MatrixError inside
        # `_run_once` (an unreadable staged output, a umask(077)'d solution,
        # etc. are exercised by their own dedicated tests elsewhere in this
        # file).
        os.environ["RUN_MATRIX_BOX_POOL"] = "4"
        real_run_once = run_matrix._run_once
        calls = []

        def exploding(*args, **kwargs):
            calls.append(1)
            if len(calls) > 3:
                raise run_matrix.MatrixError("synthetic worker failure")
            return real_run_once(*args, **kwargs)

        with mock.patch.object(run_matrix, "_run_once", exploding):
            with self.assertRaises(run_matrix.MatrixError) as ctx:
                run_matrix.run(self.problem_dir, self.testlib_dir)
        self.assertIn("synthetic worker failure", str(ctx.exception))


class MinimalIsolateFixture(unittest.TestCase):
    """Just enough to test box leasing directly: a scratch `self.tmp` and
    the same hard-dependency skip guard `TestRunMatrixFixture` uses.

    Deliberately does *not* copy the `mini` fixture or resolve the testlib
    cache — `BoxLeasingTest`'s tests never touch a problem package.
    Subclassing the full `TestRunMatrixFixture` for its ~50 unrelated
    tests, just to get three new ones, doubled this file's runtime (289 ->
    342 tests, ~108s longer) and doubled that again across the
    two-concurrent-suites acceptance check, for no coverage this class
    actually needs — a controller ruling on the Task 2 review. Tasks 3 and
    5 should use this too rather than repeat the mistake.
    """

    def setUp(self):
        if shutil.which("g++") is None:
            raise _missing_dependency("g++ not found on PATH")
        if shutil.which("isolate") is None:
            raise _missing_dependency("isolate not found on PATH")
        SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(prefix="run_matrix_test_", dir=SCRATCH_ROOT))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class ReentrancyTest(MinimalIsolateFixture):
    def setUp(self):
        super().setUp()
        os.chmod(self.tmp, 0o777)
        self.stdin_path = self.tmp / "in.txt"
        self.stdin_path.write_text("\n", encoding="utf-8")

    def test_handle_exposes_roots_not_single_files(self):
        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            self.assertTrue(isolate.meta_dir.is_dir())
            self.assertTrue(isolate.stage_root.is_dir())
            self.assertFalse(hasattr(isolate, "meta_path"))
            self.assertFalse(hasattr(isolate, "stage_dir"))
        finally:
            run_matrix.close_isolate_box(isolate)

    def test_meta_dir_is_never_inside_the_sandbox_writable_root(self):
        # A solution that could write its own meta file could write its own
        # verdict. This is the invariant that forbids the obvious tidy-up of
        # putting the meta file next to the staged output.
        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            self.assertNotIn(isolate.stage_root.resolve(),
                             isolate.meta_dir.resolve().parents)
            self.assertNotEqual(isolate.stage_root.resolve(),
                                isolate.meta_dir.resolve())
        finally:
            run_matrix.close_isolate_box(isolate)

    # ------------------------------------------------------------------
    # Argv-level capture, mirroring `TestRunMatrixFixture`'s identically
    # named helpers (duplicated rather than inherited: `ReentrancyTest`
    # deliberately does not subclass the heavy fixture — see the class
    # docstring on `MinimalIsolateFixture`).
    # ------------------------------------------------------------------

    @staticmethod
    def _mounted_host_dirs(cmd) -> set[str]:
        """The host paths in an isolate `--dir=<label>=<host>[:rw]` argv."""
        found = set()
        for arg in cmd:
            if not isinstance(arg, str) or not arg.startswith("--dir="):
                continue
            host = arg.split("=", 2)[2]
            found.add(host[:-3] if host.endswith(":rw") else host)
        return found

    def _isolate_run_argv(self, call):
        """Run `call()` with `subprocess.run` spied on; return the `--run`
        argv. `_run_once` shells out three times per call (`--init`,
        `--run`, `--cleanup`); only the middle one carries the mounts."""
        seen = []
        real = subprocess.run

        def spy(cmd, *args, **kwargs):
            seen.append(cmd)
            return real(cmd, *args, **kwargs)

        with mock.patch.object(run_matrix.subprocess, "run", spy):
            call()
        runs = [cmd for cmd in seen
                if isinstance(cmd, list) and "--run" in cmd]
        self.assertEqual(len(runs), 1,
                         f"expected exactly one isolate --run, saw {seen!r}")
        return runs[0]

    def test_meta_file_is_never_mounted_into_the_sandbox(self):
        # CRITICAL on review: `test_meta_dir_is_never_inside_the_sandbox_
        # writable_root` above only compares *handle fields*
        # (`isolate.meta_dir` vs `isolate.stage_root`), which is a weak
        # proxy for the invariant `IsolateHandle`'s docstring actually
        # claims — "never passed to --dir". A future tidy-up computing
        # `meta_path = run_dir / "meta"` would leave both of that test's
        # assertions green while putting the driver's only account of the
        # run inside the solution's own `:rw` mount — the silent
        # verdict-rewrite the docstring exists to forbid. This checks the
        # fact that actually matters: the resolved `--meta=` argument
        # isolate is invoked with never lies under any `--dir=` target in
        # the same argv. (Demonstrated to actually catch that regression —
        # and to show the handle-level test above does *not* — in the task
        # report.)
        binary = _compile("int main(){ return 0; }\n",
                          self.tmp / "trivial3", self.tmp)
        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            argv = self._isolate_run_argv(
                lambda: run_matrix._run_once(
                    isolate, binary, self.stdin_path, self.tmp / "o3.out",
                    cpu_limit_s=5.0, wall_limit_s=10.0,
                    mem_limit_kb=256 * 1024))
        finally:
            run_matrix.close_isolate_box(isolate)

        meta_args = [a for a in argv
                    if isinstance(a, str) and a.startswith("--meta=")]
        self.assertEqual(len(meta_args), 1, argv)
        meta_path = Path(meta_args[0].split("=", 1)[1]).resolve()
        mounted = {Path(h).resolve() for h in self._mounted_host_dirs(argv)}
        self.assertTrue(mounted, "no --dir= mounts found in argv, test is vacuous")
        for host in mounted:
            self.assertNotEqual(meta_path, host, (meta_path, host))
            self.assertNotIn(host, meta_path.parents,
                             f"{meta_path} is inside mounted directory {host}")

    def test_concurrent_runs_report_their_own_times_not_each_others(self):
        # The shared-meta defect in its purest form: a fast and a slow run at
        # once. With one meta file the fast run could read the slow run's
        # numbers, or vice versa.
        import concurrent.futures
        fast = _compile("int main(){ return 0; }\n",
                        self.tmp / "fast", self.tmp)
        # 3e9 iterations, not the 4e8 a slower reference machine might use:
        # measured directly on this box (Intel Core Ultra 7 258V, `nproc`
        # 8), 4e8 volatile increments finished in ~106ms at -O2 — under the
        # 200ms threshold below by construction, not because of anything
        # sandboxed. 3e9 measured at ~720ms, comfortably clear of it.
        slow = _compile("int main(){ volatile long s=0;"
                        " for(long i=0;i<3000000000L;i++) s+=i; return 0; }\n",
                        self.tmp / "slow", self.tmp)
        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                f_fast = pool.submit(run_matrix._run_once, isolate, fast,
                                     self.stdin_path, self.tmp / "fast.out",
                                     cpu_limit_s=30.0, wall_limit_s=60.0,
                                     mem_limit_kb=256 * 1024)
                f_slow = pool.submit(run_matrix._run_once, isolate, slow,
                                     self.stdin_path, self.tmp / "slow.out",
                                     cpu_limit_s=30.0, wall_limit_s=60.0,
                                     mem_limit_kb=256 * 1024)
                r_fast, r_slow = f_fast.result(), f_slow.result()
        finally:
            run_matrix.close_isolate_box(isolate)
        self.assertLess(r_fast.cpu_ms, 200, r_fast)
        self.assertGreater(r_slow.cpu_ms, 200, r_slow)

    def test_concurrent_runs_do_not_read_each_others_output(self):
        import concurrent.futures
        a = _compile('#include <cstdio>\nint main(){ puts("AAA"); }\n',
                     self.tmp / "aaa", self.tmp)
        b = _compile('#include <cstdio>\nint main(){ puts("BBB"); }\n',
                     self.tmp / "bbb", self.tmp)
        out_a, out_b = self.tmp / "a.out", self.tmp / "b.out"
        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                fs = [pool.submit(run_matrix._run_once, isolate, binary,
                                  self.stdin_path, dest, cpu_limit_s=30.0,
                                  wall_limit_s=60.0, mem_limit_kb=256 * 1024)
                      for binary, dest in ((a, out_a), (b, out_b))]
                [f.result() for f in fs]
        finally:
            run_matrix.close_isolate_box(isolate)
        self.assertEqual(out_a.read_text().strip(), "AAA")
        self.assertEqual(out_b.read_text().strip(), "BBB")

    def test_two_concurrent_run_once_calls_never_share_a_box(self):
        # The end-to-end Cause-A regression test: run the same binary from two
        # threads and assert both produced a real verdict. Before the lease
        # pool this raced on box ids and one side raised MatrixError.
        import concurrent.futures
        binary = _compile("int main(){ return 0; }\n",
                          self.tmp / "trivial", self.tmp)
        os.chmod(self.tmp, 0o777)
        stdin_path = self.tmp / "in.txt"
        stdin_path.write_text("\n", encoding="utf-8")

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                futures = [pool.submit(run_matrix._run_once, isolate, binary,
                                       stdin_path, self.tmp / f"out{i}",
                                       cpu_limit_s=5.0, wall_limit_s=10.0,
                                       mem_limit_kb=256 * 1024)
                           for i in range(2)]
                results = [f.result() for f in futures]
        finally:
            run_matrix.close_isolate_box(isolate)
        for r in results:
            self.assertFalse(r.crashed, r)
            self.assertFalse(r.killed, r)

    def test_run_directory_is_removed_after_a_successful_run(self):
        binary = _compile("int main(){ return 0; }\n",
                          self.tmp / "trivial", self.tmp)
        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            run_matrix._run_once(isolate, binary, self.stdin_path,
                                 self.tmp / "o.out", cpu_limit_s=5.0,
                                 wall_limit_s=10.0, mem_limit_kb=256 * 1024)
            self.assertEqual(list(isolate.stage_root.iterdir()), [])
        finally:
            run_matrix.close_isolate_box(isolate)

    def test_meta_file_is_removed_after_a_successful_run(self):
        # Minor #3 on review: the `meta_path.unlink` in `_run_once`'s
        # `finally` had no coverage of its own — undetected, meta files
        # would accumulate under `meta_dir` across every run of a matrix
        # (1792 runs on a full package is the review's own reference
        # figure), silent because nothing reads `meta_dir` back except this
        # one unlink.
        binary = _compile("int main(){ return 0; }\n",
                          self.tmp / "trivial2", self.tmp)
        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            run_matrix._run_once(isolate, binary, self.stdin_path,
                                 self.tmp / "o2.out", cpu_limit_s=5.0,
                                 wall_limit_s=10.0, mem_limit_kb=256 * 1024)
            self.assertEqual(list(isolate.meta_dir.iterdir()), [])
        finally:
            run_matrix.close_isolate_box(isolate)

    def test_a_solutions_stray_file_cannot_reach_the_next_run(self):
        # The Task 6 dogfood defect: a solution writing an unexpected
        # filename used to leave it behind, owned by that box's subuid, and
        # the next run got EACCES and was reported RE. A fresh directory per
        # run makes that unreachable rather than merely cleaned up.
        litterer = _compile('#include <cstdio>\n'
                            'int main(){ FILE*f=fopen("stray.txt","w");'
                            ' fputs("x",f); fclose(f); return 0; }\n',
                            self.tmp / "litterer", self.tmp)
        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            first = run_matrix._run_once(
                isolate, litterer, self.stdin_path, self.tmp / "1.out",
                cpu_limit_s=5.0, wall_limit_s=10.0, mem_limit_kb=256 * 1024,
                io_input="t.inp", io_output="t.out")
            second = run_matrix._run_once(
                isolate, litterer, self.stdin_path, self.tmp / "2.out",
                cpu_limit_s=5.0, wall_limit_s=10.0, mem_limit_kb=256 * 1024,
                io_input="t.inp", io_output="t.out")
        finally:
            run_matrix.close_isolate_box(isolate)
        # Both runs wrote the wrong filename, so both must report the same
        # thing. Before per-run directories the first was NO_OUTPUT and the
        # second RE, because the leftover file was owned by a subuid the
        # second box could not write through.
        self.assertTrue(first.no_output, first)
        self.assertTrue(second.no_output, second)
        self.assertFalse(second.crashed, second)

    def test_an_unremovable_run_directory_warns_and_keeps_the_verdict(self):
        # `_remove_run_dir`'s error branch, exercised end to end: a solution
        # leaves an unremovable (0700, foreign-owned) subdirectory behind.
        # Human ruling on review, reversing this task's original design: the
        # identical fact — a foreign-owned subdirectory this uid cannot
        # remove — is only a one-line stderr warning when `close_isolate_box`
        # meets it at teardown, so `_run_once`'s own `finally` meeting the
        # *same* fact minutes earlier must not abort the whole matrix over
        # it. `validating-solutions` runs hostile code on purpose;
        # `mkdir("d", 0700)` is an expected input class from that, not an
        # infrastructure fault, and this run's own `RunResult` is not in
        # doubt — its meta file was private, already read and parsed, and
        # its output already copied back before the `finally` ever runs.
        binary = _compile(
            "#include <sys/types.h>\n#include <sys/stat.h>\n#include <cstdio>\n"
            'int main(){ umask(0); if (mkdir("d", 0700) != 0) return 6;\n'
            '  FILE *f = fopen("t.out", "w"); if (!f) return 5;\n'
            '  fprintf(f, "ok\\n"); fclose(f); return 0; }\n',
            self.tmp / "dirlitter", self.tmp)

        isolate = run_matrix.open_isolate_box(self.tmp)
        # Bound before the `try` so the `finally` below can never hit
        # `UnboundLocalError` if something fails before either is assigned
        # (e.g. the survivor-count assertion) — an `UnboundLocalError` there
        # isn't an `OSError`, so `contextlib.suppress(OSError)` wouldn't
        # catch it, and `close_isolate_box` would never run: for this
        # fixture `stage_root` lives under `self.tmp`'s *parent* (see
        # `_stage_base`), outside what `tearDown`'s `rmtree(self.tmp)`
        # sweeps, so a failing run of this test would leak the very kind of
        # undeletable litter this test exists to exercise.
        run_dir = litter = None
        try:
            captured = io.StringIO()
            with contextlib.redirect_stderr(captured):
                result = run_matrix._run_once(
                    isolate, binary, self.stdin_path, self.tmp / "c1.produced",
                    cpu_limit_s=5.0, wall_limit_s=10.0, mem_limit_kb=256 * 1024,
                    io_input="t.inp", io_output="t.out")

            # The verdict is not swallowed by the cleanup failure — this is
            # the property the human ruling exists to protect.
            self.assertFalse(result.no_output, result)
            self.assertFalse(result.crashed, result)

            # The run's own directory survives the failed removal (rmtree
            # aborts partway rather than silently discarding the litter) —
            # find it so the test can clean it up without leaving anything
            # behind for the reviewer to explain, and so the warning's path
            # claim below can be checked against a real path.
            survivors = list(isolate.stage_root.iterdir())
            self.assertEqual(len(survivors), 1,
                             f"expected exactly one surviving run_dir, "
                             f"got {survivors}")
            run_dir = survivors[0]
            litter = run_dir / "d"
            self.assertTrue(litter.is_dir(), f"{litter} was not created")

            # Minor #2 on review: the deleted `_clear_stage_dir`-era test
            # asserted the message names the offending path, so the
            # "remove it as root" instruction stays actionable; that
            # property moves to the warning text here.
            warning = captured.getvalue()
            self.assertIn("WARNING", warning)
            self.assertIn(str(run_dir), warning,
                          "the warning does not name the leftover directory")
            self.assertIn(str(binary), warning,
                          "the warning does not name the binary responsible")
            self.assertIn(str(self.stdin_path), warning,
                          "the warning does not name the test that produced it")
            self.assertIn("root", warning.lower(),
                          "the warning drops the 'remove it as root' instruction")
        finally:
            # Removable despite not being ours to read: rmdir only needs
            # write+execute on the *parent*, which we own, and the target
            # must be empty — both true here.
            if litter is not None:
                with contextlib.suppress(OSError):
                    litter.rmdir()
            if run_dir is not None:
                with contextlib.suppress(OSError):
                    run_dir.rmdir()
            run_matrix.close_isolate_box(isolate)

    def test_a_removable_foreign_subdirectory_does_not_block_cleanup(self):
        # The non-error branch of `_remove_run_dir`: a subdirectory owned by
        # the sandboxed subuid but left world-writable (0777) is not the
        # undeletable case above, and must not be treated as one.
        binary = _compile(
            "#include <sys/types.h>\n#include <sys/stat.h>\n#include <cstdio>\n"
            'int main(){ umask(0); if (mkdir("e", 0777) != 0) return 6;\n'
            '  FILE *f = fopen("t.out", "w"); if (!f) return 5;\n'
            '  fprintf(f, "ok\\n"); fclose(f); return 0; }\n',
            self.tmp / "dirmaker2", self.tmp)

        isolate = run_matrix.open_isolate_box(self.tmp)
        try:
            result = run_matrix._run_once(isolate, binary, self.stdin_path,
                                          self.tmp / "e1.produced",
                                          cpu_limit_s=5.0, wall_limit_s=10.0,
                                          mem_limit_kb=256 * 1024,
                                          io_input="t.inp", io_output="t.out")
            self.assertFalse(result.no_output, result)
            self.assertEqual(list(isolate.stage_root.iterdir()), [],
                             "a removable foreign subdirectory left the run "
                             "directory behind")
        finally:
            run_matrix.close_isolate_box(isolate)


class BoxLeasingTest(MinimalIsolateFixture):
    def test_isolate_handle_has_no_pid_derived_counter(self):
        # The pid-derived counter is the Cause-A defect itself. Its absence
        # is the invariant, so it is asserted rather than assumed.
        self.assertFalse(hasattr(run_matrix, "_select_box_id"))
        self.assertNotIn("box_id_counter",
                         run_matrix.IsolateHandle.__dataclass_fields__)

    def test_init_box_names_the_collision_instead_of_the_install(self):
        # isolate answers "This box is currently in use by another process"
        # (rc=2) when the id is live. The old message blamed cgroup
        # delegation, subuid ranges and isolate-cg-keeper — a confident wrong
        # diagnosis that has already cost three agents an afternoon.
        fake = self._fake_isolate(
            rc=2, message="This box is currently in use by another process")
        with self.assertRaises(run_matrix.MatrixError) as ctx:
            run_matrix._init_box(fake, 7)
        message = str(ctx.exception)
        self.assertIn("in use", message)
        self.assertIn("box 7", message)
        self.assertNotIn("subuid", message)
        self.assertNotIn("cg-keeper", message)

    def test_init_box_still_names_the_install_for_a_real_config_failure(self):
        fake = self._fake_isolate(rc=1, message="Cannot initialize control group")
        with self.assertRaises(run_matrix.MatrixError) as ctx:
            run_matrix._init_box(fake, 7)
        self.assertIn("subuid", str(ctx.exception))

    def _fake_isolate(self, *, rc: int, message: str) -> str:
        script = self.tmp / f"fake_isolate_{rc}_{abs(hash(message)) % 9999}"
        script.write_text(f"#!/bin/sh\necho '{message}' >&2\nexit {rc}\n",
                          encoding="utf-8")
        script.chmod(0o755)
        return str(script)


class TestStageBase(unittest.TestCase):
    """`_stage_base` needs no sandbox, so it is tested without one."""

    def test_memory_backed_staging_is_refused_with_a_named_fix(self):
        with mock.patch.object(run_matrix, "_filesystem_type", return_value="tmpfs"):
            with self.assertRaises(run_matrix.MatrixError) as ctx:
                run_matrix._stage_base(Path(__file__).parent)
        message = str(ctx.exception)
        self.assertIn("tmpfs", message)
        self.assertIn("RUN_MATRIX_STAGE_DIR", message)
        # The fix is the last line, with a concrete value named after the
        # problem directory — not only `$RUN_MATRIX_STAGE_DIR` mid-paragraph.
        last = message.splitlines()[-1]
        name = Path(__file__).parent.name
        self.assertIn(f"RUN_MATRIX_STAGE_DIR=/var/tmp/{name}", last)
        self.assertIn(f"mkdir -p /var/tmp/{name}", last)

    def test_a_nonexistent_override_also_ends_with_the_concrete_fix(self):
        # The workaround's own failure mode: pointing the variable at a
        # /var/tmp directory that was never created.
        with mock.patch.dict(os.environ,
                             {run_matrix.STAGE_DIR_ENV: "/nonexistent/stage"}):
            with self.assertRaises(run_matrix.MatrixError) as ctx:
                run_matrix._stage_base(Path("/somewhere/flight"))
        last = str(ctx.exception).splitlines()[-1]
        self.assertIn("mkdir -p /var/tmp/flight", last)
        self.assertIn("RUN_MATRIX_STAGE_DIR=/var/tmp/flight", last)

    def test_main_prints_the_concrete_fix_for_a_problem_on_tmpfs(self):
        # End to end through the CLI, since the field report was about what
        # the user *saw*: `run()` loads problem.json and then reaches
        # `_stage_base` before isolate, compilation or the box pool, so this
        # is the message that fires for a problem under /tmp — exit 2,
        # stderr only, the fix on its final line. The suite exports the
        # override globally for its own fixtures, so it is removed here or
        # it would mask the refusal.
        err, out = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(run_matrix.STAGE_DIR_ENV, None)
            with mock.patch.object(run_matrix, "_filesystem_type",
                                   return_value="tmpfs"), \
                    contextlib.redirect_stderr(err), \
                    contextlib.redirect_stdout(out):
                code = run_matrix.main(["run_matrix.py", str(FIXTURE),
                                        "/nonexistent-testlib"])
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        lines = err.getvalue().strip().splitlines()
        self.assertTrue(lines[0].startswith("run_matrix: refusing to stage"),
                        err.getvalue())
        self.assertIn(f"RUN_MATRIX_STAGE_DIR=/var/tmp/{FIXTURE.name}", lines[-1])

    def test_env_override_wins_over_the_problem_directory(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH_ROOT) as override:
            with mock.patch.dict(os.environ,
                                 {run_matrix.STAGE_DIR_ENV: override}):
                self.assertEqual(run_matrix._stage_base(Path("/nonexistent/p")),
                                 Path(override))

    def test_default_is_the_problem_directorys_parent(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(run_matrix.STAGE_DIR_ENV, None)
            base = run_matrix._stage_base(SCRATCH_ROOT / "some-problem")
        self.assertEqual(base, SCRATCH_ROOT.resolve())

    def test_filesystem_type_identifies_a_real_mount(self):
        # Guards the detection itself: a helper that silently returned None
        # for everything would make the refusal above unreachable in
        # practice while still passing its own (mocked) test.
        self.assertIsNotNone(run_matrix._filesystem_type(Path("/")))

    def setUp(self):
        SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)


class ExitCodeContractTest(PackageFixture):
    """`main()`'s exit codes are a contract `validating-solutions` reads.

    Exit 1 means "the matrix ran and found holes and/or mismatches" — a
    statement about the *package*. Anything that prevents the matrix from
    running is exit 2. A crash reported as exit 1 is a crash read as a
    finding, which is the misread `main()`'s own docstring says it exists
    to prevent.
    """

    def _main(self):
        return run_matrix.main(["run_matrix.py", str(self.problem_dir),
                                str(self.testlib_dir)])

    def test_a_malformed_problem_json_exits_2_not_1(self):
        (self.problem_dir / "problem.json").write_text("{not json",
                                                       encoding="utf-8")
        self.assertEqual(self._main(), 2)

    def test_a_malformed_expect_header_exits_2_not_1(self):
        # Likelier in practice than a bad problem.json: a setter edits
        # solution headers constantly.
        path = self.problem_dir / "solutions" / "sol-main.cpp"
        path.write_text(path.read_text(encoding="utf-8")
                        .replace("g1=OK", "g1=NOPE"), encoding="utf-8")
        self.assertEqual(self._main(), 2)

    def test_a_corrupted_flags_json_during_a_banded_result_exits_2_not_1(self):
        # A third escapee beyond the two the plan for this task named:
        # `flags.append` (called from `_run_pass2` whenever a result is
        # retimed or lands in the (TL, kill] band) reads the existing
        # register before writing to it, so a corrupted flags.json raises
        # `flags.FlagError` from inside `run()` — but only on a run that
        # actually reaches that call site. `compute_limits` is patched
        # (same technique as
        # `TestRunMatrixFixture.test_band_result_is_reached_and_flagged_with_accurate_wording`)
        # to force every result into the band deterministically, so this
        # is not a probe that could pass by accident of timing.
        #
        # `compute_limits` is patched to a degenerate `tl_ms=-1`, so the run
        # is heavily perturbed; asserting only `code == 2` would pass just
        # as well for an unrelated `MatrixError` and prove nothing about
        # `FlagError` specifically. Pin it the way
        # `test_a_package_error_prints_to_stderr_and_nothing_to_stdout`
        # already does: capture stderr and require the message actually
        # names `flags.json`.
        (self.problem_dir / "flags.json").write_text("{not json",
                                                       encoding="utf-8")
        forced = matrix_core.Limits(t_main_ms=2, tl_ms=-1, kill_ms=5000)
        err = io.StringIO()
        with mock.patch.object(run_matrix, "compute_limits", return_value=forced):
            with contextlib.redirect_stderr(err):
                code = self._main()
        self.assertEqual(code, 2)
        self.assertIn("flags.json", err.getvalue())

    def test_a_package_error_prints_to_stderr_and_nothing_to_stdout(self):
        # stdout is the results channel. A caller that parses stdout must
        # not receive a half-line of nothing and read it as "no holes".
        (self.problem_dir / "problem.json").write_text("{not json",
                                                       encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self._main()
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("problem.json", err.getvalue())

    def test_no_tools_exception_type_escapes_main(self):
        # An end-to-end check for the one type this actually injects
        # (`ProblemMetaError`, already a `PACKAGE_ERRORS` member) — not a
        # general guarantee that *any* future error type is caught; nothing
        # about running this single case would fail if a new `tools` module
        # raised a brand-new type main() had never heard of.
        # `test_every_tools_error_type_reachable_from_run_matrix_is_in_package_errors`
        # below is what actually proves the boundary property this
        # docstring used to (wrongly) claim this test alone established.
        (self.problem_dir / "problem.json").write_text("{not json",
                                                       encoding="utf-8")
        try:
            self._main()
        except BaseException as exc:  # noqa: BLE001 - that is the point
            self.fail(f"{type(exc).__module__}.{type(exc).__name__} escaped main()")

    def test_every_tools_error_type_reachable_from_run_matrix_is_in_package_errors(self):
        # The boundary property itself, enforced rather than asserted by a
        # single injected example: every exception class actually defined
        # in `run_matrix` or in any `tools` module `run_matrix` imports
        # something from must be a member of `PACKAGE_ERRORS` (or
        # `PACKAGE_ERRORS` itself must widen to a blanket `except
        # Exception`, which `main()` also has — but that tier prints a raw
        # traceback rather than a clean message, so an exception type this
        # pipeline *names* belongs in the one-line-message tier, and this
        # test is what keeps a newly-added named type from silently falling
        # through to the traceback tier instead).
        #
        # Deliberately not a sweep of `sys.modules`: under full `discover`,
        # `tools.drift_check` is imported by its own test module, and its
        # deliberately-excluded `DriftCheckError` would then fail this test
        # for a module `main()` cannot actually reach through `run()`.
        # Building the module set from `run_matrix`'s own namespace instead
        # also self-updates if someone later imports `drift_check` (or
        # anything else) into `run_matrix` — exactly the case this test
        # exists to catch.
        #
        # Known limits of this approach, not fixed here (a review confirmed
        # each in principle and confirmed none is live today — an AST sweep
        # would close all three, but that is a rewrite this task's ruling
        # was not to make):
        #   1. A module imported *lazily inside a function* never appears
        #      in `vars(run_matrix)` — only module-level imports are
        #      one-hop-reachable this way. `run_matrix` currently has zero
        #      local imports of `tools` modules.
        #   2. A type reachable only *transitively* — imported by a module
        #      that `run_matrix` imports, but not itself re-exported into
        #      `run_matrix`'s own namespace — is missed, since this only
        #      walks one hop from `run_matrix`. Reproduced directly: a
        #      type whose `__module__` sits outside the one-hop module set
        #      built here comes back absent from `uncovered` regardless of
        #      whether `main()` could actually reach it.
        #   3. An exception class *defined inside a function body* never
        #      appears in its module's `vars()` at all — `vars(m)` only
        #      sees module-level names. `run_matrix` currently defines zero
        #      exception classes inside a function.
        mods = {run_matrix}
        for obj in vars(run_matrix).values():
            if isinstance(obj, types.ModuleType):
                name = obj.__name__
            elif inspect.isclass(obj) or inspect.isfunction(obj):
                name = getattr(obj, "__module__", "")
            else:
                continue
            if name == "tools" or name.startswith("tools."):
                mods.add(sys.modules[name])
        uncovered = [f"{m.__name__}.{n}"
                     for m in mods for n, o in vars(m).items()
                     if inspect.isclass(o) and issubclass(o, BaseException)
                     and o.__module__ == m.__name__
                     and not issubclass(o, run_matrix.PACKAGE_ERRORS)]
        self.assertEqual(uncovered, [])

    def test_a_real_hole_still_exits_1(self):
        # The contract's other half: exit 2 must not swallow genuine
        # findings. Declare the wrong solution as correct so the suite has
        # a hole to report.
        path = self.problem_dir / "solutions" / "sol-wrong.cpp"
        path.write_text(path.read_text(encoding="utf-8")
                        .replace("g1=WA", "g1=TL"), encoding="utf-8")
        self.assertEqual(self._main(), 1)


class MainExceptionTierTest(unittest.TestCase):
    """Review finding: `PACKAGE_ERRORS` alone left a real, reachable gap —
    a plain `OSError` from `invocation.json`'s own `write_text` (a full or
    read-only disk) is a stdlib exception, not a `tools/` type, so it
    escaped as a traceback and exited 1 just like `ProblemMetaError` did
    before this task. `main()`'s trailing `except Exception` closes that
    gap. No sandbox needed here — `run_matrix.run` is mocked directly, so
    this does not need `PackageFixture`'s isolate/g++ dependency at all.
    """

    def _main(self):
        return run_matrix.main(["run_matrix.py", "/nonexistent/problem",
                                "/nonexistent/testlib"])

    def test_a_driver_bug_is_exit_2_with_a_traceback_on_stderr(self):
        # A concrete stand-in for the reviewer's example: some plain
        # exception `run()` raises that is not a `tools/` type at all, so
        # it cannot be a `PACKAGE_ERRORS` member.
        with mock.patch.object(
                run_matrix, "run",
                side_effect=OSError("No space left on device")):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = self._main()
        self.assertEqual(code, 2)
        # The full traceback, not a one-line message — that tier is for
        # PACKAGE_ERRORS only; a driver bug is not something a package
        # author can silently act on the way "malformed problem.json" is.
        self.assertIn("Traceback (most recent call last)", err.getvalue())
        self.assertIn("OSError", err.getvalue())
        self.assertIn("No space left on device", err.getvalue())

    def test_keyboard_interrupt_is_not_swallowed(self):
        # `except Exception` must not catch `BaseException` subclasses that
        # are not `Exception` subclasses — confirmed rather than assumed,
        # per Python's own exception hierarchy (`KeyboardInterrupt` and
        # `SystemExit` derive from `BaseException` directly).
        with mock.patch.object(run_matrix, "run", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self._main()

    def test_system_exit_is_not_swallowed(self):
        with mock.patch.object(run_matrix, "run", side_effect=SystemExit(3)):
            with self.assertRaises(SystemExit):
                self._main()


class PoolSizeAtPassTwoTest(PackageFixture):
    def test_a_bad_pool_size_at_pass_two_is_a_matrix_error(self):
        # The plan for this task assumed `pool_size()` is called exactly
        # twice in a run — once inside `open_isolate_box` (via
        # `box_pool.lease`), once at the bare call site before pass 2 — and
        # a `len(calls) > 1` counter would isolate the second. That is
        # wrong: `_leased_box()` is also entered once per sandboxed run
        # inside `_run_once` (pass 1 times the model solution three times
        # per test, each a `_leased_box()`/`pool_size()` call of its own),
        # so a bare call-count trips on pass 1, long before pass 2, and
        # raises through `_leased_box`'s own conversion instead of the
        # target site — confirmed empirically: the counter version failed
        # with `str(ctx.exception) == "synthetic pool failure"`, not
        # wrapped with "cannot size the worker pool" at all.
        #
        # Distinguish by the immediate caller instead: `lease()` (inside
        # `box_pool.py`) calls `pool_size()` for every leased box; the bare
        # call this task added calls it directly from `run()`. Only the
        # latter should fail.
        real = box_pool.pool_size

        def flaky():
            caller = sys._getframe(1).f_code.co_name
            if caller == "run":
                raise box_pool.BoxPoolError("synthetic pool failure")
            return real()

        with mock.patch.object(box_pool, "pool_size", flaky):
            with self.assertRaises(run_matrix.MatrixError) as ctx:
                run_matrix.run(self.problem_dir, self.testlib_dir)
        self.assertIn("worker pool", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
