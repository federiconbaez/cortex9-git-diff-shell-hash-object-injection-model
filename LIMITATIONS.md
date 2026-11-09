# Limitations

- **A model is not a finding.** Nothing here was run against `git-diff`,
  Node, shelljs, a shell or git. The labels describe the model, built from
  the saved diff, the GHSA/NVD text and the POSIX shell grammar.
- **The model never executes a shell.** Because of that, its parser was
  **not cross-checked against a real `sh`** (not even `sh -n`): agreement
  with dash or bash on the 4368 sweep strings and on the fixtures is
  unverified. The parser covers words, quotes, backslash, `$(...)`,
  backticks, `$((...))`, `${...}`, `$name` / special parameters, comments,
  control and redirection operators and `( ... )` subshells. It does not
  cover here-documents, `case`/`if`/loops/functions, aliases, `!`, or
  shell-specific extensions (bash `$'...'`, `<(...)`, arithmetic that runs
  commands through array subscripts). `${}` (bad substitution, a runtime
  error in real shells) is labelled `PARAM_EXPANSION`.
- **Which shell.** shelljs `exec` runs the line through the platform shell
  (`/bin/sh` on POSIX: dash on Debian/Ubuntu, bash elsewhere); the model
  follows POSIX `sh`. On Windows (`cmd.exe`) the analysis does not apply.
- **printf is not simulated.** `PRINTF_FORMAT` only flags `%`, `\` (JSON
  adds `\n`, `\t`, `\uXXXX` for control characters) and a leading `-` in the
  format argument; the exact bytes printf would emit are not computed, so
  `stdin_blob` is shown for pre only when the content is unchanged
  (`LITERAL_OK`).
- **`CMD_INJECTION` means "the shell would run a command from the input"**,
  i.e. a non-empty command substitution. What the command could do depends
  on the process privileges (advisory: the Node.js process).
- **Outside the diff:** the rest of `generateDiff` (what happens with the two
  hashes, the `else` branch at diff:50) is not in the diff and is not
  modelled. The string form `gitDir = '--git-dir ' + gitDir` is **still
  computed after the fix** (new:21-25, diff:18-22); whether a later command
  outside the hunk still uses it in a shell is **not verified**. The
  `GITDIR_*` labels are a model observation, not a finding; the CVE is about
  the diffed strings, not about `gitDir`.
- **Stale comment:** old:25 (diff:24) said "Single quotes is needed here",
  but the code used `JSON.stringify` (double quotes). Recorded as a
  reading of the diff, nothing more.
- **Input domain:** strings up to 200 code units; gitDir 1-64 printable ASCII
  characters without quotes, backslash, tab or newline. Anything else is
  `BAD_INPUT`. Lone surrogates are written as U+FFFD, as Node does.
- **Sweep:** `results/sweep.tsv` is a fixed grid, not a proof.
- Nothing is attributed beyond the commit, GHSA and CVE in SOURCES.md.
