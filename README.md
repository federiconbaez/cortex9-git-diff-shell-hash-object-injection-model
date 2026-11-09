# cortex9-git-diff-shell-hash-object-injection-model

Offline model of **CVE-2026-110634** (GHSA-6wfj-92cw-88vg, CWE-78): OS command
injection in the npm package `git-diff` before `2.0.7`. Before the fix
commit [bfd727b](https://github.com/danday74/git-diff/commit/bfd727b6cf1daa671c3528d1d681f55b70e8fb19)
each diffed string was put inside `printf "..."` with `JSON.stringify` and the
whole line was run through a shell by `shelljs.exec`; `JSON.stringify` escapes
quotes and backslashes but not `$(...)` or backticks, which a shell still
expands inside double quotes. After the fix the string goes to
`git hash-object -w --stdin` on stdin through `execFileSync`, with no shell.

**The model never executes anything.** It builds the pre-fix command string
and the post-fix argv vector exactly as the diff does, then *classifies*
them with a static POSIX-sh parser written in Python. No shell, no git, no
Node, no subprocess, no network: `tests/` checks that `src/` and
`scripts/` import no process or network module, and that a `touch` canary
payload never creates its file. Python standard library only.

Spanish: [README.es.md](README.es.md). Exercises: [PRACTICE.md](PRACTICE.md).
Limits: [LIMITATIONS.md](LIMITATIONS.md). Sources: [SOURCES.md](SOURCES.md).

## What is modelled

`diff:N` is line N of the saved diff; `old:N` / `new:N` are lines of
`js/gitDiffReal/generateDiff/index.js` before / after the fix.

| | pre (old) | post (new) |
|---|---|---|
| gitDir | `'--git-dir ' + gitDir` string, old:19-23 (diff:18-22) | `gitDirArgs = ['--git-dir', gitDir]`, new:20 (diff:17) |
| command | `'printf ' + JSON.stringify(str1) + ' \| git ' + gitDir + ' hash-object -w --stdin'`, old:26-27 (diff:25-26) | `execFileSync('git', gitDirArgs.concat(['hash-object','-w','--stdin']), {input})`, new:33-43 (diff:33-43) |
| runner | `exec(gitHashCmd1, {silent: true})` (shelljs), old:29-30 (diff:45-46) | `gitHashObject(str1)`, new:45-46 (diff:47-48) |

`js_json_stringify` reproduces `JSON.stringify` for strings. `shell.parse`
scans the command like a POSIX `sh` would *parse* it (quotes, backslash,
`$(...)`, backticks, `$((...))`, `${...}`, `$name`, comments, operators,
subshells) and records expansions; it executes nothing.

Labels (pre): `CMD_INJECTION` (a non-empty command substitution inside the
printf argument), `EMPTY_CMDSUB`, `ARITH_EXPANSION`, `PARAM_EXPANSION`
(`$HOME`, `$$`, `${PATH}`: environment values leak into the hashed text),
`PRINTF_FORMAT` (no expansion, but `%`, `\` or a leading `-` reach printf's
format argument, so the content is altered: not injection), `SYNTAX_ERROR`
(the shell rejects the line, nothing runs), `LITERAL_OK`, `BAD_INPUT`.
Post: always `NO_SHELL`. `gitdir_label` classifies the gitDir option
separately (`GITDIR_CMD_INJECTION`, `GITDIR_REDIRECT`,
`GITDIR_ARGV_CHANGED`, `GITDIR_EXPANSION`, `GITDIR_OK` pre; `GITDIR_ARGV`
post). `stdin_blob` is the git blob id (`sha1("blob <len>\0" + bytes)`,
computed with hashlib) of what `git hash-object` would store.

## Differential evidence

| Case | pre | post |
|---|---|---|
| `p01` `$(id)` (advisory) | `CMD_INJECTION`: `printf "$(id)" \| git  hash-object -w --stdin` | `NO_SHELL`, argv `git hash-object -w --stdin`, string on stdin |
| `p02` `` `id` `` (advisory) | `CMD_INJECTION` | `NO_SHELL` |
| `p04` `\$(id)` | `CMD_INJECTION`: JSON turns `\` into `\\`, the shell reads `\\` as one `\` and `$(` stays live | `NO_SHELL` |
| `n06` `; \| & > < ( )` | `LITERAL_OK`: inside double quotes these are plain text | `NO_SHELL`, same blob |
| `o01` `$HOME` | `PARAM_EXPANSION` (not command execution) | `NO_SHELL` |
| `o07` `100%` | `PRINTF_FORMAT` (content altered, not injection) | `NO_SHELL`, exact bytes |
| `a10` gitDir `x;id` | `GITDIR_CMD_INJECTION` (unquoted in the shell line) | `GITDIR_ARGV` for hash-object |

For every `LITERAL_OK` string the pre and post blob ids are equal
(`test_literal_ok_pre_and_post_hash_the_same_bytes`). Fixed sweep
(`results/sweep.tsv`): all 4368 strings of length 1-3 over 16 shell-relevant
characters -> pre 8 `CMD_INJECTION`, 34 `EMPTY_CMDSUB`, 121
`PARAM_EXPANSION`, 1846 `PRINTF_FORMAT`, 770 `SYNTAX_ERROR`, 1589
`LITERAL_OK`; post 4368 `NO_SHELL`. Plus 156 gitDir values of length 1-2.
A sweep is a fixed grid, not a proof.

## Run

```sh
python3 tests/run.py                                 # 20 tests, a skip fails
python3 scripts/derive_expected.py | diff - fixtures/expected.tsv
python3 scripts/derive_expected.py sweep | diff - results/sweep.tsv
PYTHONPATH=src python3 -m gitdiff_model results fixtures/cases.tsv /tmp/r && diff -r results /tmp/r
PYTHONPATH=src python3 -m gitdiff_model case pre '$(id)'
PYTHONPATH=src python3 -m gitdiff_model command '$(id)' 'x;id'
```

`fixtures/cases.tsv` stores each input as a JSON string literal.
`scripts/derive_expected.py` does not import `src/`; it re-derives every
expectation with a separately written lexer + grammar check and
`json.dumps`.

A model is not a finding: see [LIMITATIONS.md](LIMITATIONS.md).

License: Apache-2.0.
