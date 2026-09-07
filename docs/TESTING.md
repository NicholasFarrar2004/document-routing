# Testing

Validation uses independently invented documents in isolated temporary directories. No original records or live migration targets are used.

## Recorded results

Validated on macOS arm64 with Python 3.12.2 and PowerShell 7.6.5:

| Check | Result |
| --- | --- |
| Python unit and CLI suite | 23 tests passed |
| Standalone exhibit example | Exact expected CSV: 3 routed, 2 review |
| PowerShell behavior suite | 14 groups passed |
| Complete Python-to-PowerShell workflow | Passed: preview, verified copy, identical rerun and conflict preservation |

The complete workflow starts with five newly created exhibit documents. It exports only three unambiguous rows, confirms preview creates no destination, copies and compares all three file contents, repeats for three identical-file skips, then introduces a fictional conflict and confirms it stays untouched. Original synthetic source bytes remain unchanged throughout.

The PowerShell suite also checks quoted CSV, punctuation and trailing spaces, missing sources, malformed mappings, traversal, duplicate destinations, file/parent collisions, symbolic links, log protection, case-variant root overlap, an actual path longer than 260 characters, and 32 files copied with eight workers. Those are test-fixture dimensions, not measurements of a production system.

## Run the checks

From the repository root, with Python 3.10+ and PowerShell 7.2+ installed:

```sh
python3 -B -m unittest discover -s python/tests -v
python3 -B python/demo.py
python3 -B tests/verify_pipeline.py
```

If PowerShell is outside PATH, pass `--pwsh /path/to/pwsh` to `tests/verify_pipeline.py`.

Run the separate copier suite with a physical, existing temporary parent directory:

```sh
python3 -B powershell/verify.py --pwsh pwsh --work-root /path/to/temporary-parent
```

The integrated test cleans only its own temporary directory. The separate copier suite retains its new fictional test directory and report for inspection.

## What remains unverified

Windows extended paths, UNC shares, Windows-specific filenames, network filesystems and lower supported runtime versions need execution on those platforms. A long path tested on macOS does not establish Windows long-path compatibility.

Path checks assume trusted, stationary folders. They do not provide protection against a hostile concurrent process changing filesystem paths. Hashes compare observed content; they do not verify permissions, metadata or an immutable snapshot. See the [copier limitations](../powershell/README.md#verification-and-limits) and [planner limitations](../python/README.md#verify-and-limitations).

This edition demonstrates its own documented behavior. It does not claim production validation or parity with the original private workflow.
