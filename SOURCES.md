# Sources

Local copies under `security-research-45/sources/cve2026/` (not in this
repo), fetched read-only; the NVD response carries the timestamp
2026-11-09T11:33:59 (UTC). Each SHA-256 below was checked against
`sources/cve2026/SHA256SUMS` (`sha256sum -c`: 269 OK, 0 FAILED) before use.
The copy in `sources/cve2026/batch3/diffs/` is byte-identical to the one in
`diffs/`.

| Source | URL | Commit | Used for | SHA-256 of copy |
|---|---|---|---|---|
| Fix diff `diffs/CVE-2026-110634_git-diff_bfd727b6cf1d.diff` (1 file, 51 lines, blob 3f14cd3 -> 41bd88c) | https://github.com/danday74/git-diff/commit/bfd727b6cf1daa671c3528d1d681f55b70e8fb19 | bfd727b6cf1daa671c3528d1d681f55b70e8fb19 | hunks diff:5-12 (old:1-6 / new:1-7) and diff:13-51 (old:16-33 / new:17-49); cited 9, 17-22, 24-26, 27-43, 45-48, 50 | 40b45e8c25de5a5eb0e0aa751b9500e1f8c6a42f1d02c5610461f59b3b8cbf17 |
| GHSA record `ghsa_rec/CVE-2026-110634.json` | https://github.com/advisories/GHSA-6wfj-92cw-88vg | references bfd727b and PR #16 | affected `< 2.0.7`, fixed `2.0.7`; CWE-78; `$(cmd)` / backtick wording; reference to the vulnerable lines `a85a649.../index.js#L26-L30` | a02b76ae4c0db60ccea72e17a87b902635ae9a0611cbb5f0d6ee9b94cd26ae1b |
| NVD record `nvd/CVE-2026-110634.json` (Deferred, published 2026-10-14) | https://nvd.nist.gov/vuln/detail/CVE-2026-110634 | references bfd727b | description, CVSS 3.1 9.8 / 4.0 9.3 (VulnCheck CNA) | f603c3eaa1553ca0e06c81e0297c8beda6d271b3705411afc7cf94718dcd198b |
| cve.org record `cveorg/CVE-2026-110634.json` (PUBLISHED 2026-10-14) | https://www.cve.org/CVERecord?id=CVE-2026-110634 | references bfd727b | state and CNA (VulnCheck) | ca5f281a21790de97d2705454bed65828b7af9c25270ff40716385242520ff71 |

The GHSA/NVD reference to `a85a649badc4c6bba991e87e82382b7d3cdd6634` lines
26-30 matches the old-side lines of the diff (old:26-27 build the commands,
old:29-30 run them). Whether a85a649 is the direct parent of bfd727b was
**not verified** (no local commit metadata: `commits.tsv` has no row for
this CVE). PR #16 and the VulnCheck advisory page were not downloaded.

POSIX shell parsing and the git object format (`blob <len>\0<data>`, SHA-1)
are used as public specifications, not downloaded sources.

Hidden instructions: none found. The diff, GHSA, NVD and cve.org copies were
read in full and grepped for text addressed to tools or agents; the only
match was the code comment `/* istanbul ignore else */` (diff:50), a normal
coverage-tool directive.
