"""Static model of how a POSIX sh (dash-like) would PARSE a command string.

It never runs anything: it only scans characters and records which expansions
(command substitution, arithmetic, parameter) the shell would perform and
whether the string is a syntax error. Grammar coverage is deliberately small
(see LIMITATIONS.md): words, quotes, backslash, `$(...)`, backticks, `$((...))`,
`${...}`, `$name`/special parameters, comments, control and redirection
operators, `( ... )` subshells. No here-documents, `case`, `if`, functions,
aliases or history expansion.
"""
from dataclasses import dataclass, field

BLANKS = " \t"
OPERATOR_CHARS = "|&;<>()"
CONTROL_OPS = ("&&", "||", ";;", "|", "&", ";", "\n")
REDIR_OPS = ("<<-", ">>", "<<", "<&", ">&", "<>", ">|", "<", ">")
SPECIAL_PARAMS = "@*#?-$!0123456789"
NAME_START = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_"
NAME_CHARS = NAME_START + "0123456789"


class ShSyntaxError(Exception):
    pass


@dataclass
class Expansion:
    kind: str      # CMDSUB_DOLLAR | CMDSUB_BACKTICK | ARITH | PARAM
    context: str   # unquoted | dq
    depth: int     # nesting depth (0 = in the top-level command)
    start: int     # offset in the scanned text
    empty: bool = False  # command substitution with an empty command list


@dataclass
class Parse:
    commands: list = field(default_factory=list)   # top-level simple commands (lists of raw words)
    operators: list = field(default_factory=list)  # top-level operators in order
    expansions: list = field(default_factory=list)
    error: str = ""
    redirections: list = field(default_factory=list)  # redirection operators seen (any depth)


