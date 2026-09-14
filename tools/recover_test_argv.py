#!/usr/bin/env python3
"""Recover the exact generator command line behind every test of a package.

`uploading-to-polygon` pushes generated tests as a Polygon generator script —
one line per test, `gen-X arg1 arg2 > <index>` — and hand-made tests as manual
uploads. A package built by `build_tests.sh` does not store those argv lists
anywhere: they live inside bash loops, helper functions and variables. The
old answer was "argv not recoverable, STOP"; the working answer was to copy
the package, instrument it, rerun the copy and diff. This module is that
procedure, made mechanical.

    python3 -m tools.recover_test_argv PROBLEM_DIR OUT_DIR [--script build_tests.sh] [--offset N]

How, without editing the script:

  * The package is copied to OUT_DIR/pkg (minus bin/, .build/ and the test
    files themselves, so a stale copy can never mask a test the script no
    longer produces). PROBLEM_DIR is never written to.
  * OUT_DIR/shim is prepended to PATH with `g++`/`c++`/`clang++` shims. Each
    runs the real compiler; when the `-o` output is a generator (basename
    `gen-*`, or a `gen-*.cpp` source), the binary is moved to `<out>.real` and
    a bash wrapper installed at `<out>` logs (name, argv0, argv, stdout
    target via `/proc/$$/fd/1`) NUL-separated, then `exec`s the real binary.
  * After the script runs, each test's LAST logged generator call targeting
    it is replayed twice; it is `gen` only if both replays are byte-identical
    to the ORIGINAL test file. Everything else is `manual`, with a reason.

Exit codes: 0 every test accounted for and the copy reproduced the suite;
1 the copy's suite differs from the original (manifest still written);
2 usage or package error (missing script/tests, script failed).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tools.problem_meta import ProblemMetaError, load

COMPILERS = ("g++", "c++", "clang++")
MANIFEST_SCHEMA = 1
REPLAY_TIMEOUT_S = 300

# Polygon's generator script is whitespace-tokenised with `>` introducing the
# test index; there is no quoting. Anything below cannot be written there.
_UNEXPRESSIBLE = re.compile(r"[\s<>\"'`#]")


class RecoverError(Exception):
    """Usage or package error — maps to exit code 2."""


@dataclass
class Call:
    name: str
    argv0: str
    real: str
    target: str
    cwd: str
    args: list[str]


# --------------------------------------------------------------------------
# Instrumentation

_SHIM = '''#!{python}
import os, shlex, subprocess, sys
REAL = {real!r}
TEMPLATE = {template!r}
LOG = {log!r}
args = sys.argv[1:]
rc = subprocess.call([REAL] + args)
if rc != 0 or "-c" in args or "-E" in args or "-S" in args:
    sys.exit(rc)
out = None
for i, a in enumerate(args):
    if a == "-o" and i + 1 < len(args):
        out = args[i + 1]
    elif a.startswith("-o") and len(a) > 2:
        out = a[2:]
if out is None or not os.path.isfile(out):
    sys.exit(0)
base = os.path.basename(out)
is_gen = base.startswith("gen-") or any(
    os.path.basename(a).startswith("gen-")
    and a.endswith((".cpp", ".cc", ".cxx", ".c")) for a in args)
if not is_gen:
    sys.exit(0)
out = os.path.abspath(out)
real = out + ".real"
os.replace(out, real)
body = (TEMPLATE.replace("@NAME@", shlex.quote(base))
        .replace("@REAL@", shlex.quote(real))
        .replace("@LOG@", shlex.quote(LOG)))
with open(out, "w") as f:
    f.write(body)
os.chmod(out, 0o755)
'''

# `$$` (not $BASHPID, not /dev/stdout) so the command substitution reads the
# wrapper's own stdout — the test file — rather than its own capture pipe.
# The explicit argc field keeps empty arguments unambiguous in the NUL log.
_WRAPPER = '''#!/usr/bin/env bash
target=$(readlink -f /proc/$$/fd/1 2>/dev/null || echo '?')
printf '%s\\0' @NAME@ "$0" @REAL@ "$target" "$PWD" "$#" "$@" >> @LOG@
exec -a "$0" @REAL@ "$@"
'''


def _install_shims(shim_dir: Path, log: Path, orig_path: str) -> list[str]:
    shim_dir.mkdir(parents=True, exist_ok=True)
    search = os.pathsep.join(
        p for p in orig_path.split(os.pathsep)
        if p and Path(p).resolve() != shim_dir.resolve())
    installed = []
    for cc in COMPILERS:
        real = shutil.which(cc, path=search)
        if real is None:
            continue
        shim = shim_dir / cc
        shim.write_text(_SHIM.format(python=sys.executable, real=real,
                                     template=_WRAPPER, log=str(log)))
        shim.chmod(0o755)
        installed.append(cc)
    return installed


def _parse_log(log: Path) -> list[Call]:
    if not log.exists():
        return []
    fields = log.read_bytes().split(b"\0")
    calls, i = [], 0
    while i + 6 <= len(fields):
        try:
            argc = int(fields[i + 5])
        except ValueError:
            break
        chunk = [f.decode("utf-8", "surrogateescape")
                 for f in fields[i:i + 6 + argc]]
        if len(chunk) < 6 + argc:
            break
        calls.append(Call(name=chunk[0], argv0=chunk[1], real=chunk[2],
                          target=chunk[3], cwd=chunk[4], args=chunk[6:]))
        i += 6 + argc
    return calls


# --------------------------------------------------------------------------
# Package handling

def _copy_package(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    tests = (src / "tests").resolve()

    def ignore(directory: str, names: list[str]) -> set[str]:
        skip = {n for n in names if n in ("bin", ".build", "__pycache__", ".git")}
        d = Path(directory).resolve()
        if d == tests or tests in d.parents:
            skip |= {n for n in names if (d / n).is_file()}
        return skip

    # symlinks=False: a preserved symlink would let the script's own
    # `rm -f tests/*.in` reach through into the original package.
    shutil.copytree(src, dst, ignore=ignore, symlinks=False,
                    ignore_dangling_symlinks=True)


def _sort_key(p: Path):
    m = re.match(r"\d+", p.stem)
    return (0, int(m.group()), p.name) if m else (1, 0, p.name)


def _enumerate_tests(problem_dir: Path) -> list[tuple[str, Path]]:
    """(group, path relative to the package) in upload order."""
    tests_dir = problem_dir / "tests"
    if not tests_dir.is_dir():
        raise RecoverError(f"{tests_dir}: no tests directory")
    groups: list[str] = []
    try:
        groups = load(problem_dir / "problem.json").subtask_ids()
    except ProblemMetaError:
        groups = []
    if not groups:
        groups = sorted(d.name for d in tests_dir.iterdir() if d.is_dir())
    out = []
    for g in groups:
        files = sorted((tests_dir / g).glob("*.in"), key=_sort_key)
        if not files:
            raise RecoverError(f"{tests_dir / g}: no .in files for group {g!r}")
        out.extend((g, f.relative_to(problem_dir)) for f in files)
    return out


def _all_ins(root: Path) -> set[Path]:
    tests = root / "tests"
    return {p.relative_to(root) for p in tests.rglob("*.in")} if tests.is_dir() else set()


def _replay(call: Call, dest: Path) -> bytes | None:
    try:
        with open(dest, "wb") as fh:
            proc = subprocess.run([call.argv0, *call.args], executable=call.real,
                                  cwd=call.cwd, stdout=fh,
                                  stderr=subprocess.DEVNULL,
                                  timeout=REPLAY_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return dest.read_bytes()


def _classify(call: Call | None, original: bytes, scratch: Path) -> dict:
    if call is None:
        return {"kind": "manual", "reason": "no generator wrote it"}
    if any(a == "" or _UNEXPRESSIBLE.search(a) for a in call.args):
        return {"kind": "manual",
                "reason": "argv not expressible in a Polygon script"}
    first = _replay(call, scratch / "a")
    second = _replay(call, scratch / "b")
    if first is None or second is None:
        return {"kind": "manual", "reason": "generator replay failed"}
    if first != second:
        return {"kind": "manual", "reason": "nondeterministic"}
    if first != original:
        return {"kind": "manual", "reason": "regenerated bytes differ"}
    return {"kind": "gen", "generator": call.name, "args": list(call.args)}


# --------------------------------------------------------------------------

def run(problem_dir: Path, out_dir: Path, script: str,
        offset: int | None) -> int:
    problem_dir = problem_dir.resolve()
    if not problem_dir.is_dir():
        raise RecoverError(f"{problem_dir}: not a directory")
    out_dir = out_dir.resolve()
    if out_dir == problem_dir or problem_dir in out_dir.parents:
        raise RecoverError(
            f"{out_dir}: OUT_DIR must not be inside PROBLEM_DIR "
            "(this tool never writes into the package)")
    if not (problem_dir / script).is_file():
        raise RecoverError(f"{problem_dir / script}: no such build script")
    tests = _enumerate_tests(problem_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    pkg = out_dir / "pkg"
    shim = out_dir / "shim"
    log = out_dir / "gen-calls.log"
    log.unlink(missing_ok=True)
    _copy_package(problem_dir, pkg)
    orig_path = os.environ.get("PATH", "")
    if not _install_shims(shim, log, orig_path):
        raise RecoverError("no C++ compiler (g++, c++, clang++) on PATH")

    env = dict(os.environ, PATH=os.pathsep.join([str(shim), orig_path]))
    proc = subprocess.run(["bash", script], cwd=pkg, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out_dir / "build.log").write_bytes(proc.stdout + b"\n--- stderr ---\n"
                                        + proc.stderr)
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").splitlines()[-20:]
        raise RecoverError(
            f"{script} exited {proc.returncode} in {pkg}; stderr tail:\n"
            + "\n".join(tail))

    calls = _parse_log(log)
    if not calls and list((pkg / "files").glob("gen-*.c*")):
        print("warning: files/gen-* exist but no generator binary went through "
              "the compiler shim (absolute compiler path or $CXX?) — every "
              "test will read as manual", file=sys.stderr)
    last: dict[str, Call] = {}
    for c in calls:
        last[os.path.realpath(c.target)] = c

    entries, mismatches = [], []
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        scratch = Path(tmp)
        for index, (group, rel) in enumerate(tests, start=1):
            original = (problem_dir / rel).read_bytes()
            copy = pkg / rel
            call = last.get(os.path.realpath(copy))
            entry = {"index": index, "group": group, "file": rel.as_posix()}
            entry.update(_classify(call, original, scratch))
            entries.append(entry)
            if not copy.is_file():
                mismatches.append(f"{rel}: not produced by {script}")
            elif copy.read_bytes() != original:
                mismatches.append(f"{rel}: rebuilt bytes differ from the original")
    extra = sorted(_all_ins(pkg) - _all_ins(problem_dir))
    mismatches += [f"{rel}: produced by {script} but absent from the original"
                   for rel in extra]

    gens = sorted({e["generator"] for e in entries if e["kind"] == "gen"})
    manifest = {"schema": MANIFEST_SCHEMA, "problem": str(problem_dir),
                "tests": entries, "generators": gens}
    (out_dir / "tests-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if offset is not None:
        lines = [" ".join([e["generator"], *e["args"], ">", str(e["index"] + offset)])
                 for e in entries if e["kind"] == "gen"]
        (out_dir / "script.txt").write_text(
            "".join(line + "\n" for line in lines), encoding="utf-8")

    n_gen = sum(e["kind"] == "gen" for e in entries)
    print(f"{n_gen} gen, {len(entries) - n_gen} manual")
    for e in entries:
        if e["kind"] == "manual":
            print(f"  manual #{e['index']} {e['file']}: {e['reason']}")
    print(f"manifest: {out_dir / 'tests-manifest.json'}")
    if mismatches:
        print(f"{script} did not reproduce the suite:", file=sys.stderr)
        for m in mismatches:
            print(f"  {m}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m tools.recover_test_argv",
        description="Recover generator argv for every test of a package.")
    parser.add_argument("problem_dir", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--script", default="build_tests.sh")
    parser.add_argument("--offset", type=int, default=None)
    try:
        ns = parser.parse_args(argv[1:])
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    try:
        return run(ns.problem_dir, ns.out_dir, ns.script, ns.offset)
    except RecoverError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
