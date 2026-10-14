"""Pure PowerShell helpers for date, environment files and directory traversal."""
EXTENDED_RUNTIME = r'''
function Get-B2PSDate([string] $Format = '', [switch] $Utc) {
    $date = if ($Utc) { [DateTimeOffset]::UtcNow } else { [DateTimeOffset]::Now }
    if ($Format -eq '' -or $Format -eq '-Is' -or $Format -eq '--iso-8601=seconds') { return $date.ToString('yyyy-MM-ddTHH:mm:sszzz') }
    if ($Format -eq '+%s') { return [string]$date.ToUnixTimeSeconds() }
    $formats = New-Object 'System.Collections.Generic.Dictionary[string,string]' ([StringComparer]::Ordinal)
    $keys = @('Y', 'm', 'd', 'H', 'M', 'S', 'F', 'T', 'z', 'Z')
    $patterns = @('yyyy', 'MM', 'dd', 'HH', 'mm', 'ss', 'yyyy-MM-dd', 'HH:mm:ss', 'zzz', 'zzz')
    for ($i = 0; $i -lt $keys.Count; $i++) { $formats[$keys[$i]] = $patterns[$i] }
    $result = New-Object Text.StringBuilder
    $format = $Format.TrimStart('+')
    for ($i = 0; $i -lt $format.Length; $i++) {
        if ($format[$i] -eq '%' -and $i + 1 -lt $format.Length) {
            $i++; $key = [string]$format[$i]
            if ($key -eq '%') { $null = $result.Append('%') }
            elseif ($formats.ContainsKey($key)) {
                $value = $date.ToString($formats[$key], [Globalization.CultureInfo]::InvariantCulture)
                if ($key -eq 'z') { $value = $value.Replace(':', '') }
                $null = $result.Append($value)
            } else { throw "Unsupported date format: %$key" }
        } else { $null = $result.Append($format[$i]) }
    }
    return $result.ToString()
}
function Import-B2PSEnv([string] $Path) {
    $number = 0
    foreach ($line in [IO.File]::ReadAllLines($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path))) {
        $number++
        if ($line -match '^\s*(#|$)') { continue }
        if ($line -notmatch '^\s*(export\s+)?([A-Za-z_][A-Za-z_0-9]*)=(.*)$') { throw "${Path}:${number}: expected a NAME=value environment assignment" }
        $export = [bool]$Matches[1]; $name = $Matches[2]; $raw = $Matches[3].Trim()
        $value = New-Object Text.StringBuilder
        $quote = ''
        for ($i = 0; $i -lt $raw.Length; $i++) {
            $c = [string]$raw[$i]
            if ($c -eq "'" -and $quote -ne '"') { $quote = if ($quote -eq "'") { '' } else { "'" }; continue }
            if ($c -eq '"' -and $quote -ne "'") { $quote = if ($quote -eq '"') { '' } else { '"' }; continue }
            if ($quote -eq '' -and $c -eq '#' -and ($i -eq 0 -or [char]::IsWhiteSpace($raw[$i-1]))) { break }
            if ($quote -ne "'" -and $c -eq '\' -and $i + 1 -lt $raw.Length) {
                $next = [string]$raw[$i+1]
                if ($quote -eq '' -or $next -in @('$', '`', '"', '\')) { $i++; $null = $value.Append($next); continue }
            }
            if ($quote -ne "'" -and $c -eq '$') {
                $match = [regex]::Match($raw.Substring($i), '^\$(?:\{([A-Za-z_][A-Za-z_0-9]*)\}|([A-Za-z_][A-Za-z_0-9]*))')
                if (-not $match.Success) { throw "${Path}:${number}: complex .env expansion is unsupported" }
                $key = if ($match.Groups[1].Success) { $match.Groups[1].Value } else { $match.Groups[2].Value }
                $null = $value.Append((Get-B2PSValue $key)); $i += $match.Length - 1; continue
            }
            if ($quote -ne "'" -and $c -eq '`') { throw "${Path}:${number}: .env command substitution is unsupported" }
            if ($quote -eq '' -and ($c -in @(';', '|', '&', '(', ')', '<', '>') -or [char]::IsWhiteSpace($raw[$i]))) {
                if ($raw.Substring($i) -match '^\s*(#.*)?$') { break }
                throw "${Path}:${number}: quote spaces and shell operators in .env values"
            }
            $null = $value.Append($c)
        }
        if ($quote) { throw "${Path}:${number}: unclosed quote" }
        Set-B2PSValue $name $value.ToString() -Export:$export
    }
}
function Find-B2PSPath([string] $Path, [int] $MinDepth = 0, [int] $MaxDepth = 2147483647,
                      [string] $Type = '', [string] $Pattern = '*', [switch] $IgnoreCase) {
    $root = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    $pending = New-Object 'System.Collections.Generic.Stack[object]'
    $pending.Push(@($root, 0))
    while ($pending.Count) {
        $entry = $pending.Pop(); $item = $entry[0]; $depth = [int]$entry[1]
        $matched = if ($IgnoreCase) { $item.Name -like $Pattern } else { $item.Name -clike $Pattern }
        if ($depth -ge $MinDepth -and $matched -and
            (($Type -eq '') -or ($Type -eq 'd' -and $item.PSIsContainer) -or ($Type -eq 'f' -and -not $item.PSIsContainer))) {
            $item.FullName
        }
        # Do not follow junctions/symlinks, matching find's default traversal.
        if ($item.PSIsContainer -and $depth -lt $MaxDepth -and -not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            $children = @(Get-ChildItem -LiteralPath $item.FullName -Force -ErrorAction Stop | Sort-Object Name -Descending)
            foreach ($child in $children) { $pending.Push(@($child, ($depth + 1))) }
        }
    }
}
'''
