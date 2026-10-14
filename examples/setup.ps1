# Bash → native PowerShell conversion


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
    try{
        $restoreInputEncoding=$false;$savedInputEncoding=[Console]::InputEncoding
        try{if($info.RedirectStandardInput){if($info.PSObject.Properties['StandardInputEncoding']){$info.StandardInputEncoding=$script:B2PSUtf8}else{[Console]::InputEncoding=$script:B2PSUtf8;$restoreInputEncoding=$true}};$null=$process.Start()}
        finally{if($restoreInputEncoding){[Console]::InputEncoding=$savedInputEncoding}}
        $outTask=$process.StandardOutput.BaseStream.CopyToAsync($script:B2PSIO.Out);$errTask=$process.StandardError.BaseStream.CopyToAsync($script:B2PSIO.Err)
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


function Initialize-B2PSMergedNative {
    if ('B2PS.NativeMerged' -as [type]) { return }
    $source=@'
using System;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using System.Runtime.InteropServices;
using System.ComponentModel;
using Microsoft.Win32.SafeHandles;
namespace B2PS {
 public static class NativeMerged {
  [StructLayout(LayoutKind.Sequential)] struct SA { public int Length; public IntPtr Descriptor; [MarshalAs(UnmanagedType.Bool)] public bool Inherit; }
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct SI {
   public int cb; public string Reserved; public string Desktop; public string Title;
   public int X,Y,XSize,YSize,XCount,YCount,Fill,Flags; public short Show,ReservedSize;
   public IntPtr ReservedPointer,Input,Output,Error;
  }
  [StructLayout(LayoutKind.Sequential)] struct PI { public IntPtr Process,Thread; public int ProcessId,ThreadId; }
  [DllImport("kernel32.dll",SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] static extern bool CreatePipe(out IntPtr read,out IntPtr write,ref SA security,int size);
  [DllImport("kernel32.dll",SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] static extern bool SetHandleInformation(IntPtr handle,int mask,int flags);
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] static extern bool CreateProcess(string application,StringBuilder command,IntPtr pa,IntPtr ta,bool inherit,int flags,IntPtr environment,string directory,ref SI startup,out PI process);
  [DllImport("kernel32.dll")] static extern int WaitForSingleObject(IntPtr handle,int milliseconds);
  [DllImport("kernel32.dll",SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] static extern bool GetExitCodeProcess(IntPtr handle,out int code);
  [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int number);
  [DllImport("kernel32.dll")] [return:MarshalAs(UnmanagedType.Bool)] static extern bool CloseHandle(IntPtr handle);
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] static extern bool SetEnvironmentVariable(string name,string value);
  public static void RemoveEnvironment(string name) { if(!SetEnvironmentVariable(name,null))throw new Win32Exception(); }
  public static void SetEnvironment(string name,string value) { if(!SetEnvironmentVariable(name,value))throw new Win32Exception(); }
  static void Close(ref IntPtr h) { if(h!=IntPtr.Zero && h!=new IntPtr(-1)){CloseHandle(h);h=IntPtr.Zero;} }
  public static int Run(string file,string arguments,string directory,Stream input,Stream output) {
   IntPtr read=IntPtr.Zero,write=IntPtr.Zero,inputRead=IntPtr.Zero,inputWrite=IntPtr.Zero;
   PI pi=new PI(); FileStream reader=null,writer=null;
   try {
    SA sa=new SA { Length=Marshal.SizeOf(typeof(SA)), Inherit=true };
    if(!CreatePipe(out read,out write,ref sa,0))throw new Win32Exception();
    if(!SetHandleInformation(read,1,0))throw new Win32Exception();
    IntPtr childInput=GetStdHandle(-10);
    if(input!=null || childInput==IntPtr.Zero || childInput==new IntPtr(-1)) {
     if(!CreatePipe(out inputRead,out inputWrite,ref sa,0))throw new Win32Exception();
     if(!SetHandleInformation(inputWrite,1,0))throw new Win32Exception();
     childInput=inputRead;
    }
    SI si=new SI { cb=Marshal.SizeOf(typeof(SI)), Flags=0x100, Input=childInput, Output=write, Error=write };
    StringBuilder command=new StringBuilder("\""+file+"\" "+arguments);
    if(!CreateProcess(file,command,IntPtr.Zero,IntPtr.Zero,true,0x08000000,IntPtr.Zero,directory,ref si,out pi))throw new Win32Exception();
    Close(ref write);Close(ref inputRead);Close(ref pi.Thread);
    reader=new FileStream(new SafeFileHandle(read,true),FileAccess.Read);read=IntPtr.Zero;
    FileStream readStream=reader;
    Task drain=Task.Run(()=>readStream.CopyTo(output));
    Task feed=null;
    if(inputWrite!=IntPtr.Zero) {
     writer=new FileStream(new SafeFileHandle(inputWrite,true),FileAccess.Write);inputWrite=IntPtr.Zero;
     FileStream writeStream=writer;
     feed=Task.Run(()=>{try{if(input!=null)input.CopyTo(writeStream);}catch(IOException){}finally{writeStream.Dispose();}});
    }
    WaitForSingleObject(pi.Process,-1);
    drain.GetAwaiter().GetResult();if(feed!=null)feed.GetAwaiter().GetResult();output.Flush();
    int code;if(!GetExitCodeProcess(pi.Process,out code))throw new Win32Exception();return code;
   } finally {
    if(reader!=null)reader.Dispose();if(writer!=null)writer.Dispose();
    Close(ref read);Close(ref write);Close(ref inputRead);Close(ref inputWrite);Close(ref pi.Thread);Close(ref pi.Process);
   }
  }
 }
}
'@
    Add-Type -TypeDefinition $source -Language CSharp
}

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

function Resolve-B2PSPath([string] $Path){return $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)}
function Copy-B2PSDirectory([string] $Source,[string] $Destination){$null=[IO.Directory]::CreateDirectory($Destination);foreach($item in Get-ChildItem -LiteralPath $Source -Force){$target=Join-Path $Destination $item.Name;if($item.PSIsContainer){Copy-B2PSDirectory $item.FullName $target}else{[IO.File]::Copy($item.FullName,$target,$true)}}}
function Test-B2PSFileComparison([string] $Left,[string] $Operator,[string] $Right){$a=Resolve-B2PSPath $Left;$b=Resolve-B2PSPath $Right;if($Operator -eq '-ef'){return $a -ieq $b};if(-not [IO.File]::Exists($a)){return $false};if(-not [IO.File]::Exists($b)){return $Operator -eq '-nt'};if($Operator -eq '-nt'){return [IO.File]::GetLastWriteTimeUtc($a) -gt [IO.File]::GetLastWriteTimeUtc($b)};return [IO.File]::GetLastWriteTimeUtc($a) -lt [IO.File]::GetLastWriteTimeUtc($b)}
function Get-B2PSTestBoolean([string[]] $Arguments){
    $a=$Arguments
    if(-not $a.Count){return $false};if($a.Count -eq 1){return $a[0].Length -gt 0}
    if($a[0] -eq '!'){return -not (Get-B2PSTestBoolean @($a[1..($a.Count-1)]))}
    if($a[0] -eq '(' -and $a[-1] -eq ')'){return Get-B2PSTestBoolean @($a[1..($a.Count-2)])}
    if($a.Count -eq 3){
        $left=$a[0];$right=$a[2]
        switch($a[1]){'=' {return $left -ceq $right};'=='{return $left -ceq $right};'!='{return $left -cne $right};'-eq'{return [long]$left -eq [long]$right};'-ne'{return [long]$left -ne [long]$right};'-gt'{return [long]$left -gt [long]$right};'-ge'{return [long]$left -ge [long]$right};'-lt'{return [long]$left -lt [long]$right};'-le'{return [long]$left -le [long]$right};{$_ -in @('-nt','-ot','-ef')}{return Test-B2PSFileComparison $left $a[1] $right}}
    }
    foreach($op in @('-o','-a')){$depth=0;for($i=0;$i -lt $a.Count;$i++){if($a[$i] -eq '('){$depth++};if($a[$i] -eq ')'){$depth--};if($depth -eq 0 -and $a[$i] -eq $op -and $i -gt 0 -and $i -lt $a.Count-1){if($op -eq '-o'){return (Get-B2PSTestBoolean @($a[0..($i-1)])) -or (Get-B2PSTestBoolean @($a[($i+1)..($a.Count-1)]))};return (Get-B2PSTestBoolean @($a[0..($i-1)])) -and (Get-B2PSTestBoolean @($a[($i+1)..($a.Count-1)]))}}}
    if($a.Count -eq 2){$value=$a[1];switch($a[0]){
        '-z'{return $value.Length -eq 0};'-n'{return $value.Length -gt 0}
        {$_ -in @('-e','-f','-d','-s','-r','-w','-x','-L','-h')}{
            if(-not $value.Length){return $false};$path=Resolve-B2PSPath $value
            if($a[0] -eq '-f'){return [IO.File]::Exists($path)};if($a[0] -eq '-d'){return [IO.Directory]::Exists($path)}
            if($a[0] -eq '-s'){return [IO.File]::Exists($path) -and (New-Object IO.FileInfo($path)).Length -gt 0}
            if($a[0] -in @('-L','-h')){$item=Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue;return $null -ne $item -and [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)}
            if($a[0] -in @('-r','-w')){if([IO.Directory]::Exists($path)){return $true};try{$access=$(if($a[0] -eq '-r'){[IO.FileAccess]::Read}else{[IO.FileAccess]::Write});$stream=[IO.File]::Open($path,[IO.FileMode]::Open,$access,[IO.FileShare]::ReadWrite);$stream.Dispose();return $true}catch{return $false}}
            return [IO.File]::Exists($path) -or [IO.Directory]::Exists($path)
        }
    }};throw 'Invalid test expression'
}
function Invoke-B2PSTest([string[]] $Arguments){try{$script:B2PSStatus=[int](-not (Get-B2PSTestBoolean $Arguments))}catch{$script:B2PSStatus=2;Write-B2PSOutput 'test: invalid condition expression\n'.Replace('\n',"`n") -ErrorStream}}
function Get-B2PSLines([string] $Text){
    if($Text.Length -eq 0){return};$parts=$Text.Split([char]10);$count=$parts.Count;if($Text.EndsWith("`n")){$count--}
    for($i=0;$i -lt $count;$i++){[pscustomobject]@{Text=$parts[$i];Newline=($i -lt $parts.Count-1)}}
}
function Get-B2PSInputText([string[]] $Paths){
    if(-not $Paths.Count){return Get-B2PSText};$builder=New-Object Text.StringBuilder
    foreach($path in $Paths){if($path -eq '-'){$null=$builder.Append((Get-B2PSText))}else{$null=$builder.Append($script:B2PSUtf8.GetString([IO.File]::ReadAllBytes((Resolve-B2PSPath $path))))}}
    return $builder.ToString()
}
function Get-B2PSInputBytes([string[]] $Paths){$buffer=New-Object IO.MemoryStream;try{if(-not $Paths.Count){$Paths=@('-')};foreach($path in $Paths){$bytes=$(if($path -eq '-'){Read-B2PSBytes}else{,[IO.File]::ReadAllBytes((Resolve-B2PSPath $path))});$buffer.Write($bytes,0,$bytes.Length)};return ,$buffer.ToArray()}finally{$buffer.Dispose()}}
function Get-B2PSByteLines([byte[]] $Bytes){$start=0;for($i=0;$i -lt $Bytes.Length;$i++){if($Bytes[$i] -eq 10){$line=$(if($i -gt $start){[byte[]]$Bytes[$start..($i-1)]}else{[byte[]]@()});[pscustomobject]@{Raw=$line;Newline=$true};$start=$i+1}};if($start -lt $Bytes.Length){[pscustomobject]@{Raw=[byte[]]$Bytes[$start..($Bytes.Length-1)];Newline=$false}}}
function Convert-B2PSEscapes([string] $Value){
    $builder=New-Object Text.StringBuilder
    for($i=0;$i -lt $Value.Length;$i++){
        if($Value[$i] -ne '\' -or $i+1 -ge $Value.Length){$null=$builder.Append($Value[$i]);continue};$i++;$c=[string]$Value[$i]
        switch -CaseSensitive($c){
            'n' {$null=$builder.Append("`n")};'r' {$null=$builder.Append("`r")};'t' {$null=$builder.Append("`t")};'a' {$null=$builder.Append([char]7)};'b' {$null=$builder.Append([char]8)};'f' {$null=$builder.Append([char]12)};'v' {$null=$builder.Append([char]11)};'\' {$null=$builder.Append('\')}
            'c' {return [pscustomobject]@{Text=$builder.ToString();Stop=$true}}
            default {
                if($c -in @('x','u','U','0') -or $c -match '^[1-7]$'){
                    $base=$(if($c -match '^\d$'){8}else{16});$maximum=$(switch($c){'x'{2};'u'{4};'U'{8};'0'{3};default{2}});$digits=$(if($c -match '^[1-7]$'){$c}else{''})
                    while($i+1 -lt $Value.Length -and $digits.Length -lt $maximum -and [string]$Value[$i+1] -match $(if($base -eq 8){'^[0-7]$'}else{'^[0-9a-fA-F]$'})){$i++;$digits+=$Value[$i]}
                    if($digits){$number=[Convert]::ToInt32($digits,$base);$null=$builder.Append([char]::ConvertFromUtf32($number))}elseif($c -eq '0'){$null=$builder.Append([char]0)}else{$null=$builder.Append('\'+$c)}
                }else{$null=$builder.Append('\'+$c)}
            }
        }
    };return [pscustomobject]@{Text=$builder.ToString();Stop=$false}
}
function Format-B2PSPrintf([string] $Format,[string[]] $Values=@()){
    $formatEscapes=Convert-B2PSEscapes $Format;$Format=$formatEscapes.Text;$result=New-Object Text.StringBuilder;$index=0
    do{$before=$index
        for($i=0;$i -lt $Format.Length;$i++){
            if($Format[$i] -ne '%'){$null=$result.Append($Format[$i]);continue}
            $match=[regex]::Match($Format.Substring($i),'^%([-+ #0]*)(\d+)?(?:\.(\d+))?([sbdifuoxXc%])')
            if(-not $match.Success){throw 'Unsupported printf format'};$i+=$match.Length-1;$type=$match.Groups[4].Value
            if($type -eq '%'){$null=$result.Append('%');continue}
            $value=$(if($index -lt $Values.Count){[string]$Values[$index]}else{''});$index++;$precision=$(if($match.Groups[3].Success){[int]$match.Groups[3].Value}else{-1})
            switch -CaseSensitive($type){
                's' {if($precision -ge 0 -and $value.Length -gt $precision){$value=$value.Substring(0,$precision)}}
                'b' {$escaped=Convert-B2PSEscapes $value;$value=$escaped.Text;if($escaped.Stop){$null=$result.Append($value);return $result.ToString()}}
                'c' {$value=$(if($value.Length){$value.Substring(0,1)}else{[string][char]0})}
                'f' {$number=$(if($value){[double]::Parse($value,[Globalization.CultureInfo]::InvariantCulture)}else{0});$value=$number.ToString('F'+$(if($precision -ge 0){$precision}else{6}),[Globalization.CultureInfo]::InvariantCulture)}
                default {
                    $number=$(if($value -eq ''){[long]0}elseif($value -match '^[\x27"](.)'){[long][char]$Matches[1]}elseif($value -match '^0[xX](.+)$'){[Convert]::ToInt64($Matches[1],16)}elseif($value -match '^0([0-7]+)$'){[Convert]::ToInt64($Matches[1],8)}else{[long]::Parse($value,[Globalization.CultureInfo]::InvariantCulture)})
                    $value=$(switch -CaseSensitive($type){'x'{$number.ToString('x')};'X'{$number.ToString('X')};'o'{[Convert]::ToString($number,8)};default{[string]$number}})
                    if($precision -gt 0){$value=$value.PadLeft($precision,'0')}
                }
            }
            $flags=$match.Groups[1].Value;if($type -in @('d','i','f') -and -not $value.StartsWith('-')){if($flags.Contains('+')){$value='+'+$value}elseif($flags.Contains(' ')){$value=' '+$value}}
            if($match.Groups[2].Success){$width=[int]$match.Groups[2].Value;if($flags.Contains('-')){$value=$value.PadRight($width)}elseif($flags.Contains('0') -and $type -notin @('s','b','c')){if($value.StartsWith('-') -or $value.StartsWith('+')){$value=$value.Substring(0,1)+$value.Substring(1).PadLeft($width-1,'0')}else{$value=$value.PadLeft($width,'0')}}else{$value=$value.PadLeft($width)}}
            $null=$result.Append($value)
        }
    }while($index -lt $Values.Count -and $index -gt $before)
    return $result.ToString()
}
function Invoke-B2PSRead([string[]] $Arguments){
    $raw=$false;$arrayName='';$names=@();$prompt=''
    for($i=0;$i -lt $Arguments.Count;$i++){switch($Arguments[$i]){'-r'{$raw=$true};'-a'{$i++;$arrayName=$Arguments[$i]};'-p'{$i++;$prompt=$Arguments[$i]};default{$names+=$Arguments[$i]}}}
    if($prompt){Write-B2PSOutput $prompt -ErrorStream};$bytes=New-Object 'Collections.Generic.List[byte]';$ended=$false
    while($true){$c=$script:B2PSIO.In.ReadByte();if($c -lt 0){break};if($c -eq 10){$ended=$true;break};if($c -eq 92 -and -not $raw){$c=$script:B2PSIO.In.ReadByte();if($c -eq 10){continue};if($c -lt 0){break}};$bytes.Add([byte]$c)}
    $value=$script:B2PSUtf8.GetString($bytes.ToArray());$ifs=Get-B2PSValue 'IFS'
    if($arrayName){$parts=$(if($ifs.Length){[regex]::Split($value.Trim([char[]]$ifs),'['+[regex]::Escape($ifs)+']+')}else{@($value)});Set-B2PSArray $arrayName $parts}
    elseif(-not $names.Count){Set-B2PSValue 'REPLY' $value}
    else{
        $parts=@(if($ifs.Length){$splitRegex=New-Object Text.RegularExpressions.Regex('['+[regex]::Escape($ifs)+']+');$splitRegex.Split($value.Trim([char[]]$ifs),$names.Count)}else{$value})
        for($i=0;$i -lt $names.Count;$i++){Set-B2PSValue $names[$i] $(if($i -lt $parts.Count){$parts[$i]}else{''})}
    };$script:B2PSStatus=$(if($ended){0}else{1})
}
function Invoke-B2PSCommand([string[]] $Words){
    if(-not $Words.Count){$script:B2PSStatus=0;return};$name=$Words[0];$a=@();if($Words.Count -gt 1){$a=@($Words[1..($Words.Count-1)])}
    if($script:B2PSTrace){Write-B2PSOutput ('+ '+($Words -join ' ')+"`n") -ErrorStream}
    $script:B2PSStatus=0
    if($script:B2PSFunctions.ContainsKey($name)){Invoke-B2PSFunction $name $a;return}
    switch -CaseSensitive($name){
        ':' {return};'true'{return};'false'{$script:B2PSStatus=1;return};'test'{Invoke-B2PSTest $a;return}
        'echo'{
            $newline=$true;$escape=$false;$i=0
            while($i -lt $a.Count -and $a[$i] -match '^-[neE]+$'){foreach($c in $a[$i].Substring(1).ToCharArray()){switch -CaseSensitive([string]$c){'n'{$newline=$false};'e'{$escape=$true};'E'{$escape=$false}}};$i++}
            $text=$(if($i -lt $a.Count){$a[$i..($a.Count-1)] -join ' '}else{''});if($escape){$escaped=Convert-B2PSEscapes $text;$text=$escaped.Text;if($escaped.Stop){$newline=$false}};if($newline){$text+="`n"};Write-B2PSOutput $text;return
        }
        'printf'{
            $variable='';if($a.Count -gt 1 -and $a[0] -eq '-v'){$variable=$a[1];$a=@($a[2..($a.Count-1)])};if(-not $a.Count){throw 'printf needs a format'}
            $values=@();if($a.Count -gt 1){$values=@($a[1..($a.Count-1)])};$text=Format-B2PSPrintf $a[0] $values;if($variable){Set-B2PSValue $variable $text}else{Write-B2PSOutput $text};return
        }
        'set'{
            for($i=0;$i -lt $a.Count;$i++){
                if($a[$i] -eq '--'){$script:B2PSArgs=$(if($i+1 -lt $a.Count){@($a[($i+1)..($a.Count-1)])}else{@()});return}
                $value=$a[$i].StartsWith('-');$flags=$a[$i].Substring(1)
                foreach($flag in $flags.ToCharArray()){switch([string]$flag){'e'{$script:B2PSErrexit=$value};'u'{$script:B2PSUnset=$value};'a'{$script:B2PSAllExport=$value};'x'{$script:B2PSTrace=$value};'o'{$i++;switch($a[$i]){'pipefail'{$script:B2PSPipefail=$value};'errexit'{$script:B2PSErrexit=$value};'nounset'{$script:B2PSUnset=$value};'allexport'{$script:B2PSAllExport=$value};'xtrace'{$script:B2PSTrace=$value};default{throw 'Unsupported set option'}}};default{throw 'Unsupported set option'}}}
            };return
        }
        'shopt'{if($a.Count -ne 2 -or $a[0] -notin @('-s','-u') -or $a[1] -notin @('nullglob','failglob')){throw 'shopt supports nullglob/failglob'};if($a[1] -eq 'nullglob'){$script:B2PSNullGlob=$a[0] -eq '-s'}else{$script:B2PSFailGlob=$a[0] -eq '-s'};return}
        'shift'{$count=$(if($a.Count){[int]$a[0]}else{1});if($count -lt 0 -or $count -gt $script:B2PSArgs.Count){$script:B2PSStatus=1;return};$script:B2PSArgs=$(if($count -lt $script:B2PSArgs.Count){@($script:B2PSArgs[$count..($script:B2PSArgs.Count-1)])}else{@()});return}
        'exit'{Send-B2PSControl 'exit' $(if($a.Count){([int]$a[0]) -band 255}else{$script:B2PSPreviousStatus})}
        'return'{Send-B2PSControl 'return' $(if($a.Count){([int]$a[0]) -band 255}else{$script:B2PSPreviousStatus})}
        'break'{Send-B2PSControl 'break' $(if($a.Count){[int]$a[0]}else{1})}
        'continue'{Send-B2PSControl 'continue' $(if($a.Count){[int]$a[0]}else{1})}
        'export'{
            foreach($arg in $a){if($arg -match '^([A-Za-z_][A-Za-z_0-9]*)(?:=(.*))?$'){$key=$Matches[1];$value=$(if($Matches.ContainsKey(2)){$Matches[2]}elseif(Test-B2PSSet $key){Get-B2PSValue $key}else{''});Set-B2PSValue $key $value -Export}else{throw 'Invalid export variable'}};return
        }
        'local'{
            if(-not $script:B2PSFrames.Count){throw 'local outside a function'};$frame=$script:B2PSFrames.Peek()
            foreach($arg in $a){if($arg -notmatch '^([A-Za-z_][A-Za-z_0-9]*)(?:=(.*))?$'){throw 'Invalid local variable'};$key=$Matches[1];$hasValue=$Matches.ContainsKey(2);$value=$Matches[2]
                if(-not $frame.Contains($key)){$frame[$key]=@{Set=$script:B2PSVars.ContainsKey($key);Value=$(if($script:B2PSVars.ContainsKey($key)){$script:B2PSVars[$key]}else{''});Array=$(if($script:B2PSArrays.ContainsKey($key)){$script:B2PSArrays[$key]}else{$null});Export=$script:B2PSExported.ContainsKey($key);Env=[Environment]::GetEnvironmentVariable($key,'Process')}}
                if($hasValue){Set-B2PSValue $key $value}else{$null=$script:B2PSVars.Remove($key);$null=$script:B2PSArrays.Remove($key);Set-B2PSEnvironment $key $null}
            };return
        }
        'unset'{foreach($arg in $a){if($arg -eq '-v'){continue};if($arg -match '^([A-Za-z_][A-Za-z_0-9]*)\[(.+)\]$'){if($script:B2PSArrays.ContainsKey($Matches[1])){$script:B2PSArrays[$Matches[1]].Remove($Matches[2])};continue};$null=$script:B2PSVars.Remove($arg);$null=$script:B2PSArrays.Remove($arg);$null=$script:B2PSExported.Remove($arg);Set-B2PSEnvironment $arg $null};return}
        'declare'{foreach($arg in $a){if($arg -in @('-a','-A')){continue};if($arg -match '^[A-Za-z_][A-Za-z_0-9]*$'){if(-not $script:B2PSArrays.ContainsKey($arg)){$script:B2PSArrays[$arg]=[ordered]@{}}}elseif($arg -match '^([A-Za-z_][A-Za-z_0-9]*)=(.*)$'){Set-B2PSValue $Matches[1] $Matches[2]}else{throw 'declare supports arrays and simple variables'}};return}
        'read'{Invoke-B2PSRead $a;return}
        'pwd'{Write-B2PSOutput ((Get-Location).Path+"`n");return}
        'cd'{
            $path=$(if(-not $a.Count){Get-B2PSValue 'HOME'}elseif($a[0] -eq '-'){Get-B2PSValue 'OLDPWD'}else{$a[0]});$old=(Get-Location).Path;Set-Location -LiteralPath $path;Set-B2PSValue 'OLDPWD' $old;Set-B2PSValue 'PWD' (Get-Location).Path;if($a.Count -and $a[0] -eq '-'){Write-B2PSOutput ((Get-Location).Path+"`n")};return
        }
        'pushd'{$script:B2PSDirStack.Push((Get-Location).Path);Set-Location -LiteralPath $a[0];return}
        'popd'{if(-not $script:B2PSDirStack.Count){throw 'Directory stack is empty'};Set-Location -LiteralPath $script:B2PSDirStack.Pop();return}
        'sleep'{$seconds=0.0;foreach($arg in $a){if($arg -notmatch '^([0-9]+(?:\.[0-9]+)?)([smhd]?)$'){throw 'Invalid sleep duration'};$number=[double]::Parse($Matches[1],[Globalization.CultureInfo]::InvariantCulture);$factor=$(switch($Matches[2]){'m'{60};'h'{3600};'d'{86400};default{1}});$seconds+=$number*$factor};Start-Sleep -Milliseconds ([int](1000*$seconds));return}
        'dirname'{foreach($arg in $a){$value=$arg.TrimEnd([char[]]'/\');$parent=[IO.Path]::GetDirectoryName($value);if(-not $parent){$parent=$(if($arg.StartsWith('/')){'/'}else{'.'})};Write-B2PSOutput ($parent+"`n")};return}
        'basename'{$value=[IO.Path]::GetFileName($a[0].TrimEnd([char[]]'/\'));if($a.Count -gt 1 -and $value.EndsWith($a[1])){$value=$value.Substring(0,$value.Length-$a[1].Length)};Write-B2PSOutput ($value+"`n");return}
        'realpath'{foreach($arg in $a){if($arg -eq '-m'){continue};Write-B2PSOutput ((Resolve-B2PSPath $arg)+"`n")};return}
        'date'{$utc=$a -contains '-u' -or $a -contains '--utc';$format=@($a|Where-Object{$_ -notin @('-u','--utc')});Write-B2PSOutput ((Get-B2PSDate $(if($format.Count){$format[0]}else{''}) -Utc:$utc)+"`n");return}
        'mkdir'{$parents=$a -contains '-p' -or $a -contains '--parents';foreach($path in $a){if($path -in @('-p','--parents','--')){continue};if(Test-Path -LiteralPath $path){if($parents -and (Test-Path -LiteralPath $path -PathType Container)){continue};throw "mkdir: path exists: $path"};$resolved=Resolve-B2PSPath $path;if(-not $parents -and -not [IO.Directory]::Exists([IO.Path]::GetDirectoryName($resolved))){throw 'mkdir: parent missing'};$null=[IO.Directory]::CreateDirectory($resolved)};return}
        'touch'{foreach($path in $a){if($path -eq '--'){continue};$resolved=Resolve-B2PSPath $path;if([IO.Directory]::Exists($resolved)){[IO.Directory]::SetLastWriteTime($resolved,[DateTime]::Now)}elseif([IO.File]::Exists($resolved)){[IO.File]::SetLastWriteTime($resolved,[DateTime]::Now)}else{[IO.File]::WriteAllBytes($resolved,[byte[]]@())}};return}
        'rmdir'{foreach($path in $a){[IO.Directory]::Delete((Resolve-B2PSPath $path),$false)};return}
        {$_ -in @('cp','mv','rm')}{
            $force=$false;$recursive=$false;$paths=@();$ended=$false
            foreach($arg in $a){if(-not $ended -and $arg -eq '--'){$ended=$true;continue};if(-not $ended -and $arg -match '^-[rfRa]+$'){$force=$force -or $arg.Contains('f');$recursive=$recursive -or $arg.Contains('r') -or $arg.Contains('R') -or $arg.Contains('a');continue};if($arg -eq '--recursive'){$recursive=$true;continue};if($arg -eq '--force'){$force=$true;continue};$paths+=$arg}
            if($name -eq 'rm'){foreach($path in $paths){if(-not (Test-Path -LiteralPath $path)){if($force){continue};throw "rm: missing path: $path"};if((Test-Path -LiteralPath $path -PathType Container) -and -not $recursive){throw 'rm needs -r for a directory'};Remove-Item -LiteralPath $path -Recurse:$recursive -Force};return}
            if($paths.Count -lt 2){throw "$name needs source and destination"};$destination=$paths[-1]
            foreach($source in $paths[0..($paths.Count-2)]){
                $target=$destination;if(Test-Path -LiteralPath $destination -PathType Container){$target=Join-Path $destination ([IO.Path]::GetFileName($source.TrimEnd([char[]]'/\')))}
                if($name -eq 'mv'){Move-Item -LiteralPath $source -Destination $target -Force}else{if(Test-Path -LiteralPath $source -PathType Container){if(-not $recursive){throw 'cp needs -r for a directory'};Copy-B2PSDirectory (Resolve-B2PSPath $source) (Resolve-B2PSPath $target)}else{[IO.File]::Copy((Resolve-B2PSPath $source),(Resolve-B2PSPath $target),$true)}}
            };return
        }
        'find'{
            $path=$(if($a.Count -and -not $a[0].StartsWith('-')){$a[0]}else{'.'});$start=$(if($a.Count -and $a[0] -eq $path){1}else{0});$min=0;$max=[int]::MaxValue;$type='';$pattern='*';$ignore=$false;$zero=$false
            for($i=$start;$i -lt $a.Count;$i++){switch($a[$i]){'-mindepth'{$i++;$min=[int]$a[$i]};'-maxdepth'{$i++;$max=[int]$a[$i]};'-type'{$i++;$type=$a[$i]};'-name'{$i++;$pattern=$a[$i]};'-iname'{$i++;$pattern=$a[$i];$ignore=$true};'-print'{ };'-print0'{$zero=$true};default{throw 'Unsupported find predicate'}}}
            $root=Resolve-B2PSPath $path;$separator=$(if($zero){[string][char]0}else{"`n"})
            foreach($item in Find-B2PSPath $path $min $max $type $pattern -IgnoreCase:$ignore){$value=$(if([IO.Path]::IsPathRooted($path)){$item}else{$path.TrimEnd('/')+($item.Substring($root.TrimEnd('\').Length).Replace('\','/'))});Write-B2PSOutput ($value+$separator)};return
        }
        'seq'{
            $separator="`n";$values=@();for($i=0;$i -lt $a.Count;$i++){if($a[$i] -eq '-s'){$i++;$separator=$a[$i]}elseif($a[$i].StartsWith('-s') -and $a[$i].Length -gt 2){$separator=$a[$i].Substring(2)}else{$values+=$a[$i]}}
            $start=1.0;$step=1.0;if($values.Count -eq 1){$end=[double]::Parse($values[0],[Globalization.CultureInfo]::InvariantCulture)}elseif($values.Count -eq 2){$start=[double]::Parse($values[0],[Globalization.CultureInfo]::InvariantCulture);$end=[double]::Parse($values[1],[Globalization.CultureInfo]::InvariantCulture)}else{$start=[double]::Parse($values[0],[Globalization.CultureInfo]::InvariantCulture);$step=[double]::Parse($values[1],[Globalization.CultureInfo]::InvariantCulture);$end=[double]::Parse($values[2],[Globalization.CultureInfo]::InvariantCulture)}
            if($step -eq 0){throw 'seq step is zero'};$output=New-Object 'Collections.Generic.List[string]';for($x=$start;$(if($step -gt 0){$x -le $end}else{$x -ge $end});$x+=$step){$output.Add($x.ToString('G',[Globalization.CultureInfo]::InvariantCulture))};if($output.Count){Write-B2PSOutput (($output -join $separator)+"`n")};return
        }
        'tee'{$append=$a -contains '-a';$bytes=Read-B2PSBytes;foreach($path in $a){if($path -in @('-a','--append','--')){continue};$resolved=Resolve-B2PSPath $path;if($append){$stream=[IO.File]::Open($resolved,[IO.FileMode]::Append);try{$stream.Write($bytes,0,$bytes.Length)}finally{$stream.Dispose()}}else{[IO.File]::WriteAllBytes($resolved,$bytes)}};Write-B2PSBytes $bytes;return}
        'printenv'{foreach($key in $a){$value=[Environment]::GetEnvironmentVariable($key,'Process');if($null -eq $value){$script:B2PSStatus=1}else{Write-B2PSOutput ($value+"`n")}};if(-not $a.Count){foreach($key in [Environment]::GetEnvironmentVariables('Process').Keys){Write-B2PSOutput ($key+'='+[Environment]::GetEnvironmentVariable($key,'Process')+"`n")}};return}
        'ln'{$symbolic=$false;$force=$false;$paths=@();foreach($arg in $a){if($arg -match '^-[sfn]+$'){$symbolic=$symbolic -or $arg.Contains('s');$force=$force -or $arg.Contains('f')}elseif($arg -ne '--'){$paths+=$arg}};if($paths.Count -ne 2){throw 'ln needs source and link paths'};$target=$paths[1];if(Test-Path -LiteralPath $target -PathType Container){$target=Join-Path $target ([IO.Path]::GetFileName($paths[0]))};if($force -and (Test-Path -LiteralPath $target)){Remove-Item -LiteralPath $target -Force};$null=New-Item -ItemType $(if($symbolic){'SymbolicLink'}else{'HardLink'}) -Path $target -Target $paths[0];return}
        'env'{
            $saved=Enter-B2PSSubshell -ExportedOnly
            try{$i=0;while($i -lt $a.Count){if($a[$i] -eq '-i' -or $a[$i] -eq '--ignore-environment'){foreach($key in [Environment]::GetEnvironmentVariables('Process').Keys){Set-B2PSEnvironment $key $null};$i++;continue};if($a[$i] -eq '-u' -or $a[$i] -eq '--unset'){$i++;Set-B2PSEnvironment $a[$i] $null;$i++;continue};if($a[$i] -match '^([A-Za-z_][A-Za-z_0-9]*)=(.*)$'){Set-B2PSValue $Matches[1] $Matches[2] -Export;$i++;continue};break}
                if($i -ge $a.Count){Invoke-B2PSCommand @('printenv')}else{Invoke-B2PSCommand @($a[$i..($a.Count-1)])};$status=$script:B2PSStatus
            }finally{Restore-B2PSSubshell $saved};$script:B2PSStatus=$status;return
        }
        {$_ -in @('which','command','type')}{
            $names=@($a|Where-Object{$_ -notin @('-v','-p','-P')});foreach($candidate in $names){if($script:B2PSFunctions.ContainsKey($candidate)){Write-B2PSOutput ($candidate+"`n");continue};$found=Get-Command -Name $candidate -CommandType Application -ErrorAction SilentlyContinue|Select-Object -First 1;if($found){Write-B2PSOutput ($found.Source+"`n")}else{$script:B2PSStatus=1}};return
        }
        'ls'{$force=$a -contains '-a' -or $a -contains '-A';$paths=@($a|Where-Object{-not $_.StartsWith('-')});if(-not $paths.Count){$paths=@('.')};foreach($path in $paths){foreach($item in Get-ChildItem -LiteralPath $path -Force:$force|Sort-Object Name){Write-B2PSOutput ($item.Name+"`n")}};return}
        {$_ -in @('cat','grep','head','tail','wc','sort','uniq','cut','tr','sed','awk','xargs')}{Invoke-B2PSTextCommand $name $a;return}
        default{Invoke-B2PSNative $name $a;return}
    }
}


function Get-B2PSOptions([string[]] $Arguments,[string] $Switches,[string] $Values='',[hashtable] $Long=@{},[string] $Optional=''){
    $flags=[Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal);$rest=New-Object 'Collections.Generic.List[string]';$ended=$false
    for($i=0;$i -lt $Arguments.Count;$i++){
        $arg=$Arguments[$i];if(-not $ended -and $arg -eq '--'){$ended=$true;continue}
        if($ended -or -not $arg.StartsWith('-') -or $arg -eq '-'){$rest.Add($arg);continue}
        if($arg.StartsWith('--')){$parts=$arg.Substring(2).Split(@('='),2);if(-not $Long.ContainsKey($parts[0])){throw "Unsupported option: $arg"};$letters=[string]$Long[$parts[0]];$attached=$(if($parts.Count -gt 1){$parts[1]}else{$null})}
        else{$letters=$arg.Substring(1);$attached=$null}
        for($j=0;$j -lt $letters.Length;$j++){
            $flag=[string]$letters[$j]
            if($Values.Contains($flag) -or $Optional.Contains($flag)){
                $value=$(if($null -ne $attached){$attached}elseif($j+1 -lt $letters.Length){$letters.Substring($j+1)}elseif($Optional.Contains($flag)){''}else{$i++;if($i -ge $Arguments.Count){throw "Option -$flag needs a value"};$Arguments[$i]})
                if(-not $flags.ContainsKey($flag)){$flags[$flag]=@()};$flags[$flag]=@($flags[$flag])+$value;break
            }
            if(-not $Switches.Contains($flag)){throw "Unsupported option: -$flag"};$flags[$flag]=$true
        }
    };return @{Flags=$flags;Rest=$rest.ToArray()}
}
function Convert-B2PSBRE([string] $Pattern,[switch] $Extended){
    if($Extended){return $Pattern};$builder=New-Object Text.StringBuilder;$bracket=$false
    for($i=0;$i -lt $Pattern.Length;$i++){
        $c=[string]$Pattern[$i]
        if($c -eq '\' -and $i+1 -lt $Pattern.Length){$i++;$next=[string]$Pattern[$i];if($next -in @('+','?','|','(',')','{','}')){$null=$builder.Append($next)}elseif($next -in @('<','>')){$null=$builder.Append('\b')}else{$null=$builder.Append('\'+$next)}}
        elseif($c -eq '['){$bracket=$true;$null=$builder.Append($c)}elseif($c -eq ']'){$bracket=$false;$null=$builder.Append($c)}
        elseif(-not $bracket -and $c -in @('+','?','|','(',')','{','}')){$null=$builder.Append('\'+$c)}else{$null=$builder.Append($c)}
    };return $builder.ToString()
}
function Get-B2PSTrSet([string] $Set){
    $classes=@{'[:lower:]'='abcdefghijklmnopqrstuvwxyz';'[:upper:]'='ABCDEFGHIJKLMNOPQRSTUVWXYZ';'[:digit:]'='0123456789';'[:space:]'=" `t`n`r"+[char]11+[char]12;'[:blank:]'=" `t";'[:alpha:]'='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ';'[:alnum:]'='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'}
    foreach($key in $classes.Keys){$Set=$Set.Replace($key,$classes[$key])};$Set=(Convert-B2PSEscapes $Set).Text;$values=New-Object 'Collections.Generic.List[int]'
    for($i=0;$i -lt $Set.Length;$i++){if($i+2 -lt $Set.Length -and $Set[$i+1] -eq '-'){$first=[int][char]$Set[$i];$last=[int][char]$Set[$i+2];if($last -lt $first){throw 'tr has a reversed range'};for($n=$first;$n -le $last;$n++){$values.Add($n)};$i+=2}else{$values.Add([int][char]$Set[$i])}}
    return $values.ToArray()
}
function Get-B2PSSedProgram([string] $Source){
    $commands=New-Object 'Collections.Generic.List[object]';$i=0
    while($i -lt $Source.Length){
        while($i -lt $Source.Length -and ($Source[$i] -eq ';' -or [char]::IsWhiteSpace($Source[$i]))){$i++};if($i -ge $Source.Length){break}
        $address='';$match=[regex]::Match($Source.Substring($i),'^(\d+(?:,\d+)?|\$|/(?:\\.|[^/])*/)')
        if($match.Success){$address=$match.Value;$i+=$match.Length};$op=[string]$Source[$i];$i++
        if($op -eq 's'){
            if($i -ge $Source.Length){throw 'sed substitution needs a delimiter'};$delimiter=$Source[$i];$i++;$parts=@()
            for($part=0;$part -lt 2;$part++){$builder=New-Object Text.StringBuilder;$closed=$false
                while($i -lt $Source.Length){$c=$Source[$i];$i++;if($c -eq $delimiter){$closed=$true;break};if($c -eq '\' -and $i -lt $Source.Length){$next=$Source[$i];$i++;if($next -eq $delimiter){$null=$builder.Append($next)}else{$null=$builder.Append('\'+$next)}}else{$null=$builder.Append($c)}}
                if(-not $closed){throw 'Unclosed sed substitution'};$parts+=$builder.ToString()
            }
            $flags='';while($i -lt $Source.Length -and $Source[$i] -ne ';' -and -not [char]::IsWhiteSpace($Source[$i])){$flags+=$Source[$i];$i++};if($flags -notmatch '^[gIp0-9]*$'){throw 'Unsupported sed substitution flags'}
            $commands.Add(@{Op='s';Address=$address;Pattern=$parts[0];Replacement=$parts[1];Flags=$flags})
        }elseif($op -in @('d','p','q')){$commands.Add(@{Op=$op;Address=$address})}else{throw 'sed supports substitutions and addressed d/p/q commands'}
    };return $commands.ToArray()
}
function Invoke-B2PSSed([string[]] $Arguments){
    $options=Get-B2PSOptions $Arguments 'nEr' 'e' @{quiet='n';silent='n';'regexp-extended'='E';expression='e';'in-place'='i'} 'i';$flags=$options.Flags;$rest=$options.Rest;$programs=@()
    if($flags.ContainsKey('e')){$programs=@($flags['e'])}else{if(-not $rest.Count){throw 'sed needs a program'};$programs=@($rest[0]);$rest=$(if($rest.Count -gt 1){@($rest[1..($rest.Count-1)])}else{@()})}
    $commands=@();foreach($program in $programs){$commands+=@(Get-B2PSSedProgram $program)};$sources=$(if($rest.Count){$rest}else{@('-')})
    foreach($path in $sources){$text=Get-B2PSInputText @($path);$lines=@(Get-B2PSLines $text);$output=New-Object Text.StringBuilder
        for($number=0;$number -lt $lines.Count;$number++){$line=[string]$lines[$number].Text;$ending=$(if($lines[$number].Newline){"`n"}else{''});$deleted=$false;$quit=$false
            foreach($command in $commands){$address=$command.Address;$selected=$true
                if($address -eq '$'){$selected=$number -eq $lines.Count-1}elseif($address.StartsWith('/')){$selected=$line -cmatch (Convert-B2PSBRE $address.Substring(1,$address.Length-2) -Extended:($flags.ContainsKey('E') -or $flags.ContainsKey('r')))}elseif($address -match '^(\d+),(\d+)$'){$selected=$number+1 -ge [int]$Matches[1] -and $number+1 -le [int]$Matches[2]}elseif($address -match '^\d+$'){$selected=$number+1 -eq [int]$address}
                if(-not $selected){continue}
                switch($command.Op){
                    'd'{$deleted=$true};'p'{$null=$output.Append($line+$ending)};'q'{$quit=$true}
                    's'{
                        $pattern=Convert-B2PSBRE $command.Pattern -Extended:($flags.ContainsKey('E') -or $flags.ContainsKey('r'));$regexOptions=$(if($command.Flags.Contains('I')){[Text.RegularExpressions.RegexOptions]::IgnoreCase}else{[Text.RegularExpressions.RegexOptions]::None});$regex=New-Object Text.RegularExpressions.Regex($pattern,$regexOptions)
                        $replacement=[string]$command.Replacement;$wasMatch=$regex.IsMatch($line)
                        $evaluator=[Text.RegularExpressions.MatchEvaluator]{param($m)$builder=New-Object Text.StringBuilder;for($k=0;$k -lt $replacement.Length;$k++){if($replacement[$k] -eq '&'){$null=$builder.Append($m.Value)}elseif($replacement[$k] -eq '\' -and $k+1 -lt $replacement.Length){$k++;if([string]$replacement[$k] -match '^\d$'){$null=$builder.Append($m.Groups[[int]([string]$replacement[$k])].Value)}elseif($replacement[$k] -eq 'n'){$null=$builder.Append("`n")}else{$null=$builder.Append($replacement[$k])}}else{$null=$builder.Append($replacement[$k])}};return $builder.ToString()}
                        if($command.Flags.Contains('g')){$line=$regex.Replace($line,$evaluator)}else{$line=$regex.Replace($line,$evaluator,1)};if($wasMatch -and $command.Flags.Contains('p')){$null=$output.Append($line+$ending)}
                    }
                };if($deleted -or $quit){break}
            }
            if(-not $deleted -and -not $flags.ContainsKey('n')){$null=$output.Append($line+$ending)};if($quit){break}
        }
        if($flags.ContainsKey('i')){if($path -eq '-'){throw 'sed -i needs a file'};$suffix=[string]$flags['i'][-1];if($suffix){[IO.File]::Copy((Resolve-B2PSPath $path),(Resolve-B2PSPath ($path+$suffix)),$true)};[IO.File]::WriteAllText((Resolve-B2PSPath $path),$output.ToString(),$script:B2PSUtf8)}else{Write-B2PSOutput $output.ToString()}
    }
}
function Invoke-B2PSAwk([string[]] $Arguments){
    $options=Get-B2PSOptions $Arguments '' 'F' @{};$rest=$options.Rest;if(-not $rest.Count){throw 'awk needs a program'};$program=$rest[0].Trim();$paths=$(if($rest.Count -gt 1){@($rest[1..($rest.Count-1)])}else{@()});$text=Get-B2PSInputText $paths;$lines=@(Get-B2PSLines $text)
    $separator=$(if($options.Flags.ContainsKey('F')){[string]$options.Flags['F'][-1]}else{' '})
    if($program -match '^\{\s*([A-Za-z_][A-Za-z_0-9]*)\s*\+=\s*\$(\d+)\s*;?\s*\}\s*END\s*\{\s*print\s+\1\s*;?\s*\}$'){
        $column=[int]$Matches[2];$sum=0.0;foreach($record in $lines){$fields=$(if($separator -eq ' '){[regex]::Split($record.Text.Trim(),'\s+')}else{[regex]::Split($record.Text,$separator)});$value=$(if($column -gt 0 -and $column -le $fields.Count){$fields[$column-1]}else{'0'});$parsed=0.0;$null=[double]::TryParse($value,[Globalization.NumberStyles]::Float,[Globalization.CultureInfo]::InvariantCulture,[ref]$parsed);$sum+=$parsed};Write-B2PSOutput ($sum.ToString('G',[Globalization.CultureInfo]::InvariantCulture)+"`n");return
    }
    if($program -notmatch '^(?:(NR)\s*(==|!=|>=|<=|>|<)\s*(\d+)\s*)?\{\s*print(?:\s+(.+?))?\s*;?\s*\}$'){throw 'awk supports print fields/NR/NF and simple column sums'}
    $comparison=$Matches[2];$limit=[int]$Matches[3];$expression=$(if($Matches[4]){$Matches[4].TrimEnd(';').Trim()}else{'$0'})
    for($i=0;$i -lt $lines.Count;$i++){
        $nr=$i+1;$selected=$(switch($comparison){'>'{$nr -gt $limit};'>='{$nr -ge $limit};'<'{$nr -lt $limit};'<='{$nr -le $limit};'=='{$nr -eq $limit};'!='{$nr -ne $limit};default{$true}});if(-not $selected){continue}
        $line=[string]$lines[$i].Text;$fields=$(if($separator -eq ' '){if($line.Trim().Length){[regex]::Split($line.Trim(),'\s+')}else{@()}}else{[regex]::Split($line,$separator)});$output=@()
        foreach($term in ($expression -split '\s*,\s*')){if($term -match '^\$(\d+)$'){$column=[int]$Matches[1];$output+=$(if($column -eq 0){$line}elseif($column -le $fields.Count){$fields[$column-1]}else{''})}elseif($term -eq '$NF'){$output+=$(if($fields.Count){$fields[-1]}else{''})}elseif($term -eq 'NF'){$output+=[string]$fields.Count}elseif($term -eq 'NR'){$output+=[string]$nr}elseif($term -match '^"(.*)"$'){$output+=$Matches[1]}else{throw 'Unsupported awk print expression'}}
        Write-B2PSOutput (($output -join ' ')+"`n")
    }
}
function Split-B2PSXargs([string] $Text){
    $values=New-Object 'Collections.Generic.List[string]';$value='';$quote='';$present=$false
    for($i=0;$i -lt $Text.Length;$i++){$c=[string]$Text[$i];if($c -eq '\' -and $quote -ne "'"){$i++;if($i -ge $Text.Length){throw 'xargs trailing backslash'};$value+=$Text[$i];$present=$true}elseif($c -in @("'",'"') -and ($quote -eq '' -or $quote -eq $c)){$quote=$(if($quote -eq ''){$c}else{''});$present=$true}elseif($quote -eq '' -and [char]::IsWhiteSpace($Text[$i])){if($present){$values.Add($value);$value='';$present=$false}}else{$value+=$c;$present=$true}}
    if($quote){throw 'xargs unmatched quote'};if($present){$values.Add($value)};return $values.ToArray()
}
function Invoke-B2PSXargs([string[]] $Arguments){
    $options=Get-B2PSOptions $Arguments '0rt' 'nIdP' @{'null'='0';'no-run-if-empty'='r';'max-args'='n';replace='I';delimiter='d';'max-procs'='P'};$f=$options.Flags;$command=$options.Rest;if(-not $command.Count){$command=@('echo')}
    if($f.ContainsKey('P') -and [int]$f['P'][-1] -ne 1){throw 'Parallel xargs requires manual adaptation'};$text=Get-B2PSText
    if($f.ContainsKey('I')){$values=@($text.Split([char]10)|Where-Object{$_.Length})}elseif($f.ContainsKey('0') -or $f.ContainsKey('d')){$delimiter=$(if($f.ContainsKey('0')){[string][char]0}else{(Convert-B2PSEscapes ([string]$f['d'][-1])).Text});$values=@($text.Split([char[]]$delimiter));if($text.EndsWith($delimiter)){$values=@($values|Select-Object -SkipLast 1)}}else{$values=@(Split-B2PSXargs $text)}
    if(-not $values.Count -and $f.ContainsKey('r')){return};$maximum=$(if($f.ContainsKey('I')){1}elseif($f.ContainsKey('n')){[int]$f['n'][-1]}else{[Math]::Max(1,$values.Count)});if($maximum -lt 1){throw 'xargs -n must be positive'};$combined=0
    $oldIO=$script:B2PSIO;$script:B2PSIO=@{Out=$oldIO.Out;Err=$oldIO.Err;In=[IO.Stream]::Null;RedirectInput=$true}
    try{for($i=0;$i -lt [Math]::Max(1,$values.Count);$i+=$maximum){$words=@($command)
        if($f.ContainsKey('I')){$placeholder=[string]$f['I'][-1];$words=@($command|ForEach-Object{$_.Replace($placeholder,[string]$values[$i])})}elseif($values.Count){$words+=@($values[$i..([Math]::Min($i+$maximum,$values.Count)-1)])}
        if($f.ContainsKey('t')){Write-B2PSOutput (($words -join ' ')+"`n") -ErrorStream};Invoke-B2PSCommand $words;$status=$script:B2PSStatus
        if($status -eq 255){$combined=124;break};if($status -in @(126,127)){$combined=$status;break};if($status -ne 0){$combined=123}
    }}finally{$script:B2PSIO=$oldIO};$script:B2PSStatus=$combined
}
function Invoke-B2PSTextCommand([string] $Name,[string[]] $Arguments){
    switch -CaseSensitive($Name){
        'cat'{
            $o=Get-B2PSOptions $Arguments 'nbsvETA' '' @{'number'='n';'number-nonblank'='b';'squeeze-blank'='s';'show-ends'='E';'show-tabs'='T';'show-all'='A'}
            if(-not $o.Flags.Count){$paths=$(if($o.Rest.Count){$o.Rest}else{@('-')});foreach($path in $paths){try{$bytes=$(if($path -eq '-'){Read-B2PSBytes}else{,[IO.File]::ReadAllBytes((Resolve-B2PSPath $path))});Write-B2PSBytes $bytes}catch{Write-B2PSOutput ("cat: ${path}: "+$_.Exception.Message+"`n") -ErrorStream;$script:B2PSStatus=1}};return}
            $number=0;$previousBlank=$false;$visible=$o.Flags.ContainsKey('v') -or $o.Flags.ContainsKey('A');$tabs=$o.Flags.ContainsKey('T') -or $o.Flags.ContainsKey('A')
            foreach($record in Get-B2PSByteLines (Get-B2PSInputBytes $o.Rest)){$blank=$record.Raw.Length -eq 0;if($o.Flags.ContainsKey('s') -and $blank -and $previousBlank){continue};$previousBlank=$blank
                if($o.Flags.ContainsKey('b') -or $o.Flags.ContainsKey('n')){if(-not $o.Flags.ContainsKey('b') -or -not $blank){$number++;Write-B2PSOutput (([string]$number).PadLeft(6)+"`t")}}
                $output=New-Object 'Collections.Generic.List[byte]'
                foreach($byte in $record.Raw){$code=[int]$byte;$shown=''
                    if($visible -and $code -ge 128){$shown='M-';$code-=128}
                    if(($visible -and ($code -lt 32 -and $code -ne 9)) -or ($tabs -and $code -eq 9)){$shown+='^'+[char]($code+64)}elseif($visible -and $code -eq 127){$shown+='^?'}else{$shown+=[char]$code}
                    if($visible -or ($tabs -and $byte -eq 9)){$output.AddRange($script:B2PSUtf8.GetBytes($shown))}else{$output.Add([byte]$byte)}
                };Write-B2PSBytes $output.ToArray();if(($o.Flags.ContainsKey('E') -or $o.Flags.ContainsKey('A')) -and $record.Newline){Write-B2PSOutput '$'};if($record.Newline){Write-B2PSOutput "`n"}
            };return
        }
        'grep'{
            $o=Get-B2PSOptions $Arguments 'ivFEnclLqohHwxrRa' 'efmABC' @{ignorecase='i';'ignore-case'='i';invert='v';'invert-match'='v';'fixed-strings'='F';'extended-regexp'='E';'line-number'='n';count='c';quiet='q';recursive='r';regexp='e';file='f';'max-count'='m';'after-context'='A';'before-context'='B';context='C'};$f=$o.Flags;$paths=$o.Rest;$patterns=@()
            if($f.ContainsKey('e')){$patterns+=@($f['e'])};if($f.ContainsKey('f')){foreach($path in $f['f']){$patterns+=@([IO.File]::ReadAllLines((Resolve-B2PSPath $path)))}}
            if(-not $patterns.Count){if(-not $paths.Count){throw 'grep needs a pattern'};$patterns=@($paths[0]);$paths=$(if($paths.Count -gt 1){@($paths[1..($paths.Count-1)])}else{@()})}
            if(-not $paths.Count){$paths=@('-')};if($f.ContainsKey('r') -or $f.ContainsKey('R')){$expanded=@();foreach($path in $paths){if(Test-Path -LiteralPath $path -PathType Container){$expanded+=@(Get-ChildItem -LiteralPath $path -File -Recurse -Force|ForEach-Object{$_.FullName})}else{$expanded+=$path}};$paths=$expanded}
            $regexPatterns=@($patterns|ForEach-Object{$p=$(if($f.ContainsKey('F')){[regex]::Escape($_)}else{Convert-B2PSBRE $_ -Extended:$f.ContainsKey('E')});if($f.ContainsKey('w')){$p='(?<!\w)(?:'+$p+')(?!\w)'};if($f.ContainsKey('x')){$p='^(?:'+$p+')$'};$p});$pattern='(?:'+($regexPatterns -join '|')+')';$regex=New-Object Text.RegularExpressions.Regex($pattern,$(if($f.ContainsKey('i')){[Text.RegularExpressions.RegexOptions]::IgnoreCase}else{[Text.RegularExpressions.RegexOptions]::None}))
            $any=$false;$failed=$false;$showName=($paths.Count -gt 1 -or $f.ContainsKey('H')) -and -not $f.ContainsKey('h')
            foreach($path in $paths){try{$text=Get-B2PSInputText @($path)}catch{$failed=$true;Write-B2PSOutput ("grep: ${path}: "+$_.Exception.Message+"`n") -ErrorStream;continue};$count=0;$number=0
                if(($f.ContainsKey('A') -or $f.ContainsKey('B') -or $f.ContainsKey('C')) -and -not $f.ContainsKey('c') -and -not $f.ContainsKey('l') -and -not $f.ContainsKey('L')){
                    $before=$(if($f.ContainsKey('B')){[int]$f['B'][-1]}elseif($f.ContainsKey('C')){[int]$f['C'][-1]}else{0});$after=$(if($f.ContainsKey('A')){[int]$f['A'][-1]}elseif($f.ContainsKey('C')){[int]$f['C'][-1]}else{0});$records=@(Get-B2PSLines $text);$selected=New-Object 'Collections.Generic.HashSet[int]';$matches=New-Object 'Collections.Generic.HashSet[int]'
                    for($n=0;$n -lt $records.Count;$n++){$matched=$regex.IsMatch($records[$n].Text);if($f.ContainsKey('v')){$matched=-not $matched};if(-not $matched){continue};$any=$true;$count++;if($f.ContainsKey('q')){$script:B2PSStatus=0;return};$null=$matches.Add($n);for($k=[Math]::Max(0,$n-$before);$k -le [Math]::Min($records.Count-1,$n+$after);$k++){$null=$selected.Add($k)};if($f.ContainsKey('m') -and $count -ge [int]$f['m'][-1]){break}}
                    $last=-1;for($n=0;$n -lt $records.Count;$n++){if(-not $selected.Contains($n)){continue};if($last -ge 0 -and $n -gt $last+1){Write-B2PSOutput "--`n"};$separator=$(if($matches.Contains($n)){':'}else{'-'});$prefix=$(if($showName){$path+$separator}else{''})+$(if($f.ContainsKey('n')){[string]($n+1)+$separator}else{''});Write-B2PSOutput ($prefix+$records[$n].Text+"`n");$last=$n};continue
                }
                foreach($record in Get-B2PSLines $text){$number++;$matched=$regex.IsMatch($record.Text);if($f.ContainsKey('v')){$matched=-not $matched};if(-not $matched){continue};$count++;$any=$true
                    if($f.ContainsKey('q')){$script:B2PSStatus=0;return};if(-not $f.ContainsKey('c') -and -not $f.ContainsKey('l') -and -not $f.ContainsKey('L')){
                        $prefix=$(if($showName){$path+':'}else{''})+$(if($f.ContainsKey('n')){[string]$number+':'}else{''})
                        if($f.ContainsKey('o') -and -not $f.ContainsKey('v')){foreach($m in $regex.Matches($record.Text)){if($m.Length){Write-B2PSOutput ($prefix+$m.Value+"`n")}}}else{Write-B2PSOutput ($prefix+$record.Text+"`n")}
                    };if($f.ContainsKey('m') -and $count -ge [int]$f['m'][-1]){break}
                }
                if($f.ContainsKey('c')){Write-B2PSOutput ($(if($showName){$path+':'}else{''})+[string]$count+"`n")};if(($f.ContainsKey('l') -and $count -gt 0) -or ($f.ContainsKey('L') -and $count -eq 0)){Write-B2PSOutput ($path+"`n")}
            };$script:B2PSStatus=$(if($failed){2}elseif($any){0}else{1});return
        }
        {$_ -in @('head','tail')}{
            $argsNormalized=@();$previous='';foreach($arg in $Arguments){if($previous -notin @('-n','-c') -and $arg -match '^-(\d+)$'){$argsNormalized+='-n';$argsNormalized+=$Matches[1]}else{$argsNormalized+=$arg};$previous=$arg};$o=Get-B2PSOptions $argsNormalized 'qv' 'nc' @{lines='n';bytes='c';quiet='q';silent='q';verbose='v'};$paths=$(if($o.Rest.Count){$o.Rest}else{@('-')});$amount=$(if($o.Flags.ContainsKey('c')){[string]$o.Flags['c'][-1]}elseif($o.Flags.ContainsKey('n')){[string]$o.Flags['n'][-1]}else{'10'});$count=[long]$amount;$from=$amount.StartsWith('+')
            foreach($path in $paths){if(($paths.Count -gt 1 -or $o.Flags.ContainsKey('v')) -and -not $o.Flags.ContainsKey('q')){if($path -ne $paths[0]){Write-B2PSOutput "`n"};Write-B2PSOutput ("==> $path <==`n")}
                if($o.Flags.ContainsKey('c')){$bytes=$(if($path -eq '-'){Read-B2PSBytes}else{,[IO.File]::ReadAllBytes((Resolve-B2PSPath $path))});$length=$bytes.Length
                    $start=$(if($Name -eq 'head'){0}elseif($from){[Math]::Min($length,[Math]::Max(0,$count-1))}else{[Math]::Max(0,$length-[Math]::Abs($count))})
                    $end=$(if($Name -eq 'head'){if($count -lt 0){[Math]::Max(0,$length+$count)}else{[Math]::Min($length,$count)}}else{$length});if($end -gt $start){Write-B2PSBytes ([byte[]]$bytes[$start..($end-1)])}
                }else{$records=@(Get-B2PSLines (Get-B2PSInputText @($path)));$length=$records.Count;$start=$(if($Name -eq 'head'){0}elseif($from){[Math]::Min($length,[Math]::Max(0,$count-1))}else{[Math]::Max(0,$length-[Math]::Abs($count))});$end=$(if($Name -eq 'head'){if($count -lt 0){[Math]::Max(0,$length+$count)}else{[Math]::Min($length,$count)}}else{$length});for($i=$start;$i -lt $end;$i++){Write-B2PSOutput ($records[$i].Text+$(if($records[$i].Newline){"`n"}else{''}))}}
            };return
        }
        'wc'{
            $o=Get-B2PSOptions $Arguments 'lwcm' '' @{lines='l';words='w';bytes='c';chars='m'};$paths=$(if($o.Rest.Count){$o.Rest}else{@('-')});$columns=@('l','w','c');if($o.Flags.Count){$columns=@('l','w','m','c'|Where-Object{$o.Flags.ContainsKey($_)})};$totals=@{l=0L;w=0L;m=0L;c=0L}
            foreach($path in $paths){$bytes=$(if($path -eq '-'){Read-B2PSBytes}else{,[IO.File]::ReadAllBytes((Resolve-B2PSPath $path))});$text=$script:B2PSUtf8.GetString($bytes);$values=@{l=@($bytes|Where-Object{$_ -eq 10}).Count;w=[regex]::Matches($text,'[^\s\u2060]+').Count;c=$bytes.Length;m=@($text.ToCharArray()|Where-Object{-not [char]::IsLowSurrogate($_)}).Count};if($env:LC_ALL -eq 'C'){$values.m=$bytes.Length};foreach($key in @($totals.Keys)){$totals[$key]+=$values[$key]};$width=$(if($columns.Count -gt 1 -and $path -eq '-'){7}else{1});$printed=@($columns|ForEach-Object{([string]$values[$_]).PadLeft($width)});Write-B2PSOutput (($printed -join ' ')+$(if($path -ne '-'){' '+$path}else{''})+"`n")}
            if($paths.Count -gt 1){Write-B2PSOutput ((@($columns|ForEach-Object{[string]$totals[$_]}) -join ' ')+" total`n")};return
        }
        'sort'{
            $o=Get-B2PSOptions $Arguments 'rnfusb' 'kto' @{reverse='r';numeric='n';'numeric-sort'='n';'ignore-case'='f';unique='u';stable='s';key='k';'field-separator'='t';output='o'};$f=$o.Flags;$records=@(Get-B2PSLines (Get-B2PSInputText $o.Rest));$list=New-Object 'Collections.Generic.List[object]';for($i=0;$i -lt $records.Count;$i++){$list.Add(@{Text=[string]$records[$i].Text;Index=$i})}
            $separator=$(if($f.ContainsKey('t')){[string]$f['t'][-1]}else{''});$keySpec=$(if($f.ContainsKey('k')){[string]$f['k'][-1]}else{''});$numeric=$f.ContainsKey('n') -or $keySpec.EndsWith('n');$comparison=$(if($f.ContainsKey('f')){[StringComparison]::OrdinalIgnoreCase}else{[StringComparison]::Ordinal})
            $comparer=[Comparison[object]]{param($left,$right)$lk=$left.Text;$rk=$right.Text
                if($keySpec -match '^(\d+)(?:,(\d+))?[nrfb]*$'){$column=[int]$Matches[1]-1;$last=$(if($Matches[2]){[int]$Matches[2]-1}else{[int]::MaxValue});$lf=$(if($separator){$lk.Split([string[]]@($separator),[StringSplitOptions]::None)}else{[regex]::Split($lk.Trim(),'\s+')});$rf=$(if($separator){$rk.Split([string[]]@($separator),[StringSplitOptions]::None)}else{[regex]::Split($rk.Trim(),'\s+')});$lk=$(if($column -lt $lf.Count){$lf[$column..([Math]::Min($last,$lf.Count-1))]-join ' '}else{''});$rk=$(if($column -lt $rf.Count){$rf[$column..([Math]::Min($last,$rf.Count-1))]-join ' '}else{''})}
                if($numeric){$lm=[regex]::Match($lk,'^\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)');$rm=[regex]::Match($rk,'^\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)');$ln=$(if($lm.Success){[double]::Parse($lm.Value,[Globalization.CultureInfo]::InvariantCulture)}else{0});$rn=$(if($rm.Success){[double]::Parse($rm.Value,[Globalization.CultureInfo]::InvariantCulture)}else{0});$order=$ln.CompareTo($rn)}else{$order=[string]::Compare($lk,$rk,$comparison)}
                if($order -eq 0 -and -not $f.ContainsKey('u')){if($f.ContainsKey('s')){$order=$left.Index.CompareTo($right.Index)}else{$order=[string]::CompareOrdinal($left.Text,$right.Text)}};if($f.ContainsKey('r')){$order=-$order};return $order}
            $list.Sort($comparer);$output=New-Object Text.StringBuilder;$previous=$null;foreach($record in $list){if($f.ContainsKey('u') -and $null -ne $previous -and $comparer.Invoke($previous,$record) -eq 0){continue};$null=$output.Append($record.Text+"`n");$previous=$record}
            if($f.ContainsKey('o')){[IO.File]::WriteAllText((Resolve-B2PSPath ([string]$f['o'][-1])),$output.ToString(),$script:B2PSUtf8)}else{Write-B2PSOutput $output.ToString()};return
        }
        'uniq'{
            $o=Get-B2PSOptions $Arguments 'cdui' '' @{count='c';repeated='d';unique='u';'ignore-case'='i'};$input=$(if($o.Rest.Count){@($o.Rest[0])}else{@()});$records=@(Get-B2PSLines (Get-B2PSInputText $input));$output=New-Object Text.StringBuilder;$i=0
            while($i -lt $records.Count){$line=[string]$records[$i].Text;$count=1;while($i+$count -lt $records.Count -and [string]::Equals($line,[string]$records[$i+$count].Text,$(if($o.Flags.ContainsKey('i')){[StringComparison]::OrdinalIgnoreCase}else{[StringComparison]::Ordinal}))){$count++}
                if((-not $o.Flags.ContainsKey('d') -or $count -gt 1) -and (-not $o.Flags.ContainsKey('u') -or $count -eq 1)){$null=$output.Append($(if($o.Flags.ContainsKey('c')){([string]$count).PadLeft(7)+' '}else{''})+$line+$(if($records[$i].Newline){"`n"}else{''}))};$i+=$count
            };if($o.Rest.Count -gt 1){[IO.File]::WriteAllText((Resolve-B2PSPath $o.Rest[1]),$output.ToString(),$script:B2PSUtf8)}else{Write-B2PSOutput $output.ToString()};return
        }
        'cut'{
            $o=Get-B2PSOptions $Arguments 's' 'fdcb' @{fields='f';delimiter='d';characters='c';bytes='b';'only-delimited'='s'};$f=$o.Flags;$mode=$(if($f.ContainsKey('f')){'f'}elseif($f.ContainsKey('b')){'b'}else{'c'});if(-not $f.ContainsKey($mode)){throw 'cut needs -f/-c/-b'};$selection=[string]$f[$mode][-1];$delimiter=$(if($f.ContainsKey('d')){[string]$f['d'][-1]}else{"`t"})
            foreach($record in Get-B2PSLines (Get-B2PSInputText $o.Rest)){
                $line=[string]$record.Text;if($mode -eq 'f'){$items=$line.Split([string[]]@($delimiter),[StringSplitOptions]::None);if(-not $line.Contains($delimiter)){if(-not $f.ContainsKey('s')){Write-B2PSOutput ($line+"`n")};continue}}else{$items=$script:B2PSUtf8.GetBytes($line)}
                $indices=New-Object 'Collections.Generic.HashSet[int]';foreach($range in $selection.Split(',')){if($range -match '^(\d+)$'){$first=[int]$Matches[1];$last=$first}elseif($range -match '^(\d*)-(\d*)$'){$first=$(if($Matches[1]){[int]$Matches[1]}else{1});$last=$(if($Matches[2]){[int]$Matches[2]}else{$items.Count})}else{throw 'Invalid cut range'};for($n=$first;$n -le [Math]::Min($last,$items.Count);$n++){$null=$indices.Add($n-1)}};$selected=@(@($indices)|Sort-Object|ForEach-Object{$items[$_]})
                if($mode -eq 'f'){Write-B2PSOutput (($selected -join $delimiter)+"`n")}else{Write-B2PSBytes ([byte[]]$selected);Write-B2PSOutput "`n"}
            };return
        }
        'tr'{
            $o=Get-B2PSOptions $Arguments 'dscC' '' @{delete='d';'squeeze-repeats'='s';complement='c'};if(-not $o.Rest.Count){throw 'tr needs a character set'};$first=@(Get-B2PSTrSet $o.Rest[0]);$second=$(if($o.Rest.Count -gt 1){@(Get-B2PSTrSet $o.Rest[1])}else{@()});if($o.Flags.ContainsKey('c') -or $o.Flags.ContainsKey('C')){$first=@(0..255|Where-Object{$first -notcontains $_})}
            $map=@{};for($i=0;$i -lt $first.Count;$i++){if($second.Count){$map[[int]$first[$i]]=[int]$second[[Math]::Min($i,$second.Count-1)]}};$squeeze=$(if($second.Count){$second}else{$first});$output=New-Object 'Collections.Generic.List[byte]';$previous=-1
            foreach($byte in (Read-B2PSBytes)){if($o.Flags.ContainsKey('d') -and $first -contains [int]$byte){continue};$value=$(if(-not $o.Flags.ContainsKey('d') -and $map.ContainsKey([int]$byte)){$map[[int]$byte]}else{[int]$byte});if($o.Flags.ContainsKey('s') -and $value -eq $previous -and $squeeze -contains $value){continue};$output.Add([byte]$value);$previous=$value};Write-B2PSBytes $output.ToArray();return
        }
        'sed'{Invoke-B2PSSed $Arguments;return};'awk'{Invoke-B2PSAwk $Arguments;return};'xargs'{Invoke-B2PSXargs $Arguments;return}
    }
}


# Main script
try {
    # Bash line 3
    Invoke-B2PSStep {
        $b2psCommandWords=@(Expand-B2PSWord -Parts @(@{ Value='set'; Quoted=$false; Split=$false; Spread=$false; Glob=$true }); Expand-B2PSWord -Parts @(@{ Value='-e'; Quoted=$false; Split=$false; Spread=$false; Glob=$true }))
        $script:B2PSPreviousStatus=$script:B2PSStatus
        Invoke-B2PSCommand $b2psCommandWords
    } -Line 3 -Required
    # Bash line 4
    Invoke-B2PSStep {
        Set-B2PSValue 'PROJECT' (Join-B2PSScalar -Parts @(@{ Value='demo project'; Quoted=$true; Split=$false; Spread=$false; Glob=$false }))
    } -Line 4 -Required -Assignment
    # Bash line 5
    Invoke-B2PSStep {
        $b2psCommandWords=@(Expand-B2PSWord -Parts @(@{ Value='export'; Quoted=$false; Split=$false; Spread=$false; Glob=$true }); (Join-B2PSScalar -Parts @(@{ Value='APP_MODE=development'; Quoted=$false; Split=$false; Spread=$false; Glob=$true })))
        $script:B2PSPreviousStatus=$script:B2PSStatus
        Invoke-B2PSCommand $b2psCommandWords
    } -Line 5 -Required
    # Bash line 6
    Invoke-B2PSStep {
        $b2psCommandWords=@(Expand-B2PSWord -Parts @(@{ Value='mkdir'; Quoted=$false; Split=$false; Spread=$false; Glob=$true }); Expand-B2PSWord -Parts @(@{ Value='-p'; Quoted=$false; Split=$false; Spread=$false; Glob=$true }); Expand-B2PSWord -Parts @(@{ Value=(Get-B2PSValue 'PROJECT'); Quoted=$true; Split=$false; Spread=$false; Glob=$false }))
        $script:B2PSPreviousStatus=$script:B2PSStatus
        Invoke-B2PSCommand $b2psCommandWords
    } -Line 6 -Required
    # Bash line 7
    Invoke-B2PSStep {
        $b2psCommandWords=@(Expand-B2PSWord -Parts @(@{ Value='cd'; Quoted=$false; Split=$false; Spread=$false; Glob=$true }); Expand-B2PSWord -Parts @(@{ Value=(Get-B2PSValue 'PROJECT'); Quoted=$true; Split=$false; Spread=$false; Glob=$false }))
        $script:B2PSPreviousStatus=$script:B2PSStatus
        Invoke-B2PSCommand $b2psCommandWords
    } -Line 7 -Required
    # Bash line 8
    Invoke-B2PSStep {
        Invoke-B2PSRedirected -Redirections @(@{ Op='>'; Value=(Join-B2PSScalar -Parts @(@{ Value='.env'; Quoted=$false; Split=$false; Spread=$false; Glob=$true })) }) -Action {
            $b2psCommandWords=@(Expand-B2PSWord -Parts @(@{ Value='printf'; Quoted=$false; Split=$false; Spread=$false; Glob=$true }); Expand-B2PSWord -Parts @(@{ Value='%s\n'; Quoted=$true; Split=$false; Spread=$false; Glob=$false }); Expand-B2PSWord -Parts @(@{ Value='APP_MODE=development'; Quoted=$true; Split=$false; Spread=$false; Glob=$false }))
            $script:B2PSPreviousStatus=$script:B2PSStatus
            Invoke-B2PSCommand $b2psCommandWords
        }
    } -Line 8 -Required
    # Bash line 9
    Invoke-B2PSStep {
        $b2psCommandWords=@(Expand-B2PSWord -Parts @(@{ Value='touch'; Quoted=$false; Split=$false; Spread=$false; Glob=$true }); Expand-B2PSWord -Parts @(@{ Value='README.md'; Quoted=$false; Split=$false; Spread=$false; Glob=$true }))
        $script:B2PSPreviousStatus=$script:B2PSStatus
        Invoke-B2PSCommand $b2psCommandWords
    } -Line 9 -Required
    # Bash line 10
    Invoke-B2PSStep {
        Invoke-B2PSTest @(Expand-B2PSWord -Parts @(@{ Value='-f'; Quoted=$false; Split=$false; Spread=$false; Glob=$true }); Expand-B2PSWord -Parts @(@{ Value='.env'; Quoted=$false; Split=$false; Spread=$false; Glob=$true }))
    } -Line 10
    if ($script:B2PSStatus -eq 0) {
        Invoke-B2PSStep {
            $b2psCommandWords=@(Expand-B2PSWord -Parts @(@{ Value='echo'; Quoted=$false; Split=$false; Spread=$false; Glob=$true }); Expand-B2PSWord -Parts @(@{ Value='Config created'; Quoted=$true; Split=$false; Spread=$false; Glob=$false }))
            $script:B2PSPreviousStatus=$script:B2PSStatus
            Invoke-B2PSCommand $b2psCommandWords
        } -Line 10 -Required
    }
    # Bash line 11
    Invoke-B2PSStep {
        Invoke-B2PSPipeline -Stages @({
            $b2psCommandWords=@(Expand-B2PSWord -Parts @(@{ Value='cat'; Quoted=$false; Split=$false; Spread=$false; Glob=$true }); Expand-B2PSWord -Parts @(@{ Value='.env'; Quoted=$false; Split=$false; Spread=$false; Glob=$true }))
            $script:B2PSPreviousStatus=$script:B2PSStatus
            Invoke-B2PSCommand $b2psCommandWords
        }, {
            $b2psCommandWords=@(Expand-B2PSWord -Parts @(@{ Value='grep'; Quoted=$false; Split=$false; Spread=$false; Glob=$true }); Expand-B2PSWord -Parts @(@{ Value='-F'; Quoted=$false; Split=$false; Spread=$false; Glob=$true }); Expand-B2PSWord -Parts @(@{ Value='APP_MODE'; Quoted=$false; Split=$false; Spread=$false; Glob=$true }))
            $script:B2PSPreviousStatus=$script:B2PSStatus
            Invoke-B2PSCommand $b2psCommandWords
        })
    } -Line 11 -Required
    # Original comments
    #  Example: directory and UTF-8 config, no network calls.
} catch {
    if ($_.Exception.Data['B2PSControl'] -in @('exit','return')) { $script:B2PSStatus=[int]$_.Exception.Data['B2PSExitCode'] } else { $script:B2PSStatus=1; Write-B2PSOutput ($_.Exception.Message+"`n") -ErrorStream }
}
# B2PS final status
exit $script:B2PSStatus
