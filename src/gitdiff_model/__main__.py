"""CLI (never runs a shell or git; it prints what the model derives).
  python -m gitdiff_model case pre|post '<string>' [gitDir]
  python -m gitdiff_model command '<string>' [gitDir]     # print the pre-fix shell string
  python -m gitdiff_model results fixtures/cases.tsv <out_dir>
"""
import sys

from .fixtures import write_results
from .model import HEADER, evaluate, post_argv, pre_command


def main(argv):
    if len(argv) >= 3 and argv[0] == "case":
        o = evaluate(argv[2], argv[1], argv[3] if len(argv) > 3 else None)
        for k, v in zip(HEADER, o.row()):
            print("%s\t%s" % (k, v))
        return 0
    if len(argv) >= 2 and argv[0] == "command":
        g = argv[2] if len(argv) > 2 else None
        print("pre  (shelljs.exec):", pre_command(argv[1], g))
        print("post (execFileSync):", post_argv(g), "+ stdin")
        return 0
    if len(argv) == 3 and argv[0] == "results":
        write_results(argv[1], argv[2])
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
