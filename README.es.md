# cortex9-git-diff-shell-hash-object-injection-model

Modelo offline de **CVE-2026-110634** (GHSA-6wfj-92cw-88vg, CWE-78):
inyección de comandos del sistema operativo en el paquete npm `git-diff`
antes de `2.0.7`. Antes del commit del fix
[bfd727b](https://github.com/danday74/git-diff/commit/bfd727b6cf1daa671c3528d1d681f55b70e8fb19)
cada cadena a comparar se metía en `printf "..."` con `JSON.stringify` y la
línea entera se ejecutaba con una shell a través de `shelljs.exec`;
`JSON.stringify` escapa comillas y barras invertidas, pero no `$(...)` ni
backticks, que la shell sigue expandiendo dentro de comillas dobles. Después
del fix la cadena llega a `git hash-object -w --stdin` por stdin mediante
`execFileSync`, sin shell.

**El modelo nunca ejecuta nada.** Construye la cadena de comando de antes
del fix y el vector argv de después exactamente como el diff, y luego los
*clasifica* con un parser estático de POSIX sh escrito en Python. Sin shell,
sin git, sin Node, sin subprocesos y sin red: `tests/` comprueba que `src/`
y `scripts/` no importan módulos de procesos ni de red, y que un payload
canario con `touch` nunca crea su archivo. Solo biblioteca estándar de
Python.

English: [README.md](README.md). Ejercicios: [PRACTICE.md](PRACTICE.md).
Límites: [LIMITATIONS.md](LIMITATIONS.md). Fuentes: [SOURCES.md](SOURCES.md).

## Qué se modela

`diff:N` es la línea N del diff guardado; `old:N` / `new:N` son líneas de
`js/gitDiffReal/generateDiff/index.js` antes / después del fix.

| | pre (old) | post (new) |
|---|---|---|
| gitDir | cadena `'--git-dir ' + gitDir`, old:19-23 (diff:18-22) | `gitDirArgs = ['--git-dir', gitDir]`, new:20 (diff:17) |
| comando | `'printf ' + JSON.stringify(str1) + ' \| git ' + gitDir + ' hash-object -w --stdin'`, old:26-27 (diff:25-26) | `execFileSync('git', gitDirArgs.concat(['hash-object','-w','--stdin']), {input})`, new:33-43 (diff:33-43) |
| ejecución | `exec(gitHashCmd1, {silent: true})` (shelljs), old:29-30 (diff:45-46) | `gitHashObject(str1)`, new:45-46 (diff:47-48) |

`js_json_stringify` reproduce `JSON.stringify` para cadenas. `shell.parse`
recorre el comando como lo *parsearía* un `sh` POSIX (comillas, barra
invertida, `$(...)`, backticks, `$((...))`, `${...}`, `$nombre`,
comentarios, operadores, subshells) y anota las expansiones; no ejecuta
nada.

Etiquetas (pre): `CMD_INJECTION` (sustitución de comandos no vacía dentro
del argumento de printf), `EMPTY_CMDSUB`, `ARITH_EXPANSION`,
`PARAM_EXPANSION` (`$HOME`, `$$`, `${PATH}`: valores del entorno se filtran
en el texto hasheado), `PRINTF_FORMAT` (sin expansión, pero `%`, `\` o un
`-` inicial llegan al formato de printf y alteran el contenido: no es
inyección), `SYNTAX_ERROR` (la shell rechaza la línea, no se ejecuta nada),
`LITERAL_OK`, `BAD_INPUT`. Post: siempre `NO_SHELL`. `gitdir_label`
clasifica aparte la opción gitDir (`GITDIR_CMD_INJECTION`,
`GITDIR_REDIRECT`, `GITDIR_ARGV_CHANGED`, `GITDIR_EXPANSION`, `GITDIR_OK`
en pre; `GITDIR_ARGV` en post). `stdin_blob` es el id de blob de git
(`sha1("blob <len>\0" + bytes)`, calculado con hashlib) de lo que guardaría
`git hash-object`.

## Evidencia diferencial

| Caso | pre | post |
|---|---|---|
| `p01` `$(id)` (advisory) | `CMD_INJECTION`: `printf "$(id)" \| git  hash-object -w --stdin` | `NO_SHELL`, argv `git hash-object -w --stdin`, la cadena por stdin |
| `p02` `` `id` `` (advisory) | `CMD_INJECTION` | `NO_SHELL` |
| `p04` `\$(id)` | `CMD_INJECTION`: JSON convierte `\` en `\\`, la shell lee `\\` como una `\` y `$(` sigue activo | `NO_SHELL` |
| `n06` `; \| & > < ( )` | `LITERAL_OK`: dentro de comillas dobles son texto | `NO_SHELL`, mismo blob |
| `o01` `$HOME` | `PARAM_EXPANSION` (no es ejecución de comandos) | `NO_SHELL` |
| `o07` `100%` | `PRINTF_FORMAT` (contenido alterado, no inyección) | `NO_SHELL`, bytes exactos |
| `a10` gitDir `x;id` | `GITDIR_CMD_INJECTION` (sin comillas en la línea de shell) | `GITDIR_ARGV` para hash-object |

Para toda cadena `LITERAL_OK` los ids de blob pre y post coinciden
(`test_literal_ok_pre_and_post_hash_the_same_bytes`). Barrido fijo
(`results/sweep.tsv`): las 4368 cadenas de longitud 1-3 sobre 16 caracteres
relevantes para la shell -> pre 8 `CMD_INJECTION`, 34 `EMPTY_CMDSUB`, 121
`PARAM_EXPANSION`, 1846 `PRINTF_FORMAT`, 770 `SYNTAX_ERROR`, 1589
`LITERAL_OK`; post 4368 `NO_SHELL`. Más 156 valores de gitDir de longitud
1-2. Un barrido es una grilla fija, no una prueba.

## Ejecutar

```sh
python3 tests/run.py                                 # 20 tests, un skip falla
python3 scripts/derive_expected.py | diff - fixtures/expected.tsv
python3 scripts/derive_expected.py sweep | diff - results/sweep.tsv
PYTHONPATH=src python3 -m gitdiff_model results fixtures/cases.tsv /tmp/r && diff -r results /tmp/r
PYTHONPATH=src python3 -m gitdiff_model case pre '$(id)'
PYTHONPATH=src python3 -m gitdiff_model command '$(id)' 'x;id'
```

`fixtures/cases.tsv` guarda cada entrada como literal de cadena JSON.
`scripts/derive_expected.py` no importa `src/`; recalcula cada expectativa
con un lexer + chequeo de gramática escritos por separado y `json.dumps`.

Un modelo no es un hallazgo: ver [LIMITATIONS.md](LIMITATIONS.md).

Licencia: Apache-2.0.
