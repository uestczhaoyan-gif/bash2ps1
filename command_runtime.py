"""Native equivalents of common shell builtins and finite file/text commands."""
from psruntime import EXTENDED_RUNTIME


def _helper(name):
    start = EXTENDED_RUNTIME.index('function ' + name + '(')
    end = EXTENDED_RUNTIME.find('\nfunction ', start + 1)
    return EXTENDED_RUNTIME[start:end if end >= 0 else len(EXTENDED_RUNTIME)]


BUILTINS = _helper('Get-B2PSDate') + '\n' + _helper('Import-B2PSEnv') + '\n' + _helper('Find-B2PSPath') + r'''
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
'''
