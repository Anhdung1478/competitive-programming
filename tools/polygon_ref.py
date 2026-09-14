"""Where a package lives on Polygon — a file of its own, deliberately.

`uploading-to-polygon` has to remember one thing between runs: the Polygon
problem this package was uploaded to. The presence of that record is what
turns a second run into a *re-sync* of one problem rather than a second
problem with the same name, so it has to survive on disk.

**Why not a key in `problem.json`.** `problem.json` is matrix evidence:
`package_status._MATRIX_SOURCES` walks it, and `invocation.json` is stale the
moment anything in that walk is newer. Writing an upload record into it would
therefore make `tools.package_status` stop printing `complete` and
`tools.review_checks` emit a high `stale-matrix` — the two gates the upload
skill must pass *before* it writes. The first upload would report a failing
gate one phase after passing it, and every later run would fail the gate
permanently, over a package nothing had actually changed. The record is not
evidence about the matrix and must not be walked as if it were, so it lives
beside `problem.json` instead of inside it.

`polygon.json` is package data, not a byproduct: unlike `flags.json.lock` it
belongs in the problem repository's history, because it is the only record of
which Polygon problem a package owns.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = 1
FILENAME = "polygon.json"


class PolygonRefError(ValueError):
    """`polygon.json` is missing a field, or one of them is malformed."""


@dataclass(frozen=True)
class PolygonRef:
    """The Polygon problem a package has been uploaded to.

    `url` is recorded rather than recomputed on read: `problem.create`
    answers with `id`, `owner`, `name` and access type and no address, and
    the skill builds `https://polygon.codeforces.com/edit-start?problemId=<id>`
    once, at record time. Storing it keeps the link a collaborator bookmarked
    in the package's history even if Polygon's URL scheme later moves.

    `committed_at` is the timestamp of the last revision the upload skill
    committed, RFC 3339 with an explicit offset. A re-sync compares file
    mtimes against it to decide what still needs uploading, so it stays
    `None` until a commit has actually succeeded — a create that never
    reached a revision must not read as one that did.
    """

    id: int
    owner: str
    url: str
    committed_at: str | None = None


def path_for(problem_dir: str | Path) -> Path:
    return Path(problem_dir) / FILENAME


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolygonRefError(
            f"{FILENAME}: {field} is {value!r}, expected a non-empty string")
    return value


def _timestamp(value: object, field: str) -> str | None:
    """An RFC 3339 timestamp with an offset, or None.

    Offset-aware on purpose. The value is compared against file mtimes on
    a machine that is not necessarily the one that wrote it, and a naive
    timestamp silently means "some local time somewhere" — which is how a
    re-sync would skip a file that had in fact changed.
    """
    if value is None:
        return None
    text = _string(value, field)
    # `datetime.fromisoformat` only learned to read a trailing `Z` in 3.11;
    # normalising here keeps this module working on the 3.10 the servers
    # are pinned to, and `Z` is the spelling Polygon's own timestamps use.
    try:
        parsed = datetime.fromisoformat(
            text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError as exc:
        raise PolygonRefError(
            f"{FILENAME}: {field} is {text!r}, expected an RFC 3339 "
            f"timestamp such as 2026-09-04T11:22:33Z ({exc})") from exc
    if parsed.tzinfo is None:
        raise PolygonRefError(
            f"{FILENAME}: {field} is {text!r}, which carries no UTC offset. "
            f"It is compared against file mtimes, so a local-time-somewhere "
            f"value would silently skip a file that had changed.")
    return text


def load(problem_dir: str | Path) -> PolygonRef | None:
    """The package's Polygon record, or None when it has never been uploaded.

    None means "not on Polygon yet" and is the ordinary state of every
    package before the upload skill runs. Every other way the file can be
    wrong raises, naming the field: a malformed record read as absent would
    send the upload skill off to create a *second* Polygon problem for a
    package that already has one, and no tidying afterwards undoes an id
    other people have bookmarked.
    """
    path = path_for(problem_dir)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise PolygonRefError(f"{path}: cannot be read: {exc}") from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PolygonRefError(f"{path}: not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise PolygonRefError(
            f"{path}: the file holds a {type(raw).__name__}, expected an object")

    schema = raw.get("schema")
    if schema != SCHEMA:
        raise PolygonRefError(
            f"{FILENAME}: schema is {schema!r}, expected {SCHEMA}")
    for field in ("id", "owner", "url"):
        if field not in raw:
            raise PolygonRefError(
                f"{FILENAME}: {field} is missing. The file is written whole "
                f"by the upload skill after `problem.create` returns — a "
                f"hand-edit that drops a field leaves a package that claims "
                f"to be on Polygon without saying where.")

    problem_id = raw["id"]
    if isinstance(problem_id, bool) or not isinstance(problem_id, int):
        raise PolygonRefError(
            f"{FILENAME}: id is {problem_id!r}, expected an integer")
    if problem_id <= 0:
        raise PolygonRefError(
            f"{FILENAME}: id is {problem_id}, expected a positive Polygon "
            f"problem id — it is passed straight into every `problem_id` "
            f"parameter of the upload")

    return PolygonRef(
        id=problem_id,
        owner=_string(raw["owner"], "owner"),
        url=_string(raw["url"], "url"),
        committed_at=_timestamp(raw.get("committed_at"), "committed_at"),
    )


def save(problem_dir: str | Path, ref: PolygonRef) -> Path:
    """Write the record, replacing any earlier one. Returns the path.

    Atomic: a temp file in the same directory, then `os.replace`. A partial
    `polygon.json` is worse than none — it reads as a package that is on
    Polygon somewhere unspecified, which is the one state the upload skill
    cannot act on.
    """
    problem_dir = Path(problem_dir)
    path = path_for(problem_dir)
    payload = {
        "schema": SCHEMA,
        "id": ref.id,
        "owner": ref.owner,
        "url": ref.url,
        "committed_at": ref.committed_at,
    }
    # Validate what is about to be written by the same rules `load` reads it
    # by, so `save` can never produce a file `load` would refuse.
    _string(ref.owner, "owner")
    _string(ref.url, "url")
    _timestamp(ref.committed_at, "committed_at")
    if isinstance(ref.id, bool) or not isinstance(ref.id, int) or ref.id <= 0:
        raise PolygonRefError(
            f"{FILENAME}: id is {ref.id!r}, expected a positive integer")

    handle, tmp_name = tempfile.mkstemp(dir=problem_dir, prefix=".polygon-",
                                        suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return path
