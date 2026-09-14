"""`tools/preferences.py` — the lookup order, the strictness, and the CLI.

Every test that reaches `load()` patches `CP_PREFERENCES`, `XDG_CONFIG_HOME`
*and* `HOME` (which is what `Path.home()` reads on Linux, and therefore how
the `~/.config` default is exercised). Leaving any of the three alone would
let a developer's real configuration file decide whether the suite passes.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

from tools import preferences
from tools.preferences import (FORMAT_DEFAULT_VALUES, PREFS_ENV,
                               PreferencesError, SCHEMA, load, main, parse)
from tools.problem_meta import FORMAT_VALUES

ROOT = Path(__file__).resolve().parents[2]
SHIPPED = ROOT / "preferences.toml"


def shipped_text() -> str:
    return SHIPPED.read_text(encoding="utf-8")


@contextlib.contextmanager
def clean_env(**overrides):
    """A process environment with every lookup input under the test's control."""
    env = dict(os.environ)
    env.pop(preferences.PREFS_ENV, None)
    env.pop(preferences.XDG_ENV, None)
    env["HOME"] = str(overrides.pop("HOME", "/nonexistent-home-for-tests"))
    env.update({k: str(v) for k, v in overrides.items()})
    with mock.patch.dict(os.environ, env, clear=True):
        yield


class TestShippedFile(unittest.TestCase):
    def test_the_shipped_file_loads_with_zero_errors(self):
        self.assertTrue(SHIPPED.is_file(), f"{SHIPPED} is missing")
        prefs = parse(shipped_text(), SHIPPED)
        self.assertEqual(prefs.source, SHIPPED)

    def test_the_shipped_file_carries_every_key_and_nothing_else(self):
        # The strict parser already rejects extras and omissions, so this is
        # really a guard on the parser: read the sections back off the loaded
        # object and check they are exactly the schema's.
        prefs = parse(shipped_text(), SHIPPED)
        for section, (cls, keys) in SCHEMA.items():
            with self.subTest(section=section):
                table = getattr(prefs, section)
                self.assertIsInstance(table, cls)
                self.assertEqual(sorted(vars(table)), sorted(keys))

    def test_shipped_values(self):
        prefs = parse(shipped_text(), SHIPPED)
        self.assertEqual(prefs.format.default, "ask")
        self.assertEqual(prefs.subtasks.policy, "suggest")
        self.assertEqual(prefs.tests.files_per_group, 12)
        self.assertEqual(prefs.multi_test.policy, "ask")
        self.assertEqual(prefs.multi_test.oi_default_t_max, 5)
        self.assertEqual(prefs.multi_test.sum_constraints, "ask")
        self.assertEqual(prefs.stress.rounds, 300)
        self.assertEqual(prefs.zoo.max_accepted, 2)
        self.assertFalse(prefs.zoo.include_presentation_error)
        self.assertFalse(prefs.zoo.include_obviously_wrong)
        self.assertEqual(prefs.polygon.statement_language, "vietnamese")
        self.assertFalse(prefs.polygon.notify_on_commit)
        self.assertTrue(prefs.polygon.grant_codeforces_read)
        self.assertEqual(prefs.polygon.name_prefix, "")

    def test_format_default_is_the_package_set_plus_ask(self):
        # Pinned to the constant rather than to a second copy typed here: a
        # third scoring model added to problem.json must reach this file.
        self.assertEqual(FORMAT_DEFAULT_VALUES, FORMAT_VALUES + ("ask",))
        self.assertEqual(SCHEMA["format"][1]["default"].values,
                         FORMAT_DEFAULT_VALUES)


