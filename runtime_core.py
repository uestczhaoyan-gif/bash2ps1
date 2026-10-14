"""PowerShell 5.1-compatible byte IO, shell state, expansions and execution."""
RUNTIME = r'''
$script:B2PSVars = [Collections.Generic.Dictionary[string,string]]::new([StringComparer]::Ordinal)
$script:B2PSArrays = [Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
$script:B2PSExported = [Collections.Generic.Dictionary[string,bool]]::new([StringComparer]::Ordinal)
$script:B2PSFunctions = [Collections.Generic.Dictionary[string,scriptblock]]::new([StringComparer]::Ordinal)
$script:B2PSScripts = @{}
$script:B2PSStatus=0; $script:B2PSErrexit=$false; $script:B2PSUnset=$false; $script:B2PSPipefail=$false
$script:B2PSAllExport=$false; $script:B2PSTrace=$false; $script:B2PSGuardDepth=0; $script:B2PSExpansionStatus=$null
$script:B2PSNullGlob=$false; $script:B2PSFailGlob=$false
$script:B2PSArgs=@($args); $script:B2PSZero=$PSCommandPath; $script:B2PSSource=$PSCommandPath
$script:B2PSFrames=New-Object 'Collections.Generic.Stack[object]'
$script:B2PSDirStack=New-Object 'Collections.Generic.Stack[string]'
$script:B2PSUtf8=New-Object Text.UTF8Encoding($false)
$script:B2PSIO=@{Out=[IO.Stream]::Synchronized([Console]::OpenStandardOutput()); Err=[IO.Stream]::Synchronized([Console]::OpenStandardError()); In=[Console]::OpenStandardInput(); RedirectInput=$false}
function Write-B2PSBytes([byte[]] $Bytes,[switch] $ErrorStream) {
    $stream=$(if($ErrorStream){$script:B2PSIO.Err}else{$script:B2PSIO.Out})
    if($Bytes.Length){$stream.Write($Bytes,0,$Bytes.Length);$stream.Flush()}
}
function Write-B2PSOutput([string] $Text,[switch] $ErrorStream){Write-B2PSBytes $script:B2PSUtf8.GetBytes($Text) -ErrorStream:$ErrorStream}
function Read-B2PSBytes {$memory=New-Object IO.MemoryStream;try{$script:B2PSIO.In.CopyTo($memory);return ,$memory.ToArray()}finally{$memory.Dispose()}}
function Get-B2PSText{return $script:B2PSUtf8.GetString((Read-B2PSBytes))}
function Stop-B2PSFatal([string] $Message){$e=New-Object Exception($Message);$e.Data['B2PSFatal']=$true;throw $e}
function Set-B2PSEnvironment([string] $Name,$Value){if($env:OS -eq 'Windows_NT'){Initialize-B2PSMergedNative;if($null -eq $Value){[B2PS.NativeMerged]::RemoveEnvironment($Name)}else{[B2PS.NativeMerged]::SetEnvironment($Name,[string]$Value)}}else{[Environment]::SetEnvironmentVariable($Name,$Value,'Process')}}
function Send-B2PSControl([string] $Kind,[int] $Code=0){$e=New-Object Exception($Kind);$e.Data['B2PSControl']=$Kind;$e.Data['B2PSExitCode']=$Code;throw $e}
function Get-B2PSValue([string] $Name){
    switch -CaseSensitive($Name){'?' {return [string]$script:B2PSStatus};'0' {return $script:B2PSZero};'BASH_SOURCE' {return $script:B2PSSource};'#' {return [string]$script:B2PSArgs.Count};'$' {return [string]$PID}}
    if($Name -match '^\d+$'){$i=[int]$Name-1;if($i -ge 0 -and $i -lt $script:B2PSArgs.Count){return [string]$script:B2PSArgs[$i]};if($script:B2PSUnset){Stop-B2PSFatal "Unset Bash argument: $Name"};return ''}
    if($script:B2PSVars.ContainsKey($Name)){return $script:B2PSVars[$Name]}
    if($script:B2PSArrays.ContainsKey($Name)){return Get-B2PSArrayItem $Name '0'}
    if($Name -eq 'HOME'){return [Environment]::GetFolderPath('UserProfile')};if($Name -eq 'PWD'){return (Get-Location).Path};if($Name -eq 'IFS'){return " `t`n"}
    $value=[Environment]::GetEnvironmentVariable($Name,'Process');if($null -eq $value -and $script:B2PSUnset){Stop-B2PSFatal "Unset Bash variable: $Name"};return [string]$value
}
function Test-B2PSSet([string] $Name){
    if($Name -in @('?','0','#','$','HOME','PWD','BASH_SOURCE','IFS')){return $true};if($Name -match '^\d+$'){return [int]$Name -le $script:B2PSArgs.Count}
    return $script:B2PSVars.ContainsKey($Name) -or $script:B2PSArrays.ContainsKey($Name) -or $null -ne [Environment]::GetEnvironmentVariable($Name,'Process')
}
function Set-B2PSValue([string] $Name,[string] $Value,[switch] $Export){
    if($Name -eq 'PATH' -and $env:OS -eq 'Windows_NT'){$Value=[regex]::Replace($Value,':(?![\\/])',';')}
    $script:B2PSVars[$Name]=$Value;if($Export -or $script:B2PSAllExport){$script:B2PSExported[$Name]=$true}
    if($script:B2PSExported.ContainsKey($Name)){Set-B2PSEnvironment $Name $Value}
}
function Get-B2PSArrayItem([string] $Name,[string] $Index){
    if($script:B2PSArrays.ContainsKey($Name) -and $script:B2PSArrays[$Name].Contains($Index)){return [string]$script:B2PSArrays[$Name][$Index]}
    if($Index -eq '0' -and $script:B2PSVars.ContainsKey($Name)){return $script:B2PSVars[$Name]}
    if($script:B2PSUnset){Stop-B2PSFatal "Unset Bash array element: ${Name}[$Index]"};return ''
}
function Get-B2PSArray([string] $Name,[switch] $Keys){
    if($Name -in @('@','*')){return $script:B2PSArgs}
    if(-not $script:B2PSArrays.ContainsKey($Name)){if($script:B2PSVars.ContainsKey($Name)){if($Keys){return '0'};return $script:B2PSVars[$Name]};return}
    $map=$script:B2PSArrays[$Name];$indices=@($map.Keys)
    if(@($indices|Where-Object{$_ -notmatch '^\d+$'}).Count -eq 0){$indices=@($indices|Sort-Object{[long]$_})}
    foreach($index in $indices){if($Keys){[string]$index}else{[string]$map[$index]}}
}
function Set-B2PSArray([string] $Name,[string[]] $Values,[switch] $Append){
    if(-not $Append -or -not $script:B2PSArrays.ContainsKey($Name)){$script:B2PSArrays[$Name]=[ordered]@{}}
    $map=$script:B2PSArrays[$Name];$next=$(if($map.Count){1+[long](@($map.Keys|Sort-Object{[long]$_})[-1])}else{0})
    foreach($value in $Values){$map[[string]$next]=$value;$next++};$null=$script:B2PSVars.Remove($Name)
}
function Set-B2PSArrayItem([string] $Name,[string] $Index,[string] $Value){if(-not $script:B2PSArrays.ContainsKey($Name)){$script:B2PSArrays[$Name]=[ordered]@{}};$script:B2PSArrays[$Name][$Index]=$Value;$null=$script:B2PSVars.Remove($Name)}
function Expand-B2PSParameter([string] $Name,[string] $Operator,[scriptblock] $Fallback){
    $set=Test-B2PSSet $Name;$value=$(if($set){Get-B2PSValue $Name}else{''});$missing=-not $set -or ($Operator.StartsWith(':') -and $value -eq '')
    switch($Operator.TrimStart(':')){
        '-' {if($missing){return [string](& $Fallback)};return $value}
        '+' {if(-not $missing){return [string](& $Fallback)};return ''}
        '=' {if($missing){$value=[string](& $Fallback);Set-B2PSValue $Name $value};return $value}
        '?' {if($missing){$message=[string](& $Fallback);if(-not $message){$message='parameter is unset or empty'};Stop-B2PSFatal "${Name}: $message"};return $value}
    }
}
function Join-B2PSScalar([object[]] $Parts){$ifs=Get-B2PSValue 'IFS';$separator=$(if($ifs.Length){[string]$ifs[0]}else{''});$builder=New-Object Text.StringBuilder;foreach($part in $Parts){$null=$builder.Append((@($part.Value)-join $separator))};return $builder.ToString()}
function Convert-B2PSGlob([string] $Pattern){
    $builder=New-Object Text.StringBuilder
    for($i=0;$i -lt $Pattern.Length;$i++){
        $c=$Pattern[$i]
        if($c -eq '*'){$null=$builder.Append('.*')}elseif($c -eq '?'){$null=$builder.Append('.')}
        elseif($c -eq '['){$end=$Pattern.IndexOf(']',$i+1);if($end -gt $i+1){$inside=$Pattern.Substring($i+1,$end-$i-1);if($inside.StartsWith('!')){$inside='^'+$inside.Substring(1)};$null=$builder.Append('['+$inside+']');$i=$end}else{$null=$builder.Append('\[')}}
        elseif($c -eq '\' -and $i+1 -lt $Pattern.Length){$i++;$null=$builder.Append([regex]::Escape([string]$Pattern[$i]))}
        else{$null=$builder.Append([regex]::Escape([string]$c))}
    };return $builder.ToString()
}
function Expand-B2PSGlob([string] $Word,[string] $Pattern){
    if($Pattern -notmatch '(?<!\\)[*?\[]'){return $Word}
    $segments=$Pattern -split '/';$paths=@('')
    if($Pattern.StartsWith('/')){$paths=@('/');$segments=$segments[1..($segments.Count-1)]}
    foreach($segment in $segments){
        $next=New-Object 'Collections.Generic.List[string]'
        foreach($prefix in $paths){
            if($segment -match '(?<!\\)[*?\[]'){
                $directory=$(if($prefix){$prefix}else{'.'});$patternRegex='^'+(Convert-B2PSGlob $segment)+'$'
                if(Test-Path -LiteralPath $directory -PathType Container){foreach($entry in Get-ChildItem -LiteralPath $directory -Force){if($entry.Name.StartsWith('.') -and -not $segment.StartsWith('.')){continue};if($entry.Name -cmatch $patternRegex){$next.Add($(if($prefix){$prefix.TrimEnd('/')+'/'+$entry.Name}else{$entry.Name}))}}}
            }else{$literal=$segment -replace '\\([*?\[\]\\])','$1';$next.Add($(if($prefix){$prefix.TrimEnd('/')+'/'+$literal}else{$literal}))}
        };$paths=$next.ToArray()
    }
    $paths=@($paths|Where-Object{Test-Path -LiteralPath $_});if(-not $paths.Count){if($script:B2PSFailGlob){Stop-B2PSFatal "No glob matches: $Word"};if(-not $script:B2PSNullGlob){return $Word};return}
    [Array]::Sort($paths,[StringComparer]::Ordinal);return $paths
}
function Expand-B2PSWord([object[]] $Parts){
    $ifs=Get-B2PSValue 'IFS';$rawWords=New-Object 'Collections.Generic.List[object]';$text='';$splits='';$globs='';$forced=$false
    foreach($part in $Parts){
        $values=@($part.Value);if(-not $part.Spread){$values=@($values -join $(if($ifs.Length){[string]$ifs[0]}else{''}))}
        for($v=0;$v -lt $values.Count;$v++){
            if($v -gt 0){$rawWords.Add(@{Text=$text;Split=$splits;Glob=$globs;Forced=$forced});$text='';$splits='';$globs='';$forced=$false}
            $value=[string]$values[$v];$text+=$value;$splits+=$(if($part.Split){'1'*$value.Length}else{'0'*$value.Length});$globs+=$(if($part.Glob){'1'*$value.Length}else{'0'*$value.Length});if($part.Quoted){$forced=$true}
        }
    }
    $rawWords.Add(@{Text=$text;Split=$splits;Glob=$globs;Forced=$forced})
    foreach($raw in $rawWords){
        $fields=New-Object 'Collections.Generic.List[object]';$field='';$pattern='';$hadDelimiter=$false
        for($i=0;$i -lt $raw.Text.Length;$i++){
            $c=[string]$raw.Text[$i]
            if($raw.Split[$i] -eq '1' -and $ifs.Contains($c)){$white=$c -in @(' ',"`t","`n");if($field.Length -or -not $white){$fields.Add(@($field,$pattern));$field='';$pattern=''};$hadDelimiter=$true}
            else{$field+=$c;$pattern+=$(if($raw.Glob[$i] -eq '1'){$c}elseif($c -in @('*','?','[',']','\')){'\'+$c}else{$c})}
        }
        if($field.Length -or ($raw.Forced -and -not $fields.Count -and -not $hadDelimiter)){$fields.Add(@($field,$pattern))}
        foreach($pair in $fields){Expand-B2PSGlob $pair[0] $pair[1]}
    }
}
function Copy-B2PSDictionary($Dictionary){$copy=[Collections.Generic.Dictionary[string,string]]::new([StringComparer]::Ordinal);foreach($key in $Dictionary.Keys){$copy[$key]=$Dictionary[$key]};return ,$copy}
function Enter-B2PSSubshell([switch] $ExportedOnly){
    $saved=@{Vars=$script:B2PSVars;Arrays=$script:B2PSArrays;Exported=$script:B2PSExported;Functions=$script:B2PSFunctions;Status=$script:B2PSStatus;Errexit=$script:B2PSErrexit;Unset=$script:B2PSUnset;Pipefail=$script:B2PSPipefail;AllExport=$script:B2PSAllExport;Trace=$script:B2PSTrace;Guard=$script:B2PSGuardDepth;Expansion=$script:B2PSExpansionStatus;Source=$script:B2PSSource;Zero=$script:B2PSZero;Arguments=$script:B2PSArgs;Directory=(Get-Location).Path;Environment=[Environment]::GetEnvironmentVariables('Process');IO=$script:B2PSIO}
    $script:B2PSVars=Copy-B2PSDictionary $saved.Vars;$script:B2PSArrays=[Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
    foreach($key in $saved.Arrays.Keys){$map=[ordered]@{};foreach($index in $saved.Arrays[$key].Keys){$map[$index]=$saved.Arrays[$key][$index]};$script:B2PSArrays[$key]=$map}
    $script:B2PSExported=[Collections.Generic.Dictionary[string,bool]]::new([StringComparer]::Ordinal);foreach($key in $saved.Exported.Keys){$script:B2PSExported[$key]=$true}
    $script:B2PSFunctions=[Collections.Generic.Dictionary[string,scriptblock]]::new([StringComparer]::Ordinal);foreach($key in $saved.Functions.Keys){$script:B2PSFunctions[$key]=$saved.Functions[$key]}
    if($ExportedOnly){$script:B2PSVars.Clear();$script:B2PSArrays.Clear();$script:B2PSFunctions.Clear();$script:B2PSErrexit=$false;$script:B2PSUnset=$false;$script:B2PSPipefail=$false;$script:B2PSAllExport=$false;$script:B2PSGuardDepth=0}
    return $saved
}
function Restore-B2PSSubshell($Saved){
    $current=[Environment]::GetEnvironmentVariables('Process');foreach($key in $current.Keys){if(-not $Saved.Environment.Contains($key)){Set-B2PSEnvironment $key $null}};foreach($key in $Saved.Environment.Keys){if($current[$key] -cne $Saved.Environment[$key]){Set-B2PSEnvironment $key $Saved.Environment[$key]}}
    Set-Location -LiteralPath $Saved.Directory;$script:B2PSVars=$Saved.Vars;$script:B2PSArrays=$Saved.Arrays;$script:B2PSExported=$Saved.Exported;$script:B2PSFunctions=$Saved.Functions;$script:B2PSStatus=$Saved.Status;$script:B2PSErrexit=$Saved.Errexit;$script:B2PSUnset=$Saved.Unset;$script:B2PSPipefail=$Saved.Pipefail;$script:B2PSAllExport=$Saved.AllExport;$script:B2PSTrace=$Saved.Trace;$script:B2PSGuardDepth=$Saved.Guard;$script:B2PSExpansionStatus=$Saved.Expansion;$script:B2PSSource=$Saved.Source;$script:B2PSZero=$Saved.Zero;$script:B2PSArgs=$Saved.Arguments;$script:B2PSIO=$Saved.IO
}
function Invoke-B2PSCapture([scriptblock] $Action){
    $saved=Enter-B2PSSubshell;$memory=New-Object IO.MemoryStream;$status=0
    try{$script:B2PSIO=@{Out=[IO.Stream]::Synchronized($memory);Err=$saved.IO.Err;In=$saved.IO.In;RedirectInput=$saved.IO.RedirectInput};$script:B2PSErrexit=$false
        try{& $Action}catch{if($_.Exception.Data['B2PSControl'] -ne 'exit'){throw};$script:B2PSStatus=[int]$_.Exception.Data['B2PSExitCode']}
        $status=$script:B2PSStatus;return $script:B2PSUtf8.GetString($memory.ToArray()).TrimEnd([char]10)
    }finally{Restore-B2PSSubshell $saved;$script:B2PSExpansionStatus=$status;$memory.Dispose()}
}
function Invoke-B2PSStep([scriptblock] $Action,[switch] $Required,[switch] $Negate,[switch] $Assignment,[int] $Line=0){
    $ErrorActionPreference='Stop';$script:B2PSExpansionStatus=$null;$guarded=$Negate -or -not $Required;if($guarded){$script:B2PSGuardDepth++}
    try{try{. $Action;if($Assignment){$script:B2PSStatus=$(if($null -ne $script:B2PSExpansionStatus){[int]$script:B2PSExpansionStatus}else{0})}}
        catch{if($_.Exception.Data.Contains('B2PSFatal') -or $_.Exception.Data.Contains('B2PSControl')){throw};$script:B2PSStatus=1;if($_.Exception.Data.Contains('B2PSExitCode')){$script:B2PSStatus=[int]$_.Exception.Data['B2PSExitCode']}else{Write-B2PSOutput ("Bash line ${Line}: "+$_.Exception.Message+"`n") -ErrorStream}}
    }finally{if($guarded){$script:B2PSGuardDepth--}}
    if($Negate){$script:B2PSStatus=$(if($script:B2PSStatus -eq 0){1}else{0})}elseif($Required -and $script:B2PSErrexit -and $script:B2PSGuardDepth -eq 0 -and $script:B2PSStatus -ne 0){Send-B2PSControl 'exit' $script:B2PSStatus}
}
function Test-B2PSCondition([scriptblock] $Action){$script:B2PSGuardDepth++;try{& $Action;return $script:B2PSStatus -eq 0}finally{$script:B2PSGuardDepth--}}
function Invoke-B2PSSubshell([scriptblock] $Action){$saved=Enter-B2PSSubshell;$status=0;try{try{& $Action}catch{if($_.Exception.Data['B2PSControl'] -ne 'exit'){throw};$script:B2PSStatus=[int]$_.Exception.Data['B2PSExitCode']};$status=$script:B2PSStatus}finally{Restore-B2PSSubshell $saved};$script:B2PSStatus=$status}
function Invoke-B2PSPipeline([scriptblock[]] $Stages){
    $parentIO=$script:B2PSIO;$incoming=$parentIO.In;$owned=$null;$statuses=@()
    try{for($i=0;$i -lt $Stages.Count;$i++){
        $saved=Enter-B2PSSubshell;$memory=New-Object IO.MemoryStream
        try{$output=$(if($i -eq $Stages.Count-1){$parentIO.Out}else{[IO.Stream]::Synchronized($memory)});$script:B2PSIO=@{Out=$output;Err=$parentIO.Err;In=$incoming;RedirectInput=($i -gt 0 -or $parentIO.RedirectInput)};$script:B2PSGuardDepth++
            try{& $Stages[$i]}catch{if($_.Exception.Data['B2PSControl'] -ne 'exit'){throw};$script:B2PSStatus=[int]$_.Exception.Data['B2PSExitCode']};$statuses+=$script:B2PSStatus
        }finally{Restore-B2PSSubshell $saved}
        if($owned){$owned.Dispose()};$owned=$memory;$incoming=$memory;$incoming.Position=0
    };$script:B2PSStatus=$statuses[-1];if($script:B2PSPipefail){foreach($status in $statuses){if($status -ne 0){$script:B2PSStatus=$status}}};Set-B2PSArray 'PIPESTATUS' @($statuses|ForEach-Object{[string]$_})
    }finally{$script:B2PSIO=$parentIO;if($owned){$owned.Dispose()}}
}
function Invoke-B2PSRedirected([object[]] $Redirections,[scriptblock] $Action){
    $saved=$script:B2PSIO;$streams=New-Object 'Collections.Generic.List[IO.Stream]';$script:B2PSIO=@{Out=$saved.Out;Err=$saved.Err;In=$saved.In;RedirectInput=$saved.RedirectInput}
    try{foreach($redir in $Redirections){$op=[string]$redir.Op;$path=[string]$redir.Value
        if($op -in @('<<','<<-','<<<')){if($op -eq '<<<'){$path+="`n"};$stream=New-Object IO.MemoryStream(,$script:B2PSUtf8.GetBytes($path));$streams.Add($stream);$script:B2PSIO.In=$stream;$script:B2PSIO.RedirectInput=$true;continue}
        if($op -in @('2>&','1>&','>&')){$target=$(if($path -eq '1'){$script:B2PSIO.Out}elseif($path -eq '2'){$script:B2PSIO.Err}elseif($path -eq '-'){[IO.Stream]::Null}else{throw 'Unsupported descriptor duplication'});if($op -eq '2>&'){$script:B2PSIO.Err=$target}else{$script:B2PSIO.Out=$target};continue}
        if($path -in @('/dev/null','NUL')){$stream=[IO.Stream]::Null}else{
            $resolved=$ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($path)
            if($op -in @('<','0<')){$stream=[IO.File]::Open($resolved,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)}else{$mode=$(if($op.EndsWith('>>')){[IO.FileMode]::Append}else{[IO.FileMode]::Create});$stream=[IO.Stream]::Synchronized([IO.File]::Open($resolved,$mode,[IO.FileAccess]::Write,[IO.FileShare]::Read))};$streams.Add($stream)
        }
        if($op -in @('<','0<')){$script:B2PSIO.In=$stream;$script:B2PSIO.RedirectInput=$true}elseif($op.StartsWith('2')){$script:B2PSIO.Err=$stream}elseif($op.StartsWith('&')){$script:B2PSIO.Out=$stream;$script:B2PSIO.Err=$stream}else{$script:B2PSIO.Out=$stream}
    };& $Action}finally{$script:B2PSIO=$saved;foreach($stream in $streams){$stream.Dispose()}}
}
function Invoke-B2PSNative([string] $Name,[string[]] $ArgumentList=@()){
    if($env:OS -eq 'Windows_NT' -and $Name -eq 'python3'){$Name='python'};if($env:OS -eq 'Windows_NT' -and $Name -eq 'pip3'){$Name='pip'}
    $command=Get-Command -Name ([Management.Automation.WildcardPattern]::Escape($Name)) -CommandType Application -ErrorAction SilentlyContinue|Select-Object -First 1
    if(-not $command){Write-B2PSOutput ("${Name}: command not found`n") -ErrorStream;$script:B2PSStatus=127;return}
    $arguments=@();foreach($value in $ArgumentList){$encoded=[regex]::Replace([string]$value,'(\\*)"','$1$1\"');$encoded=[regex]::Replace($encoded,'(\\+)$','$1$1');$arguments+='"'+$encoded+'"'}
    $info=New-Object Diagnostics.ProcessStartInfo;$info.FileName=$command.Source;$info.Arguments=$arguments -join ' ';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.WorkingDirectory=(Get-Location).Path;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true;$info.RedirectStandardInput=$script:B2PSIO.RedirectInput
    if([IO.Path]::GetExtension($info.FileName) -in @('.cmd','.bat')){if(@($ArgumentList|Where-Object{$_ -match '["%!\r\n]'}).Count){throw 'Batch arguments containing quotes, %, ! or newlines require manual adaptation.'};$info.FileName=$env:ComSpec;$info.Arguments='/d /s /c ""'+$command.Source+'" '+($arguments -join ' ')+'"'}
    if($env:OS -eq 'Windows_NT' -and [object]::ReferenceEquals($script:B2PSIO.Out,$script:B2PSIO.Err)){
        Initialize-B2PSMergedNative;$inputStream=$(if($info.RedirectStandardInput){$script:B2PSIO.In}else{$null})
        $script:B2PSStatus=([B2PS.NativeMerged]::Run($info.FileName,$info.Arguments,$info.WorkingDirectory,$inputStream,$script:B2PSIO.Out)) -band 255;return
    }
    $process=New-Object Diagnostics.Process;$process.StartInfo=$info
    try{$null=$process.Start();$outTask=$process.StandardOutput.BaseStream.CopyToAsync($script:B2PSIO.Out);$errTask=$process.StandardError.BaseStream.CopyToAsync($script:B2PSIO.Err)
        if($info.RedirectStandardInput){try{$script:B2PSIO.In.CopyTo($process.StandardInput.BaseStream)}catch{}finally{$process.StandardInput.Close()}}
        $process.WaitForExit();$null=$outTask.GetAwaiter().GetResult();$null=$errTask.GetAwaiter().GetResult();$script:B2PSStatus=$process.ExitCode -band 255
    }finally{$process.Dispose()}
}
function Invoke-B2PSWithEnvironment([object[]] $Assignments,[scriptblock] $Action){
    $saved=@{}
    try{foreach($assignment in $Assignments){$name=[string]$assignment.Name;$saved[$name]=@{Set=$script:B2PSVars.ContainsKey($name);Value=$(if($script:B2PSVars.ContainsKey($name)){$script:B2PSVars[$name]}else{''});Env=[Environment]::GetEnvironmentVariable($name,'Process')};$value=[string](& $assignment.Action);$script:B2PSVars[$name]=$value;Set-B2PSEnvironment $name $value};& $Action}
    finally{foreach($name in $saved.Keys){if($saved[$name].Set){$script:B2PSVars[$name]=$saved[$name].Value}else{$null=$script:B2PSVars.Remove($name)};Set-B2PSEnvironment $name $saved[$name].Env}}
}
function Invoke-B2PSFunction([string] $Name,[string[]] $ArgumentList){
    $oldArgs=$script:B2PSArgs;$frame=[ordered]@{};$script:B2PSFrames.Push($frame);$script:B2PSArgs=$ArgumentList
    try{try{& $script:B2PSFunctions[$Name]}catch{if($_.Exception.Data['B2PSControl'] -ne 'return'){throw};$script:B2PSStatus=[int]$_.Exception.Data['B2PSExitCode']}}
    finally{$null=$script:B2PSFrames.Pop();$script:B2PSArgs=$oldArgs;foreach($key in $frame.Keys){$old=$frame[$key];if($old.Set){$script:B2PSVars[$key]=$old.Value}else{$null=$script:B2PSVars.Remove($key)};if($null -ne $old.Array){$script:B2PSArrays[$key]=$old.Array}else{$null=$script:B2PSArrays.Remove($key)};if($old.Export){$script:B2PSExported[$key]=$true}else{$null=$script:B2PSExported.Remove($key)};Set-B2PSEnvironment $key $old.Env}}
}
function Invoke-B2PSScript([string] $Path,[string[]] $ArgumentList=@(),[switch] $Source){
    $resolved=$ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path);if(-not $script:B2PSScripts.ContainsKey($resolved)){throw "Script not included in conversion: $Path"}
    $saved=$(if($Source){$null}else{Enter-B2PSSubshell -ExportedOnly});$oldSource=$script:B2PSSource;$oldArgs=$script:B2PSArgs;$status=0
    try{$script:B2PSSource=$resolved;if(-not $Source){$script:B2PSZero=$resolved};if(-not $Source -or $ArgumentList.Count){$script:B2PSArgs=$ArgumentList}
        try{& $script:B2PSScripts[$resolved]}catch{if($_.Exception.Data['B2PSControl'] -notin @('exit','return')){throw};$script:B2PSStatus=[int]$_.Exception.Data['B2PSExitCode']};$status=$script:B2PSStatus
    }finally{if($saved){Restore-B2PSSubshell $saved}else{$script:B2PSSource=$oldSource;$script:B2PSArgs=$oldArgs}};$script:B2PSStatus=$status
}
function Invoke-B2PSArithmetic($Tree,[int] $Depth=0){
    if($Depth -gt 100){Stop-B2PSFatal 'Recursive arithmetic variable'};$op=[string]$Tree[0]
    if($op -eq 'number'){$value=[string]$Tree[1];if($value -match '^(\d+)#(.+)$'){$base=[int]$Matches[1];$digits=$Matches[2]}elseif($value -match '^0[xX](.+)$'){$base=16;$digits=$Matches[1]}elseif($value -match '^0([0-7]+)$'){$base=8;$digits=$Matches[1]}else{$base=10;$digits=$value};if($base -notin @(2,8,10,16)){throw 'Arithmetic bases 2, 8, 10, 16 are supported'};return [Convert]::ToInt64($digits,$base)}
    if($op -eq 'var'){$value=$(if($Tree.Count -gt 2){Get-B2PSArrayItem $Tree[1] ([string](Invoke-B2PSArithmetic $Tree[2] ($Depth+1)))}elseif(Test-B2PSSet $Tree[1]){Get-B2PSValue $Tree[1]}else{'0'});if($value -eq ''){return [long]0};if($value -match '^-?\d+$'){return [long]$value};if($value -match '^[A-Za-z_][A-Za-z_0-9]*$'){return Invoke-B2PSArithmetic @('var',$value) ($Depth+1)};throw 'Arithmetic variables must contain integers or variable names'}
    if($op -eq '?:'){if((Invoke-B2PSArithmetic $Tree[1] ($Depth+1)) -ne 0){return Invoke-B2PSArithmetic $Tree[2] ($Depth+1)};return Invoke-B2PSArithmetic $Tree[3] ($Depth+1)}
    $left=Invoke-B2PSArithmetic $Tree[1] ($Depth+1)
    if($op -in @('++pre','--pre','++post','--post')){$result=$left+$(if($op.StartsWith('++')){1}else{-1});Set-B2PSArithmeticVariable $Tree[1] $result;if($op.EndsWith('post')){return $left};return $result}
    switch($op){'+pre' {return $left};'-pre' {return -$left};'!pre' {return [long]($left -eq 0)};'~pre' {return -bnot $left}}
    if($op -eq '&&' -and $left -eq 0){return [long]0};if($op -eq '||' -and $left -ne 0){return [long]1}
    $right=Invoke-B2PSArithmetic $Tree[2] ($Depth+1)
    if($op -eq '='){Set-B2PSArithmeticVariable $Tree[1] $right;return $right}
    if($op -match '^(.+)=$' -and $op -notin @('==','!=','<=','>=')){$result=Invoke-B2PSArithmetic @($Matches[1],@('number',[string]$left),@('number',[string]$right)) ($Depth+1);Set-B2PSArithmeticVariable $Tree[1] $result;return $result}
    switch($op){
        '+' {return [long]($left+$right)};'-' {return [long]($left-$right)};'*' {return [long]($left*$right)}
        '/' {if($right -eq 0){throw 'Division by zero'};return [long][Math]::Truncate($left/$right)};'%' {if($right -eq 0){throw 'Division by zero'};return [long]($left%$right)};'**' {return [long][Math]::Pow($left,$right)}
        '<<' {return $left -shl $right};'>>' {return $left -shr $right};'&' {return $left -band $right};'|' {return $left -bor $right};'^' {return $left -bxor $right}
        '==' {return [long]($left -eq $right)};'!=' {return [long]($left -ne $right)};'<' {return [long]($left -lt $right)};'>' {return [long]($left -gt $right)};'<=' {return [long]($left -le $right)};'>=' {return [long]($left -ge $right)};'&&' {return [long]($right -ne 0)};'||' {return [long]($right -ne 0)};',' {return $right}
    };throw "Unsupported arithmetic operator: $op"
}
function Set-B2PSArithmeticVariable($Tree,[long] $Value){if($Tree[0] -ne 'var'){throw 'Arithmetic assignment needs a variable'};if($Tree.Count -gt 2){Set-B2PSArrayItem $Tree[1] ([string](Invoke-B2PSArithmetic $Tree[2])) ([string]$Value)}else{Set-B2PSValue $Tree[1] ([string]$Value)}}
function Expand-B2PSString([string] $Value,[string] $Operator,[string] $Pattern,[string] $Replacement=''){
    if($Operator -eq 'slice'){$parts=$Pattern.Split(',');$offset=[int]$parts[0];if($offset -lt 0){$offset=$Value.Length+$offset};$offset=[Math]::Max(0,$offset);if($offset -ge $Value.Length){return ''};$length=$(if($parts.Count -gt 1){[int]$parts[1]}else{$Value.Length-$offset});if($length -lt 0){$length=$Value.Length-$offset+$length};return $Value.Substring($offset,[Math]::Max(0,[Math]::Min($length,$Value.Length-$offset)))}
    if($Operator -eq '^^'){return $Value.ToUpperInvariant()};if($Operator -eq ',,'){return $Value.ToLowerInvariant()};$regex=Convert-B2PSGlob $Pattern
    if($Operator -in @('#','##','%','%%')){$lengths=$(if($Operator.Length -eq 1){0..$Value.Length}else{$Value.Length..0});foreach($length in $lengths){$candidate=$(if($Operator.StartsWith('#')){$Value.Substring(0,$length)}else{$Value.Substring($Value.Length-$length)});if($candidate -cmatch ('^'+$regex+'$')){if($Operator.StartsWith('#')){return $Value.Substring($length)};return $Value.Substring(0,$Value.Length-$length)}};return $Value}
    $regexObject=New-Object Text.RegularExpressions.Regex($regex);$evaluator=[Text.RegularExpressions.MatchEvaluator]{param($match)return $Replacement};if($Operator -eq '//'){return $regexObject.Replace($Value,$evaluator)};return $regexObject.Replace($Value,$evaluator,1)
}
'''
