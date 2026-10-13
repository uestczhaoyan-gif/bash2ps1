$ErrorActionPreference = 'Stop'
$projectDirectory = $PSScriptRoot
$python = Get-Command pythonw.exe -ErrorAction SilentlyContinue
$desktopDirectory = [Environment]::GetFolderPath('Desktop')
$shellObject = New-Object -ComObject WScript.Shell
$shortcutObject = $shellObject.CreateShortcut((Join-Path $desktopDirectory 'Bash to PowerShell.lnk'))
if ($python) {
    $shortcutObject.TargetPath = $python.Source
    $shortcutObject.Arguments = '"' + (Join-Path $projectDirectory 'app.py') + '"'
} else {
    $shortcutObject.TargetPath = Join-Path $projectDirectory 'Launch.cmd'
}
$shortcutObject.WorkingDirectory = $projectDirectory
$shortcutObject.Description = 'Bash to PowerShell desktop converter'
$shortcutObject.IconLocation = (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe') + ',0'
$shortcutObject.Save()
Write-Output ('Shortcut created in ' + $desktopDirectory)
