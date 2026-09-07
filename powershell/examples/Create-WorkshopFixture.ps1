#requires -Version 7.2
<# Creates new, fictional workshop files. Refuses an existing output directory. #>
[CmdletBinding()]
param([Parameter(Mandatory)][string]$OutputRoot)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($OutputRoot)
if ([IO.File]::Exists($root) -or [IO.Directory]::Exists($root)) { throw 'OutputRoot must not exist; choose a new demo directory.' }
$source = [IO.Path]::Combine($root, 'incoming')
[IO.Directory]::CreateDirectory($source) | Out-Null
$utf8 = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText([IO.Path]::Combine($source, 'bench notes.txt'), "Fictional workshop: sand the wooden display stand.`n", $utf8)
[IO.File]::WriteAllText([IO.Path]::Combine($source, 'illustration [draft].txt'), "Fictional library poster: draw three paper lanterns.`n", $utf8)
[IO.File]::WriteAllText([IO.Path]::Combine($source, 'reading, list.txt'), "Fictional reading list: The Paper Garden; Lantern Workshop.`n", $utf8)
$rows = @(
    [pscustomobject]@{ SourceRelativePath='bench notes.txt'; DestinationRelativePath='bench notes.txt' }
    [pscustomobject]@{ SourceRelativePath='illustration [draft].txt'; DestinationRelativePath='illustration [draft].txt' }
    [pscustomobject]@{ SourceRelativePath='reading, list.txt'; DestinationRelativePath='display/reading-list.txt' }
)
$rows | Export-Csv -LiteralPath ([IO.Path]::Combine($root, 'mapping.csv')) -NoTypeInformation -Encoding utf8
Write-Output 'Created three fictional source files and mapping.csv. No destination files have been copied.'
