<#
.SYNOPSIS
    One-command Windows installer for llm-provider-router (zero secret echo, ExecutionPolicy-safe).
.EXAMPLE
    $env:ROUTER_PROXY_URL = "https://your-proxy.example.com/v1"
    # Pass API key via stdin:
    "<KEY>" | powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -ApiKeyStdin
#>
[CmdletBinding()]
param(
    [string]$Url = $env:ROUTER_PROXY_URL,
    [switch]$ApiKeyStdin,
    [string]$InstallDir = (Join-Path $env:USERPROFILE "llm-provider-router"),
    [string]$Model = "chatgpt/gpt-5.3-instant",
    [string]$CodingModel = "chatgpt/gpt-5.3-codex",
    [switch]$SkipChatTest
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$RepoUrl = "https://github.com/productaivn-wq/llm-provider-router.git"
$ZipUrl = "https://github.com/productaivn-wq/llm-provider-router/archive/refs/heads/main.zip"

function Find-Python310Plus {
    $candidates = @(
        @("py", @("-3")),
        @("python3", @()),
        @("python", @()),
        @((Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"), @()),
        @((Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"), @()),
        @((Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe"), @()),
        @("C:\Program Files\Python312\python.exe", @())
    )
    foreach ($entry in $candidates) {
        $cmd = $entry[0]
        $prefixArgs = $entry[1]
        if ($cmd -like "*\*" -and -not (Test-Path $cmd)) { continue }
        try {
            $resolved = if ($cmd -like "*\*") { $cmd } else { (Get-Command $cmd -ErrorAction Stop).Source }
            if ($resolved -like "*WindowsApps*") { continue }
            $ver = & $resolved @prefixArgs -c "import sys; print(int(sys.version_info >= (3, 10)))" 2>$null
            if ($LASTEXITCODE -eq 0 -and ($ver -join "").Trim() -eq "1") {
                return @($resolved, $prefixArgs)
            }
        } catch {
            continue
        }
    }
    return $null
}

$py = Find-Python310Plus
if (-not $py) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "[1/5] Installing Python 3.12 via winget..."
        winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements --silent | Out-Null
        $py = Find-Python310Plus
    }
}
if (-not $py) {
    throw "Python 3.10+ not found and automatic winget installation failed."
}

$PyExe = $py[0]
$PyPrefix = $py[1]
Write-Host "[1/5] Using Python: $PyExe"

if (-not (Test-Path (Join-Path $InstallDir "pyproject.toml"))) {
    if (Get-Command git -ErrorAction SilentlyContinue) {
        Write-Host "[2/5] Cloning repository into $InstallDir..."
        git clone $RepoUrl $InstallDir
    } else {
        Write-Host "[2/5] Git missing; downloading repository ZIP..."
        $tmpZip = Join-Path $env:TEMP "llm-provider-router-main.zip"
        $parentDir = Split-Path -Parent $InstallDir
        if (-not (Test-Path $parentDir)) { New-Item -ItemType Directory -Path $parentDir -Force | Out-Null }
        Invoke-WebRequest -Uri $ZipUrl -OutFile $tmpZip -UseBasicParsing
        Expand-Archive -Path $tmpZip -DestinationPath $parentDir -Force
        Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue
        $extracted = Join-Path $parentDir "llm-provider-router-main"
        if (Test-Path $InstallDir) { Remove-Item $InstallDir -Recurse -Force }
        Move-Item -Path $extracted -Destination $InstallDir
    }
} else {
    Write-Host "[2/5] Using existing folder $InstallDir"
}

$VenvDir = Join-Path $InstallDir ".venv"
$VenvPy = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-Host "[3/5] Creating virtual environment..."
    & $PyExe @PyPrefix -m venv $VenvDir
}

Write-Host "[3/5] Installing package into .venv (ExecutionPolicy-safe)..."
& $VenvPy -m pip install --upgrade pip --quiet
& $VenvPy -m pip install -e $InstallDir --quiet

if (-not $Url) {
    $Url = Read-Host "Proxy URL (e.g. https://your-proxy.example.com/v1)"
}

$ApiKey = ""
if ($ApiKeyStdin) {
    $ApiKey = [Console]::In.ReadToEnd().Trim()
} elseif ($env:ROUTER_API_KEY) {
    $ApiKey = $env:ROUTER_API_KEY.Trim()
} else {
    $sec = Read-Host "Personal API Key (hidden)" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try {
        $ApiKey = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr).Trim()
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}
if (-not $ApiKey) {
    throw "API key is required."
}

Write-Host "[4/5] Configuring encrypted-permission .env and probing proxy..."
$EnvPath = Join-Path $InstallDir ".env"
$ApiKey | & $VenvPy -m llm_provider_router setup `
    --url $Url `
    --api-key-stdin `
    --model $Model `
    --coding-model $CodingModel `
    --user-agent "LLM-Provider-Router/1.0" `
    --env-file $EnvPath `
    --probe `
    --json

Write-Host "[5/5] Auto-wiring Orchestrator rules & skills (AGY / Claude / Codex / Cursor)..."
& $VenvPy -m llm_provider_router connect --install-dir $InstallDir --python-exe $VenvPy --env-file $EnvPath --json

if (-not $SkipChatTest) {
    Write-Host "[Verify] Listing models and testing OpenAI sub-agent delegation..."
    & $VenvPy -m llm_provider_router models --env-file $EnvPath --json | Out-Null
    & $VenvPy -m llm_provider_router delegate --env-file $EnvPath --role writing "Reply OK if connected" --json
}

Write-Host "Setup complete. Install folder: $InstallDir. Open a NEW chat in Antigravity / Claude / Codex / Cursor to start offloading sub-tasks to OpenAI."
