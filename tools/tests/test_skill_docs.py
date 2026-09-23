"""Guard the prose the tools cannot guard.

`preparing-tests` and `reviewing-problems` both carry the reaching-check
recipe, and that duplication is deliberate: skills load independently, with no
include mechanism, so a reviewer who never opens `preparing-tests` still has to
find the recipe in front of them. What was *not* deliberate is the claim that
followed it — "byte-for-byte identical, so they cannot drift". That is an
observation about a moment in time, not a guarantee, and it was already false
when it was written: block 1's trailing comment read

    # first number is the shortest A in the group      (preparing-tests)
    # first line is the shortest value in the group    (reviewing-problems)

Two copies with no mechanism holding them together drift silently, and the
half that drifts is whichever one the next editor did not have open. This
module is that mechanism.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path

from tools import bootstrap_testlib, box_pool, preferences, problem_meta, run_matrix
from tools.matrix_core import _SEVERITY
from tools.package_status import PHASE_ORDER, _matrix
from tools.problem_meta import FORMAT_VALUES
from tools.scan_solutions import TAGS as SOLUTION_ZOO_TAGS
from tools.scan_solutions import VERDICTS

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"
PLUGIN_DIR = ROOT / ".claude-plugin"

# A fenced block, tagged with its language. Non-greedy so each match is one
# complete fence rather than everything between the first and last one.
_FENCE = re.compile(r"^```(?P<lang>[a-zA-Z0-9_-]*)\n(?P<body>.*?)^```$",
                    re.DOTALL | re.MULTILINE)

# The two halves of the recipe, identified by content rather than by line
# number — line numbers move every time a paragraph above them is edited, and
# a test that has to be renumbered on every edit is a test that gets deleted.
RECIPE_MARKERS = {
    "per-test validator log loop": "--testOverviewLogFileName",
    "non-numeric bound fallback": "FNR==1",
}

DUPLICATED_IN = ("preparing-tests", "reviewing-problems")


def skill_text(skill: str) -> str:
    return (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")


def flatten(text: str) -> str:
    """Collapse every run of whitespace to one space.

    These files are hard-wrapped at ~76 columns, so any phrase long enough to
    be worth pinning is split across a newline. Matching raw text would make a
    test pass or fail on where a paragraph happened to wrap.
    """
    return re.sub(r"\s+", " ", text)


def skill_dirs() -> set[str]:
    return {p.name for p in SKILLS.iterdir() if (p / "SKILL.md").is_file()}


def bash_blocks(skill: str) -> list[str]:
    text = skill_text(skill)
    return [m.group("body") for m in _FENCE.finditer(text)
            if m.group("lang") == "bash"]


def manifest_descriptions() -> dict[str, str]:
    """The plugin `description` as each of the two manifests spells it.

    `plugin.json` is what an installed plugin reports; `marketplace.json` is
    what the listing shows before anyone installs it. They are two copies of
    one sentence, with nothing between them.
    """
    plugin = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((PLUGIN_DIR / "marketplace.json").read_text(encoding="utf-8"))
    entries = [p for p in market["plugins"] if p["name"] == plugin["name"]]
    if len(entries) != 1:
        raise AssertionError(
            f"marketplace.json lists {len(entries)} entries named "
            f"{plugin['name']!r}; expected exactly one")
    return {"plugin.json": plugin["description"],
            "marketplace.json": entries[0]["description"]}


class TestFenceExtraction(unittest.TestCase):
    """The extractor itself, so a failure below is a real drift and not this
    module quietly matching nothing. A `find_recipe` that returned `None` for
    both files would otherwise make every comparison trivially pass — the same
    vacuous-guard shape this branch has already been bitten by twice."""

    def test_every_skill_file_exists(self):
        for skill in DUPLICATED_IN:
            self.assertTrue((SKILLS / skill / "SKILL.md").is_file(),
                            f"{skill}/SKILL.md is missing")

    def test_bash_blocks_are_found_in_both_files(self):
        for skill in DUPLICATED_IN:
            self.assertTrue(bash_blocks(skill),
                            f"no ```bash blocks extracted from {skill}")

    def test_a_fence_is_not_swallowed_into_its_neighbour(self):
        # Non-greedy matching: no extracted block may contain a fence marker.
        for skill in DUPLICATED_IN:
            for block in bash_blocks(skill):
                self.assertNotIn("```", block,
                                 f"{skill}: fence extraction ran past a block end")


class TestReachingCheckRecipeDoesNotDrift(unittest.TestCase):
    def recipe(self, skill: str, marker: str) -> str:
        matches = [b for b in bash_blocks(skill) if marker in b]
        self.assertEqual(
            len(matches), 1,
            f"{skill}: expected exactly one ```bash block containing "
            f"{marker!r}, found {len(matches)}")
        return matches[0]

    def test_both_copies_of_each_recipe_block_are_byte_identical(self):
        first, second = DUPLICATED_IN
        for name, marker in RECIPE_MARKERS.items():
            with self.subTest(block=name):
                self.assertEqual(
                    self.recipe(first, marker), self.recipe(second, marker),
                    f"the {name} block has drifted between {first} and "
                    f"{second}. The duplication is deliberate (skills load "
                    f"independently, there is no include mechanism), so the "
                    f"fix is to copy one over the other — not to delete "
                    f"either copy and not to relax this test.")

    def test_the_validator_loop_checks_the_validators_exit_code(self):
        # A validator that rejects a test writes an empty log, and an empty log
        # contributes nothing to the union — which reads back as "unreached",
        # the exact false finding the per-test-log fix removed. Losing the exit
        # check would reintroduce it silently.
        for skill in DUPLICATED_IN:
            with self.subTest(skill=skill):
                block = self.recipe(skill, "--testOverviewLogFileName")
                self.assertIn("REJECTED", block,
                              f"{skill}: the reaching-check loop ignores the "
                              f"validator's exit code")


class TestFileIOProseMatchesTheDriver(unittest.TestCase):
    """The IO-mode paragraphs, pinned to the code they describe.

    For two whole stages `preparing-tests`, `validating-solutions` and the
    README all said file IO was "rejected loudly by `run_matrix`". Nothing
    caught it when that stopped being true, because nothing was watching
    those sentences — three separate documents making the same claim, and
    no test naming any of them. This class is that mechanism, and it is
    deliberately written against *values imported from the code* rather
    than against a second copy of the prose: a test that only compares one
    string in this file to one string in a document goes green the moment
    someone edits both, which is precisely how the retired claim survived.
    """

    DOCUMENTS = {
        "README.md": ROOT / "README.md",
        "preparing-tests": SKILLS / "preparing-tests" / "SKILL.md",
        "validating-solutions": SKILLS / "validating-solutions" / "SKILL.md",
    }

    # Sentences that were true before file IO landed and are false now. They
    # are listed literally, because the failure mode being guarded is a
    # revert or a copy-paste from an old draft, not a paraphrase.
    # Each one is the phrase as it actually stood, not a shortened key: the
    # substring `"rejected loudly by"` on its own also matches a future
    # document legitimately writing "rejected loudly by the validator", and a
    # guard that fires on true sentences gets deleted rather than obeyed.
    RETIRED_CLAIMS = (
        "Only stdin/stdout problems are supported",
        "rejected loudly by `run_matrix",
        "the file-IO guard",
        "it is a later feature, not a silent partial mode",
    )

    def text(self, name: str) -> str:
        path = self.DOCUMENTS[name]
        self.assertTrue(path.is_file(), f"{path} is missing")
        body = path.read_text(encoding="utf-8")
        # The extractor guard, same role as TestFenceExtraction above: an
        # empty read would make every assertNotIn below trivially pass.
        self.assertGreater(len(body), 1000, f"{path} read back nearly empty")
        return body

    def test_no_document_still_claims_file_io_is_rejected(self):
        # Matched against `flat`, not `text`: these documents are hard-wrapped
        # at ~76 columns, and the claims above are long enough that the
        # originals were split across a newline in both skills that carried
        # them — so a raw match would silently stop catching them the moment a
        # phrase got specific enough to be worth pinning.
        for name in self.DOCUMENTS:
            body = self.flat(name)
            for claim in self.RETIRED_CLAIMS:
                with self.subTest(document=name, claim=claim):
                    # `assertTrue`, not `assertNotIn`: unittest renders the
                    # container in an assertIn/assertNotIn failure with no
                    # length cap, and these containers are whole normalized
                    # documents (~10 KB of noise around the one fact that
                    # matters, which is the claim named here).
                    self.assertTrue(
                        claim not in body,
                        f"{name} still carries a pre-file-IO claim "
                        f"{claim!r}. run_matrix.run() accepts file-IO "
                        f"problems — the refusal it describes was deleted.")

    def flat(self, name: str) -> str:
        """`text`, with every run of whitespace collapsed to one space.

        These documents are hard-wrapped at ~76 columns, so any phrase long
        enough to be worth pinning is split across a newline in at least one
        of them. Matching the raw text would make this test pass or fail on
        where a paragraph happened to wrap.
        """
        return re.sub(r"\s+", " ", self.text(name))

    def test_every_document_states_what_file_io_does_not_change(self):
        # The two facts a setter most needs and most doubts. Duplicated
        # across all three documents on purpose (skills load independently,
        # there is no include mechanism), which is exactly why they need a
        # test holding them together.
        required = (
            "enerators and validators are unaffected",
            "three file paths",
        )
        for name in self.DOCUMENTS:
            body = self.flat(name)
            for phrase in required:
                with self.subTest(document=name, phrase=phrase):
                    # `assertTrue`, not `assertIn` — see above: `assertIn`
                    # would print the whole ~10 KB normalized document into
                    # the failure, burying the one line that says what is
                    # wrong and which file to open.
                    self.assertTrue(
                        phrase in body,
                        f"{name} describes file IO without saying that "
                        f"{phrase!r} — the question every setter asks first.")

    def test_prose_names_the_drivers_real_staged_stdout_file(self):
        # `validating-solutions` tells a reader their `io.output` may not
        # collide with the driver's staged stdout, and names it. Rename
        # STAGED_STDOUT_NAME and that instruction silently starts naming a
        # file that no longer exists.
        self.assertIn(f"(`{run_matrix.STAGED_STDOUT_NAME}`)",
                      self.flat("validating-solutions"),
                      "the collision warning names a file the driver no "
                      "longer stages to")

    def test_the_declarable_verdicts_in_prose_are_the_ones_the_scanner_takes(self):
        # `validating-solutions` claims @expect accepts exactly
        # `OK WA TL ML PE RE`. That list lives in scan_solutions.VERDICTS,
        # and the whole NO_OUTPUT-is-a-mismatch-not-a-hole explanation
        # around it is only true while NO_OUTPUT stays out of it.
        body = self.flat("validating-solutions")
        match = re.search(r"`([A-Z][A-Z ]+)` \(`scan_solutions\.VERDICTS`\)", body)
        self.assertIsNotNone(
            match, "validating-solutions no longer quotes the declarable "
                   "verdict list next to `scan_solutions.VERDICTS`")
        self.assertEqual(match.group(1).split(), list(VERDICTS),
                         "the verdict list in validating-solutions has "
                         "drifted from scan_solutions.VERDICTS")
        self.assertNotIn("NO_OUTPUT", VERDICTS,
                         "NO_OUTPUT became declarable, so the prose calling "
                         "it 'not declarable' is now wrong")
        self.assertIn("NO_OUTPUT", _SEVERITY,
                      "NO_OUTPUT left the severity table the prose ranks it in")

    def test_no_output_is_documented_as_ranked_next_to_FAIL(self):
        # The ranking claim in prose, checked against the table itself:
        # NO_OUTPUT must sit immediately after FAIL, above every verdict a
        # solution can earn on its own merits.
        self.assertEqual(_SEVERITY[:2], ["FAIL", "NO_OUTPUT"], _SEVERITY)
        self.assertIn("NO_OUTPUT", self.text("validating-solutions"))


class TestFormatFieldDocs(unittest.TestCase):
    """`shaping-problems` quotes `problem.json`'s `format` values and its
    inference rule; both are pinned against the code rather than retyped."""

    def test_shaping_problems_names_the_accepted_values_from_the_source(self):
        # The prose quotes the closed set next to the name of the constant
        # it came from — pull the two quoted values back out and check them
        # against the constant itself, not against a second copy typed here.
        body = flatten(skill_text("shaping-problems"))
        match = re.search(
            r'`format`\*\* is `"(\w+)"` or `"(\w+)"` \(the closed set '
            r'`problem_meta\.FORMAT_VALUES`\)', body)
        self.assertIsNotNone(
            match, "shaping-problems no longer quotes the accepted "
                   "`format` values next to `problem_meta.FORMAT_VALUES`")
        self.assertEqual(match.groups(), FORMAT_VALUES,
                         "the format values quoted in shaping-problems have "
                         "drifted from problem_meta.FORMAT_VALUES")

    def test_shaping_problems_states_the_inference_rule(self):
        body = flatten(skill_text("shaping-problems"))
        self.assertIn(
            'more than one subtask reads as `"oi"`, one (or none) reads '
            'as `"icpc"`', body,
            "shaping-problems dropped the format inference rule")

    def test_creating_problems_g1_list_includes_format(self):
        body = flatten(skill_text("creating-problems"))
        self.assertIn("G1 — idea, story, subtasks, format.", body,
                      "creating-problems' G1 summary no longer lists "
                      "format among what the gate settles")


class TestMultiTestAndKillPolicyDocs(unittest.TestCase):
    """Two pieces of doctrine keyed on `format`, split across two skills.

    The small-`T` file and the OI kill policy are the same argument seen
    from two ends — a ladder that pays partial credit must leave something
    for a slightly-slow solution to score on — so the two skills state it in
    the two places the decision is actually made (`shaping-problems` picks
    the numbers, `creating-problems` decides the zoo's expectations). Both
    halves are pinned, because a half deleted on its own reads as complete.
    """

    SECTION = "## Kill policy, by format"

    def kill_policy_section(self) -> str:
        text = skill_text("creating-problems")
        start = text.find(self.SECTION)
        self.assertNotEqual(
            start, -1,
            f"creating-problems has no {self.SECTION!r} section — the kill "
            f"policy is the only place the zoo's expectations are decided "
            f"per format")
        end = text.find("\n## ", start + len(self.SECTION))
        return text[start:end if end != -1 else len(text)]

    def test_both_skills_state_the_small_T_file(self):
        # The one test file that makes the OI ladder pay what it promises. It
        # is stated in both skills on purpose (skills load independently,
        # there is no include mechanism), which is why it needs a test
        # holding the two copies together.
        phrase = "one file with a small `T`"
        for skill in ("shaping-problems", "creating-problems"):
            with self.subTest(skill=skill):
                body = flatten(skill_text(skill))
                # `assertTrue`, not `assertIn`: the container is a whole
                # normalized skill, and unittest would render all of it.
                self.assertTrue(
                    phrase in body,
                    f"{skill} no longer states the `T` protocol's "
                    f"{phrase!r} — without it an OI package times every "
                    f"rung out at T = X and pays no partial credit at all.")

    def test_creating_problems_states_a_kill_policy_for_every_format(self):
        # The bullet markers are read back out of the section and checked
        # against the constant, not against a second copy of the two values
        # typed here: a format added to FORMAT_VALUES with no kill policy
        # written for it must fail this, and so must a renamed one.
        section = self.kill_policy_section()
        found = re.findall(r"^- \*\*`(\w+)`\*\*", section, re.MULTILINE)
        self.assertEqual(
            sorted(found), sorted(FORMAT_VALUES),
            f"creating-problems' kill policy covers {sorted(found)}; "
            f"problem_meta.FORMAT_VALUES is {sorted(FORMAT_VALUES)}. Every "
            f"accepted format needs its own policy — the zoo's `@expect` "
            f"lines are written from it.")

    def test_the_kill_policy_points_at_the_matrix_not_a_manual_sweep(self):
        # `run_matrix` is the enforcement, and `holes` is how a violation
        # surfaces. Prose describing a second manual pass over every
        # solution × every stronger group is prose telling a setter to
        # re-run, by hand, the one thing the tooling already does.
        section = flatten(self.kill_policy_section())
        for term in ("`@expect`", "`run_matrix`", "`holes`"):
            with self.subTest(term=term):
                self.assertTrue(
                    term in section,
                    f"the kill policy no longer names {term}, the mechanism "
                    f"that actually enforces subtask separation")


class TestShapingProblemsMissionLineJudgementCount(unittest.TestCase):
    """`shaping-problems`' mission line states how many judgements the gate
    makes and lists them in order. The `## Multi-test input and the T
    protocol` section was added as its own peer gate decision — sitting
    between the subtask ladder and the JSON hand-off — and the stated count
    went stale the moment that section landed without the mission line being
    updated alongside it.

    Rather than pin a second literal copy of the number (which drifts the
    same way the first one did), this counts the `##` sections that fall
    between the first judgement (`Originality`) and the section that closes
    the gate out (`Done means`) — that span is exactly the judgements the
    mission line claims to enumerate, so a section inserted or removed
    inside it changes the count this test checks against automatically.
    """

    SKILL = "shaping-problems"
    FIRST_JUDGEMENT_SECTION = "## Originality — before anything else"
    # Not itself a judgement — the check that closes the gate out — so it
    # marks where the judgement span ends rather than being counted in it.
    POST_JUDGEMENT_SECTION = "## Done means"

    _NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                      "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

    def _judgement_sections(self) -> list[str]:
        text = skill_text(self.SKILL)
        start = text.find(self.FIRST_JUDGEMENT_SECTION)
        end = text.find(self.POST_JUDGEMENT_SECTION)
        self.assertNotEqual(
            start, -1,
            f"{self.SKILL} no longer has a {self.FIRST_JUDGEMENT_SECTION!r} "
            f"section — the judgement span this test counts starts there")
        self.assertNotEqual(
            end, -1,
            f"{self.SKILL} no longer has a {self.POST_JUDGEMENT_SECTION!r} "
            f"section — the judgement span this test counts ends there")
        self.assertLess(
            start, end,
            f"{self.FIRST_JUDGEMENT_SECTION!r} must come before "
            f"{self.POST_JUDGEMENT_SECTION!r} for the span between them to "
            f"mean anything")
        return re.findall(r"^## .+$", text[start:end], re.MULTILINE)

    def test_stated_count_matches_the_number_of_judgement_sections(self):
        sections = self._judgement_sections()
        body = flatten(skill_text(self.SKILL))
        match = re.search(r"\. (\w+) judgements, in order:", body)
        self.assertIsNotNone(
            match,
            f"{self.SKILL} no longer states '<N> judgements, in order:' in "
            f"its mission line — the count this test pins against is gone")
        word = match.group(1).lower()
        self.assertIn(
            word, self._NUMBER_WORDS,
            f"{word!r} is not a number word this test knows how to check")
        self.assertEqual(
            self._NUMBER_WORDS[word], len(sections),
            f"the mission line claims {word!r} judgements, but "
            f"{len(sections)} sections sit between "
            f"{self.FIRST_JUDGEMENT_SECTION!r} and "
            f"{self.POST_JUDGEMENT_SECTION!r} ({sections}) — a section was "
            f"added or removed without updating the count, or the count was "
            f"changed without the sections it describes")


class TestWritingStatementsRoutingTable(unittest.TestCase):
    """The routing table `writing-statements` carries, pinned to the things
    outside it that it names.

    That file spent two stages as the terminus of every "the prose belongs
    elsewhere" row in the other skills' boundary tables, with no table of its
    own and no statement of where control went next. The table it now carries
    names sibling skills and `PHASE_ORDER` phases — both of which live in
    other files and can be renamed by someone who never opens this one. A
    table naming a skill that cannot be loaded is worse than no table at all:
    a router that finds nothing falls back to asking, while a router handed a
    dead name follows it.

    Every assertion below reads the filesystem or imports from
    `package_status`, so it fails on a rename rather than on a second copy of
    the same prose kept in this file.
    """

    SKILL = "writing-statements"
    SECTIONS = ("## Am I the right skill?", "## Two passes, and where each one exits")

    # Named in the `Use` column of the boundary table.
    TABLE_NEIGHBOURS = ("shaping-problems", "preparing-tests",
                        "reviewing-problems", "creating-problems",
                        "solving-problems")
    # Named in the routing prose but not offered as a pre-load alternative.
    ALSO_REFERENCED = ("validating-solutions",)

    # The reciprocal direction. "check my statement" appears verbatim in
    # `reviewing-problems`' own description, so a router can land there for a
    # request that means `writing-statements` — and mediating the collision
    # from one side only leaves the other side with no prompt to ask at all.
    # `(skill, boundary-table heading)`.
    RECIPROCAL = ("reviewing-problems", "## Am I the right skill?")

    # Phases the exit prose names, in the order it claims they run.
    CLAIMED_PHASE_ORDER = ("statement", "constraints_header", "model_solution")

    def body(self, skill: str | None = None) -> str:
        skill = skill or self.SKILL
        text = skill_text(skill)
        # Extractor guard: an empty or truncated read would make several
        # assertions below trivially pass.
        self.assertGreater(len(text), 4000,
                           f"{skill}/SKILL.md read back nearly empty")
        return text

    def section(self, heading: str, skill: str | None = None) -> str:
        skill = skill or self.SKILL
        text = self.body(skill)
        start = text.find(heading)
        self.assertNotEqual(start, -1, f"{skill} has no {heading!r} section")
        end = text.find("\n## ", start + len(heading))
        return text[start:end if end != -1 else len(text)]

    def use_cells(self, skill: str | None = None,
                  heading: str | None = None) -> list[str]:
        """The right-hand column of the boundary table, header and rule
        dropped."""
        rows = []
        for line in self.section(heading or self.SECTIONS[0], skill).splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) != 2 or set(cells[0]) <= set("-: "):
                continue
            if cells == ["If it's really about", "Use"]:
                continue
            rows.append(cells[1])
        return rows

    def test_the_boundary_table_parses_into_rows(self):
        # Guard for every table assertion below: a heading with no table
        # under it, or a parser that matched nothing, would make them vacuous.
        self.assertGreaterEqual(
            len(self.use_cells()), 4,
            f"{self.SKILL}'s boundary table did not parse into rows — either "
            f"the table was removed or its shape changed")

    def test_every_use_cell_names_a_skill_that_exists_on_disk(self):
        real = skill_dirs()
        for cell in self.use_cells():
            names = re.findall(r"competitive-programming:([a-z][a-z-]*)", cell)
            with self.subTest(row=cell):
                self.assertTrue(
                    names,
                    f"{self.SKILL}: boundary table row routes somewhere "
                    f"unnamed — every `Use` cell must name a "
                    f"`competitive-programming:<skill>` destination")
                for name in names:
                    self.assertIn(
                        name, real,
                        f"{self.SKILL}'s boundary table routes to "
                        f"{name!r}, which is not a skill directory. Skills "
                        f"on disk: {sorted(real)}")

    def test_the_table_offers_every_neighbour_a_statement_request_can_mean(self):
        cells = " ".join(self.use_cells())
        real = skill_dirs()
        for name in self.TABLE_NEIGHBOURS:
            with self.subTest(neighbour=name):
                self.assertIn(name, real,
                              f"{name} is no longer a skill directory — the "
                              f"routing table and this list both need updating")
                self.assertIn(f"competitive-programming:{name}", cells,
                              f"{self.SKILL}'s boundary table dropped the row "
                              f"routing to {name}")

        # And the same offer, back the other way. `reviewing-problems` claims
        # "check my statement" verbatim in its own description, so it is a
        # live destination for a request that means this skill; a router that
        # lands there must be prompted to ask, exactly as one that lands here
        # is prompted about `reviewing-problems`. The fix for that collision
        # shipped in one direction only, and nothing was watching the other.
        back_skill, back_heading = self.RECIPROCAL
        self.assertIn(back_skill, real,
                      f"{back_skill} is no longer a skill directory")
        back_rows = self.use_cells(back_skill, back_heading)
        # Same vacuity guard as `test_the_boundary_table_parses_into_rows`:
        # a heading with no table under it must not pass silently.
        self.assertGreaterEqual(
            len(back_rows), 3,
            f"{back_skill}'s boundary table under {back_heading!r} did not "
            f"parse into rows — the table was removed or its shape changed")
        self.assertIn(
            f"competitive-programming:{self.SKILL}", " ".join(back_rows),
            f"{back_skill}'s boundary table has no row routing back to "
            f"{self.SKILL}, so the 'check my statement' collision — which "
            f"{back_skill}'s own description claims verbatim — is mediated "
            f"in one direction only")

    def test_no_stale_skill_name_survives_anywhere_in_the_file(self):
        # Bare backticked names in the exit prose (`preparing-tests`,
        # `solving-problems`, ...) are not caught by the table check above.
        # A token shaped like one of this plugin's skill names must be one:
        # `sol-main`, `gen-max`, `ff-only` and `kitchen-sink` do not match,
        # because their prefixes are not skill-name prefixes.
        real = skill_dirs()
        prefixes = {name.split("-")[0] for name in real}
        shaped = re.compile(r"`((?:%s)-[a-z]+)`" % "|".join(sorted(prefixes)))
        found = set(shaped.findall(self.body()))
        self.assertTrue(found, f"{self.SKILL} names no sibling skill at all")
        for name in sorted(found):
            with self.subTest(reference=name):
                self.assertIn(name, real,
                              f"{self.SKILL} refers to `{name}`, which is not "
                              f"a skill directory")

    def test_every_referenced_skill_is_loadable(self):
        real = skill_dirs()
        text = self.body()
        for name in self.TABLE_NEIGHBOURS + self.ALSO_REFERENCED:
            with self.subTest(skill=name):
                self.assertIn(name, real, f"{name} is not a skill directory")
                self.assertIn(f"`{name}`", text,
                              f"{self.SKILL} no longer names {name}, which its "
                              f"routing depends on")

    def test_the_exit_prose_names_phases_the_driver_actually_has(self):
        prose = self.section(self.SECTIONS[1])
        for phase in self.CLAIMED_PHASE_ORDER + ("samples",):
            with self.subTest(phase=phase):
                self.assertIn(phase, PHASE_ORDER,
                              f"{phase!r} left package_status.PHASE_ORDER")
                self.assertIn(f"`{phase}`", prose,
                              f"{self.SKILL}'s exit prose no longer names the "
                              f"{phase!r} phase")

    def test_the_claimed_phase_sequence_matches_PHASE_ORDER(self):
        # The exact failure this branch has already shipped once: a skill
        # enumerating the phases in an order the driver does not use. The
        # prose claims statement -> constraints_header -> model_solution, and
        # that `samples` is the pipeline's last phase.
        indices = [PHASE_ORDER.index(p) for p in self.CLAIMED_PHASE_ORDER]
        self.assertEqual(
            indices, sorted(indices),
            f"{self.SKILL} claims the phases run in the order "
            f"{self.CLAIMED_PHASE_ORDER}, but PHASE_ORDER is {PHASE_ORDER}")
        self.assertEqual(
            PHASE_ORDER[-1], "samples",
            f"{self.SKILL} says the samples pass is the last phase before the "
            f"audit; PHASE_ORDER now ends with {PHASE_ORDER[-1]!r}")

    def test_the_statement_ambiguity_stop_is_not_reopened(self):
        # Stage 2 shipped `creating-problems` drawing this as a STOP while
        # `validating-solutions` routed onward to `writing-statements` and
        # kept going. All four documents must keep saying the same thing, and
        # the newest one is the one pointed at.
        agree = {
            "writing-statements":
                "is a STOP, and it does not route here",
            "validating-solutions":
                "Do **not** hand off to `writing-statements` and carry on "
                "validating",
            "reviewing-problems": "## The one hard stop",
            "creating-problems": "STOP: unresolvable HIGH",
        }
        for skill, claim in agree.items():
            with self.subTest(skill=skill):
                self.assertIn(
                    claim, flatten(skill_text(skill)),
                    f"{skill} no longer states the unresolvable HIGH "
                    f"statement-ambiguity stop the same way the other three "
                    f"do. This single edge is what the gate model hangs on — "
                    f"fix the disagreement, do not relax this test.")


class TestParallelSafetyDocs(unittest.TestCase):
    """`run_matrix` stopped deriving box ids from `pid` (Tasks 1-5): it now
    leases them from a per-user pool and runs pass 2 concurrently. The old
    "run it alone" warning trained readers to serialise work that no longer
    needs it, and a stale safety warning is worse than none — these guard
    against it creeping back in.

    Pinned against the code's own names, not string literals copied from
    prose: renaming `box_pool.POOL_ENV`/`LOCK_DIR_ENV` or the
    `"retimed_serially"` payload key should fail these tests, the same way
    `test_prose_names_the_drivers_real_staged_stdout_file` above is pinned
    to `run_matrix.STAGED_STDOUT_NAME` rather than a copy of the string.
    """

    def test_readme_no_longer_claims_the_tools_are_serial_only(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("not parallel-safe", readme)
        self.assertIn(box_pool.POOL_ENV, readme)
        self.assertIn(box_pool.LOCK_DIR_ENV, readme)

    def test_validating_solutions_documents_the_worker_knob(self):
        skill = skill_text("validating-solutions")
        self.assertIn(box_pool.POOL_ENV, skill)
        self.assertIn("retimed_serially", skill)
        # The payload field the doc's promise actually depends on: a reader
        # parsing invocation.json needs this exact key to still exist.
        self.assertIn('"retimed_serially"', inspect.getsource(run_matrix),
                      "run_matrix.py no longer writes a literal "
                      "'retimed_serially' payload key; the docs still "
                      "promise readers can look for one")


class TestTestGenerationReference(unittest.TestCase):
    """`preparing-tests` delegates its generator-design doctrine to a
    reference file, the same way `solving-problems` delegates the black-magic
    toolbox and `running-contests` the judge registry.

    A pointer to a file that does not exist reads as authoritative and
    delivers nothing, so the pointer and the file are pinned to each other.
    The seven sections are pinned in order: they are a sequence — kill policy
    decides what the rest of the doctrine is even for — and a section quietly
    dropped from the middle would otherwise leave the pointer's one-sentence
    summary promising content that is gone.
    """

    REFERENCE = SKILLS / "preparing-tests" / "references" / "test-generation.md"
    POINTER = "references/test-generation.md"

    # A stable phrase from each section, in the order the file must carry
    # them. Matched against the flattened text, since these files are
    # hard-wrapped and a heading's neighbours move whenever a paragraph above
    # them is reflowed.
    SECTIONS = (
        "## Kill policy by format",
        "## Subtask separation",
        "## Parameter saturation",
        "## Brute-kill table",
        "## Shape catalogue",
        "## Corners present but rare",
        "## Multi-test `T` policy",
    )

    # Claims inside those sections that the brief's correctness turns on, and
    # which a later editor could plausibly "simplify" back into being wrong.
    CLAIMS = (
        # OI-style partial credit is the half that gets lost first.
        '"Kill everything" is wrong here',
        # The undersized-group leak, stated concretely.
        "never exceed `n = 5000`",
        # Saturation and the reaching check are different properties.
        "Saturation is not the reaching check",
        # The fork claimed a random tree is ~log N tall. Both facts, and the
        # conclusion that a bamboo is needed regardless, are load-bearing.
        "has height `Θ(√N)`",
        "a bamboo is required either way",
        # The one rule that cannot be softened into a convenience.
        "Never invent a Σ-constraint the statement does not state",
    )

    def body(self) -> str:
        self.assertTrue(self.REFERENCE.is_file(),
                        f"{self.REFERENCE} is missing, but "
                        f"preparing-tests/SKILL.md tells the reader to open it")
        text = self.REFERENCE.read_text(encoding="utf-8")
        # Extractor guard, as elsewhere in this module: a truncated read must
        # not make the ordering assertion below trivially pass.
        self.assertGreater(len(text), 1000,
                           f"{self.REFERENCE} read back nearly empty")
        return text

    def test_the_skill_points_at_the_reference(self):
        self.assertIn(self.POINTER, flatten(skill_text("preparing-tests")),
                      "preparing-tests/SKILL.md no longer sends the reader to "
                      "the generator-design reference before it lists the "
                      "five families")

    def test_the_reference_carries_every_section_in_order(self):
        text = self.body()
        positions = []
        for heading in self.SECTIONS:
            with self.subTest(section=heading):
                # `assertNotEqual` on `find`, not `assertIn`: an assertIn
                # failure would print the whole reference around the one
                # heading that is missing.
                where = text.find(heading)
                self.assertNotEqual(
                    where, -1,
                    f"{self.REFERENCE.name} no longer carries the "
                    f"{heading!r} section, which SKILL.md's pointer promises")
                positions.append(where)
        self.assertEqual(
            positions, sorted(positions),
            f"the sections of {self.REFERENCE.name} have been reordered; "
            f"the doctrine reads as a sequence, so keep them in the order "
            f"{list(self.SECTIONS)}")

    def test_the_corrected_claims_survive(self):
        flat = flatten(self.body())
        for claim in self.CLAIMS:
            with self.subTest(claim=claim):
                self.assertTrue(
                    flatten(claim) in flat,
                    f"{self.REFERENCE.name} no longer states {claim!r}. Each "
                    f"of these is a correction over the doctrine as it was "
                    f"first written — fix the prose, do not relax this test.")

    def test_the_reference_reinforces_the_reaching_check(self):
        # The doctrine this reference was adapted from downgraded the
        # reaching check to optional. Pinned positively — the sentence that
        # hands authority back to SKILL.md's loop — rather than as a
        # blacklist of softening words: a substring guard that also fires on
        # a future *true* sentence gets deleted rather than obeyed, which is
        # the lesson RETIRED_CLAIMS above is annotated with.
        self.assertIn(
            "treat its output as the answer", flatten(self.body()),
            f"{self.REFERENCE.name} no longer defers to SKILL.md's "
            f"reaching-check loop as the authority on which bounds are "
            f"reached. Saturation is a design target; the union of the "
            f"per-test logs is the evidence, and the reference must not "
            f"leave a reader thinking the first substitutes for the second.")

    def test_the_reference_does_not_grow_its_own_copy_of_the_recipe(self):
        # The recipe is pinned byte-for-byte between two SKILL.md files by
        # TestReachingCheckRecipeDoesNotDrift. A third copy here would drift
        # out from under that pin, since nothing would be holding it. Scoped
        # to ```bash blocks — the same shape `recipe()` uses — so that prose
        # naming the flag, which the reference legitimately does, is fine.
        for block in [m.group("body")
                      for m in _FENCE.finditer(self.body())
                      if m.group("lang") == "bash"]:
            self.assertNotIn(
                "--testOverviewLogFileName", block,
                f"{self.REFERENCE.name} carries a runnable copy of the "
                f"reaching-check recipe. That recipe is pinned "
                f"byte-for-byte between preparing-tests and "
                f"reviewing-problems; a third copy is held by nothing. "
                f"Link to ../SKILL.md#reaching-check instead.")


class TestBootstrapTestlibDocs(unittest.TestCase):
    """The README's testlib paragraph promises two things a reader might
    act on: that `CP_TESTLIB` skips cloning, and that `python3 -m
    tools.bootstrap_testlib` is the portable entry point `bootstrap_testlib.
    sh` wraps. Pinned against the module's own env-var constants rather than
    copies of the strings, so a rename doesn't leave the README describing a
    variable that no longer does anything.
    """

    def test_readme_documents_cp_testlib_and_the_portable_entry_point(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(bootstrap_testlib.CP_TESTLIB_ENV, readme)
        self.assertIn("python3 -m tools.bootstrap_testlib", readme)


if __name__ == "__main__":
    unittest.main()


class TestReadmeLayoutMatchesDisk(unittest.TestCase):
    """The root README's layout tree is a claim about what is on disk.

    It drifted once already: `tools/box_pool.py` was added, discussed at
    length in the README's own prose, and never entered the tree. Nothing
    held the two together, so this does.
    """

    README = (ROOT / "README.md").read_text(encoding="utf-8")

    def _layout_block(self) -> str:
        blocks = [m.group("body") for m in _FENCE.finditer(self.README)
                  if "competitive-programming/" in m.group("body")]
        self.assertEqual(len(blocks), 1, "expected exactly one layout tree in README.md")
        return blocks[0]

    def test_every_tools_module_is_in_the_layout_tree(self):
        tree = self._layout_block()
        modules = sorted(p.name for p in (ROOT / "tools").iterdir()
                         if p.suffix in {".py", ".sh"} and p.name != "__init__.py")
        self.assertTrue(modules)
        missing = [m for m in modules if m not in tree]
        self.assertEqual(missing, [], f"tools files absent from README layout: {missing}")

    def test_every_skill_directory_is_in_the_layout_tree(self):
        tree = self._layout_block()
        skills = sorted(p.name for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())
        self.assertEqual(len(skills), 11)
        missing = [s for s in skills if f"{s}/SKILL.md" not in tree]
        self.assertEqual(missing, [], f"skills absent from README layout: {missing}")

    def test_the_layout_tree_names_nothing_that_is_not_on_disk(self):
        tree = self._layout_block()
        named = re.findall(r"\b([a-z_]+\.(?:py|sh))\b", tree)
        ghosts = [n for n in named if not (ROOT / "tools" / n).exists()
                  and not (ROOT / "mcp-server" / n).exists()]
        self.assertEqual(ghosts, [], f"README layout names files that do not exist: {ghosts}")


class TestServerEnvTableMatchesConfig(unittest.TestCase):
    """The root README says `mcp-server/README.md` owns the environment-variable
    table and `.env.example` mirrors it. Both are claims about `config.py`, which
    is the only thing that actually reads the environment, so check all three
    against each other. `CF_MCP_TIMEOUT` had been read by config.py and listed in
    `.env.example` while absent from the README table.
    """

    SERVER = ROOT / "mcp-server"
    CONFIG = (SERVER / "src" / "cf_mcp" / "config.py").read_text(encoding="utf-8")
    README = (SERVER / "README.md").read_text(encoding="utf-8")
    ENV_EXAMPLE = (SERVER / ".env.example").read_text(encoding="utf-8")

    _NAME = r"(?:CODEFORCES|CF_MCP|CF)_[A-Z_]+"

    def _config_names(self) -> set[str]:
        return set(re.findall(rf'"({self._NAME})"', self.CONFIG))

    def _table_names(self) -> set[str]:
        return set(re.findall(rf"^\| `({self._NAME})` \|", self.README, re.MULTILINE))

    def _env_example_names(self) -> set[str]:
        return set(re.findall(rf"^#? ?({self._NAME})=", self.ENV_EXAMPLE, re.MULTILINE))

    def test_every_name_config_reads_is_mentioned_in_the_server_readme(self):
        missing = sorted(n for n in self._config_names() if n not in self.README)
        self.assertEqual(missing, [], f"config.py reads variables the README never mentions: {missing}")

    def test_the_readme_table_and_env_example_list_the_same_variables(self):
        self.assertEqual(self._table_names(), self._env_example_names())

    def test_the_readme_table_lists_only_variables_config_reads(self):
        ghosts = sorted(self._table_names() - self._config_names())
        self.assertEqual(ghosts, [], f"README documents variables config.py does not read: {ghosts}")


class TestP5ProseFixesPin(unittest.TestCase):
    """Three one-paragraph facts adapted from a fork's prose, pinned so a
    later rewrite of the surrounding section cannot silently drop the fact
    along with the prose around it. These are knowledge pins, not code
    pins — there is no importable value to check them against — so each
    one pins a distinctive clause of the actual sentence rather than a
    paraphrase."""

    def test_preparing_tests_states_the_unknown_group_defence(self):
        flat = flatten(skill_text("preparing-tests"))
        self.assertIn(
            "it silently skips the subtask-specific bound, and the "
            "under-checked test sails through Polygon validation",
            flat,
            "preparing-tests no longer states what an unguarded `if` on "
            "the wrong group spelling costs (a silent skip, not a "
            "rejection)")
        self.assertIn(
            "testlib's `_fail`, exit code 3", flat,
            "preparing-tests no longer states what an `else`-guarded "
            "branch on the wrong group spelling costs (an outright "
            "package rejection)")
        self.assertIn(
            "accepting both spellings for the same group", flat,
            "preparing-tests no longer prescribes accepting both the "
            "`g1` spelling and the bare-number spelling of a group")

    def test_writing_statements_states_explanations_never_argue(self):
        flat = flatten(skill_text("writing-statements"))
        self.assertIn(
            "an explanation that argues is an editorial leaking into "
            "the statement",
            flat,
            "writing-statements no longer states that a sample "
            "\\Explanation must describe rather than argue")

    def test_validating_solutions_states_the_zoo_strength_rule(self):
        flat = flatten(skill_text("validating-solutions"))
        self.assertIn(
            "the new class can never surface a hole the stronger one "
            "wouldn't already have found",
            flat,
            "validating-solutions no longer forbids a time-limit-exceeded "
            "entry strictly weaker than one already in the zoo")


class TestManifestDescriptionsAgree(unittest.TestCase):
    """The two manifests carry the same sentence, and nothing held them there.

    This is the same failure this module was written for: two copies with no
    mechanism between them, and the half that drifts is the one the next
    editor did not have open. Here the half nobody opens is
    `marketplace.json`, which is the copy every prospective user reads.
    """

    def test_both_manifests_spell_the_description_the_same_way(self):
        described = manifest_descriptions()
        self.assertGreater(len(described["plugin.json"]), 100,
                           "plugin.json's description read back nearly empty")
        self.assertEqual(described["plugin.json"], described["marketplace.json"],
                         "plugin.json and marketplace.json describe the plugin "
                         "differently; they are meant to be one sentence kept "
                         "in two places")

    def test_both_manifests_mention_polygon(self):
        # The plugin bundles two MCP servers now, not one; the description
        # must say so or the marketplace listing undersells the Polygon
        # server the same way it once undersold the editorial skill. Match
        # the two-servers clause specifically ("one for Polygon"), not a
        # bare "Polygon" substring — that already appeared in the stale
        # description via "Polygon-ready package" and would never catch
        # regressing back to "the bundled Codeforces MCP server".
        described = manifest_descriptions()
        for manifest, description in described.items():
            with self.subTest(manifest=manifest):
                self.assertIn(
                    "one for Polygon", description,
                    f"{manifest}'s description no longer says one of the "
                    "bundled MCP servers is for Polygon")


class TestWritingEditorialsSkill(unittest.TestCase):
    """`writing-editorials` is the one skill nothing in the pipeline calls.

    Every other skill is reached from `creating-problems`, so a phase that
    stopped loading would surface the next time a package was built. This one
    is opt-in: it runs only when a conversation asks for an editorial, and a
    broken `name:`, a lost theme file, or a description that stopped saying
    "only when asked" would be discovered by nobody — the failure mode is
    either silence or an editorial written after a package the user never
    asked to have explained.

    The slot pins below are the same shape as
    `test_prose_names_the_drivers_real_staged_stdout_file`: the prose names
    markers in a file that lives next to it, so the file is what they are
    checked against.
    """

    SKILL = "writing-editorials"
    DIR = SKILLS / SKILL
    THEME = DIR / "references" / "themes" / "space-dark.html"
    GLOSSARY = DIR / "references" / "vi-glossary.md"

    # The page frame the SKILL.md documents, as it appears in the theme file.
    # A slot the skill tells the writer to fill has to be there to fill.
    SLOTS = (
        "<!-- PROBLEM_NAME -->", "TIME_LIMIT", "MEMORY_LIMIT",
        "EXPECTED_RATING", 'class="tag"', 'id="statement"', 'id="tutorial"',
        'id="complexity"', 'id="other"', 'id="fun"', 'class="subtask"',
        'class="toc"', 'class="problem"',
    )

    def body(self) -> str:
        text = skill_text(self.SKILL)
        # Extractor guard, as elsewhere in this module: a truncated read would
        # make the "no stale skill name" assertion below trivially pass.
        self.assertGreater(len(text), 4000,
                           f"{self.SKILL}/SKILL.md read back nearly empty")
        return text

    def frontmatter(self) -> str:
        text = self.body()
        match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
        self.assertIsNotNone(match, f"{self.SKILL}/SKILL.md has no frontmatter")
        return match.group(1)

    def description_lines(self) -> list[str]:
        """The folded `description: >` block, one entry per source line."""
        lines = self.frontmatter().splitlines()
        start = next((i for i, l in enumerate(lines)
                      if l.startswith("description:")), None)
        self.assertIsNotNone(start, "the frontmatter has no `description:` key")
        out = []
        for line in lines[start + 1:]:
            if line and not line[0].isspace():   # the next top-level key
                break
            out.append(line.strip())
        self.assertTrue(out, "the `description:` block is empty")
        return out

    def test_the_skill_ships_its_default_theme_and_glossary(self):
        # The skill copies the theme verbatim and reads the glossary before
        # writing Vietnamese. Neither is optional, and neither is generated.
        for path in ((self.DIR / "SKILL.md"), self.THEME, self.GLOSSARY):
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file(), f"{path} is missing")
        self.assertIn(self.SKILL, skill_dirs(),
                      f"{self.SKILL} is not loadable as a skill directory")

    def test_the_frontmatter_name_matches_the_directory(self):
        # A `name:` that disagrees with its directory does not fail loudly —
        # the skill simply is not there under the name everything else uses.
        match = re.search(r"^name:\s*(\S+)\s*$", self.frontmatter(), re.MULTILINE)
        self.assertIsNotNone(match, "the frontmatter has no `name:` key")
        self.assertEqual(match.group(1), self.DIR.name)

    def test_the_description_says_the_skill_runs_only_when_asked(self):
        # The opt-in rule lives in the description because that is the only
        # part of the file a router reads. Lose it there and the skill starts
        # firing off the end of a finished package, which is the exact
        # behaviour it exists to refuse.
        flat = flatten(" ".join(self.description_lines()))
        self.assertIn("Use ONLY when this conversation explicitly asks", flat)
        self.assertIn("editorial.html", flat)
        self.assertIn("creating-problems is not", flat,
                      "the description no longer refuses to run off the end "
                      "of a finished package")
        self.assertLessEqual(
            len(self.description_lines()), 6,
            "the description grew past six lines; routing reads it in full "
            "on every request, so it is kept short deliberately")

    def test_every_slot_the_skill_documents_exists_in_the_default_theme(self):
        skill = self.body()
        theme = self.THEME.read_text(encoding="utf-8")
        self.assertGreater(len(theme), 4000, f"{self.THEME} read back empty")
        for slot in self.SLOTS:
            with self.subTest(slot=slot):
                # `assertTrue`, not `assertIn` — the containers here are a
                # whole SKILL.md and a whole theme file, and unittest would
                # print both around the one marker that matters.
                self.assertTrue(
                    slot in theme,
                    f"the default theme no longer carries the {slot!r} slot "
                    f"that {self.SKILL} tells the writer to fill")
        for marker in ("PROBLEM_NAME", "TIME_LIMIT", "MEMORY_LIMIT",
                       "EXPECTED_RATING"):
            with self.subTest(marker=marker):
                self.assertTrue(
                    marker in skill,
                    f"{self.SKILL} stopped naming the {marker!r} slot, so its "
                    f"page-frame table no longer describes the theme it ships")

    def test_no_retired_transformation_box_survives(self):
        # Transformation was retired as a box type: a pivotal transformation
        # is an Observation, a routine one is prose. A `.card.transform` rule
        # left in the theme is an invitation to author one anyway.
        self.assertNotIn("card.transform", self.THEME.read_text(encoding="utf-8"))
        self.assertIn("no Transformation box", self.body())

    def test_the_skill_routes_only_to_skills_that_exist(self):
        # Same failure as the `writing-statements` routing table guards
        # against: a router handed a dead name follows it, while one that
        # finds nothing falls back to asking.
        real = skill_dirs()
        named = set(re.findall(r"competitive-programming:([a-z][a-z-]*)",
                               self.body()))
        self.assertTrue(named, f"{self.SKILL} names no sibling skill at all")
        for name in sorted(named):
            with self.subTest(destination=name):
                self.assertIn(
                    name, real,
                    f"{self.SKILL} routes to {name!r}, which is not a skill "
                    f"directory. Skills on disk: {sorted(real)}")

    def test_the_limit_keys_the_skill_quotes_are_the_ones_problem_meta_reads(self):
        # The skill tells the writer to fill the header from
        # `limits.time_ms_published` and `limits.memory_mb`. Those names are
        # `problem_meta.Problem` fields, not string literals to be copied:
        # renaming one there must fail here rather than leaving the skill
        # instructing a reader to look up a key that no longer exists.
        fields = problem_meta.Problem.__dataclass_fields__
        skill = self.body()
        for key in ("time_ms_published", "memory_mb"):
            with self.subTest(key=key):
                self.assertIn(key, fields,
                              f"{key!r} left problem_meta.Problem")
                self.assertTrue(
                    f"`limits.{key}`" in skill,
                    f"{self.SKILL} no longer names `limits.{key}`, the field "
                    f"its header is filled from")

    def test_the_answer_extension_the_skill_diffs_against_is_the_driver_s(self):
        # `sol-editorial.cpp` is verified by diffing against the jury's `.a`
        # answer files. That suffix is `run_matrix`'s, not this skill's, and
        # a reader following the instruction against a renamed extension
        # would diff against nothing and see a clean run.
        self.assertIn('.with_suffix(".a")', inspect.getsource(run_matrix),
                      "run_matrix.py no longer writes `.a` answer files; the "
                      "editorial skill still tells readers to diff against one")
        self.assertIn("`.a` answer file", self.body())

    def test_the_readme_counts_this_skill(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"competitive-programming:{self.SKILL}", readme,
                      "the README component table has no row for this skill")
        self.assertIn("eleven skills", readme,
                      "the README intro still counts the skills without this one")
        self.assertIn("11 skills, 2 MCP servers", readme,
                      "the README's `claude plugin details` expectation counts "
                      "fewer skills than are on disk")

    def test_the_manifest_description_counts_this_skill(self):
        # The manifest description enumerates the plugin's capabilities one
        # clause per skill, and it is what a marketplace listing shows — the
        # externally visible twin of the README count above. It drifted
        # silently when this skill was added because nothing read it.
        for manifest, description in manifest_descriptions().items():
            with self.subTest(manifest=manifest):
                self.assertIn(
                    "editorial", description,
                    "the plugin description enumerates every skill but this "
                    "one, so the marketplace listing undersells the plugin")


class TestCalculatingDifficultiesSkill(unittest.TestCase):
    """`calculating-difficulties` is opt-in like `writing-editorials`, and it
    is worse off: its output is read by that other opt-in skill, so a break
    in either half of the handoff is discovered by nobody.

    Three things in it are claims about files beside it rather than prose.
    The output template's `Anchor placement` rows cite anchors by id with
    their printed rating, year and today rating; a reader copies that shape,
    so a template row whose anchor has left `anchors.md`, or whose today
    rating disagrees with Pass C.1's own discount table, teaches the wrong
    arithmetic by example. The gate quotes `package_status`'s matrix detail
    strings verbatim and tells the agent which to accept and which to
    reject — a detail reworded in the tool and not here turns the accept
    string into one nothing prints, and every package reads `not
    estimable`. And the `not estimable` handoff is spelled in two skills
    that load independently, which is exactly the duplication
    `TestReachingCheckRecipeDoesNotDrift` exists for.
    """

    SKILL = "calculating-difficulties"
    DIR = SKILLS / SKILL
    ANCHORS = DIR / "references" / "anchors.md"

    # An anchor id is a Codeforces contest number plus a problem index, which
    # may carry a digit (`1867E1`). Anything else in the first cell is the
    # header or the separator row, not an anchor.
    _ANCHOR_ID = re.compile(r"^\d+[A-Z]\d?$")

    def body(self) -> str:
        text = skill_text(self.SKILL)
        # Extractor guard: a truncated read would make every "names X"
        # assertion below fail for the wrong reason, or a "no row missing"
        # loop pass over nothing.
        self.assertGreater(len(text), 4000,
                           f"{self.SKILL}/SKILL.md read back nearly empty")
        return text

    def section(self, heading: str, text: str | None = None) -> str:
        """The body under `heading`, up to the next `## ` heading.

        Not up to any `#`: the output template and the failure branch are
        fenced Markdown documents whose own `# Estimated difficulty` would
        otherwise end the section inside its fence.
        """
        text = self.body() if text is None else text
        match = re.search(rf"^{re.escape(heading)}\n(.*?)(?=^## |\Z)", text,
                          re.DOTALL | re.MULTILINE)
        self.assertIsNotNone(match, f"{self.SKILL} has no {heading!r} section")
        return match.group(1)

    @staticmethod
    def table_rows(text: str) -> list[list[str]]:
        """Every body row of every pipe table in `text`, cells stripped.

        The header row is kept (callers filter on content), the `|---|`
        separator is not.
        """
        rows = []
        for line in text.splitlines():
            if not line.startswith("|") or re.match(r"^\|[\s|:-]+\|$", line):
                continue
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
        return rows

    def anchors(self) -> dict[str, tuple[int, int]]:
        """`anchors.md` as {id: (printed rating, year)}."""
        out: dict[str, tuple[int, int]] = {}
        for cells in self.table_rows(self.ANCHORS.read_text(encoding="utf-8")):
            if self._ANCHOR_ID.match(cells[0]):
                out[cells[0]] = (int(cells[1]), int(cells[2]))
        return out

    def era_discount(self) -> list[tuple[int, int, int]]:
        """Pass C.1's table as (first year, last year, discount) triples.

        Parsed from the skill rather than retyped, so this test checks the
        template against the table the reader is actually told to use.
        `2018 or earlier` is open below; no anchor predates Codeforces.
        """
        spans = []
        for cells in self.table_rows(self.section("## Pass C.1 — era correction")):
            years = re.fullmatch(r"(\d{4})-(\d{4})", cells[0])
            earlier = re.fullmatch(r"(\d{4}) or earlier", cells[0])
            discount = re.fullmatch(r"`(-?\d+)`", cells[1])
            if discount is None or not (years or earlier):
                continue
            lo, hi = ((int(years[1]), int(years[2])) if years
                      else (0, int(earlier[1])))
            spans.append((lo, hi, int(discount[1])))
        self.assertGreaterEqual(len(spans), 4,
                                "the Pass C.1 discount table did not parse")
        return spans

    def discount_for(self, year: int) -> int:
        hits = [d for lo, hi, d in self.era_discount() if lo <= year <= hi]
        self.assertEqual(len(hits), 1,
                         f"Pass C.1 gives {len(hits)} discounts for {year}; "
                         f"a year has to fall in exactly one row")
        return hits[0]

    def test_the_frontmatter_name_matches_the_directory(self):
        match = re.match(r"---\n(.*?)\n---\n", self.body(), re.DOTALL)
        self.assertIsNotNone(match, f"{self.SKILL}/SKILL.md has no frontmatter")
        name = re.search(r"^name:\s*(\S+)\s*$", match.group(1), re.MULTILINE)
        self.assertIsNotNone(name, "the frontmatter has no `name:` key")
        self.assertEqual(name.group(1), self.DIR.name)

    def test_every_anchor_row_parses_and_no_id_repeats(self):
        # Pass C reads this table by eye and `calibration/retrodict.py` by
        # parser. A row that parses for neither — a stray cell, a rating off
        # the 100-step grid, a year Codeforces never held — is an anchor the
        # placement silently cannot use, and a repeated id is two labels for
        # one problem with no rule for which to believe.
        text = self.ANCHORS.read_text(encoding="utf-8")
        ids = []
        for cells in self.table_rows(text):
            if not self._ANCHOR_ID.match(cells[0]):
                self.assertIn(cells[0], ("id",),
                              f"an anchors.md row has no parseable id: {cells}")
                continue
            ids.append(cells[0])
            with self.subTest(anchor=cells[0]):
                self.assertTrue(re.fullmatch(r"\d+", cells[1]),
                                f"rating cell is not an integer: {cells[1]!r}")
                self.assertTrue(re.fullmatch(r"\d{4}", cells[2]),
                                f"year cell is not a year: {cells[2]!r}")
                rating, year = int(cells[1]), int(cells[2])
                self.assertTrue(800 <= rating <= 3500 and rating % 100 == 0,
                                f"{rating} is not a Codeforces rating")
                self.assertTrue(2010 <= year <= 2026,
                                f"{year} is not a plausible round year")
        self.assertGreater(len(ids), 100, "anchors.md read back nearly empty")
        repeated = sorted({i for i in ids if ids.count(i) > 1})
        self.assertFalse(repeated, f"anchors.md lists {repeated} more than once")

    def test_the_template_anchor_rows_are_real_anchors_era_corrected(self):
        # The template is a worked example, and a worked example is copied
        # more faithfully than a rule is read. Every row has to be an anchor
        # that exists, with its real printed rating and year, and a today
        # column that is Pass C.1's formula applied to them — otherwise the
        # example teaches a correction the skill does not make.
        anchors = self.anchors()
        template = self.section("## Anchor placement")
        rows = [c for c in self.table_rows(template)
                if self._ANCHOR_ID.match(c[0])]
        self.assertGreaterEqual(len(rows), 2,
                                "the template's anchor table did not parse")
        for cells in rows:
            anchor, printed, year, today = cells[0], *map(int, cells[1:4])
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, anchors,
                              f"the template cites {anchor}, which is not in "
                              f"references/anchors.md")
                self.assertEqual((printed, year), anchors[anchor],
                                 f"the template's printed rating or year for "
                                 f"{anchor} disagrees with anchors.md")
                self.assertEqual(
                    today, printed + self.discount_for(year),
                    f"{anchor}: today {today} is not printed {printed} "
                    f"corrected by Pass C.1's discount for {year}")

    def test_the_gate_quotes_the_matrix_details_package_status_prints(self):
        # Driven through `_matrix` on a real fixture rather than grepped out
        # of its source: what matters is the string a reader will see, and a
        # detail assembled from an f-string is not in the source verbatim.
        # Fixture and staleness mechanics are `test_package_status`'s.
        fixture = Path(__file__).parent / "fixtures" / "mini"
        details = {}
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "p"
            shutil.copytree(fixture, d, ignore=shutil.ignore_patterns(
                ".build", "invocation.json", "solutions.json", "flags.json",
                "*.a"))

            def matrix(holes):
                (d / "invocation.json").write_text(
                    json.dumps({"schema": 1, "holes": holes,
                                "mismatches": []}), encoding="utf-8")
                return _matrix(d, problem_meta.load(d / "problem.json"))

            clean = matrix([])
            self.assertTrue(clean.done)
            details["accept"] = clean.detail
            holed = matrix([{"solution": "x", "group": "g1"}] * 2)
            self.assertFalse(holed.done)
            details["holes"] = holed.detail
            self.assertTrue(matrix([]).done)
            later = (d / "invocation.json").stat().st_mtime + 10
            os.utime(d / "problem.json", (later, later))
            stale = _matrix(d, problem_meta.load(d / "problem.json"))
            self.assertFalse(stale.done)
            details["stale"] = stale.detail.split(":")[0] + ":"

        gate = flatten(self.section("## Gate: is this estimable at all?"))
        self.assertEqual(details["accept"], "holes 0, mismatches 0")
        self.assertTrue(f"`{details['accept']}`" in gate,
                        "the gate no longer accepts the exact clean detail "
                        "package_status prints")
        self.assertTrue(f"[ ] matrix {details['holes']}" in gate,
                        f"the gate's rejected-holes example is not the "
                        f"detail package_status prints: {details['holes']!r}")
        self.assertTrue(f"[ ] matrix {details['stale']}" in gate,
                        f"the gate's rejected-stale example is not the "
                        f"detail package_status prints: {details['stale']!r}")
        self.assertTrue("`[x] matrix`" in gate,
                        "the gate no longer names the done checkbox")
        self.assertIn('python3 -m tools.package_status "$PROBLEM"',
                      self.body())

    def test_both_skills_agree_on_the_difficulty_handoff(self):
        # `writing-editorials` copies the number out of `difficulty.md` and
        # leaves its field blank on `not estimable`. Rename the file or the
        # sentinel on one side and the other side keeps looking for the old
        # one: the editorial re-estimates free-hand, or copies the words
        # "not estimable" into a rating field.
        mine = self.body()
        editorials = skill_text("writing-editorials")
        # The editorial side is held to the bare filename: it resolves the
        # path from its own `$PROBLEM`, and the name is what has to agree.
        for needle, theirs in (("$PROBLEM/difficulty.md", "difficulty.md"),
                               ("not estimable", "not estimable")):
            with self.subTest(needle=needle):
                self.assertTrue(needle in mine,
                                f"{self.SKILL} no longer names {needle!r}")
                self.assertTrue(theirs in editorials,
                                f"writing-editorials no longer names "
                                f"{theirs!r}, so it stops reading what "
                                f"{self.SKILL} writes")
        self.assertIn("**Expected rating: not estimable**",
                      self.section("## Failure branch"))


class TestPreferencesDocs(unittest.TestCase):
    """`preferences.toml` and the skills that read it, held together.

    The fork this file's key inventory came from accumulated dead entries —
    keys nobody read, still sitting in the shipped file looking authoritative.
    Nothing there was watching, so the drift ran both ways: a key could be
    documented and unread, or read under a name the file never had. Both
    directions are checked here, against the file parsed with `tomllib` rather
    than against a list retyped in this module.
    """

    # The skills whose Bootstrap block reads preferences. `writing-statements`
    # is the sixth setter skill and has no such block at all — it neither
    # `cd`s to `$PLUGIN_ROOT` nor runs a `tools/` module — so there is nothing
    # there to add the line to, and inventing a block for it is not this pin's
    # call.
    #
    # `calculating-difficulties` is the other way round and is deliberately
    # absent: it *has* a Bootstrap block, because it `cd`s to `$PLUGIN_ROOT`
    # and runs `tools.package_status` for its gate, but it reads no key of
    # `preferences.toml` — the estimate is for the full-constraint problem as
    # a single all-or-nothing task, so neither `format.default` nor
    # `subtasks.policy` moves it. A `PREFS` line there would load config the
    # skill never consults. Give it one the moment it grows a real key.
    BOOTSTRAP_SKILLS = ("creating-problems", "shaping-problems",
                        "preparing-tests", "reviewing-problems",
                        "validating-solutions", "uploading-to-polygon")

    PREFS_LINE = 'PREFS="$(python3 -m tools.preferences)"'

    def shipped(self) -> dict:
        path = ROOT / "preferences.toml"
        self.assertTrue(path.is_file(), f"{path} is missing")
        return tomllib.loads(path.read_text(encoding="utf-8"))

    def shipped_keys(self) -> set[str]:
        return {f"{section}.{key}"
                for section, table in self.shipped().items()
                for key in table}

    # A section name followed by a file extension is a *filename*, not a key.
    # `[polygon]` is a section of the file and `polygon.json` is the package
    # file `uploading-to-polygon` writes its Polygon record into, so without
    # this the skill naming its own artifact reads as a preferences key
    # called `json` that the shipped file has never had.
    FILE_SUFFIXES = ("json", "toml", "lock", "md", "py", "sh", "tex")

    def mentions(self) -> dict[str, set[str]]:
        """Every backticked `section.key` in every skill, by skill.

        The section names come from the parsed file, so the pattern cannot
        match `tools.package_status` or `problem_meta.FORMAT_VALUES` — only a
        dotted name whose left half is an actual section of the file and
        whose right half is not a file extension.
        """
        sections = "|".join(sorted(self.shipped()))
        suffixes = "|".join(self.FILE_SUFFIXES)
        pattern = re.compile(rf"`({sections})\.(?!(?:{suffixes})`)([a-z_]+)`")
        return {skill: {f"{m[0]}.{m[1]}"
                        for m in pattern.findall(skill_text(skill))}
                for skill in sorted(skill_dirs())}

    def test_the_shipped_file_parses_and_has_keys(self):
        # Vacuity guard: an unparseable or empty file would make both
        # directions below trivially pass.
        self.assertGreaterEqual(len(self.shipped_keys()), 13)

    def test_every_key_a_skill_names_exists_in_the_shipped_file(self):
        shipped = self.shipped_keys()
        for skill, named in self.mentions().items():
            for key in sorted(named):
                with self.subTest(skill=skill, key=key):
                    self.assertIn(
                        key, shipped,
                        f"{skill} tells a reader to consult `{key}`, which is "
                        f"not a key in preferences.toml. Keys: "
                        f"{sorted(shipped)}")

    def test_every_shipped_key_is_read_by_at_least_one_skill(self):
        # No exemptions. `[polygon]` shipped unread for one PR behind a
        # `RESERVED_FOR_LATER_PR` set; `uploading-to-polygon` is the skill
        # that reads those three, so the set is gone and every key in the
        # file is now covered by this check again.
        named = set().union(*self.mentions().values())
        dead = sorted(self.shipped_keys() - named)
        self.assertEqual(
            dead, [],
            f"preferences.toml ships keys no skill reads: {dead}. A default "
            f"nothing consults is drift wearing a config file's clothes — "
            f"either name it in the skill that should honour it, or delete it "
            f"from the file.")

    def test_the_bootstrap_block_reads_preferences_the_same_way_everywhere(self):
        for skill in self.BOOTSTRAP_SKILLS:
            with self.subTest(skill=skill):
                blocks = [b for b in bash_blocks(skill) if "PREFS=" in b]
                self.assertEqual(
                    len(blocks), 1,
                    f"{skill}: expected exactly one ```bash block setting "
                    f"PREFS, found {len(blocks)}")
                lines = blocks[0].splitlines()
                self.assertIn(
                    self.PREFS_LINE, lines,
                    f"{skill}'s Bootstrap block sets PREFS differently from "
                    f"its siblings. The line is duplicated on purpose — skills "
                    f"load independently — so the fix is to copy one over the "
                    f"others.")
                # After the `cd`, not before: `python3 -m tools.preferences`
                # is a `tools/` module and is only importable with
                # `$PLUGIN_ROOT` as the working directory, exactly as every
                # Bootstrap block's own prose says.
                self.assertLess(
                    lines.index('cd "$PLUGIN_ROOT"'),
                    lines.index(self.PREFS_LINE),
                    f"{skill}: PREFS is read before the `cd` to $PLUGIN_ROOT, "
                    f"so the command fails with ModuleNotFoundError")

    def test_writing_statements_has_no_bootstrap_block_to_add_it_to(self):
        # The exemption above, checked rather than assumed: the moment
        # `writing-statements` grows a Bootstrap block, it joins the five.
        self.assertNotIn("## Bootstrap", skill_text("writing-statements"),
                         "writing-statements now has a Bootstrap block — add "
                         "it to BOOTSTRAP_SKILLS and give it the PREFS line")

    def test_the_readme_documents_the_lookup_order(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for fragment in ("preferences.toml", "tools.preferences",
                         preferences.PREFS_ENV, preferences.XDG_ENV):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, readme,
                              f"the README's Preferences paragraph no longer "
                              f"names {fragment}")


class TestPolygonServerEnvTableMatchesConfig(TestServerEnvTableMatchesConfig):
    """The same three-way check for the second server.

    `TestServerEnvTableMatchesConfig` is keyed to the `CODEFORCES_*`/`CF_*`
    namespace and reads `cf_mcp/config.py`; widening its regex would make every
    Polygon row a ghost, since `cf_mcp` reads none of them. So the Polygon
    server gets its own three-way pin over its own config module.
    """

    CONFIG = (
        TestServerEnvTableMatchesConfig.SERVER
        / "src" / "polygon_mcp" / "config.py"
    ).read_text(encoding="utf-8")

    _NAME = r"POLYGON_[A-Z_]+"


class TestPolygonToolTableMatchesTheServer(unittest.TestCase):
    """The Polygon README's tool table is thirty-five claims about `server.py`.

    Each tool's docstring names the one API method it wraps, and the README
    repeats that mapping in a table a reader consults instead of reading the
    code. Two copies with nothing holding them together drift, and the half
    that drifts is the one the next editor did not have open — the same
    argument this module opens with. Read as text rather than imported:
    `tools/` is stdlib-only and `polygon_mcp` needs `mcp` and `httpx`.
    """

    SOURCE = (
        ROOT / "mcp-server" / "src" / "polygon_mcp" / "server.py"
    ).read_text(encoding="utf-8")
    README = (ROOT / "mcp-server" / "README.md").read_text(encoding="utf-8")

    # Every tool, paired with the method its own docstring points at.
    _TOOL = re.compile(r"^async def (polygon_\w+)\(", re.MULTILINE)
    _METHOD = re.compile(r"→ `([\w.]+)`")

    def _declared(self) -> dict[str, str]:
        starts = [(m.group(1), m.start()) for m in self._TOOL.finditer(self.SOURCE)]
        self.assertTrue(starts, "no tools found in polygon_mcp/server.py")
        pairs = {}
        for i, (name, start) in enumerate(starts):
            end = starts[i + 1][1] if i + 1 < len(starts) else len(self.SOURCE)
            found = self._METHOD.search(self.SOURCE, start, end)
            self.assertIsNotNone(
                found, f"{name}'s docstring names no `→ <method>`"
            )
            pairs[name] = found.group(1)
        return pairs

    def test_every_tool_has_a_row_naming_the_method_it_wraps(self):
        for tool, method in self._declared().items():
            row = [line for line in self.README.splitlines()
                   if line.startswith(f"| `{tool}(")]
            self.assertEqual(len(row), 1,
                             f"README has {len(row)} table rows for {tool}")
            self.assertIn(f"`{method}`", row[0],
                          f"README says {tool} wraps something other than {method}")

    def test_the_table_names_no_tool_the_server_does_not_have(self):
        rows = set(re.findall(r"^\| `(polygon_\w+)\(", self.README, re.MULTILINE))
        ghosts = sorted(rows - set(self._declared()))
        self.assertEqual(ghosts, [], f"README documents tools that do not exist: {ghosts}")

    def test_the_readme_counts_the_tools_it_lists(self):
        # "thirty-six tools" in the prose, and a row apiece in the table.
        self.assertEqual(len(self._declared()), 36)
        self.assertIn("thirty-six tools", self.README)


class TestUploadingToPolygonSkill(unittest.TestCase):
    """`uploading-to-polygon` describes a tool contract it does not own.

    Every call the skill and its reference name has to exist on
    `polygon_mcp/server.py`, with the method its own docstring claims — a
    skill that instructs the model to call `save_problem_test` (the fork's
    name for it) sends the model looking for a tool no server here has, and
    nothing in the skill itself can notice. `TestPolygonToolTableMatchesTheServer`
    holds the server's README to the same source; this holds the skill and
    its reference.

    The credential guard is the other half. Rule one of this skill is that
    the secrets live in the server's environment and never reach the agent,
    and the cheapest way for that to rot is a well-meant "set
    POLYGON_API_KEY first" paragraph — so both names are asserted *absent*
    from prose that is loaded into a model's context.
    """

    SKILL = "uploading-to-polygon"
    REFERENCE = SKILLS / SKILL / "references" / "polygon-tools.md"
    SERVER = (
        ROOT / "mcp-server" / "src" / "polygon_mcp" / "server.py"
    ).read_text(encoding="utf-8")

    # A backtick immediately before the name, so `mcp-server/src/polygon_mcp/…`
    # in a path is not read as a tool called `polygon_mcp` — and a closing
    # `(` or backtick after it, so `polygon_ref.load` (the `tools/` module
    # this skill writes its Polygon record with) is not read as a tool
    # called `polygon_ref`. The same anchor `LOAD_BEARING` uses below.
    _MENTION = re.compile(r"`(polygon_\w+)(?=\(|`)")
    _TOOL = re.compile(r"^async def (polygon_\w+)\(", re.MULTILINE)
    _METHOD = re.compile(r"→ `([\w.]+)`")

    def documents(self) -> dict[str, str]:
        self.assertTrue(self.REFERENCE.is_file(), f"{self.REFERENCE} is missing")
        return {f"{self.SKILL}/SKILL.md": skill_text(self.SKILL),
                f"{self.SKILL}/references/polygon-tools.md":
                    self.REFERENCE.read_text(encoding="utf-8")}

    def declared(self) -> dict[str, str]:
        """Every tool on the server, paired with the method it wraps."""
        starts = [(m.group(1), m.start()) for m in self._TOOL.finditer(self.SERVER)]
        self.assertTrue(starts, "no tools found in polygon_mcp/server.py")
        pairs = {}
        for i, (name, start) in enumerate(starts):
            end = starts[i + 1][1] if i + 1 < len(starts) else len(self.SERVER)
            found = self._METHOD.search(self.SERVER, start, end)
            self.assertIsNotNone(found, f"{name}'s docstring names no method")
            pairs[name] = found.group(1)
        return pairs

    def description(self) -> str:
        """The frontmatter `description:`, whitespace collapsed.

        It is a YAML folded block hard-wrapped at ~76 columns, so every
        assertion below has to be made against the flattened form or it
        passes and fails on where the block happened to wrap.
        """
        text = skill_text(self.SKILL)
        match = re.search(r"^description: >\n(.*?)^---$", text,
                          re.DOTALL | re.MULTILINE)
        self.assertIsNotNone(match, f"{self.SKILL} has no folded description")
        return flatten(match.group(1)).strip()

    def test_the_skill_exists_and_its_name_matches_its_directory(self):
        self.assertIn(self.SKILL, skill_dirs())
        self.assertIn(f"name: {self.SKILL}\n", skill_text(self.SKILL))

    def test_the_description_says_only_when_explicitly_asked(self):
        # Routing happens before the skill loads, so this sentence is the
        # only thing standing between "the package is finished" and a
        # helpful unasked-for upload to a live account.
        self.assertTrue(
            self.description().startswith(
                "Use ONLY when the user explicitly asks to upload"),
            f"{self.SKILL}'s description no longer opens by restricting "
            f"itself to an explicit request: {self.description()[:120]!r}")

    def test_the_description_names_the_bundled_server(self):
        self.assertIn("`polygon` MCP server", self.description(),
                      f"{self.SKILL}'s description no longer says which "
                      f"server it drives")

    def test_the_manifest_description_counts_this_skill(self):
        # Mirrors TestWritingEditorialsSkill's own pin below: the manifest
        # description enumerates every skill in one clause each, and it
        # drifted silently when this skill was added because nothing read
        # it. "Polygon" alone would not catch that drift — the stale
        # description already said "Polygon" via the two-servers clause and
        # via "Polygon-ready package" — so this pins the distinct word
        # "uploading" instead.
        for manifest, description in manifest_descriptions().items():
            with self.subTest(manifest=manifest):
                self.assertIn(
                    "uploading", description,
                    f"{manifest}'s description enumerates every skill but "
                    f"uploading-to-polygon, so the marketplace listing "
                    f"undersells the plugin")

    def test_the_skill_names_both_preconditions_by_tool(self):
        body = flatten(skill_text(self.SKILL))
        for tool in ("tools.package_status", "tools.review_checks"):
            with self.subTest(precondition=tool):
                self.assertIn(
                    tool, body,
                    f"{self.SKILL} no longer names {tool}. Both are required: "
                    f"package_status says every phase produced its artifact, "
                    f"review_checks says nothing drifted across them.")

    # The calls the skill's own phases are built on. Listed because the ghost
    # check below only catches an invented name that still *looks* like one
    # of this server's — and the failure actually worth catching is the fork's
    # vocabulary (`create_problem`, `save_problem_test`,
    # `commit_problem_changes`) surviving a paraphrase, which looks like no
    # polygon tool at all and so casts no ghost.
    LOAD_BEARING = (
        "polygon_whoami", "polygon_problems_list", "polygon_problem_create",
        "polygon_problem_update_info", "polygon_save_statement",
        "polygon_save_file", "polygon_set_checker", "polygon_set_validator",
        "polygon_save_solution", "polygon_save_script", "polygon_save_test",
        "polygon_tests", "polygon_enable_groups", "polygon_enable_points",
        "polygon_set_test_group", "polygon_save_test_group", "polygon_commit", "polygon_build_package",
        "polygon_packages", "polygon_set_access",
    )

    def test_every_tool_the_prose_names_exists_on_the_server(self):
        real = set(self.declared())
        for name, body in self.documents().items():
            found = set(self._MENTION.findall(body))
            with self.subTest(document=name):
                self.assertTrue(found, f"{name} names no polygon tool at all")
                ghosts = sorted(found - real)
                self.assertEqual(
                    ghosts, [],
                    f"{name} tells the model to call {ghosts}, which "
                    f"polygon_mcp/server.py does not define. Tools: "
                    f"{sorted(real)}")

    def test_the_skill_still_names_every_call_its_phases_are_built_on(self):
        real = set(self.declared())
        body = skill_text(self.SKILL)
        for tool in self.LOAD_BEARING:
            with self.subTest(tool=tool):
                self.assertIn(tool, real,
                              f"{tool} left polygon_mcp/server.py — the skill "
                              f"and this list both need updating")
                # Closed by `(` or a backtick, so `polygon_save_test` is not
                # satisfied by a mention of `polygon_save_test_group` — the
                # exact way a prefix check goes vacuous on this server, whose
                # tool names nest.
                #
                # `assertTrue`, not `assertIn`: the container here is the
                # whole skill, and unittest would render all 340 lines of it
                # around the one sentence that says which tool went missing.
                self.assertTrue(
                    re.search(rf"`{tool}(?:\(|`)", body) is not None,
                    f"{self.SKILL} no longer names {tool}. Either the phase "
                    f"that called it is gone, or it was renamed to something "
                    f"this server does not have — the fork's vocabulary "
                    f"(`create_problem`, `save_problem_test`) reads as prose, "
                    f"not as a ghost, so nothing else would notice.")

    # Only the counts this table can plausibly reach; an unmapped count fails
    # loudly rather than passing by not being looked for.
    _COUNT_WORDS = {34: "thirty-four", 35: "thirty-five", 36: "thirty-six",
                    37: "thirty-seven", 38: "thirty-eight"}

    def test_the_skill_counts_the_tools_the_reference_lists(self):
        # The skill tells the reader the reference lists them *all*, which is
        # what makes it safe to stop looking there. A stale count is how a
        # tool added to the server stays invisible to the skill that would
        # have used it — the drift that left Phase 7 assigning groups through
        # `polygon_save_test` while `problem.setTestGroup` sat unwrapped.
        total = len(self.declared())
        self.assertIn(total, self._COUNT_WORDS,
                      f"{total} tools on the server — add the word for it")
        self.assertIn(f"{self._COUNT_WORDS[total]} with the API method",
                      skill_text(self.SKILL),
                      f"{self.SKILL} no longer says the reference lists all "
                      f"{total} of the server's tools")

    def test_the_reference_maps_every_tool_to_the_method_it_wraps(self):
        body = self.documents()[f"{self.SKILL}/references/polygon-tools.md"]
        rows = {line for line in body.splitlines() if line.startswith("| `polygon_")}
        for tool, method in self.declared().items():
            with self.subTest(tool=tool):
                matching = [r for r in rows if r.startswith(f"| `{tool}(")]
                self.assertEqual(len(matching), 1,
                                 f"the reference has {len(matching)} rows for {tool}")
                self.assertIn(f"`{method}`", matching[0],
                              f"the reference says {tool} wraps something "
                              f"other than {method}")

    def test_neither_document_names_a_credential_variable(self):
        # Rule one, guarded: the server reads these from its own environment
        # and the agent never sees them. A skill that names one is one
        # paragraph away from telling a model to go and read it.
        for name, body in self.documents().items():
            for variable in ("POLYGON_API_KEY", "POLYGON_API_SECRET"):
                with self.subTest(document=name, variable=variable):
                    self.assertTrue(
                        variable not in body,
                        f"{name} names {variable}. The credentials live in "
                        f"the server's environment and never reach the "
                        f"agent; setup belongs in mcp-server/README.md.")

    def test_the_tag_table_is_total_over_the_packages_own_tag_set(self):
        # The mapping the skill calls "total over `scan_solutions.TAGS`",
        # checked against that tuple and against the server's own list of
        # tags Polygon accepts — not against a third copy typed here.
        body = skill_text(self.SKILL)
        rows = dict(re.findall(r"^\| `([a-z-]+)` \| `([A-Z]{2})` \|$", body,
                               re.MULTILINE))
        self.assertEqual(
            sorted(rows), sorted(SOLUTION_ZOO_TAGS),
            f"{self.SKILL}'s @tag table no longer covers exactly "
            f"scan_solutions.TAGS. A tag with no row leaves the model "
            f"inventing a Polygon tag for it.")
        accepted = re.search(r"^SOLUTION_TAGS = \((.*?)\)$", self.SERVER,
                             re.DOTALL | re.MULTILINE)
        self.assertIsNotNone(accepted, "server.py no longer declares SOLUTION_TAGS")
        accepted = set(re.findall(r'"(\w+)"', accepted.group(1)))
        self.assertTrue(
            set(rows.values()) <= accepted,
            f"{self.SKILL} maps a tag to {sorted(set(rows.values()) - accepted)}, "
            f"which polygon_save_solution refuses before the request goes out")
        self.assertEqual(rows["main"], "MA",
                         "the model solution must map to Polygon's MA — "
                         "Polygon computes every answer by running it")


class TestMcpJsonRegistersBothServers(unittest.TestCase):
    """`.mcp.json` is what actually launches the servers, and the root README
    tells the reader what to expect from it. Three claims that can drift apart:
    the console script each server is launched with, the credentials passed
    through to it, and the inventory line naming how many servers there are.
    """

    MCP_JSON = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    README = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_both_servers_are_registered(self):
        self.assertEqual(sorted(self.MCP_JSON), ["codeforces", "polygon"])

    def test_each_server_is_launched_with_its_own_console_script(self):
        scripts = (ROOT / "mcp-server" / "pyproject.toml").read_text(encoding="utf-8")
        for server, script in (("codeforces", "cf-mcp"), ("polygon", "polygon-mcp")):
            self.assertEqual(self.MCP_JSON[server]["args"][-1], script)
            self.assertIn(f"{script} = ", scripts,
                          f"pyproject.toml declares no {script} console script")

    def test_the_polygon_server_is_handed_the_variables_it_needs(self):
        # Credentials plus the path guard's root: a `path=` argument is refused
        # outright when POLYGON_MCP_ROOT never reaches the server's environment.
        env = self.MCP_JSON["polygon"]["env"]
        self.assertEqual(
            sorted(env),
            ["POLYGON_API_KEY", "POLYGON_API_SECRET", "POLYGON_MCP_ROOT"],
        )
        for name, reference in env.items():
            self.assertEqual(reference, "${%s}" % name,
                             "a literal value here would put a secret in the repo")

    def test_the_readme_inventory_line_counts_both_servers(self):
        self.assertIn("2 MCP servers", self.README)
        self.assertIn("MCP server `polygon`", self.README)

    def test_the_handshake_probe_is_run_against_both_servers(self):
        for script in ("cf-mcp", "polygon-mcp"):
            self.assertIn(f"uvx --from ./mcp-server {script}", self.README)


class TestPolygonUploadFeedbackPins(unittest.TestCase):
    """What the 2026-09-14 Trinity Force upload taught, pinned.

    Five problems went to Polygon and four instructions in
    `uploading-to-polygon` turned out to be wrong in practice: the stock
    testlib does not have `registerGen(..., 2)`, `$$$` is the delimiter of a
    renderer new problems no longer use, the URL can be built from the id,
    and a hand-made test is not a reason to stop. Each wrong sentence is
    listed literally, the way `RETIRED_CLAIMS` above lists the file-IO ones —
    the failure being guarded is a revert, not a paraphrase.

    The markup reference and the linter are two copies of one whitelist,
    so the reference is checked against the linter's own constants rather
    than against a third list typed here.
    """

    SKILL = "uploading-to-polygon"
    MARKUP = SKILLS / SKILL / "references" / "polygon-statement-markup.md"

    RETIRED_CLAIMS = (
        "`testlib.h` is Polygon's own — do not upload it",
        "`$$$x$$$` for inline math",
        "ask the user for the problem's URL",
        "If the exact argv is not recoverable, STOP",
        "There is no documented way to build a working Polygon link",
    )

    def documents(self) -> dict[str, str]:
        refs = SKILLS / self.SKILL / "references"
        return {
            "SKILL.md": skill_text(self.SKILL),
            "polygon-tools.md": (refs / "polygon-tools.md").read_text(encoding="utf-8"),
            "polygon-statement-markup.md": self.markup(),
        }

    def markup(self) -> str:
        self.assertTrue(self.MARKUP.is_file(), f"{self.MARKUP} is missing")
        text = self.MARKUP.read_text(encoding="utf-8")
        self.assertGreater(len(text), 2000, f"{self.MARKUP} read back nearly empty")
        return text

    def test_no_document_carries_a_retired_upload_instruction(self):
        for name, body in self.documents().items():
            flat = flatten(body)
            for claim in self.RETIRED_CLAIMS:
                with self.subTest(document=name, claim=claim):
                    self.assertTrue(
                        claim not in flat,
                        f"{name} still says {claim!r}, which the Trinity Force "
                        f"upload proved wrong. See CHANGELOG [Unreleased].")

    def test_phase_3_states_the_convention_and_points_at_the_reference(self):
        body = flatten(skill_text(self.SKILL))
        for phrase in ("### Statement markup on Polygon",
                       "references/polygon-statement-markup.md",
                       "`$x$` inline, `$$x$$` display",
                       "`\\emph` renders as underline",
                       "python3 -m tools.cf_statement_lint"):
            with self.subTest(phrase=phrase):
                self.assertTrue(phrase in body,
                                f"{self.SKILL} no longer states {phrase!r}")

    def test_the_skill_uploads_the_packages_testlib(self):
        body = flatten(skill_text(self.SKILL))
        self.assertIn('`$TESTLIB/testlib.h`', body)
        self.assertIn("registerGen(argc, argv, 2)", body)
        self.assertIn("FL or RJ on the first generated tests", body)

    def test_the_skill_runs_the_modules_it_names(self):
        body = skill_text(self.SKILL)
        for module in ("cf_statement_lint", "recover_test_argv"):
            with self.subTest(module=module):
                self.assertTrue((ROOT / "tools" / f"{module}.py").is_file(),
                                f"tools/{module}.py is missing")
                self.assertIn(f"python3 -m tools.{module}", body)

    def test_every_linted_text_command_is_documented_in_the_reference(self):
        # Imported here, not at module top: a broken linter should fail this
        # test, not every test in the module.
        from tools import cf_statement_lint
        markup = self.markup()
        for command in sorted(cf_statement_lint.TEXT_COMMANDS):
            with self.subTest(command=command):
                token = command if command.startswith("\\") else "\\" + command
                self.assertTrue(
                    token in markup,
                    f"cf_statement_lint accepts {token} in text mode but "
                    f"polygon-statement-markup.md does not list it")
        for env in sorted(cf_statement_lint.ENVIRONMENTS):
            with self.subTest(environment=env):
                self.assertTrue(f"`{env}`" in markup,
                                f"environment {env} is linted as supported "
                                f"but not documented")

    def test_the_reference_examples_of_breakage_are_what_the_linter_rejects(self):
        from tools import cf_statement_lint
        for bad in ("\\emph{sau $k$ lần}", "$P(5) = \\texttt{aabaa}$",
                    "$\\text{lên } (0,+1)$", "$\\mathrm{dist}(u,v)$",
                    "$\\{2$--$3, 3$--$1\\}$", "$$$x$$$"):
            with self.subTest(source=bad):
                errors = [f for f in cf_statement_lint.lint(bad)
                          if f.severity == "error"]
                self.assertTrue(errors, f"the linter accepts {bad!r}")

    def test_writing_statements_carries_the_polygon_authoring_notes(self):
        body = flatten(skill_text("writing-statements"))
        self.assertIn("`time = 2.5`", body)
        self.assertIn("## When the statement will also go to Polygon", body)


class TestMcpJsonNeverBakesCodeforcesSecrets(unittest.TestCase):
    """The polygon half of `.mcp.json` is pinned to `${NAME}` references
    above; a published 0.6.0 build carried a literal Codeforces handle and
    session cookie instead. Same pin, other server."""

    def test_codeforces_env_is_placeholders_only(self):
        env = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["codeforces"]["env"]
        self.assertTrue(env)
        for name, reference in env.items():
            with self.subTest(variable=name):
                self.assertEqual(reference, "${%s}" % name,
                                 "a literal value here would publish a secret")
