#!/usr/bin/env python3
"""Independent derivation of fixtures/expected.tsv and results/sweep.tsv.

Does not import src/. Written separately from the model and in a different
style: a lexer that emits a flat token list (tracking subshell depth with a
counter) and a separate grammar check over that list, instead of the model's
recursive-descent scanner; JSON.stringify via json.dumps plus a lone-surrogate
fix-up. It never runs a shell, git or any process.

  python3 scripts/derive_expected.py          -> fixtures/expected.tsv
  python3 scripts/derive_expected.py sweep    -> results/sweep.tsv
"""
import hashlib
import itertools
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NAME0 = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
NAMEN = NAME0 | set("0123456789")
SPECIAL = set("@*#?-$!0123456789")
OPS = ["<<-", "&&", "||", ";;", ">>", "<<", "<&", ">&", "<>", ">|", "|", "&", ";", "<", ">", "(", ")", "\n"]
REDIRS = {"<<-", ">>", "<<", "<&", ">&", "<>", ">|", "<", ">"}


class Bad(Exception):
    pass


def stringify(s):
    body = json.dumps(s, ensure_ascii=False)
    return "".join("\\u%04x" % ord(c) if 0xD800 <= ord(c) <= 0xDFFF else c for c in body)


class Lexer:
    def __init__(self, text, exps, depth, offset, redirs):
        self.t, self.exps, self.depth, self.off, self.redirs = text, exps, depth, offset, redirs

    def tokens(self, pos, until_paren):
        """Flat token list from pos; stops at an unmatched `)` when until_paren."""
        t, toks, paren = self.t, [], 0
        while True:
            while pos < len(t) and t[pos] in " \t":
                pos += 1
            if pos >= len(t):
                if until_paren:
                    raise Bad("eof in $(")
                return pos, toks
            if t[pos] == "#":
                nl = t.find("\n", pos)
                pos = len(t) if nl < 0 else nl
                continue
            op = next((o for o in OPS if t.startswith(o, pos)), None)
            if op is not None:
                if op == ")":
                    if paren == 0:
                        if until_paren:
                            return pos, toks
                        raise Bad("stray )")
                    paren -= 1
                elif op == "(":
                    paren += 1
                if op in REDIRS:
                    self.redirs.append(op)
                toks.append(("R" if op in REDIRS else "O", op))
                pos += len(op)
                continue
            start = pos
            pos = self.word(pos)
            toks.append(("W", t[start:pos]))

    def word(self, pos):
        t = self.t
        while pos < len(t) and t[pos] not in " \t\n|&;<>()":
            c = t[pos]
            if c == "\\":
                pos = min(pos + 2, len(t))
            elif c == "'":
                end = t.find("'", pos + 1)
                if end < 0:
                    raise Bad("open '")
                pos = end + 1
            elif c == '"':
                pos = self.dquote(pos + 1)
            elif c == "$":
                pos = self.dollar(pos, "unquoted")
            elif c == "`":
                pos = self.backq(pos, "unquoted")
            else:
                pos += 1
        return pos

    def dquote(self, pos):
        t = self.t
        while True:
            if pos >= len(t):
                raise Bad('open "')
            c = t[pos]
            if c == '"':
                return pos + 1
            if c == "\\":
                pos += 2 if (pos + 1 < len(t) and t[pos + 1] in '$`"\\\n') else 1
            elif c == "$":
                pos = self.dollar(pos, "dq")
            elif c == "`":
                pos = self.backq(pos, "dq")
            else:
                pos += 1

    def add(self, kind, ctx, pos):
        rec = {"kind": kind, "ctx": ctx, "start": self.off + pos, "empty": False}
        self.exps.append(rec)
        return rec

    def dollar(self, pos, ctx):
        t = self.t
        two = t[pos + 1:pos + 3]
        if two == "((":
            self.add("ARITH", ctx, pos)
            q, level = pos + 3, 0
            while q < len(t):
                c = t[q]
                if c == "\\":
                    q += 2
                elif c == "$":
                    q = self.dollar(q, ctx)
                elif c == "`":
                    q = self.backq(q, ctx)
                elif c == "(":
                    level += 1
                    q += 1
                elif c == ")" and level > 0:
                    level -= 1
                    q += 1
                elif c == ")":
                    if t[q:q + 2] != "))":
                        raise Bad("arith")
                    return q + 2
                else:
                    q += 1
            raise Bad("open $((")
        if two[:1] == "(":
            rec = self.add("CMDSUB_DOLLAR", ctx, pos)
            sub = Lexer(t, self.exps, self.depth + 1, self.off, self.redirs)
            end, toks = sub.tokens(pos + 2, True)
            grammar(toks)
            rec["empty"] = not any(k == "W" for k, _ in toks)
            return end + 1
        if two[:1] == "{":
            self.add("PARAM", ctx, pos)
            q = pos + 2
            while q < len(t):
                c = t[q]
                if c == "}":
                    return q + 1
                if c == "\\":
                    q += 2
                elif c == "'" and ctx == "unquoted":
                    end = t.find("'", q + 1)
                    if end < 0:
                        raise Bad("open '")
                    q = end + 1
                elif c == '"':
                    q = self.dquote(q + 1)
                elif c == "$":
                    q = self.dollar(q, ctx)
                elif c == "`":
                    q = self.backq(q, ctx)
                else:
                    q += 1
            raise Bad("open ${")
        nxt = two[:1]
        if nxt in NAME0:
            self.add("PARAM", ctx, pos)
            q = pos + 2
            while q < len(t) and t[q] in NAMEN:
                q += 1
            return q
        if nxt and nxt in SPECIAL:
            self.add("PARAM", ctx, pos)
            return pos + 2
        return pos + 1

    def backq(self, pos, ctx):
        t = self.t
        rec = self.add("CMDSUB_BACKTICK", ctx, pos)
        q, inner = pos + 1, ""
        unesc = "$`\\" + ('"' if ctx == "dq" else "")
        while q < len(t):
            if t[q] == "`":
                sub = Lexer(inner, self.exps, self.depth + 1, self.off + pos + 1, self.redirs)
                _, toks = sub.tokens(0, False)
                grammar(toks)
                rec["empty"] = not any(k == "W" for k, _ in toks)
                return q + 1
            if t[q] == "\\" and q + 1 < len(t):
                inner += t[q + 1] if t[q + 1] in unesc else t[q:q + 2]
                q += 2
            else:
                inner += t[q]
                q += 1
        raise Bad("open `")