class _Scanner:
    def __init__(self, text, depth=0, sink=None, base=0, redirs=None):
        self.s = text
        self.redirs = redirs if redirs is not None else []
        self.depth = depth
        self.exp = sink if sink is not None else []
        self.base = base

    # ---------------------------------------------------------------- lists
    def parse_list(self, i, closer=None):
        """Parse a command list from i until EOF (closer None) or an unquoted
        `)` (closer ')'). Returns (index, commands, operators)."""
        s = self.s
        commands, operators = [], []
        words, need_cmd, last_op, pending_redir = [], True, None, None
        after_subshell = False
        while True:
            while i < len(s) and s[i] in BLANKS:
                i += 1
            if i >= len(s):
                if closer:
                    raise ShSyntaxError("EOF before closing %r" % closer)
                break
            c = s[i]
            if c == "#":  # a token that starts with # opens a comment
                while i < len(s) and s[i] != "\n":
                    i += 1
                continue
            if c == ")" and closer == ")":
                break
            if c in OPERATOR_CHARS or c == "\n":
                op = self._operator(i)
                if op == "(":
                    if words or pending_redir:
                        raise ShSyntaxError("unexpected (")
                    j, sub_cmds, _ = self.parse_list(i + 1, closer=")")
                    if not sub_cmds:
                        raise ShSyntaxError("empty subshell")
                    i = j + 1
                    words.append("(subshell)")
                    after_subshell = True
                    continue
                if op == ")":
                    raise ShSyntaxError("unexpected )")
                if op in REDIR_OPS:
                    if pending_redir:
                        raise ShSyntaxError("redirection without target")
                    pending_redir = op
                    self.redirs.append(op)
                    i += len(op)
                    continue
                # control operator
                if pending_redir:
                    raise ShSyntaxError("redirection without target")
                if words:
                    commands.append(words)
                    words = []
                    need_cmd = False
                after_subshell = False
                if op == "\n":
                    if last_op in ("|", "&&", "||"):
                        i += 1
                        continue
                    operators.append(op)
                    last_op, need_cmd = None, True
                    i += 1
                    continue
                if need_cmd:
                    raise ShSyntaxError("unexpected %r" % op)
                if op == ";;":
                    raise ShSyntaxError("unexpected ;;")
                operators.append(op)
                last_op, need_cmd = op, True
                i += len(op)
                continue
            j, word = self._word(i)
            i = j
            if after_subshell and not pending_redir:
                raise ShSyntaxError("word after subshell")
            if pending_redir:
                pending_redir = None
                if not words:
                    words.append("(redir)")
                continue
            words.append(word)
        if pending_redir:
            raise ShSyntaxError("redirection without target")
        if words:
            commands.append(words)
        elif last_op in ("|", "&&", "||"):
            raise ShSyntaxError("EOF after %r" % last_op)
        return i, commands, operators

    def _operator(self, i):
        s = self.s
        for op in REDIR_OPS + CONTROL_OPS + ("(", ")"):
            if s.startswith(op, i):
                return op
        raise AssertionError("not an operator")

    # ---------------------------------------------------------------- words
    def _word(self, i):
        s, start = self.s, i
        while i < len(s) and s[i] not in BLANKS and s[i] not in OPERATOR_CHARS and s[i] != "\n":
            c = s[i]
            if c == "\\":
                i += 2 if i + 1 < len(s) else 1
            elif c == "'":
                j = s.find("'", i + 1)
                if j < 0:
                    raise ShSyntaxError("unterminated single quote")
                i = j + 1
            elif c == '"':
                i = self._dq(i + 1)
            elif c == "$":
                i = self._dollar(i, "unquoted")
            elif c == "`":
                i = self._backtick(i, "unquoted")
            else:
                i += 1
        return i, s[start:i]

    def _dq(self, i):
        s = self.s
        while i < len(s):
            c = s[i]
            if c == '"':
                return i + 1
            if c == "\\":
                i += 2 if i + 1 < len(s) and s[i + 1] in '$`"\\\n' else 1
            elif c == "$":
                i = self._dollar(i, "dq")
            elif c == "`":
                i = self._backtick(i, "dq")
            else:
                i += 1
        raise ShSyntaxError("unterminated double quote")

    def _record(self, kind, ctx, i):
        self.exp.append(Expansion(kind, ctx, self.depth, self.base + i))

    def _dollar(self, i, ctx):
        s = self.s
        nxt = s[i + 1] if i + 1 < len(s) else ""
        if s.startswith("$((", i):
            self._record("ARITH", ctx, i)
            j, depth = i + 3, 0
            while j < len(s):
                c = s[j]
                if c == "\\":
                    j += 2
                    continue
                if c == "$":
                    j = self._dollar(j, ctx)
                    continue
                if c == "`":
                    j = self._backtick(j, ctx)
                    continue
                if c == "(":
                    depth += 1
                elif c == ")":
                    if depth == 0:
                        if s.startswith("))", j):
                            return j + 2
                        raise ShSyntaxError("bad arithmetic close")
                    depth -= 1
                j += 1
            raise ShSyntaxError("unterminated $((")
        if nxt == "(":
            self._record("CMDSUB_DOLLAR", ctx, i)
            rec = self.exp[-1]
            inner = _Scanner(s, self.depth + 1, self.exp, self.base, self.redirs)
            j, cmds, _ = inner.parse_list(i + 2, closer=")")
            rec.empty = not cmds
            return j + 1
        if nxt == "{":
            self._record("PARAM", ctx, i)
            j = i + 2
            while j < len(s):
                c = s[j]
                if c == "}":
                    return j + 1
                if c == "\\":
                    j += 2
                elif c == "'" and ctx == "unquoted":
                    k = s.find("'", j + 1)
                    if k < 0:
                        raise ShSyntaxError("unterminated single quote")
                    j = k + 1
                elif c == '"':
                    j = self._dq(j + 1)
                elif c == "$":
                    j = self._dollar(j, ctx)
                elif c == "`":
                    j = self._backtick(j, ctx)
                else:
                    j += 1
            raise ShSyntaxError("missing }")
        if nxt and (nxt in NAME_START or nxt in SPECIAL_PARAMS):
            self._record("PARAM", ctx, i)
            if nxt in NAME_START:
                j = i + 2
                while j < len(s) and s[j] in NAME_CHARS:
                    j += 1
                return j
            return i + 2
        return i + 1  # a lone `$` is literal

    def _backtick(self, i, ctx):
        s = self.s
        self._record("CMDSUB_BACKTICK", ctx, i)
        rec = self.exp[-1]
        j, body = i + 1, []
        while j < len(s):
            c = s[j]
            if c == "`":
                inner = _Scanner("".join(body), self.depth + 1, self.exp, self.base + i + 1, self.redirs)
                _, cmds, _ = inner.parse_list(0)
                rec.empty = not cmds
                return j + 1
            if c == "\\" and j + 1 < len(s):
                n = s[j + 1]
                if n in "$`\\" or (ctx == "dq" and n == '"'):
                    body.append(n)
                else:
                    body.append(c + n)
                j += 2
                continue
            body.append(c)
            j += 1
        raise ShSyntaxError("unterminated backquote")


def parse(text: str) -> Parse:
    sc = _Scanner(text)
    try:
        _, commands, operators = sc.parse_list(0)
    except ShSyntaxError as e:
        return Parse([], [], sc.exp, str(e) or "syntax error", sc.redirs)
    return Parse(commands, operators, sc.exp, "", sc.redirs)
