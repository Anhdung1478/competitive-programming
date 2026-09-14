#!/usr/bin/env python3
"""Build every solution, run it on every test, and write invocation.json.

Timing policy, from the spec: the model solution is timed as the median of
three runs per test and the limit follows from its slowest test. Adversary
solutions get one run, and only a result landing in the (TL, kill] band —
strictly over TL, since a run exactly at TL is accepted, up through kill — is
re-run three times before being reported — three runs of everything triples
the cost of the pipeline for no gain outside the band. Pass 2 also runs on
several sandboxes at once (see `_run_pass2`), which can inflate a single
run's CPU time; a measurement close enough to TL that contention could have
decided it gets one extra serial re-time, before classification, on top of
the band re-run above — see `matrix_core.needs_serial_retime`.

Runner: every solution runs inside the ioi/isolate sandbox (isolate 2.x).
This module previously spawned children itself (`os.posix_spawn` + a
`/proc/<pid>/status` polling loop for peak memory) and that approach had two
proven, opposite defects that no amount of polishing fixed: the `ru_maxrss`
fallback occasionally reported the *driver's* memory (a false-positive ML on
a correct solution), and `VmHWM` polling could only under-report a peak,
never over it (a false-negative ML on a solution engineered just over the
limit). isolate runs the solution in its own cgroup and reports the
outcome in a meta file: `max-rss` is the kernel's own peak for that child
(not a polled reading, and not this driver's), a memory kill is
`cg-oom-killed:1` from the cgroup, and a time kill is `status:TO` from the
sandbox's own clock, not a wait-loop deadline this process has to race
against.

What this module *does* guarantee about accounting, stated precisely
because a stronger claim ("neither defect is possible here") stood in this
docstring for two tasks and was false the whole time — see the staging
paragraph below for the third relocation of the same defect class:

    Memory is judged from `max-rss` (`_classify`: ML iff the child's peak
    RSS is strictly over `memory_mb`, or the cgroup killed it). Output
    size is bounded by `--fsize` (`OUTPUT_LIMIT_KB`) and is *not* reported
    at all. The cgroup cap `--cg-mem` is **not** `memory_mb`: it is
    `memory_mb + OUTPUT_SLACK_KB`. On cgroup v2 the page cache a solution
    dirties by writing its output is charged to its cgroup until writeback
    drains it — on a disk-backed filesystem too, not only on tmpfs — so a
    cap set exactly at `memory_mb` was OOM-killing solutions for their
    *output*, with almost no RSS of their own, on whichever runs the
    flusher happened to lose the race (measured here: 48 MB of output under
    a 32 MB cap, OOM on anywhere from one run in five to two in three,
    varying between sessions). Disk-backed page cache is
    reclaimable once written back, so the slack — sized to `--fsize`, the
    largest file the sandbox permits — is enough headroom for any allowed
    output to sit fully dirty; `max-rss` never includes page cache, so the
    verdict itself is unaffected by output either way. tmpfs is a different
    case, and `_stage_base()` still refuses it rather than warning: its
    pages are *never* reclaimable, so no finite slack makes output and
    memory independent there (measured: 70 MB of output at a 64 MB limit
    reported `max-rss:1668 cg-oom-killed:1`). `--fsize` is passed
    explicitly rather than left to the accident of where the staging
    directory happened to land, and the slack is sized to it.

There is no fallback runner. If isolate is missing, or installed but not
usable (unconfigured cgroup delegation, no subuid/subgid range, the
isolate-cg-keeper service not running), `run()` raises `MatrixError` naming
the fix rather than silently reverting to something unsandboxed — see
`open_isolate_box()`.

isolate 2.x box-access model, and the trap it sets: after `--init` the box
directory is owned by the mapped subuid at mode 0700, so files cannot be
copied into it directly. This driver never touches that directory at all —
every run instead bind-mounts host directories straight into the sandbox
(`--dir=<in>=<out>[:rw]`), which is unaffected by that ownership and is the
documented way to get files in and out.

Task 9b's own review found and this driver now avoids a second trap in the
same neighbourhood: an *earlier* version of this module bind-mounted real
repository directories (`tests/<group>/`, `.build/`) as the `:rw` target so
the sandboxed process could write its stdout (the regenerated `.a` answer
file, a solution's `.out`) directly into them. That "worked" but was wrong
in a way `git status` cannot see, because both paths are gitignored: the
sandboxed process runs as a mapped subuid that is neither our uid nor our
group, so making a directory writable to it meant granting the repo
directory an `o+w` bit that was never restored, and every file the sandbox
created inside it came back owned by that subuid — not us, not writable or
even `chmod`-able by us afterward. That is permanent, silent damage to the
user's working tree: `chmod -R`, `rsync -p`, `tar --same-owner`, or a
CI rewrite of the checkout would all fail on those files, and — worse —
`tests/<group>/` at `o+rwx` on a shared jury machine means any local
account could substitute test inputs or answer keys for a problem still
under preparation. This driver instead gives every `--run` a *private*
staging directory (one `mkdtemp()` per call, under `IsolateHandle.stage_root`
— Task 3: per-*call*, not per-`run()`, so two calls sharing one handle never
share a directory either — world-writable, which is harmless there, since
it is ours and ephemeral) as the only `:rw` mount; the binary's and the test
input's directories are mounted read-only. After each run, the
staged output is copied back into the repository with an ordinary
`Path.write_bytes()` call from *this* (unprivileged) process — never
bind-mounted — so every artifact that lands in the user's tree keeps its
normal ownership and the repo directory's own mode is never touched. The
copy always unlinks the destination first (`stdout_dest.unlink(missing_ok=
True)`, relying only on directory-write permission, which this process
already has as the owner), which doubles as a self-heal for a repo already
damaged by the old behaviour: a stale, foreign-owned `.a`/`.out` left over
from a previous run of this driver is simply replaced, not fought with.
`_ensure_dir_traversable()` similarly self-heals the directory-mode half of
that damage — it strips any stray `o+w` bit left on `tests/<group>/` or
`.build/` while granting the `o+x` (traverse) bit these read-only mounts
still need, every time `run()` starts.

Meta-file contract this module parses (all four cases verified against the
isolate 2.6 build on this machine, not read off documentation):

    OK:  no `status` line at all; `exitcode:0`; `max-rss`; `cg-mem`.
    TLE: `status:TO`; `killed:1`; `time`; `message:Time limit exceeded`
         (the message differs for a wall-clock kill, the status does not).
    MLE: `status:SG`; `cg-oom-killed:1`; `cg-mem` pinned at the cgroup cap (`memory_mb + OUTPUT_SLACK_KB`, not `memory_mb`);
         `exitsig:9`; no `exitcode` line.
    RE:  `status:RE`; `exitcode:N`; `message:Exited with error status N`.

Two traps, both handled explicitly in `_run_once`: success emits no
`status` line at all (absence must be read as OK, not as "field missing");
and a memory kill arrives as `status:SG` — indistinguishable from a bare
segfault by the status text alone — so `cg-oom-killed` must be tested
*before* treating an `SG` status as a plain crash, or every OOM misreports
as RE.

Task 9c: a fresh box per `--run`, not one box reused for the whole
invocation. The `flight` dogfood found what neither the 9b migration nor
its review did: isolate's cgroup counters are **not reset between `--run`s
in the same box** — reproduced with bare isolate, no involvement from this
module: a memory hog OOMing at 400 MB in box N, followed by
`int main(){return 0;}` in the *same* box N, reports the hog's
`cg-oom-killed:1` for the trivial program too. Since ML outranks WA in
`_SEVERITY` (`matrix_core`), one OOM used to silently overwrite every
later solution's verdict in that run — not merely add a wrong row, replace
correct ones. This is the bug that mattered: `cg-oom-killed` is sticky
across `--run`s in the same box, and this module's classification reads it
directly (see `_run_once`). `cg-mem` is *also* a box-lifetime high-water
mark in the same way — verified directly against the same box (a 200 MB
run followed by a trivial one reported `cg-mem` unchanged) — but this is
not a second consequence for this driver specifically: `peak_kb` is read
from `max-rss`, never from `cg-mem` (see `_run_once`), and `max-rss` is
sourced from `wait4()`/`getrusage()` on the sandboxed *process* rather
than the cgroup, so it resets correctly with every fresh process
regardless of box reuse (also verified directly: same before/after pair,
`max-rss` dropped back down while `cg-mem` stayed pinned). `peak_kb` was
never contaminated, and no `invocation.json` produced before this fix has
an inflated memory column — but `cg-mem` remains unreliable across `--run`s
in a shared box and must not be read that way in the future without this
same per-run isolation. This is the same class of defect the 9b migration
was fixing (memory accounting contaminated by something other than the
process being measured); the live instance of it here had just relocated
from the parent process's address space into the box's cgroup, and it
surfaced as a corrupted verdict rather than a corrupted number. The fix:
`_run_once` now owns a full `--init`/`--run`/`--cleanup` cycle for its own
box id, so no run can ever observe another run's counters — on any field,
whether or not this driver currently reads it. `open_isolate_box()` still
does one probe `--init`/`--cleanup` at startup (to fail fast, before any
compilation, if isolate is missing or unconfigured) but no longer holds a
box open across the whole invocation — see `box_pool` for how each call
leases its own id, and why a lease rather than a pid-derived id: two
concurrently-running `run_matrix` invocations belonging to the *same
user* no longer collide on the same box. Cross-user collision remains a
live, deliberate limit of a per-user lock directory — see `box_pool`'s
own module docstring for why, and `_init_box` for how that specific case
is diagnosed rather than silently misattributed.

Where the staging directory lives, and why it is not `/tmp`: the third
relocation of one defect class. The staging directory 9b introduced was a
plain `tempfile.mkdtemp()`, which lands under `$TMPDIR` — `/tmp` — and
`/tmp` is `tmpfs` on this machine and on most modern Linux. `--stdout`
points into that directory while `--cg-mem` caps the same cgroup, and
tmpfs pages are charged to the writing cgroup and are never reclaimable, so
**a solution's own stdout counted against its memory limit**. Reproduced
with bare isolate, no involvement from this module: a 1.6 MB program
writing 70 MB to stdout under a 64 MB limit reported
`max-rss:1668  cg-mem:65536  cg-oom-killed:1  status:SG` — a false ML on a
program using 2.5% of the limit it was given. This is the same class as
the two above (memory accounting contaminated by something other than the
process being measured): it was the parent's `mm` (9), then the box's
cgroup (9c), and then the directory the output was staged in. The fix has
two halves and both are load-bearing — plus a third, found later, without
which the first two were not enough (`OUTPUT_SLACK_KB`: disk-backed page
cache is charged too, only transiently, and the cap must leave room for
it):

  * `_stage_base()` picks a **disk-backed** location — by default the
    problem directory's parent (the same filesystem as the work being
    staged), overridable with `$RUN_MATRIX_STAGE_DIR`, never falling back
    to `/tmp`. If the chosen location is memory-backed it raises
    `MatrixError` rather than warning: this driver's standing doctrine is
    that it refuses to run rather than produce a confidently wrong
    verdict, the same call already made for a missing sandbox and for an
    `io.output` that would collide with the staged stdout, and a warning
    on stderr in the middle of a few hundred runs is exactly the thing a
    caller reads past.

  * `--fsize=OUTPUT_LIMIT_KB` bounds the output explicitly. Until this
    fix, tmpfs *accidentally* capped output at `memory_mb`; moving staging
    to disk removes that accident, and a `while(1) putchar()` solution —
    precisely the kind a deliberately-wrong zoo invites — would otherwise
    write until the disk filled and then have the whole file loaded into
    the driver's RAM by `staged_out.read_bytes()`. Exceeding `--fsize`
    kills the process with SIGXFSZ, which arrives as `status:SG` with no
    `cg-oom-killed`, so it is classified `RE` — the honest verdict for a
    solution whose output ran away, and distinct from the `ML` a real
    memory hog gets.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import dataclasses
import json
import os
import platform
import shutil
import stat
import statistics
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

from tools import box_pool
from tools import flags
from tools.matrix_core import (
    CONTENTION_BOUND,
    Limits,
    Outcome,
    classify,
    compare,
    compute_limits,
    group_verdict,
    needs_serial_retime,
)
from tools.problem_meta import Problem, ProblemMetaError, load
from tools.scan_solutions import ScanError, scan

SCHEMA = 1
CXXFLAGS = ["-std=c++17", "-O2"]

# testlib checker exit codes: 0 ok(), 1 quitf(_wa), 2 quitf(_pe) — which is
# also what _dirt (trailing garbage) and _unexpected_eof surface as, since
# testlib treats both as "the participant's output is malformed" rather than
# a distinct code — and 3 quitf(_fail), the package-bug signal. 7 (_points,
# partial-credit scoring) is deliberately left unmapped: this pipeline only
# uses whole-subtask stock checkers (ncmp et al.), none of which call
# quitp, so a 7 here would mean a checker mismatched to the problem, not a
# real partial-credit result — and should surface as FAIL, the same as any
# other exit code this table doesn't recognise. Defaulting every unmapped
# code to FAIL (never silently to OK/WA) keeps an unexpected checker
# exit from ever being mistaken for a verdict on the *solution*.
CHECKER_EXIT = {0: "OK", 1: "WA", 2: "PE", 3: "FAIL"}

# A checker only reads two or three files already on disk and compares them
# — even a checker doing something unusually heavy (diffing large output
# files) should finish in well under a second. 10s is a deliberately
# generous multiple of that (not tied to the problem's own TL, which bounds
# the *solution*, not the checker) so a merely-slow checker is never
# mistaken for a hung one, while a genuine infinite loop in a custom
# checker (externally-authored data, per R1) still fails in bounded time
# instead of hanging the whole pipeline.
CHECKER_TIMEOUT_S = 10

# Pass 1 has no TL/kill yet (they are derived *from* this pass), so it needs
# its own hard safety ceiling — same role the old fixed 60_000 ms kill
# played. The wall-time backstop is a separate, larger number: a model
# solution stuck blocking on I/O rather than burning CPU would never trip
# the CPU cap.
MODEL_SAFETY_CPU_S = 60.0
MODEL_SAFETY_WALL_S = 90.0

# Where the per-invocation staging directory is created, and the escape
# hatch for a machine whose problem tree is somewhere unsuitable. Read by
# `_stage_base()`; deliberately not defaulted to `/tmp` under any
# circumstance — see the module docstring for the false-ML that caused.
STAGE_DIR_ENV = "RUN_MATRIX_STAGE_DIR"

# Filesystems whose pages are charged to the writing process's cgroup and
# are not reclaimable — i.e. the ones where a file write is indistinguishable
# from an allocation as far as `--cg-mem` is concerned.
MEMORY_BACKED_FSTYPES = frozenset({"tmpfs", "ramfs", "devtmpfs"})

# `--fsize`: the hard ceiling, in KB, on any single file the sandboxed
# process can create — in practice its stdout, the only file it writes.
#
# 256 MB, chosen deliberately rather than inherited:
#   * It must be far above any legitimate output. The largest plausible
#     answer for a problem this pipeline handles is on the order of 10^6
#     numbers at ~20 bytes each, i.e. tens of MB; 256 MB is an order of
#     magnitude clear of that, so no correct solution is ever truncated
#     into a false WA/RE. A false verdict is the expensive failure here,
#     and it is the one this number is sized against.
#   * It must be low enough that the runaway case stays survivable, because
#     `_run_once` reads the staged file whole into this process's memory
#     (`source.read_bytes()`) before copying it back. Per run, 256 MB is a
#     bounded, recoverable read; an unbounded one is not, and neither is a
#     `while(1) putchar()` allowed to fill the user's disk. That per-run
#     bound is still what this constant is sized against — but pass 2 runs
#     `_run_once` on `workers` threads inside this one process at once, so
#     the driver's own peak from this read alone is `workers * 256 MB`, not
#     256 MB: 2 GB at `RUN_MATRIX_BOX_POOL=8`.
#   * 256 MB is also the output cap mainstream judges use (Codeforces),
#     so a solution that trips this one would have tripped a real judge's.
# Note the consequence for `.build/`: a runaway solution can leave a file
# of this size per test until the next run overwrites it. That is the
# deliberate price of not truncating a legitimate answer.
OUTPUT_LIMIT_KB = 256 * 1024

# Headroom added to `--cg-mem` on top of the problem's `memory_mb`, in KB.
#
# On cgroup v2 every page a process writes to a file — even on a disk-backed
# filesystem — is charged to its cgroup while dirty or in writeback, and
# `--cg-mem` becomes the cgroup's hard `memory.max`. A solution that dirties
# output faster than the flusher drains it therefore hits the cap and is
# OOM-killed with almost no RSS of its own (kernel report on this machine:
# anon 160 KB, file 32 MB — all of it dirty/writeback — under a 32 MB cap;
# a `GFP_NOFS|__GFP_NOFAIL` allocation cannot reclaim dirty pages and forces
# the kill). Page cache is *reclaimable* once written back, so unlike tmpfs
# this is not a permanent charge; but it is a real one at the moment the
# cap is checked, and it made a solution's verdict depend on the flusher's
# timing rather than on its memory.
#
# So the cap `_run_once` applies is `memory_mb + OUTPUT_SLACK_KB`, sized to
# `--fsize`: the largest single file the sandbox permits can sit fully
# dirty without tripping the cap. ML is then judged by `_classify` from
# `max-rss` against the *unslacked* `memory_mb`, and `cg-oom-killed` only
# fires for a solution that overshoots the limit by more than the slack.
# Deliberately not a multiplier: an output allowance is a fixed number of
# bytes, and scaling it with `memory_mb` would let a 64 MB problem keep
# false-OOMing on 70 MB of output.
OUTPUT_SLACK_KB = OUTPUT_LIMIT_KB


class MatrixError(RuntimeError):
    """The matrix could not be run: a build, fixture, or environment problem."""


def _compile(source: Path, binary: Path, extra: list[str] | None = None,
             *, context: str) -> None:
    if not source.exists():
        raise MatrixError(f"{context}: source file not found: {source}")
    cmd = ["g++", *CXXFLAGS, *(extra or []), str(source), "-o", str(binary)]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0:
        raise MatrixError(
            f"{context}: compile failed\n$ {' '.join(cmd)}\n{done.stderr}"
        )


# ---------------------------------------------------------------------------
# isolate lifecycle: locate the binary, open one box for the whole run(),
# and guarantee its cleanup.
# ---------------------------------------------------------------------------

_ISOLATE_HOME = "https://github.com/ioi/isolate"


@dataclasses.dataclass(frozen=True)
class IsolateHandle:
    """The isolate environment shared by one `run()` invocation.

    Everything per-*run* now lives under a per-run directory that
    `_run_once` creates and removes, because a single meta file and a single
    staging directory shared across runs are exactly what stopped this
    driver from ever running two solutions at once: two concurrent `--run`s
    would have written the same meta file (one reads the other's verdict —
    silent and wrong) and cleared the same staging directory out from under
    each other.

    `meta_dir` is deliberately NOT under `stage_root` and is never passed to
    `--dir`. The meta file is the driver's only account of what happened; a
    solution able to open it could write its own verdict.

    `stage_root` is the disk-backed parent of every per-run staging
    directory. Disk-backed, never `/tmp`: on tmpfs the bytes a solution
    writes to its output are charged to the same cgroup `--cg-mem` caps
    and never reclaimed, which is a false ML on any solution with a large
    answer no matter how much slack the cap carries. See `_stage_base()`
    and `OUTPUT_SLACK_KB`.

    Box ids are not a field here at all — `_run_once` leases one per run from
    `tools.box_pool`, which is cross-process and therefore also excludes
    *other* invocations by this user, something no per-handle counter
    could do.
    """

    binary: str
    version: str
    meta_dir: Path
    stage_root: Path


def _filesystem_type(path: Path) -> str | None:
    """The type of the filesystem `path` lives on, or None if unknowable.

    Reads `/proc/mounts` and picks the longest mount point that is a prefix
    of the resolved path — the same longest-prefix rule the kernel itself
    uses, so a `tmpfs` mounted *inside* a disk-backed tree (or the reverse)
    is resolved correctly rather than by the first line that happens to
    match. Mount points in `/proc/mounts` are octal-escaped; the three
    escapes that occur in practice are decoded.

    Returns None on any platform without `/proc/mounts` rather than
    guessing: an unknown filesystem type is treated as acceptable by
    `_stage_base()`, since refusing to run everywhere `/proc` is absent
    would be a worse failure than the one this detection prevents.
    """
    try:
        raw = Path("/proc/mounts").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    target = os.path.realpath(path)
    best_len, best_type = -1, None
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) < 3:
            continue
        point = (fields[1].replace("\\040", " ").replace("\\011", "\t")
                 .replace("\\012", "\n").replace("\\134", "\\"))
        if target == point or target.startswith(point.rstrip("/") + "/"):
            if len(point) > best_len:
                best_len, best_type = len(point), fields[2]
    return best_type


def _stage_base(problem_dir: str | Path | None) -> Path:
    """Pick the directory the per-invocation staging directory is created in.

    Order: `$RUN_MATRIX_STAGE_DIR` if set, otherwise the problem
    directory's *parent* — same filesystem as the package being staged,
    which is the property that matters — otherwise the current working
    directory (only reachable when a caller opens a box without naming a
    problem, e.g. a unit test driving `_run_once` directly).

    There is no `/tmp` fallback on any path through this function, and that
    is the entire point of it existing: `tempfile.mkdtemp()` with no `dir=`
    lands in `/tmp`, `/tmp` is tmpfs here and on most modern Linux, and a
    file written to tmpfs is charged to the writing cgroup — the same
    cgroup `--cg-mem` caps — and is never reclaimable, so the slack the cap
    carries for disk-backed page cache (`OUTPUT_SLACK_KB`) does not help.
    See the module docstring for the measured false ML that produced.

    Raises `MatrixError` — never warns — when the chosen location is
    unusable or memory-backed. A warning would be the wrong call twice
    over: it scrolls past in the middle of a few hundred sandboxed runs,
    and the failure it precedes is a *wrong verdict on a correct
    solution*, which this driver already refuses to risk elsewhere (a
    missing sandbox, a model solution that writes no output file at all)
    rather than proceed through.
    """
    override = os.environ.get(STAGE_DIR_ENV)
    if override:
        base, source = Path(override), f"${STAGE_DIR_ENV}"
    elif problem_dir is not None:
        base, source = Path(problem_dir).resolve().parent, "the problem directory's parent"
    else:
        base, source = Path.cwd(), "the current working directory"

    # Every refusal below ends with the fix as a runnable line of its own,
    # with a concrete value in it. Field report: a problem drafted in a
    # scratchpad under /tmp exited 2 before running anything, and the
    # user found `RUN_MATRIX_STAGE_DIR=/var/tmp/<name>` by themselves. The
    # variable *was* named, but only as `$RUN_MATRIX_STAGE_DIR` near the
    # end of an 800-character single line whose first 600 characters
    # explain cgroup accounting — the part a skim or a clipped terminal
    # tail drops. A reader should be able to copy the last line and go.
    # `/var/tmp` because it is the disk-backed, world-writable, survives-
    # reboot temporary directory on most Linux (FHS), and the directory
    # must already exist — `is_dir()` below refuses one that does not —
    # hence the `mkdir -p`.
    example_dir = f"/var/tmp/{Path(problem_dir).name if problem_dir is not None else '<problem-name>'}"
    fix = (f"\nFix: mkdir -p {example_dir} && "
           f"export {STAGE_DIR_ENV}={example_dir}  "
           "(any existing, writable directory on a disk-backed filesystem "
           "works; `df -T <dir>` shows the filesystem type)")

    if not base.is_dir():
        raise MatrixError(
            f"staging directory base {base} ({source}) is not a directory. "
            f"Set ${STAGE_DIR_ENV} to a writable directory on a disk-backed "
            "filesystem." + fix
        )
    if not os.access(base, os.W_OK | os.X_OK):
        raise MatrixError(
            f"staging directory base {base} ({source}) is not writable by "
            f"this process. Set ${STAGE_DIR_ENV} to a writable directory on "
            "a disk-backed filesystem." + fix
        )

    fstype = _filesystem_type(base)
    if fstype in MEMORY_BACKED_FSTYPES:
        raise MatrixError(
            f"refusing to stage sandbox output on {base} ({source}): it is "
            f"on a {fstype} filesystem, which is memory-backed. Every byte a "
            "solution writes to stdout would be charged against its own "
            "--cg-mem limit and never reclaimed, so a correct solution that "
            "prints a large answer is OOM-killed and reported ML while using "
            "a fraction of the memory it was given (measured: 70 MB of output "
            "at a 64 MB limit reported max-rss:1668 KB, cg-oom-killed:1). "
            f"Set ${STAGE_DIR_ENV} to a directory on a disk-backed "
            "filesystem. This driver does not fall back to /tmp, and does "
            "not run with an accounting defect it can see." + fix
        )
    return base


def _isolate_binary_name() -> str:
    """The isolate executable to resolve.

    Reads `$ISOLATE_BIN` so both the test suite and a manual demonstration
    of the refuse-to-run path can point this at a nonexistent binary
    without editing source; defaults to plain "isolate" resolved off PATH.
    """
    return os.environ.get("ISOLATE_BIN", "isolate")


# isolate's own words when an id is already claimed. Matched as a substring
# because it is the only signal that separates "another invocation is using
# this box" from "this install is broken", and the two need opposite advice.
_ISOLATE_BOX_BUSY = "currently in use by another process"


def _init_box(binary: str, box_id: int) -> None:
    """`isolate --init` for one box id, raising `MatrixError` on failure.

    Two failures with opposite fixes, so they get two messages. A busy box
    means a *lease* was violated from outside this driver's own
    coordination: another user's `run_matrix` (the pool is per-user, see
    `box_pool`'s module docstring), another tool using isolate directly, or
    a sibling `run_matrix` invocation whose `$RUN_MATRIX_BOX_LOCK_DIR`
    diverges from this one's, so the two never see each other's leases at
    all. (Not `$RUN_MATRIX_BOX_POOL` sized too large on one side: the lock
    directory creates one lock file per id on demand, so no pool size can
    outrun it — disproved empirically: a `POOL=2` holder on id 0 and a
    concurrent `POOL=8` sweep of the same lock directory got `[1..7]`, never
    0.) The old code folded a busy box into the install-is-broken message
    and sent three agents chasing a cgroup misconfiguration that was never
    there.
    """
    init = subprocess.run([binary, "--cg", f"--box-id={box_id}", "--init"],
                          capture_output=True, text=True)
    if init.returncode == 0:
        return
    detail = (init.stderr or init.stdout).strip()
    if _ISOLATE_BOX_BUSY in detail:
        try:
            lock_dir_repr = str(box_pool.lock_dir())
        except box_pool.BoxPoolError:
            # Formatting a diagnosis must not itself fail with an unrelated
            # error at the worst possible moment — lock_dir() does a mkdir
            # and can raise on its own.
            lock_dir_repr = f"${box_pool.LOCK_DIR_ENV} (unresolvable right now)"
        raise MatrixError(
            f"isolate box {box_id} is already in use by another process "
            f"({detail}). This driver leases every box id through "
            f"{lock_dir_repr} before touching it, and that lease pool is "
            "per-user — so the cause is something the pool cannot see: "
            "another user running run_matrix on this machine, another "
            "tool using isolate directly, or a sibling run_matrix "
            f"invocation whose ${box_pool.LOCK_DIR_ENV} points somewhere "
            "else, so the two are not coordinating through the same lock "
            "directory. Nothing about cgroup delegation, the isolate "
            "service, or the sandbox user's uid ranges needs changing."
        )
    raise MatrixError(
        f"isolate is installed at {binary} but `--init` failed for box "
        f"{box_id} (exit {init.returncode}): {detail}\n"
        "A missing binary would have failed with a different message "
        "(see open_isolate_box); this looks instead like an "
        "installed-but-unconfigured sandbox — isolate needs cgroup v2 "
        "delegation, the isolate-cg-keeper service (isolate.service) "
        "enabled and running, and the 'isolate' system user's range "
        f"registered in /etc/subuid and /etc/subgid. See {_ISOLATE_HOME}."
    )


def _cleanup_box(binary: str, box_id: int) -> None:
    """`isolate --cleanup` for one box id; best-effort, never raises.

    Called from a `finally` around every single `--run` (Task 9c: a box is
    now this short-lived, not held for the whole invocation), so a cleanup
    failure here must not mask whatever real error or result is already
    propagating out of that call.
    """
    subprocess.run([binary, "--cg", f"--box-id={box_id}", "--cleanup"],
                    capture_output=True, text=True)


@contextlib.contextmanager
def _leased_box(**kwargs):
    """`box_pool.lease()`, translating `BoxPoolError` into `MatrixError`.

    `box_pool.BoxPoolError` is a bare `RuntimeError` — deliberately:
    `box_pool` has no dependency on this module's error type. `main()`'s
    `PACKAGE_ERRORS` boundary catch already includes `box_pool.BoxPoolError`
    itself, so an unconverted one would still exit 2, not 1 — this
    conversion is no longer what stands between a pool-exhaustion timeout,
    an unwritable lock directory, or a malformed `$RUN_MATRIX_BOX_POOL` and
    an uncaught traceback. What it still buys is the message: `MatrixError`
    naming the problem the way this driver's other refusals do, rather than
    a bare `box_pool` exception surfacing `box_pool`'s own wording to a
    reader who has never heard of that module.
    """
    try:
        with box_pool.lease(**kwargs) as box_id:
            yield box_id
    except box_pool.BoxPoolError as exc:
        raise MatrixError(str(exc)) from exc


def open_isolate_box(problem_dir: str | Path | None = None) -> IsolateHandle:
    """Verify isolate is installed and usable, then prepare this
    invocation's isolate environment.

    `problem_dir` only decides where the staging directory is created —
    next to the problem package, on the same (disk-backed) filesystem as
    the work being staged. See `_stage_base()` for why it must not be
    `/tmp` and why an unusable location raises rather than warns.

    Raises `MatrixError` — naming the fix — for three distinct failure
    families rather than letting a bare `FileNotFoundError` or
    `subprocess.CalledProcessError` (or `box_pool.BoxPoolError`) surface
    (R1: isolate's own failure modes, and the lease pool's, are as much
    "externally authored" surface as a checker's exit code is):

    1. isolate is not on PATH at all.
    2. isolate is on PATH but `--init` fails — the likely case being an
       installed-but-unconfigured sandbox (no cgroup delegation, no
       isolate-cg-keeper service, no subuid/subgid range for the `isolate`
       user) or a box id busy with another process. This is diagnosed as
       a *different* message from case 1 (and the busy sub-case from the
       unconfigured one) so a reader is not sent chasing a reinstall when
       the real problem is configuration, or chasing configuration when
       the real problem is a collision — see `_init_box`.
    3. The probe box id could not be leased at all — `box_pool` exhausted
       its pool waiting, or its lock directory could not be created or
       written. `box_pool.lease()` raises its own `BoxPoolError` for this
       (a bare `RuntimeError`, since `box_pool` has no dependency on this
       module's error type); `_leased_box()` converts it to `MatrixError`
       here for the message — naming the problem the way this driver's
       other refusals do — not to keep it from escaping `main()`: that is
       `main()`'s `PACKAGE_ERRORS` boundary catch's job, and it already
       covers a bare `box_pool.BoxPoolError` too. See `main()`'s own
       docstring and the comment on `PACKAGE_ERRORS`.

    This still does one `--init`/`--cleanup` probe cycle up front — so a
    missing/unconfigured sandbox is diagnosed here, before any compilation
    touches the tree — but does not hold that box open: Task 9c found
    isolate's cgroup counters persist across `--run`s in the same box, so
    every actual sandboxed execution (`_run_once`) now opens and tears down
    its own box instead, each leased from `box_pool` like this probe is.
    """
    # Resolved (and validated) before isolate is even probed: a staging
    # location that cannot be used is a refuse-to-run, and refusing early
    # keeps it a true no-op on the tree, exactly as the isolate probe below
    # is (see `run()`).
    stage_base = _stage_base(problem_dir)

    name = _isolate_binary_name()
    binary = shutil.which(name)
    if binary is None:
        raise MatrixError(
            f"isolate not found: {name!r} is not an executable on PATH. "
            "This pipeline runs every solution inside the ioi/isolate "
            "sandbox and does not fall back to an unsandboxed runner. "
            f"Install isolate and put it on PATH — {_ISOLATE_HOME}"
        )

    version_done = subprocess.run([binary, "--version"], capture_output=True, text=True)
    version = version_done.stdout.splitlines()[0] if version_done.stdout else "unknown"

    # A usability probe, so a missing or unconfigured sandbox is diagnosed
    # before any compilation touches the tree. It leases an id like every
    # other box: probing an id another invocation is using is the exact
    # collision this pool exists to prevent.
    with _leased_box() as probe_box_id:
        _init_box(binary, probe_box_id)
        _cleanup_box(binary, probe_box_id)

    # `meta_dir` is never bind-mounted (see IsolateHandle) — it holds one
    # meta file per run, created and removed by `_run_once` itself, and its
    # only requirement is to live somewhere a sandboxed process can never
    # reach. It does not need to be disk-backed the way `stage_root` does:
    # isolate writes it, not the sandboxed process, so nothing here is
    # charged against a solution's cgroup.
    meta_dir = Path(tempfile.mkdtemp(prefix=".run_matrix_meta_", dir=stage_base))

    # The parent of every per-run `:rw` mount (see module docstring: a real
    # repo directory must never be the write target again). Private, ours,
    # and deleted whole in `close_isolate_box` — world-writable is harmless
    # on a directory with that lifetime, and it is unrelated to box identity:
    # every box this invocation opens and closes shares this same plain host
    # tree. `dir=stage_base` is the load-bearing argument: without it
    # `mkdtemp` lands in `/tmp`, which is tmpfs, which charges a solution's
    # stdout against its own memory limit.
    stage_root = Path(tempfile.mkdtemp(prefix=".run_matrix_stage_", dir=stage_base))
    os.chmod(stage_root, 0o777)

    return IsolateHandle(binary=binary, version=version,
                         meta_dir=meta_dir, stage_root=stage_root)


def close_isolate_box(handle: IsolateHandle) -> None:
    """Best-effort teardown of this invocation's isolate environment; never
    raises.

    No box needs cleaning up here any more (Task 9c): every box `_run_once`
    opens is torn down in its own `finally` before this function is ever
    reached, so there is nothing left to leak at the box level regardless
    of how `run()` exited. Likewise, every per-run meta file and staging
    directory is already removed by `_run_once`'s own `finally` (Task 3)
    before this is ever reached in the ordinary case — this only tears
    down the two *roots* those per-run entries lived under, as a backstop
    for whatever a run's own cleanup could not remove, and, like the old
    box cleanup, must not raise and mask whatever real error or result is
    already propagating.
    """
    for path in (handle.meta_dir, handle.stage_root):
        # Either tree may still contain files the sandboxed subuid created
        # — deletable regardless of who owns them, because we own the
        # directory itself (verified: see module docstring / task report).
        # ignore_errors so a teardown problem here still cannot mask a real
        # error propagating.
        shutil.rmtree(path, ignore_errors=True)
        # ...but `ignore_errors=True` used to mean the one case that
        # survives — a foreign-owned *subdirectory* whose contents this uid
        # cannot unlink — was left on disk with the user told nothing at
        # all. It is not removable without root, so silence means someone
        # finds it weeks later and cannot explain it. Say so, on stderr,
        # naming the path; still no raise, so a teardown problem cannot
        # mask a real error propagating.
        if path.exists():
            print(f"WARNING: could not remove {path} — it holds something "
                  f"created inside the sandbox that this user cannot delete. "
                  f"Remove it as root: sudo rm -rf {path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Sandboxed execution.
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class RunResult:
    """One sandboxed execution, already classified from isolate's meta file.

    `oom` and `killed` are mutually exclusive by construction (isolate only
    ever reports one `status`), and `oom` must be checked independently of
    `status` text — a memory kill arrives as `status:SG`, the same status a
    bare segfault gets, and `cg-oom-killed` is the only field that tells
    them apart (see module docstring). `crashed` folds together isolate's
    `RE` status and a genuine non-OOM `SG` (the process died from a signal
    that was not the cgroup's doing, e.g. its own SIGSEGV/SIGABRT) into one
    "this is a runtime error, don't consult the checker" signal, mirroring
    what the old driver did with `code != 0`.

    `cpu_ms` (isolate's `time`) is the primary metric fed to `classify()`
    (judges limit CPU time, and it is far less sensitive to other load on
    this ratio-based model); `wall_ms` (`time-wall`) is carried alongside
    purely so `invocation.json` records both and is never ambiguous about
    which clock produced a reading.

    `status` (the raw meta field, `""` when absent — i.e. OK) and `message`
    (isolate's own prose, e.g. "Time limit exceeded (wall clock)") are kept
    verbatim rather than boiled down further, specifically so a *diagnostic*
    built from a `RunResult` (a crash report, a kill report) can quote
    isolate's own account of what happened instead of reconstructing it —
    review found two ways reconstructing it from `killed`/`crashed`/
    `exit_code` alone went wrong: a signal death has no `exitcode` line, so
    defaulting to 0 read as "exited 0" (looks like success); and `killed`
    alone can't tell a CPU-time kill from a wall-time kill, which matters
    for pass 1's diagnostic naming the *right* limit it tripped.

    `no_output` means the process exited without being killed and never
    created the problem's output file. Only reachable in file-IO mode — a
    stdin/stdout run always has a stdout file, because isolate creates it
    whether or not the solution writes a byte to it. It is not a crash: the
    exit status was clean, so `crashed` is False and `exit_code` is whatever
    the solution returned; it is a separate fact about the *artifact*, and
    classifying it is the caller's job, not this dataclass's.
    """

    cpu_ms: int
    wall_ms: int
    killed: bool
    oom: bool
    crashed: bool
    exit_code: int
    peak_kb: int
    status: str
    message: str
    no_output: bool = False


def _parse_meta(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        meta[key] = value
    return meta


# isolate's default without `--processes` is already a single process — but
# an *inherited* default is not the same as a *chosen* one. A judge that
# limits CPU time and memory almost always limits process/thread count too
# (most stock judges reject a std::thread solution outright), so pinning
# this to 1 explicitly makes "this driver does not sandbox multi-process
# solutions" a documented decision with a name attached, rather than
# something a reader has to know isolate's own default to discover. A
# solution that spawns a second thread now dies (pthread_create fails,
# typically an uncaught exception or abort) and is recorded as RE — a
# real behaviour change from the old posix_spawn driver, which imposed no
# such limit; flagged in the task report rather than left undisclosed.
ISOLATE_PROCESSES = 1

# The fixed name every `--run` writes its *stdout* to inside the staging
# directory, in both IO modes. Named rather than inlined because file-IO
# mode has to refuse a problem whose own `io.output` is this string: Task 1
# accepts any bare filename, so the collision is reachable, and it would put
# isolate and the solution on the same file with no error anywhere.
STAGED_STDOUT_NAME = "run.out"


def _remove_run_dir(run_dir: Path) -> None:
    """Delete one run's private staging directory.

    Called from `_run_once`'s `finally`, so a run cleans up after itself
    rather than clearing the *previous* run's litter on the way in — which
    is how the old `_clear_stage_dir` worked and why a cleanup failure used
    to be reported against an innocent run. Each `_run_once` call now gets
    its own fresh directory under `isolate.stage_root` (Task 3), so the
    contamination `_clear_stage_dir` existed to prevent — a solution's
    leftover file deciding a *later* run's verdict — is gone by
    construction: a directory created fresh for one run cannot hold another
    run's files, and nothing that runs concurrently with this one can share
    it either, because each concurrent call gets its own `mkdtemp()`.

    This process can unlink files it does not own, because unlinking is
    governed by the *directory's* permissions and this driver created the
    directory. The one case that fails is a foreign-owned *subdirectory*
    with contents, and it raises rather than being swallowed: a staging
    directory this driver cannot guarantee it emptied is one whose disk
    usage grows without bound across a matrix, and silence is how the old
    `ignore_errors=True` left users with directories they could not explain.
    Because this runs from `_run_once`'s `finally`, raising here can
    replace that call's own successful return with this `MatrixError` (or
    replace/chain onto whatever the `try` body itself raised) — the failed
    cleanup is attributed to the run that made the mess, not silently lost
    and not blamed on whichever run happens to go next.
    """
    try:
        shutil.rmtree(run_dir)
    except OSError as exc:
        raise MatrixError(
            f"could not remove the sandbox staging directory {run_dir}: "
            f"{exc} — the solution left a directory this process cannot "
            "delete. Remove it as root before running the matrix again."
        ) from exc


def _refuse_irregular_output(st: os.stat_result, source: Path, binary: Path,
                             stdin_path: Path) -> None:
    """Refuse to read the solution's output file unless it is a regular file.

    Only reachable in file-IO mode, and that is the whole point: in stdin
    mode `staged_out` is created by isolate itself, so nothing a solution
    does can decide what kind of filesystem object sits at that name. File
    IO handed the solution that choice, and `Path.read_bytes()` then does
    whatever the solution picked — as **this driver's own uid, outside the
    sandbox**, on a path the sandbox merely named. Two shapes, both measured
    rather than theorised:

    * `symlink("/etc/hostname", "t.out")` and exit 0. `read_bytes()` follows
      it and returns the host file, which is then handed to the checker as
      the solution's answer — and in pass 1 written into the jury's `.a`
      answer key. Any file readable by the user running this pipeline is in
      range; the sandbox's own confinement is irrelevant, because the read
      does not happen inside it. Hence `os.lstat` at the call site, never
      `os.stat`: following the link to discover it is a regular file is
      exactly the bug.
    * `mkfifo("t.out")` and exit 0. `read_bytes()` blocks on open forever.
      Nothing times this read out, so the whole matrix hangs — and it hangs
      *inside* the `try`, so `_run_once`'s `finally` never runs and the box
      leaks too.

    A directory is the third shape and needs no separate argument: it is
    simply not something a solution's output may be.

    This is the same family as the `PermissionError` case the branch already
    closed — solution-controlled state reaching a bare stdlib call — and it
    is refused the same way, with a `MatrixError` rather than by folding
    into `no_output`. A solution that substituted a pipe for its output is
    not a solution that produced no output, and reporting it as one would be
    a confidently wrong verdict of exactly the kind this driver exists to
    avoid.
    """
    if stat.S_ISREG(st.st_mode):
        return
    raise MatrixError(
        f"the output file {source} that {binary} produced on {stdin_path} is "
        f"not a regular file ({stat.filemode(st.st_mode)}) — a solution may "
        "not substitute a symlink, FIFO, socket, device or directory for its "
        "output. Reading one would either hand this driver's own view of the "
        "filesystem to the checker as the solution's answer, or block "
        "forever. That is not the same as producing no output at all, so it "
        "is reported rather than judged."
    )


def _run_once(isolate: IsolateHandle, binary: Path, stdin_path: Path,
              stdout_dest: Path, cpu_limit_s: float, wall_limit_s: float,
              mem_limit_kb: int, *, io_input: str = "stdin",
              io_output: str = "stdout") -> RunResult:
    """Run one process inside `isolate`'s sandbox and return its verdict.

    `binary`'s and `stdin_path`'s directories are mounted **read-only**
    (deduplicated by resolved path when they coincide, e.g. pass 2's
    binary and the checker's binary both under `.build/`) — the sandboxed
    process never needs to write anywhere inside them. The *only* `:rw`
    mount is `run_dir`, a directory this call creates fresh under
    `isolate.stage_root` (Task 3: one `mkdtemp()` per call, not once per
    `run()` invocation — see `IsolateHandle`) and removes in its own
    `finally` before returning; every `--run` writes its stdout there
    under a fixed name, and this function copies the result back to
    `stdout_dest` itself, as this (unprivileged) process, immediately
    afterward. A fresh, private directory per call is what makes this
    function safe to call from multiple threads sharing one `isolate`
    handle: two concurrent calls never see the same `:rw` mount.

    Two limits apply to that write. `--fsize=OUTPUT_LIMIT_KB` caps the
    solution's *output*; `--cg-mem` caps its cgroup, and is passed as
    `mem_limit_kb + OUTPUT_SLACK_KB`, not `mem_limit_kb`, because on cgroup
    v2 the output's dirty page cache is charged to that same cgroup until
    writeback drains it (see `OUTPUT_SLACK_KB`). The slack is what keeps
    the two limits independent on a disk-backed staging directory; on a
    memory-backed one nothing could, because tmpfs pages are never
    reclaimable, which is why `_stage_base()` refuses it. The memory limit
    itself is enforced by `_classify` from `max-rss`; a `cg-oom-killed`
    here means the solution overshot the limit by more than the slack. A
    solution that exceeds `--fsize` dies of SIGXFSZ and arrives here as
    `status:SG` with no `cg-oom-killed`, i.e. classified `crashed`/RE —
    not ML.

    This is the fix for a real bug an earlier version of this module had:
    bind-mounting a real `tests/<group>/` or `.build/` directory as the
    `:rw` target meant the sandboxed subuid — not us — created the file
    that ended up in the user's working tree, which is permanent,
    `git status`-invisible damage (both paths are gitignored) that
    `chmod -R`/`rsync -p`/`tar --same-owner` all trip over afterward. See
    the module docstring and the task report for the measured before/after.

    The copy-back always unlinks `stdout_dest` first
    (`stdout_dest.unlink(missing_ok=True)` then `write_bytes`), which needs
    only *directory* write permission — something this process already has,
    as the owner — never the target file's own permission bits. That also
    means this call self-heals a `stdout_dest` left over from the old,
    buggy behaviour (foreign-owned, possibly not writable by us at all): it
    is simply replaced, not fought with.

    `run_dir` is created empty by `mkdtemp()`, so no call can ever see
    another call's files — there is no pre-run clear to do any more, since
    a directory made fresh for this call cannot hold anything from an
    earlier or concurrent one (see `_remove_run_dir`) — and the staged
    stdout is unlinked again after the copy-back purely to keep `run_dir`
    small while `_remove_run_dir` still has to walk it in the `finally`
    below. Both rely only on `run_dir`'s own permissions, which this
    process set to 0o777 when it created it — never on the permissions of
    the files themselves, which the sandboxed subuid owns.

    **File-based IO** (`io_input`/`io_output` naming real files instead of
    the `"stdin"`/`"stdout"` sentinels; Task 1 guarantees each is either a
    sentinel or a bare filename, so neither is re-validated here). Three
    things change and nothing else does — every existing call site passes
    neither keyword and gets exactly the previous behaviour:

      * The test input is *copied* into `run_dir` under `io_input`, because
        the solution opens it by relative name and the directory it opens
        it in must be writable for `io_output`. There is still exactly one
        `:rw` mount and it is still on the same disk-backed filesystem as
        every other call's (`isolate.stage_root`, chosen by `_stage_base()`):
        a second, memory-backed writable mount for the solution's output
        would recreate — a fourth time — the accounting bug of charging a
        solution's output to its own `--cg-mem` with no way to reclaim it
        (see the module docstring's staging paragraph). Note that file-IO
        mode has *two* `--fsize`-capped files (`io_output` and the staged
        stdout), while `OUTPUT_SLACK_KB` is sized to one; a solution that
        fills both would need the flusher to keep up.
      * `--chdir` points at that staging mount rather than at the binary's,
        which is mounted read-only. A file-IO solution chdir'd into a
        read-only mount cannot create its output file at all.
      * The output is read back from `io_output` instead of from the staged
        stdout. `--stdout` still points at `STAGED_STDOUT_NAME` in both
        modes, so a file-IO solution's stray debug printing goes there, is
        discarded, and is still capped by `--fsize`; `--stdin` is pointed at
        the staged *copy* of the input, so a solution that reads stdin as
        well as its file still sees the test data.

    Two name collisions are refused with `MatrixError` rather than run,
    because both are silent: `io_output == STAGED_STDOUT_NAME` would have
    isolate and the solution writing the same file, and `io_input ==
    io_output` would have the staged *input* read back as the solution's
    answer (so a solution that writes nothing scores OK on every test).
    `problem_meta` refuses the second at load time too; this one is the
    check at the point of use.

    Permissions cut both ways here and neither direction is hypothetical.
    The staged copy of the input is re-granted the "other" read bit
    (`_ensure_sandbox_readable`) that `run()` granted the original and that
    `shutil.copyfile` drops, or a strict umask on the *driver's* side makes
    every file-IO run fail as isolate `status:XX`. In the other direction
    the solution owns its own output file and may leave it unreadable to
    us (`umask(077)`); that is surfaced as `MatrixError` naming the file
    and the solution, never as `no_output` — it is a different fact.

    `run_dir` is removed *after* this run, in the `finally` below, not
    cleared before the next one — the reverse of the old `_clear_stage_dir`.
    That direction matters: the old pre-run clear reported a cleanup
    failure against whichever run happened to go next, an entirely
    innocent bystander to the mess an *earlier* run left. A per-run
    directory, removed by the run that made it, attributes that failure
    correctly — see `_remove_run_dir`. It also stops being merely a
    tidiness concern once two calls can share one `isolate` handle at once
    (`_time_median` still calls this three times, but no longer onto one
    shared directory): a pre-run clear of a directory another thread might
    already be using inside its own `--run` would be a second,
    timing-dependent way to corrupt a verdict.

    `_remove_run_dir` removes the whole tree rather than unlinking the
    three names this driver itself knows (`run.out`, `io_input`,
    `io_output`) because the Task 6 dogfood proved three names are not
    enough. A solution that writes *any other* filename — the
    wrong-output-filename mistake this whole feature exists to diagnose
    writes `output.txt` — used to leave that file behind owned by the
    mapped subuid of the box it ran in; every box gets a *fresh* box id,
    hence a different subuid (Task 9c), so a later run sharing that
    directory could not even `fopen(..., "w")` it: EACCES, nonzero exit,
    reported RE. Measured on the dogfood package, back when every call in
    a `run()` shared one staging directory: the wrong-filename solution
    came back `NO_OUTPUT` on the first test it ran and `RE` on the eleven
    after it — a verdict that depended on execution order, and worse, one
    solution's leftover file silently changing a *different* solution's
    verdict. A directory created fresh per call and removed by that same
    call (Task 3) makes the whole class unreachable rather than merely
    cleaned up: there is no later run that could ever see it.

    A file-IO run whose output file is absent afterwards returns
    `no_output=True` (and an empty `stdout_dest`, rewritten like any other
    run so a stale answer already in the repository cannot be read as this
    run's). It is reported, not classified, here.

    Task 9c: every call gets its **own, freshly-`--init`ed box** — one is
    leased from `box_pool`, `--init`ed before the sandboxed execution, and
    `--cleanup`ed in a `finally` regardless of how this function returns or
    raises; the lease wraps the whole cycle so no other invocation's
    `--init`/`--cleanup` can land on this box id while it's ours. isolate's
    cgroup counters (`cg-mem`,
    `cg-oom-killed`) persist across `--run`s in the same box — verified
    with bare isolate, no involvement from this module (see module
    docstring for the precise before/after values). Of the two, only
    `cg-oom-killed` reached this driver's output: reusing a box let one
    solution's OOM stick as `oom=True` for every later, memory-innocent
    run in the same box, which is a corrupted *verdict* (ML silently
    overwrote a correct one, since ML outranks WA), not a corrupted
    number — `peak_kb` is read from `max-rss` below, never from `cg-mem`,
    and `max-rss` was independently verified to reset correctly per
    process regardless of box reuse. Still the same class of defect this
    sandbox migration was meant to eliminate (memory-adjacent accounting
    contaminated by something other than the process being measured); a
    box that lives only from just before this one `--run` to just after it
    can never observe another call's counters, on any field.

    Task 3: `run_dir` and `meta_path` are private to *this call*, not to
    the `run()` invocation — see `IsolateHandle` for why a single shared
    meta file and staging directory made two concurrent calls unsafe. The
    `finally` below always attempts to remove `run_dir` via
    `_remove_run_dir`; if that raises `MatrixError` (a solution left a
    foreign-owned subdirectory this process cannot delete — `validating-
    solutions` runs hostile code on purpose, and `mkdir(dir, 0700)` is an
    expected input class from that, not an infrastructure fault), the
    `finally` catches it and warns on stderr instead of letting it
    propagate. It does **not** discard this call's own `RunResult` (a human
    ruling reversing an earlier version of this docstring — see the task
    report): the identical fact is only a one-line warning when
    `close_isolate_box` meets it at the end of the whole invocation, and
    nothing about a leftover directory makes any field of the `RunResult`
    already computed above suspect — the meta file was private to this
    run, already read and parsed, and the output already copied back to
    `stdout_dest`. Per-run directories mean the litter cannot contaminate a
    *later* verdict by construction (unlike the pre-Task-3 shared staging
    directory), so the only remaining cost of leaving it for the warning to
    name is disk, not correctness.
    """
    with _leased_box() as box_id:
        # Created before `_init_box`, not after: if `mkdtemp`/`chmod` here
        # raised *after* `_init_box`, the leased box would never be
        # `--cleanup`ed (nothing else sweeps a box id once it's ours) and
        # would leak until the pool wraps around to it. An empty `run_dir`
        # created before the box is touched is instead swept for free by
        # `close_isolate_box`'s `rmtree(stage_root)` if this call never gets
        # any further — the same "leave nothing behind on an early failure"
        # property the box lease itself gives every path below.
        run_dir = Path(tempfile.mkdtemp(prefix="run_", dir=isolate.stage_root))
        os.chmod(run_dir, 0o777)
        meta_path = isolate.meta_dir / f"meta_{box_id}_{run_dir.name}"
        _init_box(isolate.binary, box_id)
        try:
            mounts: dict[Path, str] = {}

            def _label(path: Path) -> str:
                resolved = path.resolve()
                if resolved not in mounts:
                    mounts[resolved] = f"/host{len(mounts)}"
                return mounts[resolved]

            file_io = io_input != "stdin" or io_output != "stdout"

            bin_label = _label(binary.parent)
            # The test directory is mounted ONLY in stdin mode, where `--stdin`
            # has to name a path inside the box. In file-IO mode `--stdin` points
            # at the staged copy (`{stage_label}/{staged_in.name}`) and this
            # mount is referenced nowhere — dead weight that also handed the
            # solution a readable `01.a` next to every `01.in`, i.e. the jury's
            # answers. That exposure is not new (stdin mode has always mounted
            # this directory, and still must), but in file-IO mode nothing is
            # bought by it, so it goes.
            stdin_label = _label(stdin_path.parent) if not file_io else None
            stage_label = _label(run_dir)
            run_dir_resolved = run_dir.resolve()

            if file_io and io_input == io_output:
                # `problem_meta` refuses this at load time; this is the same
                # check at the point of use, because `_run_once` is also called
                # directly (tests, and anything that builds its own arguments)
                # and the consequence is silent: the solution's output file is
                # the staged *input* file, so a solution that writes nothing
                # hands the test data back as its answer and the checker
                # accepts it.
                raise MatrixError(
                    f"io.input and io.output are both {io_input!r}: the "
                    "solution's output file would be the file it read the test "
                    "from, so a solution that wrote nothing would have the test "
                    "input itself checked as its answer. Give them different "
                    "names."
                )
            if file_io and (io_input == STAGED_STDOUT_NAME
                            or io_output == STAGED_STDOUT_NAME):
                raise MatrixError(
                    f"io.input/io.output may not be named {STAGED_STDOUT_NAME!r}: "
                    "that is the fixed name this driver stages the sandboxed "
                    "process's stdout under, so isolate and the solution would "
                    "write the same file (io.input="
                    f"{io_input!r}, io.output={io_output!r}) — rename the "
                    "problem's IO files."
                )

            # `run_dir` is a fresh `mkdtemp()` (see above) — empty by
            # construction, so there is nothing left behind by an earlier or
            # concurrent run to clear here. See `_remove_run_dir` and the
            # docstring above for why removal moved to this call's own
            # `finally` instead.
            staged_out = run_dir / STAGED_STDOUT_NAME

            # In file-IO mode the solution reads and writes real files in its
            # cwd, which must be the ONE `:rw` mount.
            staged_in = staged_result = None
            if file_io:
                staged_in = run_dir / io_input
                staged_result = run_dir / io_output
                shutil.copyfile(stdin_path, staged_in)
                # `run()` already granted the original test file the "other"
                # read bit the mapped subuid needs (`_ensure_sandbox_readable`);
                # the copy is created fresh at `0666 & ~umask` and would throw
                # that away. Under a strict umask (077) the sandbox then cannot
                # open its own input, and it surfaces as isolate's status:XX —
                # i.e. as this driver blaming isolate for a permission bit it
                # set itself. Re-grant it on the copy.
                _ensure_sandbox_readable(staged_in)

            cmd = [
                isolate.binary, "--cg", f"--box-id={box_id}", "--run",
                f"--meta={meta_path}", f"--processes={ISOLATE_PROCESSES}",
                f"--time={cpu_limit_s:.3f}", f"--wall-time={wall_limit_s:.3f}",
                f"--cg-mem={mem_limit_kb + OUTPUT_SLACK_KB}",
                f"--fsize={OUTPUT_LIMIT_KB}",
            ]
            for resolved, label in mounts.items():
                opt = ":rw" if resolved == run_dir_resolved else ""
                cmd.append(f"--dir={label}={resolved}{opt}")
            cmd += [
                f"--chdir={stage_label if file_io else bin_label}",
                (f"--stdin={stage_label}/{staged_in.name}" if file_io
                 else f"--stdin={stdin_label}/{stdin_path.name}"),
                f"--stdout={stage_label}/{staged_out.name}",
                "--", f"{bin_label}/{binary.name}",
            ]

            subprocess.run(cmd, capture_output=True, text=True)
            # isolate's own process exit code is not the contract here — 0 means
            # OK but 1 covers TO/SG/RE alike, so it cannot distinguish them. The
            # meta file is the actual contract (verified against this exact
            # isolate build; see the module docstring and the task report for
            # pasted output from all four cases).
            try:
                meta_text = meta_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise MatrixError(
                    f"isolate produced no readable meta file for {binary} on "
                    f"{stdin_path}: {exc}"
                ) from exc
            if not meta_text.strip():
                raise MatrixError(
                    f"isolate produced an empty meta file for {binary} on "
                    f"{stdin_path} — the sandboxed run did not report any outcome"
                )
            meta = _parse_meta(meta_text)

            status = meta.get("status", "")  # absent -> OK; see module docstring trap 1
            if status == "XX":
                raise MatrixError(
                    f"isolate reported an internal error (status XX) running "
                    f"{binary} on {stdin_path}: {meta.get('message', '(no message)')} "
                    "— this is isolate's own failure, not a verdict on the solution."
                )

            oom = meta.get("cg-oom-killed") == "1"  # must be tested before treating
            killed = status == "TO"                 # SG as a plain crash (trap 2)
            crashed = (not oom) and status in ("RE", "SG")
            message = meta.get("message", "")

            try:
                cpu_ms = int(round(float(meta.get("time", "0")) * 1000))
                wall_ms = int(round(float(meta.get("time-wall", "0")) * 1000))
                peak_kb = int(meta.get("max-rss", "0"))
                exit_code = int(meta.get("exitcode", "0"))
            except ValueError as exc:
                raise MatrixError(
                    f"isolate meta file malformed for {binary} on {stdin_path}: "
                    f"{meta!r} ({exc})"
                ) from exc

            # Copy the sandboxed output back into the repository as *this*
            # process — never write it through a bind mount again (see
            # docstring above).
            source = staged_result if file_io else staged_out
            try:
                # `lstat`, never `stat`: this asks what the *solution* left at
                # that name, and following a symlink is precisely the thing being
                # refused two branches down.
                source_st = os.lstat(source)
            except FileNotFoundError:
                # In file-IO mode this is the reportable outcome `no_output`; in
                # stdin mode isolate always created the file, so an absent one
                # is not a fact about the solution and stays unreported.
                data, no_output = b"", file_io
            else:
                _refuse_irregular_output(source_st, source, binary, stdin_path)
                try:
                    data, no_output = source.read_bytes(), False
                except OSError as exc:
                    # The file exists but this process cannot read it — reachable
                    # in file-IO mode because the *solution* owns that file: a
                    # `umask(077)` in the solution leaves it `-rw-------` under
                    # the sandbox's subuid, which is neither our uid nor our
                    # group, and we own only the directory, so we cannot even
                    # chmod it. Left bare this escaped `_run_once` as
                    # `PermissionError` and took the whole matrix down mid-run on
                    # one careless solution. Deliberately NOT folded into
                    # `no_output`: "we could not read it" and "it was never
                    # written" are different facts about the solution, and
                    # conflating them is how this project has produced wrong
                    # verdicts before.
                    raise MatrixError(
                        f"could not read the output file {source} that {binary} "
                        f"produced on {stdin_path}: {exc} — the file exists but is "
                        "not readable by this process (a solution that restricts "
                        "its own output's permissions, e.g. umask(077), does this). "
                        "That is not the same as producing no output at all, so it "
                        "is reported rather than judged."
                    ) from exc
            stdout_dest.unlink(missing_ok=True)
            stdout_dest.write_bytes(data)
            staged_out.unlink(missing_ok=True)

            return RunResult(cpu_ms=cpu_ms, wall_ms=wall_ms, killed=killed, oom=oom,
                              crashed=crashed, exit_code=exit_code, peak_kb=peak_kb,
                              status=status, message=message, no_output=no_output)
        finally:
            with contextlib.suppress(OSError):
                meta_path.unlink(missing_ok=True)
            _cleanup_box(isolate.binary, box_id)
            try:
                _remove_run_dir(run_dir)
            except MatrixError as exc:
                # Warn, don't abort (human ruling, reversing the brief's
                # original "raise from this call's own finally" design —
                # see the docstring above). The identical fact — a
                # foreign-owned subdirectory this uid cannot remove — was
                # already a one-line stderr warning at the whole-invocation
                # level (`close_isolate_box`); treating it as a
                # whole-matrix-aborting MatrixError here, minutes earlier,
                # for the exact same fact was two responses to one
                # condition. The RunResult already computed above is not
                # in doubt: its meta file was private to this run, written,
                # read, and parsed, and its output was already copied back
                # to `stdout_dest` before this `finally` ever runs — the
                # leftover directory says nothing about any of that.
                print(
                    f"WARNING: {exc} — this happened while running "
                    f"{binary} on {stdin_path}; that run's own verdict is "
                    "unaffected and is still being reported. Remove it as "
                    f"root: sudo rm -rf {run_dir}", file=sys.stderr)


def _time_median(isolate: IsolateHandle, binary: Path, stdin_path: Path,
                  stdout_dest: Path, cpu_limit_s: float, wall_limit_s: float,
                  mem_limit_kb: int, runs: int, *, io_input: str = "stdin",
                  io_output: str = "stdout") -> RunResult:
    """Median the CPU/wall time over `runs` runs; any bad outcome wins.

    `killed`/`oom`/`crashed`/`no_output` are all sticky-OR (never cleared
    once True) and `exit_code`/`status`/`message` are sticky-first-nonempty
    — mirroring the old driver's reasoning for the model solution
    specifically: a run that fails once and happens to succeed on a later
    retry must not have that failure silently overwritten, or a flaky answer
    file could pass as jury truth, and the diagnostic for that failure must
    survive to be reported even though it happened on an earlier iteration
    than the last one.

    `no_output` joined that list when `run()` started passing real IO
    filenames down here: dropping it was unreachable while every call was
    stdin/stdout (isolate always creates a stdout file), and became live the
    moment file-IO problems reached this function. It is sticky in both
    directions that matter — a first run that wrote nothing must not be
    erased by two later runs that did, and the flag must actually reach the
    returned `RunResult`, or `_classify` never sees it and the whole
    NO_OUTPUT verdict silently disappears on any re-timed (banded) run and
    on the model solution's entire pass 1.

    `io_input`/`io_output` are forwarded verbatim to `_run_once`, which owns
    every file-IO behaviour and every refusal; nothing is interpreted here.
    """
    cpu_samples, wall_samples = [], []
    killed = oom = crashed = no_output = False
    exit_code = 0
    status = message = ""
    peak = 0
    for _ in range(runs):
        r = _run_once(isolate, binary, stdin_path, stdout_dest,
                      cpu_limit_s, wall_limit_s, mem_limit_kb,
                      io_input=io_input, io_output=io_output)
        cpu_samples.append(r.cpu_ms)
        wall_samples.append(r.wall_ms)
        killed = killed or r.killed
        oom = oom or r.oom
        crashed = crashed or r.crashed
        no_output = no_output or r.no_output
        exit_code = exit_code or r.exit_code
        status = status or r.status
        message = message or r.message
        peak = max(peak, r.peak_kb)
    return RunResult(
        cpu_ms=int(statistics.median(cpu_samples)),
        wall_ms=int(statistics.median(wall_samples)),
        killed=killed, oom=oom, crashed=crashed,
        exit_code=exit_code, peak_kb=peak,
        status=status, message=message, no_output=no_output,
    )


def _check(checker: Path, test_in: Path, out: Path, ans: Path,
           *, timeout_s: float = CHECKER_TIMEOUT_S) -> str:
    try:
        done = subprocess.run([str(checker), str(test_in), str(out), str(ans)],
                              capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        print(f"WARNING: checker {checker} did not finish within {timeout_s}s "
              f"on test {test_in} — reporting FAIL", file=sys.stderr)
        return "FAIL"
    return CHECKER_EXIT.get(done.returncode, "FAIL")


def _git_rev(path: str | Path) -> str | None:
    """The git revision checked out at `path`, or None if it isn't a checkout.

    Used to pin the testlib revision into `invocation.json`: the checker is
    compiled against `$TESTLIB/testlib.h` and `bootstrap_testlib.sh` pulls
    on every invocation, so an artifact that records only "isolate 2.6" is
    not enough to reproduce the run that produced it.
    """
    try:
        done = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 and done.stdout.strip() else None


def _tests_by_group(problem_dir: Path, problem: Problem) -> dict[str, list[Path]]:
    """Resolve every subtask's test files, failing loudly on a bad fixture.

    A missing tests/<group>/ directory or an empty one is a package defect,
    not "zero tests to run" — `Path.glob` on a nonexistent directory just
    yields nothing, so left unchecked this would silently produce an empty
    group and only fail much later inside `group_verdict`, far from the
    directory that is actually missing.
    """
    result: dict[str, list[Path]] = {}
    for sub in problem.subtasks:
        group_dir = problem_dir / "tests" / sub.id
        if not group_dir.is_dir():
            raise MatrixError(f"missing tests directory: {group_dir}")
        paths = sorted(group_dir.glob("*.in"))
        if not paths:
            raise MatrixError(f"no .in tests found in {group_dir}")
        result[sub.id] = paths
    return result


def _ensure_sandbox_readable(path: Path) -> None:
    """Grant "other" read access to a file the sandbox must open.

    The sandboxed process runs as a mapped subuid that is neither our uid
    nor our group (isolate 2.x's bind-mount model — see module docstring),
    so anything it must read needs the "other" bits regardless of the
    umask a real problem package happened to be created under. This
    matters beyond the checked-in fixture (which already satisfies it by
    luck of the default 022 umask): a stricter umask must not turn into a
    silent, spurious sandbox permission failure. Never grants write — every
    directory this driver hands to the sandbox is now read-only (see
    `_ensure_dir_traversable` and the module docstring); the only `:rw`
    mount is the private staging directory in `IsolateHandle`.
    """
    os.chmod(path, path.stat().st_mode | 0o004)


def _ensure_sandbox_executable(path: Path) -> None:
    """Grant "other" read+execute on a compiled binary the sandbox must run.

    Defensive, for the same reason as `_ensure_sandbox_readable`: a
    stricter umask than this machine's could otherwise produce a binary
    without the "other" bits g++'s default output happens to carry, and
    that must be a granted permission, not a silent, spurious exec failure.
    """
    os.chmod(path, path.stat().st_mode | 0o005)


def _ensure_dir_traversable(path: Path) -> None:
    """Grant "other" traverse (search) access to a directory the sandbox
    reads through — and, just as importantly, strip any stray "other"
    write bit already sitting on it.

    Every directory this driver bind-mounts is read-only now (see the
    module docstring): the sandboxed subuid only ever needs to look up a
    file by exact name inside it (`os.execve`/`open` by path), which is
    what the directory's own *execute* bit controls on Linux — not its
    read bit (that only gates directory *listing*, e.g. `ls`), and
    certainly not its write bit, which this driver never has a reason to
    grant to a real repository directory again.

    The `& ~stat.S_IWOTH` half of this is a deliberate self-heal, not just
    a guard: an earlier version of this module *did* grant that bit (to
    bind-mount `tests/<group>/` and `.build/` read-write, so the sandboxed
    process could write its own stdout there) and never restored it,
    leaving real problem directories at `o+w` permanently. Every `run()`
    from here on strips that bit back off its own accord, so a problem
    directory that was damaged by the old behaviour heals the next time
    this tool touches it — no separate migration step required.
    """
    mode = path.stat().st_mode
    healed = (mode | stat.S_IXOTH) & ~stat.S_IWOTH
    if healed != mode:
        path.chmod(healed)


def _classify(r: RunResult, checker: Path, test: Path, out: Path, ans: Path,
              limits: Limits, mem_limit_kb: int) -> Outcome:
    """Turn one sandboxed execution into an `Outcome`.

    Memory is decided first and from two signals, either of which is ML:
    `cg-oom-killed` (the kernel killed the cgroup at its cap, which is
    `mem_limit_kb + OUTPUT_SLACK_KB` — see `_run_once`) or `peak_kb`, the
    sandbox's own `max-rss` of the child, strictly greater than
    `mem_limit_kb`. The second is the ordinary path: the cap carries slack
    for the output's dirty page cache, so a solution that overshoots the
    limit by less than the slack finishes rather than being killed, and
    only `max-rss` shows it. `max-rss` is isolate's reading of the child's
    resident peak (never this driver's own memory, and never the box's
    cumulative `cg-mem` — see the module docstring), and it does not
    include page cache, so output never inflates it. Exactly at the limit
    is accepted, mirroring the time rule. An ML run short-circuits to
    `Outcome("ML", ...)` without consulting `classify()` or the checker,
    and takes precedence over a kill or a crash exactly as the OOM-only
    check always did. A killed (TL) or crashed (RE) run likewise skips
    the checker: "a judge stops a solution at the limit, so the checker
    never runs on one that exceeded it" is already `classify()`'s own
    stated doctrine for the TL case, and it applies just as much to a run
    that never produced valid output to check at all.

    `no_output` (file-IO mode only: the process exited cleanly and never
    created the problem's output file, typically because it wrote the wrong
    filename) becomes the verdict `NO_OUTPUT`, and is checked *after*
    `killed` and `crashed`, never before: a solution that segfaulted is RE,
    and one that was stopped at the limit is TL — both would also leave no
    output file, and reporting either as NO_OUTPUT would name the symptom
    instead of the cause. Only a run that finished cleanly and still wrote
    nothing is NO_OUTPUT. It is fed through `classify()` as a checker
    verdict rather than returned directly, because `classify()` decides time
    before correctness (`matrix_core`): a run that overran the limit without
    being killed is TL, not NO_OUTPUT. The checker is never invoked on this
    path, so it is never handed a nonexistent file.
    """
    if r.oom or r.peak_kb > mem_limit_kb:
        return Outcome("ML", banded=False)
    if r.killed:
        verdict_src = ""  # unused: classify() returns TL before consulting it
    elif r.crashed:
        verdict_src = "RE"
    elif r.no_output:
        verdict_src = "NO_OUTPUT"
    else:
        verdict_src = _check(checker, test, out, ans)
    return classify(r.cpu_ms, r.killed, verdict_src, limits)


def _is_wall_clock_kill(message: str) -> bool:
    """True when a `status:TO` kill was isolate's wall-clock ceiling, not
    its CPU one.

    isolate's own `status:TO` fires for either kill; only the message text
    ("Time limit exceeded (wall clock)" vs plain "Time limit exceeded")
    tells them apart (verified against a real `sleep()`-bound run). Pass 1
    (`run()`) and pass 2 (`_run_pass2`) both need this distinction, so it
    lives in exactly one place rather than being reimplemented at each call
    site.
    """
    return "wall clock" in message.lower()


def _run_pass2(isolate: IsolateHandle, problem: Problem, problem_dir: Path,
               manifest: dict, binaries: dict[str, Path], checker: Path,
               tests: dict[str, list[Path]], limits: Limits,
               mem_limit_kb: int, runs: int, workers: int
               ) -> tuple[list[dict], dict[str, dict[str, str]]]:
    """Run every solution on every test, on `workers` sandboxes at once.

    Only pass 2 is parallel. Pass 1 stays serial in `run()` because it
    measures `t_main`, from which `compute_limits` derives TL: timing the
    model solution under contention inflates TL, and an inflated TL lets
    genuinely-too-slow solutions pass, which manufactures holes — the one
    claim this pipeline makes that has to be true. Pass 1 is also a small
    share of the wall clock relative to pass 2 (the plan's own analysis put
    it at 1-6% across the packages it measured — not re-verified by this
    task; this task's own measurement is `goldenseed`: 182.4s serial to
    65.4s at 4 workers, 2.79x), so serialising it costs almost nothing.

    Two phases. The first fans out; the second re-times, **serially and with
    every one of this process's own workers idle** (this process's thread
    pool has shut down by then — but the box-id lease is a cross-process
    pool, so a sibling `run_matrix` invocation can still be holding boxes
    and driving CPU contention elsewhere on the machine while this re-time
    runs; "every worker idle" is a fact about this invocation, not a
    guarantee about the machine, and the re-timed value is never fed back
    through `needs_serial_retime` to check whether it is still ambiguous —
    an open design question, deliberately deferred rather than patched:
    see `docs/superpowers/specs/2026-08-09-retime-quiescence.md` for why
    the obvious fix deadlocks and what any real one must preserve), only
    those results that are undecidable
    under contention: `needs_serial_retime` calls a CPU-time measurement
    undecidable when it lands close enough to TL that contention could have
    decided it (that set is tiny in practice — the plan's own analysis put
    it at 18 of 5508 results across the packages it measured, not
    re-verified by this task; `goldenseed` alone saw 1 of 546 — because
    contention is one-sided and a kernel *CPU*-time kill therefore still
    implies a genuine TL, see `matrix_core.needs_serial_retime`), and this
    function additionally re-times any **wall-clock** kill whenever more
    than one worker is live (the `workers > 1` gate below — at `workers ==
    1` there is no contention to begin with, so nothing needs correcting),
    because `needs_serial_retime`'s CPU-time bound (`CONTENTION_BOUND`)
    says nothing about wall time: a descheduled process accrues wall time
    without accruing CPU time, so a solution that genuinely finishes under
    TL can still be wall-killed under contention, and left unflagged that
    is a `TL` verdict matching an `@expect TL` declaration — a real hole,
    silently masked. A CPU-time kill keeps `needs_serial_retime`'s existing
    short-circuit (never ambiguous); only the wall-clock case is treated
    differently, and it is why `_is_wall_clock_kill` mirrors pass 1's own
    kill-kind check exactly rather than reimplementing it.

    Threads, not processes: every unit of work is a `subprocess.run` on
    isolate, which releases the GIL, and the workers share one
    `IsolateHandle`. Each `_run_once` leases its own box id and creates its
    own staging directory, so no state is shared between them; the shared
    handle carries only the two roots those live under.

    A `MatrixError` raised in any worker propagates out of iterating
    `pool.map`'s results; un-started work is cancelled and in-flight runs
    complete, so the abort costs at most one round of `workers` runs. That
    is deliberate: every `MatrixError` in this driver means "this run
    cannot be judged", and turning one into a verdict is precisely the
    confidently-wrong outcome the whole module refuses. A `flags.FlagError`
    from `flags.append` below (a corrupted `flags.json` read back before a
    retimed/banded result is recorded) takes the identical path.
    """
    cpu_limit_s = limits.kill_ms / 1000.0
    wall_limit_s = max(3 * limits.tl_ms, limits.kill_ms) / 1000.0
    build = problem_dir / ".build"
    work = [(entry["file"], group, test)
            for entry in manifest["solutions"]
            for group, paths in tests.items()
            for test in paths]

    def one(item):
        name, group, test = item
        out = build / f"{Path(name).stem}.{group}.{test.stem}.out"
        r = _run_once(isolate, binaries[name], test, out,
                      cpu_limit_s, wall_limit_s, mem_limit_kb,
                      io_input=problem.input, io_output=problem.output)
        return item, out, r

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        measured = list(pool.map(one, work))

    results, actual = [], {}
    for (name, group, test), out, r in measured:
        answer = test.with_suffix(".a")
        # `needs_serial_retime` short-circuits to False whenever `killed` is
        # true, and its justification (`kill_ms / bound > tl_ms`) is about
        # CPU time — `CONTENTION_BOUND` bounds CPU-time inflation, not
        # wall-time inflation. A wall-clock kill is a different failure mode
        # entirely: a descheduled process accrues wall time without
        # accruing CPU time, so nothing bounds how far contention can push
        # a genuinely-fast solution's wall clock past its wall ceiling. Left
        # unchecked, a solution declared TL that actually finishes under TL
        # gets wall-killed, `expected == actual`, and a real hole is masked
        # — the one non-circular claim this pipeline makes. So a wall kill
        # gets its own re-time here, alongside (not instead of)
        # `needs_serial_retime`'s CPU-time case; a CPU kill keeps the
        # existing short-circuit (it is never ambiguous — see
        # `matrix_core.needs_serial_retime`).
        wall_killed = r.killed and _is_wall_clock_kill(r.message)
        retimed = workers > 1 and (
            needs_serial_retime(r.cpu_ms, r.killed, limits) or wall_killed)
        if retimed:
            first_run_ms = r.cpu_ms
            # For a CPU-time kill the number that explains it is `cpu_ms`
            # (captured above as `first_run_ms`); for a wall-clock kill the
            # number that explains it is the *wall* reading, which
            # `first_run_ms` never carries. Captured here, before
            # `_time_median` reassigns `r` below, so the wall-kill flag can
            # embed its original reading the same way the near-TL flag
            # below embeds `first_run_ms`.
            first_wall_ms = r.wall_ms
            r = _time_median(isolate, binaries[name], test, out,
                             cpu_limit_s, wall_limit_s, mem_limit_kb, runs,
                             io_input=problem.input, io_output=problem.output)
            if wall_killed:
                flags.append(
                    problem_dir, phase="validate-solutions", severity="low",
                    kind="timing-band",
                    what=f"{name} on {group}/{test.stem} was killed by "
                         f"isolate's wall-clock ceiling at {first_wall_ms} ms "
                         f"wall time with {workers} sandboxes running — a "
                         "wall-clock kill is not bounded by the contention "
                         "model (CONTENTION_BOUND covers CPU-time inflation "
                         "only; a descheduled process accrues wall time "
                         "without accruing CPU time), so it cannot be "
                         "trusted as a genuine TL under contention",
                    assumed=f"re-timed {runs}x serially with every one of "
                            f"this process's own workers idle (a sibling "
                            f"run_matrix invocation could still have been "
                            f"running); the median came out {r.cpu_ms} ms "
                            f"CPU time, {r.wall_ms} ms wall time",
                    changes_if_wrong=f"the expected tag of {name}")
            else:
                flags.append(
                    problem_dir, phase="validate-solutions", severity="low",
                    kind="timing-band",
                    what=f"{name} on {group}/{test.stem} measured {first_run_ms} ms "
                         f"CPU time with {workers} sandboxes running, close enough "
                         f"to TL {limits.tl_ms} that contention could have decided it",
                    assumed=f"re-timed {runs}x serially with every one of "
                            f"this process's own workers idle (a sibling "
                            f"run_matrix invocation could still have been "
                            f"running); the median came out {r.cpu_ms} ms",
                    changes_if_wrong=f"the expected tag of {name}")
        outcome = _classify(r, checker, test, out, answer, limits, mem_limit_kb)
        if outcome.banded:
            first_run_ms = r.cpu_ms
            r = _time_median(isolate, binaries[name], test, out,
                             cpu_limit_s, wall_limit_s, mem_limit_kb, runs,
                             io_input=problem.input, io_output=problem.output)
            outcome = _classify(r, checker, test, out, answer, limits, mem_limit_kb)
            flags.append(
                problem_dir, phase="validate-solutions", severity="medium",
                kind="timing-band",
                what=f"{name} on {group}/{test.stem} ran {first_run_ms} ms CPU "
                     f"time, between TL {limits.tl_ms} and kill {limits.kill_ms} "
                     f"({workers} worker(s))",
                assumed=f"re-timed {runs}x for stability; the median came out "
                        f"{r.cpu_ms} ms, and the recorded verdict is "
                        f"{outcome.verdict} — there is no separate 'banded' "
                        "verdict, only ever a real one (TL if still over the "
                        "limit, otherwise whatever the checker returned)",
                changes_if_wrong=f"the expected tag of {name}")
        actual.setdefault(name, {}).setdefault(group, []).append(outcome.verdict)
        results.append({
            "solution": name, "group": group, "test": test.stem,
            "verdict": outcome.verdict,
            "time_ms": r.cpu_ms, "wall_ms": r.wall_ms,
            "ratio": round(r.cpu_ms / max(limits.t_main_ms, 1), 2),
            "peak_kb": r.peak_kb, "killed": r.killed, "oom": r.oom,
            "banded": outcome.banded, "retimed_serially": retimed,
        })
    collapsed = {name: {group: group_verdict(v) for group, v in groups.items()}
                 for name, groups in actual.items()}
    return results, collapsed


def run(problem_dir: str | Path, testlib_dir: str | Path, runs: int = 3) -> dict:
    problem_dir, testlib_dir = Path(problem_dir), Path(testlib_dir)
    problem = load(problem_dir / "problem.json")
    # Both IO modes run through the same code from here on. `problem.input`
    # and `problem.output` are either the sentinels "stdin"/"stdout" or bare
    # filenames — `problem_meta.load` validated that, refused a path
    # separator or a dot-segment, and refused input == output, so nothing is
    # re-validated here. They are threaded, unchanged, into every sandboxed
    # execution below; `_run_once` owns what they mean and owns the two
    # remaining refusals (a name colliding with the staged stdout, and the
    # same check on input == output for callers that build their own
    # arguments).
    # Task 9b review, aggravating detail: an earlier version of this
    # function only discovered whether isolate was even usable *after*
    # already compiling every solution and touching the tree — so a
    # refuse-to-run (isolate missing or unconfigured) still left `.build/`
    # and its binaries behind, on a path that was never going to reach the
    # sandbox at all. Opening the box first means a refusal here is a true
    # no-op on the tree: nothing is compiled, nothing is chmod'd, nothing
    # is created. (`--init`/`--cleanup` themselves only touch
    # `/var/local/lib/isolate/`, never this problem's directory.)
    isolate = open_isolate_box(problem_dir)
    try:
        manifest = scan(problem_dir, problem)

        build = problem_dir / ".build"
        build.mkdir(exist_ok=True)
        # Read-only from the sandbox's perspective — it only ever needs to
        # look up and exec a binary here by name, never write.
        # `_ensure_dir_traversable` also self-heals a `.build/` left `o+w`
        # by an earlier version of this module that bind-mounted it
        # read-write (see module docstring); this driver never grants that
        # bit to a real repo directory again.
        _ensure_dir_traversable(build)

        if problem.checker_kind == "stock":
            checker_src = testlib_dir / "checkers" / f"{problem.checker_name}.cpp"
        else:
            checker_src = problem_dir / "files" / problem.checker_name
        checker = build / "checker"
        _compile(checker_src, checker, ["-Wpedantic", "-Werror", f"-I{testlib_dir}"],
                 context=f"checker ({problem.checker_name})")
        # The checker itself is never sandboxed (`_check` runs it directly,
        # as this process) — no permission grant needed. The reason is that
        # a checker is *jury-authored* code, not a submission: it is part of
        # the package the setter is building, it must read the test input
        # and the jury's own answer file, and nothing about it is under a
        # contestant's control. The sandbox exists to contain untrusted,
        # possibly-adversarial submissions and to *measure* them; a checker
        # is neither untrusted nor measured. It is still bounded in time by
        # CHECKER_TIMEOUT_S, which is the one failure mode a jury-authored
        # checker realistically has (an infinite loop in a hand-written one).

        binaries = {}
        for entry in manifest["solutions"]:
            binary = build / Path(entry["file"]).stem
            _compile(problem_dir / "solutions" / entry["file"], binary,
                      context=f"solution {entry['file']}")
            _ensure_sandbox_executable(binary)
            binaries[entry["file"]] = binary

        main_file = next(e["file"] for e in manifest["solutions"] if e["tag"] == "main")
        tests = _tests_by_group(problem_dir, problem)
        for paths in tests.values():
            # Read-only for the same reason as `.build/` above: pass 1's
            # regenerated `.a` answer file is no longer written through
            # this bind mount (see `_run_once` and the module docstring) —
            # it is copied back by this process afterward, so the
            # directory itself never needs an `o+w` bit, and this call
            # self-heals one left by the earlier, buggy version of this
            # module.
            _ensure_dir_traversable(paths[0].parent)
            for test in paths:
                _ensure_sandbox_readable(test)

        mem_limit_kb = problem.memory_mb * 1024

        # Pass 1 — the model solution defines both the answers and the
        # limits. The 60s/90s CPU/wall ceiling here is a hard safety cap,
        # not a real limit: the real TL/kill only exist once this pass has
        # finished timing the model solution, so there is no other number
        # to use yet. A genuine infinite loop in the model solution is
        # diagnosed clearly below (it raises, naming the test and why)
        # rather than hanging the whole pipeline silently.
        #
        # t_main is now CPU time (isolate's `time`), not wall time — this
        # is the change instruction 1 calls for, since judges limit CPU
        # time and it is far less sensitive to other load on this box. It
        # changes what every `t_main_ms`/`time_ms`/`ratio` figure in
        # invocation.json means; see the task report.
        t_main: dict[str, int] = {}
        for group, paths in tests.items():
            for test in paths:
                answer = test.with_suffix(".a")
                r = _time_median(isolate, binaries[main_file], test, answer,
                                 MODEL_SAFETY_CPU_S, MODEL_SAFETY_WALL_S,
                                 mem_limit_kb, runs,
                                 io_input=problem.input,
                                 io_output=problem.output)
                if r.killed:
                    # isolate's own `status:TO` fires for either a CPU-time
                    # kill or a wall-time kill, and this pass has two
                    # different safety ceilings for them — the message
                    # text is what tells them apart ("Time limit exceeded"
                    # vs "Time limit exceeded (wall clock)", verified
                    # against a real sleep()-bound run; see the task
                    # report), so it, not a hardcoded guess, picks which
                    # limit to name here.
                    if _is_wall_clock_kill(r.message):
                        kind, limit_ms = "wall-clock", int(MODEL_SAFETY_WALL_S * 1000)
                    else:
                        kind, limit_ms = "CPU", int(MODEL_SAFETY_CPU_S * 1000)
                    raise MatrixError(
                        f"model solution did not finish within {limit_ms} ms "
                        f"{kind} time on {test} (hard safety kill during "
                        "pass 1, before real limits exist; isolate reported: "
                        f"{r.message or '(no message)'})")
                # Same two signals as `_classify`: the cgroup cap sits
                # `OUTPUT_SLACK_KB` above the limit, so a model solution
                # that overshoots by less than that is never OOM-killed
                # and only `max-rss` (`_time_median`'s max over runs) shows
                # it. Without this half it would define the answers while
                # breaking its own limit.
                if r.oom or r.peak_kb > mem_limit_kb:
                    raise MatrixError(
                        f"model solution exceeded the memory limit "
                        f"({problem.memory_mb} MB) on {test}: "
                        + ("OOM-killed at the cgroup cap of "
                           f"{(mem_limit_kb + OUTPUT_SLACK_KB) // 1024} MB"
                           if r.oom else f"peak max-rss {r.peak_kb} KB"))
                if r.crashed or r.exit_code != 0:
                    # A signal death (status SG, a real segfault/abort, not
                    # an OOM — that's handled above) carries no `exitcode`
                    # line at all, so defaulting it to 0 and reporting
                    # "exited 0" would read as a bug in this check rather
                    # than a crashing model solution. Quote isolate's own
                    # status/message instead of reconstructing one.
                    detail = f"status {r.status or 'RE'}"
                    if r.message:
                        detail += f", {r.message}"
                    elif r.status != "SG":
                        detail += f", exitcode {r.exit_code}"
                    raise MatrixError(
                        f"model solution crashed on {test} ({detail}) — a "
                        "solution that exits abnormally cannot define the "
                        "jury's expected timing or answers")
                if r.no_output:
                    # File-IO mode only, and new with it: the model solution
                    # exited 0 and never created `io.output`. Left unchecked
                    # this writes an EMPTY `.a` answer file and carries on,
                    # so pass 2 checks every solution — including the model
                    # one — against a blank jury answer. That is precisely
                    # the confidently-wrong matrix this driver refuses to
                    # produce, and it is reachable the moment `run()` stops
                    # rejecting file IO: the usual cause is a model solution
                    # written for stdout, or one writing a filename that
                    # disagrees with `problem.json`.
                    raise MatrixError(
                        f"model solution exited 0 on {test} without creating "
                        f"its output file {problem.output!r} — the jury's "
                        "answer file would be empty and every verdict below "
                        "would be measured against it. Check that the model "
                        "solution writes the filename problem.json declares "
                        f"(io.input={problem.input!r}, "
                        f"io.output={problem.output!r}).")
                t_main[f"{group}/{test.stem}"] = r.cpu_ms

        limits = compute_limits(t_main)

        # Pass 2 — everything else, fanned out across `workers` sandboxes at
        # once (see `_run_pass2`), band results re-timed. `--time` is set to
        # `kill_ms` (not `tl_ms`): that is the value the old driver's own
        # wait loop enforced as its hard kill deadline, and preserving it
        # here is what keeps the (TL, kill] band reachable at all — a
        # solution genuinely running between TL and kill must be allowed to
        # actually finish in that window so `classify()` can band it, not be
        # cut off by isolate at TL first. `--wall-time` is
        # `max(3 * tl_ms, kill_ms)`: the instructed "3x TL" backstop, floored
        # at `kill_ms` so it is never smaller than the CPU cap it backstops
        # (which would happen if a caller ever forces a degenerate tl_ms,
        # e.g. this module's own timing-band test). Both limits are computed
        # inside `_run_pass2` itself; nothing here duplicates them.
        # The one `box_pool` call in this module not routed through
        # `_leased_box`. It is currently unreachable-with-a-raise —
        # `open_isolate_box` above already called `pool_size()`
        # successfully under the same environment, inside `lease()` — but
        # "currently unreachable" is not "handled", and `PACKAGE_ERRORS`
        # would already turn a bare `BoxPoolError` here into exit 2 with no
        # help from this `try`. This exists for the message: naming the
        # worker pool rather than surfacing whatever `box_pool.pool_size`
        # happened to say.
        try:
            workers = box_pool.pool_size()
        except box_pool.BoxPoolError as exc:
            raise MatrixError(
                f"cannot size the worker pool: {exc}"
            ) from exc
        results, actual = _run_pass2(isolate, problem, problem_dir, manifest,
                                     binaries, checker, tests, limits,
                                     mem_limit_kb, runs, workers)
    finally:
        close_isolate_box(isolate)

    expected = {e["file"]: e["expect"] for e in manifest["solutions"]}
    holes, mismatches = compare(expected, actual)

    payload = {
        "schema": SCHEMA,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "machine": {
            "cxx": subprocess.run(["g++", "--version"], capture_output=True,
                                  text=True).stdout.splitlines()[0],
            "flags": " ".join(CXXFLAGS),
            "platform": platform.platform(),
            "runner": "isolate",
            "runner_version": isolate.version,
            # A declaration, not a measurement. This driver passes `--cg` to
            # every isolate invocation unconditionally (`_init_box`,
            # `_run_once`, `_cleanup_box`), so what this field records is
            # what was *requested*; nothing here probes the kernel to
            # confirm cgroup accounting was actually honoured. The previous
            # name (`cg`) read as an observation of the machine and was
            # hardcoded `True` — renamed rather than deleted, because a
            # reader of an old invocation.json still needs to know which
            # mode the runner asked for.
            "cg_requested": True,
            # The cgroup cap actually passed as `--cg-mem`, and the slack
            # that separates it from the problem's `memory_mb`. Provenance
            # for every ML in `results`: a `peak_kb` over `memory_mb` with
            # `oom` false was judged from max-rss against the limit, and
            # an `oom` true was a kernel kill at *this* cap, not at the
            # limit. See `OUTPUT_SLACK_KB` for why they differ.
            "cg_mem_kb": mem_limit_kb + OUTPUT_SLACK_KB,
            "output_slack_kb": OUTPUT_SLACK_KB,
            # Pins the testlib revision the checker in this run was
            # compiled against. `bootstrap_testlib.sh` runs `git pull` on
            # every invocation, so without this the artifact certifying
            # "no solution survives" could not be reproduced against the
            # header that produced it.
            "testlib": _git_rev(testlib_dir),
            # How many sandboxes were running at once, and the inflation
            # bound the ambiguity rule assumed. Both are provenance, not
            # settings: a reader asking whether a recorded 1040 ms is
            # trustworthy needs to know it was measured with three other
            # boxes live.
            "workers": workers,
            "contention_bound": CONTENTION_BOUND,
        },
        "t_main_ms": {"per_test": t_main, "max": limits.t_main_ms,
                      "runs": runs, "method": "median", "metric": "cpu"},
        "limits": {"tl_ms": limits.tl_ms, "kill_ms": limits.kill_ms},
        "results": results,
        "holes": holes,
        "mismatches": mismatches,
    }
    (problem_dir / "invocation.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


# Every exception type this pipeline raises for a package it cannot use.
# `main()` catches the family rather than a list of call sites, because the
# property that has to hold is a *boundary* one: nothing reaches a caller as
# an unhandled exception, whatever future module raises it. A per-site
# conversion list — the shape `_leased_box` uses for `BoxPoolError`, which is
# right there because it has exactly two adjacent call sites — cannot state
# that invariant, and is defeated by the next call site someone adds.
#
# Measured, not assumed. Driving `main()` against a real package surfaced
# three escapees, each as a traceback exiting 1 — the code
# `validating-solutions` reads as "the matrix ran and found holes":
#   - a malformed `problem.json`            -> `problem_meta.ProblemMetaError`
#   - a malformed `@expect` header on a solution -> `scan_solutions.ScanError`
#   - a corrupted `flags.json` while a result lands in the (TL, kill] band
#     or is retimed, which is when `_run_pass2` calls `flags.append` and
#     `flags.append` reads the existing register before writing to it
#     -> `flags.FlagError`. A probe with a corrupted `flags.json` but no
#     banded/retimed result in the run does *not* escape — `flags.append`
#     is simply never called on that path — which is why "exit 0 on a
#     corrupted flags.json" is not proof of nothing to fix here, only proof
#     that particular probe didn't reach the call site.
# `box_pool.BoxPoolError` is included for the boundary invariant itself: it
# is already converted to `MatrixError` at both of its call sites
# (`_leased_box`, and the bare `pool_size()` call in `run()`), so nothing
# here should ever actually raise a bare one, but "should never" is exactly
# the claim a boundary catch exists to not have to trust.
# `drift_check.DriftCheckError` is deliberately absent: `drift_check` is
# never imported by this module, so nothing on any path `run()` takes can
# raise it — traced by grepping this file for the name, not assumed.
PACKAGE_ERRORS = (MatrixError, box_pool.BoxPoolError, ProblemMetaError,
                  ScanError, flags.FlagError)


def main(argv: list[str]) -> int:
    """Exit codes are a contract `validating-solutions` reads directly:

        0 — every solution's @expect was met.
        1 — the matrix ran and found holes and/or mismatches. This is a
            *result*, printed to stdout: the signal to keep reading.
        2 — the matrix could not be run at all: usage error, any
            `PACKAGE_ERRORS` member (a compile failure, a missing tests
            directory, a model solution that produced no output file, an
            unusable sandbox or staging location, a malformed
            `problem.json` or solution `@expect` header, a corrupted
            `flags.json`), or any *other* exception `run()` raises — a
            driver bug, or an environment failure this pipeline has no
            named type for (`invocation.json` on a full or read-only disk
            is a plain `OSError`, not anything under `tools/`). Nothing
            that happens while sizing up whether the matrix could run
            reaches a caller as exit 1.
            A message on stderr; for `PACKAGE_ERRORS` a message naming the
            package problem, with no traceback, for anything else the full
            traceback (`traceback.print_exc()`) so the failure is not
            hidden, just correctly coded. Nothing on stdout either way.

    Two tiers, deliberately not one `except Exception`: `PACKAGE_ERRORS` are
    problems in the *package* — a user can act on "malformed problem.json"
    without seeing a stack trace, and a message naming the problem, with no
    traceback, is more useful to them than 40 lines of this driver's
    internals. Everything else is
    unexpected — some driver bug or environment condition this pipeline
    never named — and for those the traceback is the useful artifact; only
    the *exit code* changes from the Python default, to the one that
    correctly describes "the matrix could not be run", not to a swallowed
    silence. `except Exception` does not catch `SystemExit` or
    `KeyboardInterrupt` — both derive from `BaseException`, not
    `Exception` — so neither is intercepted here; a `^C` or an explicit
    `sys.exit()` inside `run()` still propagates as itself.

    `test_no_tools_exception_type_escapes_main` in
    `tools/tests/test_run_matrix.py` only proves this for the one type it
    injects (`ProblemMetaError`); the property that *every* `tools/` error
    type is a member of `PACKAGE_ERRORS` — the thing that decides whether a
    given failure gets the one-line message or the traceback tier — is
    proven separately, by
    `test_every_tools_error_type_reachable_from_run_matrix_is_in_package_errors`,
    which enumerates the actual types defined in every `tools` module
    reachable from this module's own namespace rather than trusting one
    injected example to stand for all of them.

    Before this, `main()` caught only `MatrixError`. `ProblemMetaError` and
    `ScanError` surfaced as tracebacks and exited 1 as well, so an agent
    told "exit 1 means holes or mismatches" would read a crash as a finding
    — a typo in a solution's metadata header reported as "the suite has a
    hole".
    """
    if len(argv) != 3:
        print("usage: run_matrix.py <problem-dir> <testlib-dir>", file=sys.stderr)
        return 2
    try:
        payload = run(argv[1], argv[2])
    except PACKAGE_ERRORS as exc:
        print(f"run_matrix: {exc}", file=sys.stderr)
        return 2
    except Exception:
        # Not a package problem this pipeline has a name for — a driver bug
        # or an unnamed environment failure (e.g. `invocation.json`'s own
        # `write_text` on a full or read-only disk, a plain `OSError`).
        # Exit 2 is still the right code ("the matrix could not be run at
        # all" is exactly what a driver crash is), and the traceback on
        # stderr means nothing is hidden — only the exit code changes from
        # what an uncaught exception would otherwise produce.
        traceback.print_exc()
        return 2
    print(f"TL {payload['limits']['tl_ms']} ms  "
          f"kill {payload['limits']['kill_ms']} ms  "
          f"holes {len(payload['holes'])}  "
          f"mismatches {len(payload['mismatches'])}")
    for record in payload["holes"]:
        print(f"HOLE      {record['solution']} survived {record['group']} "
              f"(expected {record['expected']})")
    for record in payload["mismatches"]:
        print(f"MISMATCH  {record['solution']} on {record['group']}: "
              f"expected {record['expected']}, got {record['actual']}")
    return 1 if payload["holes"] or payload["mismatches"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
