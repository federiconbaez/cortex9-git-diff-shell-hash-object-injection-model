"""Fixture loading, fixed sweep and results writer (deterministic, stdlib only).

fixtures/cases.tsv columns: id, input string as a JSON string literal, gitDir
as a JSON string literal or `-` for none.
"""
import hashlib
import itertools
import json
from pathlib import Path

from .model import HEADER, evaluate

SWEEP_ALPHABET = ("a", " ", "$", "(", ")", "`", "{", "}", '"', "\\", "%", ";", "|", "#", "-", "\n")
GITDIR_ALPHABET = ("a", " ", "$", "(", ")", "`", ";", "|", "&", ">", "#", "{")


def load_cases(path):
    cases = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        f = line.split("\t")
        if len(f) != 3:
            raise ValueError("bad fixture line: %r" % line)
        s = json.loads(f[1])
        g = None if f[2] == "-" else json.loads(f[2])
        cases.append((f[0], s, g))
    ids = [c[0] for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate fixture id")
    return cases


def sweep_strings():
    for k in (1, 2, 3):
        for combo in itertools.product(SWEEP_ALPHABET, repeat=k):
            yield "".join(combo)


def sweep_gitdirs():
    for k in (1, 2):
        for combo in itertools.product(GITDIR_ALPHABET, repeat=k):
            yield "".join(combo)


def _j(s):
    return json.dumps(s, ensure_ascii=True)


def case_rows(cases):
    yield ["id"] + HEADER
    for cid, s, g in cases:
        for v in ("pre", "post"):
            yield [cid] + evaluate(s, v, g).row()


def sweep_rows():
    yield ["kind", "input_json", "pre_label", "pre_expansions", "printf_hazard", "pre_gitdir", "post_label"]
    for s in sweep_strings():
        a, b = evaluate(s, "pre"), evaluate(s, "post")
        yield ["str", _j(s), a.label, a.expansions, a.printf_hazard, "-", b.label]
    for g in sweep_gitdirs():
        a, b = evaluate("x", "pre", g), evaluate("x", "post", g)
        yield ["gitdir", _j(g), a.label, a.expansions, a.printf_hazard, a.gitdir_label, b.gitdir_label]


def write_results(cases_path, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "cases.tsv": "".join("\t".join(r) + "\n" for r in case_rows(load_cases(cases_path))),
        "sweep.tsv": "".join("\t".join(r) + "\n" for r in sweep_rows()),
    }
    sums = []
    for name, text in files.items():
        data = text.encode("utf-8")
        (out / name).write_bytes(data)
        sums.append("%s  %s\n" % (hashlib.sha256(data).hexdigest(), name))
    (out / "SHA256SUMS").write_bytes("".join(sums).encode("utf-8"))