def grammar(toks):
    """Grammar over the flat token list; returns (commands, top-level control ops)."""
    stack = [{"words": [], "cmds": [], "need": True, "last": None, "redir": False, "sub": False}]
    top_ops = []
    for kind, val in toks:
        f = stack[-1]
        if kind == "W":
            if f["sub"] and not f["redir"]:
                raise Bad("word after subshell")
            if f["redir"]:
                f["redir"] = False
                if not f["words"]:
                    f["words"].append("(redir)")
            else:
                f["words"].append(val)
        elif kind == "R":
            if f["redir"]:
                raise Bad("redir redir")
            f["redir"] = True
        elif val == "(":
            if f["words"] or f["redir"]:
                raise Bad("( mid command")
            stack.append({"words": [], "cmds": [], "need": True, "last": None, "redir": False, "sub": False})
        elif val == ")":
            if len(stack) == 1:
                raise Bad("stray )")
            if f["redir"]:
                raise Bad("redir before )")
            if f["words"]:
                f["cmds"].append(f["words"])
            elif f["last"] in ("|", "&&", "||"):
                raise Bad("op before )")
            if not f["cmds"]:
                raise Bad("empty subshell")
            stack.pop()
            stack[-1]["words"].append("(subshell)")
            stack[-1]["sub"] = True
        else:
            if f["redir"]:
                raise Bad("redir before op")
            if f["words"]:
                f["cmds"].append(f["words"])
                f["words"] = []
                f["need"] = False
            f["sub"] = False
            if val == "\n":
                if f["last"] in ("|", "&&", "||"):
                    continue
                if len(stack) == 1:
                    top_ops.append(val)
                f["last"], f["need"] = None, True
                continue
            if f["need"] or val == ";;":
                raise Bad("unexpected op")
            if len(stack) == 1:
                top_ops.append(val)
            f["last"], f["need"] = val, True
    if len(stack) != 1:
        raise Bad("open (")
    f = stack[0]
    if f["redir"]:
        raise Bad("redir at end")
    if f["words"]:
        f["cmds"].append(f["words"])
    elif f["last"] in ("|", "&&", "||"):
        raise Bad("op at end")
    return f["cmds"], top_ops


def analyse(cmd):
    exps, redirs = [], []
    try:
        _, toks = Lexer(cmd, exps, 0, 0, redirs).tokens(0, False)
        cmds, ops = grammar(toks)
        return cmds, ops, exps, redirs, False
    except Bad:
        return None, None, exps, redirs, True


def blob(s):
    data = "".join("\ufffd" if 0xD800 <= ord(c) <= 0xDFFF else c for c in s).encode("utf-8")
    return hashlib.sha1(("blob %d" % len(data)).encode() + b"\x00" + data).hexdigest()


