"""Offline model of CVE-2026-110634 (git-diff < 2.0.7, fixed by bfd727b).

`diff:N` is line N of the saved fix diff; `old:N` / `new:N` are lines of
js/gitDiffReal/generateDiff/index.js before / after the fix. The model
BUILDS the command string (pre) or the argv vector (post) exactly as the
diff does and CLASSIFIES it. It never starts a process, never calls a shell
and never calls git: the git blob id is computed with hashlib.
"""
import hashlib
from dataclasses import dataclass

from .shell import parse

MAX_LEN = 200


def js_json_stringify(s: str) -> str:
    """JSON.stringify for a JS string (ES2019 well-formed variant): escapes `"`
    and `\\`, \\b \\f \\n \\r \\t, other code units < 0x20 and lone surrogates as
    \\u00xx / \\udxxx (lowercase hex); everything else is copied."""
    short = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch in short:
            out.append(short[ch])
        elif o < 0x20 or 0xD800 <= o <= 0xDFFF:
            out.append("\\u%04x" % o)
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def pre_git_dir_string(git_dir):
    """old:19-23 (diff:18-22): `--git-dir <dir>` concatenated, or ''."""
    return "--git-dir " + git_dir if isinstance(git_dir, str) else ""


def pre_command(s: str, git_dir=None) -> str:
    """old:26 (diff:25): 'printf ' + JSON.stringify(str1) + ' | git ' + gitDir +
    ' hash-object -w --stdin'. Passed to shelljs.exec at old:29 (diff:45)."""
    return "printf " + js_json_stringify(s) + " | git " + pre_git_dir_string(git_dir) + " hash-object -w --stdin"


def post_argv(git_dir=None):
    """new:20 (diff:17) and new:35 (diff:35): execFileSync('git', gitDirArgs.concat(
    ['hash-object', '-w', '--stdin']), {input}) -- no shell, the string goes to stdin."""
    git_dir_args = ["--git-dir", git_dir] if isinstance(git_dir, str) else []
    return ["git"] + git_dir_args + ["hash-object", "-w", "--stdin"]


def utf8_like_node(s: str) -> bytes:
    """Node encodes a lone surrogate as U+FFFD when writing a string as utf8."""
    return "".join("\ufffd" if 0xD800 <= ord(c) <= 0xDFFF else c for c in s).encode("utf-8")


def git_blob_id(data: bytes) -> str:
    """What `git hash-object --stdin` prints for these bytes (SHA-1 object format)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


ARG_START = len("printf ")


def _expected_shape(cmds, ops, git_dir):
    return ops == ["|"] and len(cmds) == 2 and len(cmds[0]) == 2 and cmds[0][0] == "printf" \
        and cmds[1][0] == "git" and cmds[1][-3:] == ["hash-object", "-w", "--stdin"] \
        and (cmds[1] == ["git", "hash-object", "-w", "--stdin"] if git_dir is None
             else cmds[1] == ["git", "--git-dir", git_dir, "hash-object", "-w", "--stdin"])


@dataclass(frozen=True)
class Outcome:
    version: str
    label: str
    shell: str
    expansions: str
    structure: str
    printf_hazard: str
    stdin_blob: str
    gitdir_label: str

    def row(self):
        return [self.version, self.label, self.shell, self.expansions, self.structure,
                self.printf_hazard, self.stdin_blob, self.gitdir_label]


HEADER = ["version", "label", "shell", "expansions", "structure", "printf_hazard", "stdin_blob", "gitdir_label"]

GITDIR_FORBIDDEN = set("'\"\\\n\t")


def check_input(s: str, git_dir) -> None:
    if len(s) > MAX_LEN:
        raise ValueError("string longer than %d" % MAX_LEN)
    if git_dir is not None:
        if not git_dir or len(git_dir) > 64 or any(c in GITDIR_FORBIDDEN or not (0x20 <= ord(c) < 0x7F) for c in git_dir):
            raise ValueError("gitDir outside the modelled domain")


def _printf_hazard(s: str) -> str:
    """Characters printf would interpret in its FORMAT argument after the shell
    has removed the quotes: `%` (conversion), `\\` (escape; JSON adds them for
    control characters) or a leading `-` (option-like in some printf builtins)."""
    flags = []
    if "%" in s:
        flags.append("percent")
    if "\\" in s or any(ord(c) < 0x20 for c in s):
        flags.append("backslash")
    if s.startswith("-"):
        flags.append("leading_dash")
    return "+".join(flags) if flags else "-"


def _gitdir_label_pre(git_dir, p):
    if git_dir is None:
        return "-"
    if p.error:
        return "GITDIR_SYNTAX_ERROR"
    gd_start = len(pre_command("", None).split(" | git ")[0]) + len(" | git ")
    gd_exp = [e for e in p.expansions if e.start >= gd_start]
    if any(e.kind.startswith("CMDSUB") and not e.empty for e in gd_exp):
        return "GITDIR_CMD_INJECTION"
    if len(p.operators) != 1:
        return "GITDIR_CMD_INJECTION"
    if p.redirections:
        return "GITDIR_REDIRECT"
    if not _expected_shape(p.commands, p.operators, git_dir):
        return "GITDIR_ARGV_CHANGED"
    if gd_exp:
        return "GITDIR_EXPANSION"
    return "GITDIR_OK"


def evaluate(s: str, version: str, git_dir=None) -> Outcome:
    if version not in ("pre", "post"):
        raise ValueError("version must be pre|post")
    try:
        check_input(s, git_dir)
    except ValueError:
        return Outcome(version, "BAD_INPUT", "-", "-", "-", "-", "-", "-")

    if version == "post":
        argv = post_argv(git_dir)
        # the string only travels as stdin (`input`, diff:36); no shell (diff:33-43)
        return Outcome(version, "NO_SHELL", "no", "-", "argv:" + " ".join(argv),
                       "-", git_blob_id(utf8_like_node(s)), "-" if git_dir is None else "GITDIR_ARGV")

    cmd = pre_command(s, git_dir)
    p = parse(cmd)
    arg_end = ARG_START + len(js_json_stringify(s))
    str_exp = [e for e in p.expansions if ARG_START <= e.start < arg_end]
    kinds = sorted({e.kind for e in str_exp})
    hazard = _printf_hazard(s)
    gd = _gitdir_label_pre(git_dir, p)
    if p.error:
        label = "SYNTAX_ERROR"
        structure = "error"
    else:
        structure = "pipeline" if _expected_shape(p.commands, p.operators, git_dir) else "changed"
        if any(e.kind.startswith("CMDSUB") and not e.empty for e in str_exp):
            label = "CMD_INJECTION"
        elif any(k.startswith("CMDSUB") for k in kinds):
            label = "EMPTY_CMDSUB"
        elif "ARITH" in kinds:
            label = "ARITH_EXPANSION"
        elif "PARAM" in kinds:
            label = "PARAM_EXPANSION"
        elif hazard != "-":
            label = "PRINTF_FORMAT"
        else:
            label = "LITERAL_OK"
    blob = git_blob_id(utf8_like_node(s)) if label == "LITERAL_OK" and structure == "pipeline" else "-"
    return Outcome(version, label, "sh", "+".join(kinds) if kinds else "-", structure, hazard, blob, gd)
