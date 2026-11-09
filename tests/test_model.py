import ast
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

from gitdiff_model import evaluate, post_argv, pre_command
from gitdiff_model.__main__ import main as cli_main
from gitdiff_model.fixtures import load_cases, sweep_rows, sweep_strings, write_results
from gitdiff_model.model import git_blob_id, js_json_stringify
from gitdiff_model.shell import parse

REPO = Path(__file__).resolve().parent.parent
CASES = load_cases(REPO / "fixtures" / "cases.tsv")


def _load_derive():
    spec = importlib.util.spec_from_file_location("derive", REPO / "scripts" / "derive_expected.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DERIVE = _load_derive()


def _expected():
    rows = {}
    for line in (REPO / "fixtures" / "expected.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        f = line.split("\t")
        rows[(f[0], f[1])] = f[1:]
    return rows


class FixturesAgainstDerivation(unittest.TestCase):
    def test_every_fixture_matches_independent_derivation(self):
        exp = _expected()
        self.assertEqual(len(exp), 2 * len(CASES))
        for cid, s, g in CASES:
            for v in ("pre", "post"):
                with self.subTest(cid=cid, version=v):
                    self.assertEqual(evaluate(s, v, g).row(), exp[(cid, v)])
                    self.assertEqual(DERIVE.derive(s, v, g), exp[(cid, v)])

    def test_sweep_matches_independent_derivation(self):
        n = 0
        for s in sweep_strings():
            for v in ("pre", "post"):
                self.assertEqual(evaluate(s, v).row(), DERIVE.derive(s, v, None), repr(s))
                n += 1
        self.assertEqual(n, 2 * (16 + 16 ** 2 + 16 ** 3))


class DiffTied(unittest.TestCase):
    def test_pre_command_is_old_line_26(self):
        # 'printf ' + JSON.stringify(str1) + ' | git ' + gitDir + ' hash-object -w --stdin'
        self.assertEqual(pre_command("$(id)"), 'printf "$(id)" | git  hash-object -w --stdin')
        self.assertEqual(pre_command("hello", ".git"), 'printf "hello" | git --git-dir .git hash-object -w --stdin')

    def test_post_argv_is_new_lines_20_and_35(self):
        self.assertEqual(post_argv(), ["git", "hash-object", "-w", "--stdin"])
        self.assertEqual(post_argv(".git"), ["git", "--git-dir", ".git", "hash-object", "-w", "--stdin"])

    def test_diff_comment_examples_new_29_30(self):
        for s in ("$(cmd)", "`cmd`"):
            self.assertEqual(evaluate(s, "pre").label, "CMD_INJECTION")
            self.assertEqual(evaluate(s, "post").label, "NO_SHELL")

    def test_json_stringify_only_escapes_quotes_backslashes_controls(self):
        self.assertEqual(js_json_stringify('a"b\\c'), '"a\\"b\\\\c"')
        self.assertEqual(js_json_stringify("$(x)`y`"), '"$(x)`y`"')
        self.assertEqual(js_json_stringify("\n\t\x01\x7f"), '"\\n\\t\\u0001\x7f"')
        self.assertEqual(js_json_stringify("\ud800"), '"\\ud800"')
        self.assertEqual(js_json_stringify("ñ"), '"ñ"')

    def test_git_blob_id_known_value(self):
        # well-known id of the empty blob
        self.assertEqual(git_blob_id(b""), "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")


class Differential(unittest.TestCase):
    def test_post_never_puts_the_string_in_argv(self):
        for s in sweep_strings():
            o = evaluate(s, "post")
            self.assertEqual((o.label, o.shell, o.structure),
                             ("NO_SHELL", "no", "argv:git hash-object -w --stdin"), repr(s))

    def test_literal_ok_pre_and_post_hash_the_same_bytes(self):
        for s in sweep_strings():
            a, b = evaluate(s, "pre"), evaluate(s, "post")
            if a.label == "LITERAL_OK":
                self.assertEqual(a.stdin_blob, b.stdin_blob, repr(s))

    def test_injection_needs_a_substitution(self):
        for s in sweep_strings():
            a = evaluate(s, "pre")
            if a.label == "CMD_INJECTION":
                self.assertIn("CMDSUB", a.expansions)
                self.assertTrue("$(" in s or "`" in s, repr(s))

    def test_sweep_counts(self):
        rows = list(sweep_rows())[1:]
        labels = {}
        for r in rows:
            if r[0] == "str":
                labels[r[2]] = labels.get(r[2], 0) + 1
        self.assertEqual(labels, {"CMD_INJECTION": 8, "EMPTY_CMDSUB": 34, "LITERAL_OK": 1589,
                                  "PARAM_EXPANSION": 121, "PRINTF_FORMAT": 1846, "SYNTAX_ERROR": 770})

    def test_gitdir_pre_vs_post(self):
        self.assertEqual(evaluate("x", "pre", "x;id").gitdir_label, "GITDIR_CMD_INJECTION")
        self.assertEqual(evaluate("x", "pre", "$(id)").gitdir_label, "GITDIR_CMD_INJECTION")
        self.assertEqual(evaluate("x", "pre", "x>y").gitdir_label, "GITDIR_REDIRECT")
        self.assertEqual(evaluate("x", "pre", "a b").gitdir_label, "GITDIR_ARGV_CHANGED")
        for g in ("x;id", "$(id)", "x>y", "a b", ".git"):
            self.assertEqual(evaluate("x", "post", g).gitdir_label, "GITDIR_ARGV")


class Adversarial(unittest.TestCase):
    def test_syntax_errors_and_bad_input(self):
        for s in ("$(id", "`id", "$(#)", "${x", "$((1", "$(;)", "$(|a)", "$(a|)", "$(()"):
            self.assertEqual(evaluate(s, "pre").label, "SYNTAX_ERROR", s)
        self.assertEqual(evaluate("$(())x", "pre").label, "ARITH_EXPANSION")  # empty arithmetic is 0
        self.assertEqual(evaluate("a" * 201, "pre").label, "BAD_INPUT")
        for g in ("", "q'", 'q"', "a\\b", "a\nb", "x" * 65, "é"):
            self.assertEqual(evaluate("x", "pre", g).label, "BAD_INPUT", repr(g))
        with self.assertRaises(ValueError):
            evaluate("x", "mid")

    def test_parser_basics(self):
        p = parse('printf "a" | git  hash-object -w --stdin')
        self.assertEqual((p.error, p.operators), ("", ["|"]))
        self.assertEqual(p.commands, [["printf", '"a"'], ["git", "hash-object", "-w", "--stdin"]])
        self.assertTrue(parse("(a) b").error)
        self.assertFalse(parse("(a) > f").error)
        self.assertEqual(parse("echo 'x$(id)'").expansions, [])

    def test_canary_is_never_created(self):
        with tempfile.TemporaryDirectory() as d:
            canary = Path(d) / "canary"
            payloads = ["$(touch %s)" % canary, "`touch %s`" % canary, "${x:-$(touch %s)}" % canary]
            for s in payloads:
                for v in ("pre", "post"):
                    evaluate(s, v)
                    evaluate("x", v, "a;touch %s" % canary)
                    with contextlib.redirect_stdout(io.StringIO()):
                        cli_main(["case", v, s])
                        cli_main(["command", s, "a;touch %s" % canary])
            self.assertFalse(canary.exists())

    def test_src_never_imports_process_or_network_modules(self):
        banned_mod = {"subprocess", "os", "pty", "ctypes", "socket", "shlex", "multiprocessing",
                      "asyncio", "http", "urllib", "ssl", "signal"}
        banned_call = {"system", "popen", "exec", "eval", "spawn", "fork", "execv", "compile", "__import__"}
        files = list((REPO / "src").rglob("*.py")) + [REPO / "scripts" / "derive_expected.py"]
        for f in files:
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertNotIn(a.name.split(".")[0], banned_mod, (f.name, a.name))
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    self.assertNotIn(node.module.split(".")[0], banned_mod, (f.name, node.module))
                elif isinstance(node, ast.Call):
                    fn = node.func
                    name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                    self.assertNotIn(name, banned_call, (f.name, name))


class Results(unittest.TestCase):
    def test_results_regenerate_byte_identical(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            write_results(REPO / "fixtures" / "cases.tsv", a)
            write_results(REPO / "fixtures" / "cases.tsv", b)
            for name in ("cases.tsv", "sweep.tsv", "SHA256SUMS"):
                ra = (Path(a) / name).read_bytes()
                self.assertEqual(ra, (Path(b) / name).read_bytes(), name)
                self.assertEqual(ra, (REPO / "results" / name).read_bytes(), name)

    def test_expected_equals_results_cases(self):
        self.assertEqual((REPO / "fixtures" / "expected.tsv").read_bytes(),
                         (REPO / "results" / "cases.tsv").read_bytes())

    def test_fixture_strings_round_trip(self):
        for line in (REPO / "fixtures" / "cases.tsv").read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                json.loads(line.split("\t")[1])


class PracticeLevels(unittest.TestCase):
    """Answers of PRACTICE.md."""

    def test_levels(self):
        self.assertEqual(evaluate("hello world", "pre").label, "LITERAL_OK")                     # 1
        self.assertEqual(pre_command("$(id)"), 'printf "$(id)" | git  hash-object -w --stdin')   # 2
        self.assertEqual(evaluate("$(id)", "pre").label, "CMD_INJECTION")                        # 3
        self.assertEqual(evaluate("\\$(id)", "pre").label, "CMD_INJECTION")                      # 4
        self.assertEqual(evaluate("$(id)", "post").label, "NO_SHELL")                            # 5
        self.assertEqual(evaluate("$HOME", "pre").label, "PARAM_EXPANSION")                      # 6
        self.assertEqual(evaluate("100%", "pre").label, "PRINTF_FORMAT")                         # 6
        self.assertEqual(evaluate("$(id", "pre").label, "SYNTAX_ERROR")                          # 7
        self.assertEqual(evaluate("x", "pre", "x;id").gitdir_label, "GITDIR_CMD_INJECTION")      # 8
        self.assertEqual(evaluate("x", "post", "x;id").gitdir_label, "GITDIR_ARGV")              # 8


if __name__ == "__main__":
    unittest.main()
