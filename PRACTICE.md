# Guía práctica (8 niveles)

Ejercicios **offline y locales**. Úsalos solo con este modelo o en tus
propios laboratorios (un contenedor desechable tuyo, sin red, con
`git-diff` 2.0.6 y 2.0.7, o máquinas de HTB que te corresponda atacar).
Nunca contra sistemas ni servicios de terceros. Cada respuesta está
comprobada en `tests/test_model.py` (`PracticeLevels`). El modelo no ejecuta
nada: solo clasifica.

Comandos: `PYTHONPATH=src python3 -m gitdiff_model case pre|post '<cadena>' [gitDir]`
y `PYTHONPATH=src python3 -m gitdiff_model command '<cadena>' [gitDir]`.

**Básico**

1. **El caso normal.** `hello world` en `pre`. (nivel 1: `LITERAL_OK`)
2. **La línea de shell.** ¿Qué comando arma old:26 para `$(id)`? (nivel 2:
   `printf "$(id)" | git  hash-object -w --stdin`, con dos espacios porque
   gitDir está vacío)

**Intermedio**

3. **La inyección.** `$(id)` en `pre`. ¿Por qué las comillas dobles de
   `JSON.stringify` no protegen? (nivel 3: `CMD_INJECTION`)
4. **El escape que no escapa.** `\$(id)`. (nivel 4: `CMD_INJECTION`: JSON
   duplica la barra y la shell la consume)
5. **El fix bfd727b.** `$(id)` en `post`. ¿Qué líneas del diff quitan la
   shell? (nivel 5: `NO_SHELL`, diff:33-43 y diff:47-48)

**Avanzado**

6. **No todo es ejecución.** `$HOME` y `100%` en `pre`. (nivel 6:
   `PARAM_EXPANSION` y `PRINTF_FORMAT`: filtración de entorno y contenido
   alterado, no ejecución de comandos)
7. **Cuando la shell se niega.** `$(id` en `pre`. (nivel 7: `SYNTAX_ERROR`:
   no se ejecuta nada)
8. **La otra entrada.** gitDir `x;id` en `pre` y en `post`. (nivel 8:
   `GITDIR_CMD_INJECTION` y `GITDIR_ARGV`. Observación del modelo **no
   verificada**: ver LIMITATIONS.md)

Más allá, en tu laboratorio local: compara las etiquetas con el
comportamiento real solo dentro de tu contenedor desechable y sin red,
usando payloads inocuos (por ejemplo `$(touch /tmp/canario)`), nunca datos
ni sistemas ajenos. Anota las diferencias en LIMITATIONS.md antes de sacar
conclusiones. Para practicar con el modelo: añade un caso a
`fixtures/cases.tsv`, regenera `fixtures/expected.tsv` con
`scripts/derive_expected.py` y comprueba que el modelo coincide.
