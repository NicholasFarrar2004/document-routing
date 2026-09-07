#requires -Version 7.2
<#
.SYNOPSIS
Preview or copy explicitly mapped files without replacing existing files.
.DESCRIPTION
CSV columns: SourceRelativePath,DestinationRelativePath. Preview is the default.
No classification, folder template, deletion, reset or move operation is included.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$CatalogPath,
    [Parameter(Mandatory)][string]$SourceRoot,
    [Parameter(Mandatory)][string]$DestinationRoot,
    [ValidateRange(1,16)][int]$ThrottleLimit = 4,
    [switch]$Execute,
    [string]$LogPath,
    [switch]$AsJson
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-LongSafePath([string]$Path) {
    if (-not $IsWindows -or $Path.StartsWith('\\?\')) { return $Path }
    if ($Path.StartsWith('\\')) { return '\\?\UNC\' + $Path.Substring(2) }
    return '\\?\' + $Path
}

function Assert-NoLinks([string]$Path) {
    # Inspect existing ancestors, not just the leaf. Missing destination segments
    # are allowed; symbolic links and Windows junctions are not.
    $cursor = $Path
    while ($cursor) {
        try {
            $attributes = [IO.File]::GetAttributes((Get-LongSafePath $cursor))
            if (($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Symbolic links and junctions are not allowed in copy paths.'
            }
        } catch [IO.FileNotFoundException] {
        } catch [IO.DirectoryNotFoundException] {
        }
        $parent = [IO.Path]::GetDirectoryName($cursor)
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
}

function Resolve-Root([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path).TrimEnd([IO.Path]::DirectorySeparatorChar)
    if (-not $full) { throw 'A filesystem root is not a valid copy workspace.' }
    Assert-NoLinks $full
    return $full
}

function Resolve-Contained([string]$Root, [string]$Relative) {
    if ([string]::IsNullOrWhiteSpace($Relative) -or [IO.Path]::IsPathRooted($Relative) -or $Relative.Contains(':')) {
        throw 'CSV paths must be nonempty relative paths without drive or stream syntax.'
    }
    $segments = $Relative.Replace('\','/').Split('/')
    if (@($segments | Where-Object { $_ -in @('', '.', '..') }).Count) {
        throw 'Empty, dot and parent-traversal path segments are not allowed.'
    }
    $normalized = [string]::Join([IO.Path]::DirectorySeparatorChar, $segments)
    $full = [IO.Path]::GetFullPath([IO.Path]::Combine($Root, $normalized))
    $comparison = [StringComparison]::OrdinalIgnoreCase
    if (-not $full.StartsWith($Root + [IO.Path]::DirectorySeparatorChar, $comparison)) {
        throw 'CSV path escapes its configured root.'
    }
    Assert-NoLinks $full
    return $full
}

function Read-Mapping([string]$Path) {
    # Quoted commas, doubled quotes, embedded newlines and trailing spaces are
    # handled by the CSV parser. Paths are never interpreted as wildcards.
    Add-Type -AssemblyName Microsoft.VisualBasic.Core
    $parser = [Microsoft.VisualBasic.FileIO.TextFieldParser]::new([IO.Path]::GetFullPath($Path))
    $rows = [Collections.Generic.List[object]]::new()
    try {
        $parser.SetDelimiters(',')
        $parser.HasFieldsEnclosedInQuotes = $true
        $parser.TrimWhiteSpace = $false
        $header = $parser.ReadFields()
        if ($null -eq $header -or $header.Count -ne 2 -or
            $header[0] -cne 'SourceRelativePath' -or $header[1] -cne 'DestinationRelativePath') {
            throw 'CSV requires exactly SourceRelativePath,DestinationRelativePath in that order.'
        }
        while (-not $parser.EndOfData) {
            $fields = $parser.ReadFields()
            if ($fields.Count -ne 2) { throw 'Every CSV row must have exactly two fields.' }
            $rows.Add([pscustomobject]@{ SourceRelativePath=$fields[0]; DestinationRelativePath=$fields[1] })
        }
    } finally { $parser.Close() }
    if ($rows.Count -eq 0) { throw 'The mapping must contain at least one row.' }
    return $rows
}

$source = Resolve-Root $SourceRoot
$destination = Resolve-Root $DestinationRoot
$comparison = [StringComparison]::OrdinalIgnoreCase
$separator = [IO.Path]::DirectorySeparatorChar
if ($source.Equals($destination, $comparison) -or
    $source.StartsWith($destination + $separator, $comparison) -or
    $destination.StartsWith($source + $separator, $comparison)) {
    throw 'Source and destination roots must be separate, non-overlapping directories.'
}
if (-not [IO.Directory]::Exists((Get-LongSafePath $source))) { throw 'SourceRoot must be an existing directory.' }
if ([IO.File]::Exists((Get-LongSafePath $destination))) { throw 'DestinationRoot must be a directory path.' }

$items = [Collections.Generic.List[object]]::new()
# Conservative case-insensitive duplicates also protect case-insensitive volumes
# when validation runs on a Unix host.
$seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$ordinal = 0
foreach ($row in (Read-Mapping $CatalogPath)) {
    $src = Resolve-Contained $source $row.SourceRelativePath
    $dst = Resolve-Contained $destination $row.DestinationRelativePath
    if (-not $seen.Add($dst)) { throw 'Two mapping rows target the same destination.' }
    $items.Add([pscustomobject]@{ Index=$ordinal; Source=$src; Destination=$dst;
        SourceRelativePath=$row.SourceRelativePath; DestinationRelativePath=$row.DestinationRelativePath })
    $ordinal++
}
# Reject file/parent collisions before making any directories.
foreach ($item in $items) {
    $parent = [IO.Path]::GetDirectoryName($item.Destination)
    while ($parent.Length -gt $destination.Length) {
        if ($seen.Contains($parent)) { throw 'A destination file is also used as another row directory.' }
        $parent = [IO.Path]::GetDirectoryName($parent)
    }
}

$writer = $null
if ($LogPath) {
    $log = [IO.Path]::GetFullPath($LogPath)
    Assert-NoLinks $log
    if ($log.Equals($source, $comparison) -or $log.Equals($destination, $comparison) -or
        $log.Equals([IO.Path]::GetFullPath($CatalogPath), $comparison) -or
        $log.StartsWith($source + $separator, $comparison) -or
        $log.StartsWith($destination + $separator, $comparison)) {
        throw 'LogPath must be separate from the catalog and both copy roots.'
    }
    # Explicitly requesting a log permits only a NEW file; preview otherwise
    # writes nothing. The parent directory must already exist.
    $stream = [IO.File]::Open($log, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    $writer = [IO.StreamWriter]::new($stream, [Text.UTF8Encoding]::new($false))
    $writer.WriteLine('"Index","Action","SourceRelativePath","DestinationRelativePath","Bytes","SourceSHA256","DestinationSHA256","Error"')
}

$worker = {
    param($item, $execute, $windows)
    Set-StrictMode -Version Latest
    $ErrorActionPreference = 'Stop'
    function LongSafe([string]$p) {
        if (-not $windows -or $p.StartsWith('\\?\')) { return $p }
        if ($p.StartsWith('\\')) { return '\\?\UNC\' + $p.Substring(2) }
        return '\\?\' + $p
    }
    function Hash([string]$p) {
        $stream = [IO.File]::OpenRead($p)
        $algorithm = [Security.Cryptography.SHA256]::Create()
        try { return [Convert]::ToHexString($algorithm.ComputeHash($stream)).ToLowerInvariant() }
        finally { $stream.Dispose(); $algorithm.Dispose() }
    }
    $result = [ordered]@{ Index=$item.Index; Action='ERROR'; SourceRelativePath=$item.SourceRelativePath;
        DestinationRelativePath=$item.DestinationRelativePath; Bytes=0L; SourceSHA256=''; DestinationSHA256=''; Error='' }
    try {
        $src = LongSafe $item.Source
        $dst = LongSafe $item.Destination
        $info = [IO.FileInfo]::new($src)
        if (-not $info.Exists) { $result.Action='MISSING_SOURCE'; return [pscustomobject]$result }
        $result.Bytes = $info.Length
        $result.SourceSHA256 = Hash $src
        if ([IO.Directory]::Exists($dst)) { $result.Action='CONFLICT'; return [pscustomobject]$result }
        if ([IO.File]::Exists($dst)) {
            $result.DestinationSHA256 = Hash $dst
            $result.Action = if ($result.SourceSHA256 -eq $result.DestinationSHA256) { 'SKIP_IDENTICAL' } else { 'CONFLICT' }
            return [pscustomobject]$result
        }
        if (-not $execute) { $result.Action='WOULD_COPY'; return [pscustomobject]$result }
        # Every worker waits for idempotent directory creation. Do not gate it
        # behind a cache entry that another worker could see before it finishes.
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($dst)) | Out-Null
        [IO.File]::Copy($src, $dst, $false)
        $result.DestinationSHA256 = Hash $dst
        $result.Action = if ($result.SourceSHA256 -eq $result.DestinationSHA256) { 'COPIED_VERIFIED' } else { 'HASH_MISMATCH' }
    } catch {
        # Preserve partial/failed output for inspection. Nothing is deleted or
        # overwritten on recovery, including a destination created by a race.
        $result.Error = $_.Exception.GetType().Name
    }
    return [pscustomobject]$result
}

function ConvertTo-CsvField([string]$Value) {
    if ($null -eq $Value) { $Value = '' }
    return '"' + $Value.Replace('"', '""') + '"'
}

$pool = [RunspaceFactory]::CreateRunspacePool(1, $ThrottleLimit)
$pending = [Collections.Generic.List[object]]::new()
$results = [Collections.Generic.List[object]]::new()
try {
    $pool.Open()
    $next = 0
    while ($next -lt $items.Count -or $pending.Count -gt 0) {
        while ($next -lt $items.Count -and $pending.Count -lt $ThrottleLimit) {
            $shell = [PowerShell]::Create()
            $shell.RunspacePool = $pool
            $null = $shell.AddScript($worker.ToString()).AddArgument($items[$next]).AddArgument([bool]$Execute).AddArgument([bool]$IsWindows)
            $pending.Add([pscustomobject]@{ Shell=$shell; Handle=$shell.BeginInvoke() })
            $next++
        }
        $finished = @($pending | Where-Object { $_.Handle.IsCompleted })
        foreach ($job in $finished) {
            try {
                $output = @($job.Shell.EndInvoke($job.Handle))
                if ($job.Shell.HadErrors -or $output.Count -ne 1) { throw 'Worker did not return exactly one valid result.' }
                $result = $output[0]
                $results.Add($result)
                if ($writer) {
                    $values = @($result.Index, $result.Action, $result.SourceRelativePath, $result.DestinationRelativePath,
                        $result.Bytes, $result.SourceSHA256, $result.DestinationSHA256, $result.Error)
                    $writer.WriteLine((($values | ForEach-Object { ConvertTo-CsvField ([string]$_) }) -join ','))
                    $writer.Flush()
                }
            } finally { $job.Shell.Dispose(); $null = $pending.Remove($job) }
        }
        if ($pending.Count -gt 0 -and $finished.Count -eq 0) { Start-Sleep -Milliseconds 5 }
    }
} finally {
    foreach ($job in $pending) { $job.Shell.Stop(); $job.Shell.Dispose() }
    $pool.Close(); $pool.Dispose()
    if ($writer) { $writer.Dispose() }
}
$ordered = @($results | Sort-Object Index)
if ($AsJson) { ConvertTo-Json -InputObject $ordered -Depth 4 } else { $ordered }
if (@($ordered | Where-Object { $_.Action -in @('ERROR','HASH_MISMATCH','CONFLICT','MISSING_SOURCE') }).Count) { exit 2 }
