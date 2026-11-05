<#
  Construit le programme d'installation de HA Taskbar :
    1. HATaskbar.exe autonome avec PyInstaller (plus besoin de Python sur le PC cible)
    2. dist\HATaskbar-Setup-<version>.exe avec Inno Setup

  Prerequis (une seule fois) :
    - Python 3.8+          (python.org)
    - Inno Setup 6         winget install -e --id JRSoftware.InnoSetup --scope user
  PyInstaller est installe automatiquement dans un environnement virtuel dedie.

  Usage :  powershell -ExecutionPolicy Bypass -File build.ps1
#>
param(
    [string]$Python = "python",
    # Dossier de travail sur disque local (plus rapide qu'un partage reseau)
    [string]$BuildRoot = "$env:LOCALAPPDATA\HATaskbar-build"
)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot

$version = (Select-String -Path "$here\ha_core.py" -Pattern '^__version__ = "(.+)"').Matches[0].Groups[1].Value
Write-Host "== HA Taskbar $version"

# --- 1. environnement de construction
$venv = "$BuildRoot\venv"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    Write-Host "== Creation de l'environnement de construction"
    & $Python -m venv $venv
    if ($LASTEXITCODE) { throw "venv a echoue" }
}
& "$venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check --upgrade pyinstaller
if ($LASTEXITCODE) { throw "installation de PyInstaller impossible" }

# --- 2. executable
Write-Host "== PyInstaller"
& "$venv\Scripts\pyinstaller.exe" --noconfirm --clean --log-level WARN `
    --name HATaskbar --windowed --onedir `
    --icon "$here\assets\ha_taskbar.ico" `
    --add-data "$here\assets\ha_taskbar.ico;assets" `
    --add-data "$here\sv_ttk;sv_ttk" `
    --hidden-import settings_ui --hidden-import card_ui --hidden-import update_ui --hidden-import ui_theme --hidden-import tray `
    --distpath "$BuildRoot\dist" --workpath "$BuildRoot\work" --specpath "$BuildRoot" `
    "$here\ha_taskbar.py"
if ($LASTEXITCODE) { throw "PyInstaller a echoue" }

# --- 3. programme d'installation
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
          "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 introuvable : winget install -e --id JRSoftware.InnoSetup --scope user" }
Write-Host "== Inno Setup"
& $iscc /Q "/DAppVersion=$version" "/DDistDir=$BuildRoot\dist" "$here\installer\ha_taskbar.iss"
if ($LASTEXITCODE) { throw "Inno Setup a echoue" }

$setup = "$here\dist\HATaskbar-Setup-$version.exe"
Write-Host "== OK : $setup ($([math]::Round((Get-Item $setup).Length / 1MB, 1)) Mo)"
