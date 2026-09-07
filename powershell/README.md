# Preview-first file copying with PowerShell

This utility copies files according to a two-column CSV. It shows what would happen before copying, preserves existing files, and records a result for every mapping row. It does not decide where files belong: the mapping is explicit input.

The included demonstration uses entirely invented workshop notes and library-poster text. No real documents, catalogs, folder templates or business rules are included.

**Explore:** [Try the demo](#try-the-demo) · [Interface](#interface) · [How it works](#how-it-works) · [Verification](#verification-and-limits)

## A small example

| Source relative path | Destination relative path | Result when destination is absent |
|---|---|---|
| `bench notes.txt` | `bench notes.txt` | Preview: `WOULD_COPY`; execute: `COPIED_VERIFIED` |
| `illustration [draft].txt` | `illustration [draft].txt` | Brackets are literal filename characters |
| `reading, list.txt` | `display/reading-list.txt` | Quoted CSV handles the comma; the destination parent is created only during execution |

If a destination file already has the same SHA-256, the result is `SKIP_IDENTICAL`. Different content produces `CONFLICT`, even when the files have the same size. Existing destination files are never overwritten.

## Try the demo

Requires PowerShell 7.2 or newer. The executable is normally `pwsh`. Run these commands **inside PowerShell**, from this directory. The fixture command explicitly creates a new temporary directory; it refuses an existing one.

```powershell
$demo = Join-Path ([IO.Path]::GetTempPath()) ('workshop-' + [guid]::NewGuid().ToString('N'))
./examples/Create-WorkshopFixture.ps1 -OutputRoot $demo
# Resolve platform aliases in the temporary path before containment checks.
$demo = (Get-Item -LiteralPath $demo).FullName
if ($IsMacOS -and $demo.StartsWith('/var/')) { $demo = '/private' + $demo }
$catalog = Join-Path $demo 'mapping.csv'
$source = Join-Path $demo 'incoming'
$destination = Join-Path $demo 'collection'

./Copy-WorkshopFiles.ps1 -CatalogPath $catalog -SourceRoot $source -DestinationRoot $destination -AsJson
```

Expected preview: three `WOULD_COPY` records and no `collection` directory. After reviewing those records, explicitly opt in:

```powershell
./Copy-WorkshopFiles.ps1 -CatalogPath $catalog -SourceRoot $source -DestinationRoot $destination -Execute -LogPath (Join-Path $demo 'copy-log.csv') -AsJson
```

Expected execution: three `COPIED_VERIFIED` records with matching source/destination SHA-256 values. Repeating without `-LogPath` returns three `SKIP_IDENTICAL` records. Existing logs cannot be overwritten. The fixture and resulting files remain available for inspection; no reset or cleanup command is provided.

## Interface

```text
Copy-WorkshopFiles.ps1
  -CatalogPath <CSV>
  -SourceRoot <existing directory>
  -DestinationRoot <separate directory path>
  [-ThrottleLimit <1..16>] [-Execute] [-LogPath <new CSV>] [-AsJson]
```

The CSV must contain exactly `SourceRelativePath,DestinationRelativePath` in that order. Paths cannot be absolute, contain traversal segments or name alternate streams. Duplicate destinations, file/parent collisions, overlapping roots and existing symbolic-link/junction ancestors are refused. Comparisons are deliberately conservative about case.

Preview is the default and writes nothing unless a new `-LogPath` is explicitly requested. Execution creates only required destination directories and missing files. Source files remain untouched. Logs contain relative paths, hashes, action names and error-type names; they are ordinary runtime output, not safe-to-publish data automatically.

Exit status is **0** for successful preview/copy/identical-file outcomes, **2** for per-file missing-source, conflict, copy-error or hash-mismatch outcomes, and nonzero for invalid configuration or fatal errors. Per-file outcomes are returned as PowerShell objects, or a JSON array with `-AsJson`. Explicit CSV logs are flushed as results arrive; their row order may differ under concurrency. JSON results follow input order.

## How it works

[Copy-WorkshopFiles.ps1](Copy-WorkshopFiles.ps1) retains reusable engineering patterns from an earlier file-copy utility: quoted CSV parsing, literal long-path handling, bounded worker runspaces, coordinator-owned CSV logging, and per-file failure reporting. The public interface, validation and fixtures were independently prepared for this generic edition. No operational classification rules or original data were retained.

The edition strengthens conservative copying: preview checks current destinations; existing files are compared by SHA-256; new files use the no-overwrite copy API and are hashed afterward. A count or equal byte length is not represented as content verification. Each worker waits for directory creation rather than racing against a shared directory-cache flag.

This is copying only. There are no organizer, move, reset, deletion, template or folder-taxonomy operations.

## Verification and limits

Run the fictional-only verification suite with Python 3.10+ and PowerShell:

```text
python3 verify.py --pwsh pwsh --work-root <existing-temporary-directory>
```

The suite creates a new isolated directory under that parent and retains its files and `verification.json`. Use a resolved physical path: symbolic-link ancestors are intentionally rejected.

Executed on macOS arm64 with the official portable PowerShell 7.6.5 runtime. Checks cover preview non-mutation, copy hashes, reruns, same-size and different-size conflicts, quoted/punctuated filenames and trailing spaces, missing sources, invalid mappings, containment, symbolic links, log protection, a real path longer than 260 characters, and 32 files copied with eight workers.

**Windows extended-path and UNC branches have not been executed on Windows.** Network-share behavior, Windows-specific filename restrictions and lower PowerShell versions remain unverified. Windows-incompatible quote characters are tested only on Unix hosts.

Use trusted, stationary folders. Ancestor validation does not prevent a hostile process from swapping paths after validation; the utility is not a security sandbox. Source edits during copying can produce a hash mismatch. Failed or mismatching outputs are retained for inspection, never automatically deleted or replaced. Hash checks verify observed file content, not metadata, permissions, ACLs or an immutable filesystem snapshot.

Runtime documentation: [Microsoft's PowerShell installation guide](https://learn.microsoft.com/en-us/powershell/scripting/install/install-powershell-on-macos) and [official release assets](https://github.com/PowerShell/PowerShell/releases). Validation used a temporary portable runtime with its publisher-provided SHA-256 checked, not a system installation.

This edition was prepared with AI-assisted code adaptation and verification. No open-source license is assigned here; publication is handled separately from local preparation.