def hazard(s):
    out = [name for name, hit in (("percent", "%" in s),
                                  ("backslash", "\\" in s or any(ord(c) < 32 for c in s)),
                                  ("leading_dash", s[:1] == "-")) if hit]
    return "+".join(out) or "-"


def derive(s, version, gd):
    if len(s) > 200 or (gd is not None and (gd == "" or len(gd) > 64 or
                                            any(c in "'\"\\\n\t" or ord(c) < 32 or ord(c) > 126 for c in gd))):
        return [version, "BAD_INPUT", "-", "-", "-", "-", "-", "-"]
    if version == "post":
        argv = ["git"] + ([] if gd is None else ["--git-dir", gd]) + ["hash-object", "-w", "--stdin"]
        return [version, "NO_SHELL", "no", "-", "argv:" + " ".join(argv), "-", blob(s),
                "-" if gd is None else "GITDIR_ARGV"]
    lit = stringify(s)
    gds = "" if gd is None else "--git-dir " + gd
    cmd = "printf " + lit + " | git " + gds + " hash-object -w --stdin"
    cmds, ops, exps, redirs, err = analyse(cmd)
    lo, hi = 7, 7 + len(lit)
    mine = [e for e in exps if lo <= e["start"] < hi]
    kinds = sorted({e["kind"] for e in mine})
    want = [["printf", lit], ["git"] + ([] if gd is None else ["--git-dir", gd]) + ["hash-object", "-w", "--stdin"]]
    shape = (not err) and ops == ["|"] and cmds == want
    hz = hazard(s)
    if err:
        label, structure = "SYNTAX_ERROR", "error"
    else:
        structure = "pipeline" if shape else "changed"
        cmdsubs = [e for e in mine if e["kind"] in ("CMDSUB_DOLLAR", "CMDSUB_BACKTICK")]
        if any(not e["empty"] for e in cmdsubs):
            label = "CMD_INJECTION"
        elif cmdsubs:
            label = "EMPTY_CMDSUB"
        elif "ARITH" in kinds:
            label = "ARITH_EXPANSION"
        elif "PARAM" in kinds:
            label = "PARAM_EXPANSION"
        else:
            label = "PRINTF_FORMAT" if hz != "-" else "LITERAL_OK"
    if gd is None:
        gl = "-"
    elif err:
        gl = "GITDIR_SYNTAX_ERROR"
    else:
        gstart = len("printf ") + len(lit) + len(" | git ")
        gx = [e for e in exps if e["start"] >= gstart]
        if any(e["kind"].startswith("CMDSUB") and not e["empty"] for e in gx) or len(ops) != 1:
            gl = "GITDIR_CMD_INJECTION"
        elif redirs:
            gl = "GITDIR_REDIRECT"
        elif not shape:
            gl = "GITDIR_ARGV_CHANGED"
        elif gx:
            gl = "GITDIR_EXPANSION"
        else:
            gl = "GITDIR_OK"
    b = blob(s) if label == "LITERAL_OK" and structure == "pipeline" else "-"
    return [version, label, "sh", "+".join(kinds) or "-", structure, hz, b, gl]


def main():
    if sys.argv[1:] == ["sweep"]:
        print("\t".join(["kind", "input_json", "pre_label", "pre_expansions", "printf_hazard", "pre_gitdir", "post_label"]))
        alpha = ("a", " ", "$", "(", ")", "`", "{", "}", '"', "\\", "%", ";", "|", "#", "-", "\n")
        for k in (1, 2, 3):
            for c in itertools.product(alpha, repeat=k):
                s = "".join(c)
                a, b = derive(s, "pre", None), derive(s, "post", None)
                print("\t".join(["str", json.dumps(s), a[1], a[3], a[5], "-", b[1]]))
        galpha = ("a", " ", "$", "(", ")", "`", ";", "|", "&", ">", "#", "{")
        for k in (1, 2):
            for c in itertools.product(galpha, repeat=k):
                g = "".join(c)
                a, b = derive("x", "pre", g), derive("x", "post", g)
                print("\t".join(["gitdir", json.dumps(g), a[1], a[3], a[5], a[7], b[7]]))
        return
    print("\t".join(["id", "version", "label", "shell", "expansions", "structure", "printf_hazard",
                     "stdin_blob", "gitdir_label"]))
    for line in (REPO / "fixtures" / "cases.tsv").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        cid, sj, gj = line.split("\t")
        s, g = json.loads(sj), (None if gj == "-" else json.loads(gj))
        for v in ("pre", "post"):
            print("\t".join([cid] + derive(s, v, g)))


if __name__ == "__main__":
    main()