class TestLookupOrder(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        # A plugin root standing in for the repository's own, so a test that
        # falls through to step 3 does not depend on the real shipped file.
        self.plugin_root = self.tmp / "plugin"
        self.plugin_root.mkdir()
        self.write(self.plugin_root / "preferences.toml", rounds=1)

    def write(self, path: Path, *, rounds: int) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = shipped_text().replace("rounds = 300", f"rounds = {rounds}")
        self.assertIn(f"rounds = {rounds}", text)
        path.write_text(text, encoding="utf-8")
        return path

    def xdg_file(self, home: Path, *, rounds: int) -> Path:
        return self.write(
            home / "competitive-programming" / "preferences.toml", rounds=rounds)

    def test_explicit_env_file_wins(self):
        explicit = self.write(self.tmp / "mine.toml", rounds=7)
        xdg = self.tmp / "xdg"
        self.xdg_file(xdg, rounds=9)
        with clean_env(**{PREFS_ENV: explicit, "XDG_CONFIG_HOME": xdg}):
            prefs = load(self.plugin_root)
        self.assertEqual(prefs.stress.rounds, 7)
        self.assertEqual(prefs.source, explicit)

    def test_a_missing_explicit_file_is_an_error_not_a_fallback(self):
        # The whole point of naming a file explicitly: a typo in the variable
        # must not read as a working configuration somewhere else.
        missing = self.tmp / "typo.toml"
        with clean_env(**{PREFS_ENV: missing}):
            with self.assertRaises(PreferencesError) as ctx:
                load(self.plugin_root)
        self.assertIn(str(missing), str(ctx.exception))
        self.assertIn(PREFS_ENV, str(ctx.exception))

    def test_xdg_config_home_is_step_two(self):
        xdg = self.tmp / "xdg"
        path = self.xdg_file(xdg, rounds=9)
        with clean_env(**{"XDG_CONFIG_HOME": xdg}):
            prefs = load(self.plugin_root)
        self.assertEqual(prefs.stress.rounds, 9)
        self.assertEqual(prefs.source, path)

    def test_xdg_defaults_to_dot_config_under_home(self):
        home = self.tmp / "home"
        path = self.xdg_file(home / ".config", rounds=11)
        with clean_env(HOME=home):
            prefs = load(self.plugin_root)
        self.assertEqual(prefs.stress.rounds, 11)
        self.assertEqual(prefs.source, path)

    def test_the_shipped_file_is_the_last_step(self):
        with clean_env():
            prefs = load(self.plugin_root)
        self.assertEqual(prefs.stress.rounds, 1)
        self.assertEqual(prefs.source, self.plugin_root / "preferences.toml")

    def test_load_with_no_plugin_root_finds_this_repository(self):
        with clean_env():
            prefs = load()
        self.assertEqual(prefs.source, SHIPPED)

    def test_nothing_found_at_all_is_an_error(self):
        empty = self.tmp / "empty-root"
        empty.mkdir()
        with clean_env():
            with self.assertRaises(PreferencesError) as ctx:
                load(empty)
        self.assertIn(str(empty / "preferences.toml"), str(ctx.exception))


class TestStrictness(unittest.TestCase):
    PATH = Path("/some/preferences.toml")

    def mutate(self, old: str, new: str) -> str:
        text = shipped_text()
        self.assertIn(old, text)
        return text.replace(old, new)

    def fails_with(self, text: str, *fragments: str) -> str:
        with self.assertRaises(PreferencesError) as ctx:
            parse(text, self.PATH)
        message = str(ctx.exception)
        self.assertIn(str(self.PATH), message)
        for fragment in fragments:
            self.assertIn(fragment, message)
        return message

    def test_unknown_section(self):
        self.fails_with(shipped_text() + "\n[editorial]\ntheme = \"space-dark\"\n",
                        "editorial")

    def test_unknown_key(self):
        self.fails_with(self.mutate("rounds = 300", "rounds = 300\nn_cap = 20"),
                        "stress.", "n_cap")

    def test_missing_key(self):
        # No layering means nothing underneath to fall back to, so an absent
        # key is an error rather than a silent default.
        message = self.fails_with(self.mutate("rounds = 300\n", ""),
                                  "stress.rounds")
        self.assertIn("no layering", message)

    def drop_section(self, name: str, next_name: str) -> str:
        text = shipped_text()
        start, end = text.index(f"[{name}]"), text.index(f"[{next_name}]")
        self.assertLess(start, end)
        return text[:start] + text[end:]

    def test_missing_section(self):
        message = self.fails_with(self.drop_section("stress", "zoo"), "[stress]")
        self.assertIn("no layering", message)

    def test_wrong_type_string_where_an_integer_belongs(self):
        self.fails_with(self.mutate("rounds = 300", 'rounds = "300"'),
                        "stress.rounds", "integer >= 1")

    def test_a_boolean_is_not_an_integer(self):
        # `isinstance(True, int)` is true in Python; `rounds = true` must not
        # load as 1.
        self.fails_with(self.mutate("rounds = 300", "rounds = true"),
                        "stress.rounds", "boolean")

    def test_integer_below_its_minimum(self):
        self.fails_with(self.mutate("rounds = 300", "rounds = 0"),
                        "stress.rounds", "integer >= 1")
        self.fails_with(self.mutate("max_accepted = 2", "max_accepted = -1"),
                        "zoo.max_accepted", "integer >= 0")

    def test_zero_is_allowed_where_the_minimum_is_zero(self):
        prefs = parse(self.mutate("max_accepted = 2", "max_accepted = 0"),
                      self.PATH)
        self.assertEqual(prefs.zoo.max_accepted, 0)

    def test_wrong_type_where_a_boolean_belongs(self):
        self.fails_with(
            self.mutate("notify_on_commit = false", 'notify_on_commit = "no"'),
            "polygon.notify_on_commit", "true or false")

    def test_value_outside_the_closed_set(self):
        message = self.fails_with(
            self.mutate('policy = "suggest"', 'policy = "propose"'),
            "subtasks.policy", "propose")
        for value in SCHEMA["subtasks"][1]["policy"].values:
            self.assertIn(repr(value), message)

    def test_multi_test_policy_no_longer_takes_the_forks_fourth_value(self):
        self.fails_with(
            self.mutate('policy = "ask"\n# When multi-test',
                        'policy = "ask_when_lucky"\n# When multi-test'),
            "multi_test.policy", "ask_when_lucky")

    def test_a_polygon_name_prefix_in_polygons_alphabet_loads(self):
        # The field report's own conventions.
        for prefix in ("qhh-", "qhhoj-", "c0ntest-2026-"):
            with self.subTest(prefix=prefix):
                prefs = parse(self.mutate('name_prefix = ""',
                                          f'name_prefix = "{prefix}"'),
                              self.PATH)
                self.assertEqual(prefs.polygon.name_prefix, prefix)

    def test_a_polygon_name_prefix_outside_polygons_alphabet_is_refused(self):
        # Uppercase, underscore, space, a trailing newline (which `^...$`
        # with `re.match` would have let through), and non-latin letters —
        # each a name Polygon's `problem.create` would reject mid-upload.
        for bad in ("QHH-", "qhh_", "qhh -", "qhh-\\n", "đề-"):
            with self.subTest(prefix=bad):
                self.fails_with(
                    self.mutate('name_prefix = ""', f'name_prefix = "{bad}"'),
                    "polygon.name_prefix",
                    "lowercase latin letters, digits and dashes")

    def test_a_polygon_name_prefix_must_be_a_string(self):
        self.fails_with(self.mutate('name_prefix = ""', "name_prefix = 1"),
                        "polygon.name_prefix", "integer", "a string of")
        self.fails_with(self.mutate('name_prefix = ""', "name_prefix = false"),
                        "polygon.name_prefix", "boolean")

    def test_not_valid_toml(self):
        self.fails_with("[format\ndefault = 1", "not valid TOML")


class TestCli(unittest.TestCase):
    def run_main(self, argv):
        out, err = StringIO(), StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_json_carries_every_section_and_the_source(self):
        with clean_env():
            code, out, err = self.run_main([None])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["source"], str(SHIPPED))
        self.assertEqual(sorted(set(payload) - {"source"}), sorted(SCHEMA))
        self.assertEqual(payload["stress"]["rounds"], 300)
        self.assertIs(payload["zoo"]["include_obviously_wrong"], False)

    def test_exit_2_and_a_message_on_stderr_when_the_file_is_bad(self):
        tmp = Path(tempfile.mkdtemp()) / "broken.toml"
        tmp.write_text(shipped_text().replace("rounds = 300", 'rounds = "many"'),
                       encoding="utf-8")
        with clean_env(**{PREFS_ENV: tmp}):
            code, out, err = self.run_main([None])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("stress.rounds", err)

    def test_exit_2_on_too_many_arguments(self):
        code, out, err = self.run_main([None, "a", "b"])
        self.assertEqual(code, 2)
        self.assertIn("usage", err)

    def test_the_plugin_root_argument_relocates_only_the_last_step(self):
        tmp = Path(tempfile.mkdtemp())
        root = tmp / "plugin"
        root.mkdir()
        (root / "preferences.toml").write_text(
            shipped_text().replace("rounds = 300", "rounds = 42"),
            encoding="utf-8")
        with clean_env():
            code, out, err = self.run_main([None, str(root)])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["stress"]["rounds"], 42)

        # ... and the environment still wins over it.
        explicit = tmp / "mine.toml"
        explicit.write_text(shipped_text(), encoding="utf-8")
        with clean_env(**{PREFS_ENV: explicit}):
            code, out, err = self.run_main([None, str(root)])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["source"], str(explicit))


if __name__ == "__main__":
    unittest.main()
