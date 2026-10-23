# Creates or removes a "Home Panel" shortcut (pythonw.exe directly, not run.bat).
#   powershell -NoProfile -ExecutionPolicy Bypass -File shortcut.ps1 -Folder Programs|Startup [-Remove]
param(
    [Parameter(Mandatory = $true)][ValidateSet('Programs', 'Startup')][string]$Folder,
    [switch]$Remove,
    [string]$Pythonw = ''
)
$ErrorActionPreference = 'Stop'
$appDir = $PSScriptRoot
$lnk = Join-Path ([Environment]::GetFolderPath($Folder)) 'Home Panel.lnk'
if ($Remove) {
    if (Test-Path -LiteralPath $lnk) { Remove-Item -LiteralPath $lnk; Write-Host "Removed $lnk" }
    exit 0
}
if (-not $Pythonw) {
    $venv = Join-Path $appDir '.venv\Scripts\pythonw.exe'
    if (Test-Path -LiteralPath $venv) { $Pythonw = $venv }
    else {
        $py = (& py -3 -c "import os,sys;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))").Trim()
        $Pythonw = $py
    }
}
if (-not (Test-Path -LiteralPath $Pythonw)) { throw "pythonw.exe not found: $Pythonw" }
if (Test-Path -LiteralPath $lnk) { Write-Host "Already exists (not overwritten): $lnk"; exit 0 }
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath = $Pythonw
$s.Arguments = '"' + (Join-Path $appDir 'home_panel.py') + '"'
$s.WorkingDirectory = $appDir
$s.IconLocation = (Join-Path $appDir 'icon.ico') + ',0'
$s.Description = 'Home Panel - Google Home on your desktop'
$s.Save()
Write-Host "Created $lnk -> $Pythonw"
