"""Finite UTF-8 text tools; byte operations and native pipes preserve raw bytes."""
TEXT_RUNTIME = r'''
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
'''
