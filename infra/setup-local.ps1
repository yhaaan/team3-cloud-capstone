param(
    [switch]$SkipPythonInstall,
    [switch]$SkipNeo4jStart
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message =="
}

function Test-CommandExists {
    param([string]$CommandName)
    return [bool](Get-Command $CommandName -ErrorAction SilentlyContinue)
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

Write-Step "Checking Docker"
if (-not (Test-CommandExists "docker")) {
    throw "Docker CLI was not found. Install Docker Desktop manually, start it, then rerun this script."
}
Write-Host "Docker CLI found"

Write-Host "Waiting for Docker engine..."
$dockerReady = $false
for ($i = 0; $i -lt 24; $i++) {
    try {
        docker info *> $null
        $dockerReady = $true
        break
    } catch {
        Start-Sleep -Seconds 5
    }
}
if (-not $dockerReady) {
    throw "Docker engine is not ready. Start Docker Desktop manually, wait until it finishes starting, then rerun this script."
}
Write-Host "Docker engine is ready"

if (-not $SkipPythonInstall) {
    Write-Step "Setting up Python virtual environment"
    if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
        python -m venv .venv
    }
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}

Write-Step "Preparing .env"
if (-not (Test-Path ".\.env") -and (Test-Path ".\.env.example")) {
    Copy-Item ".\.env.example" ".\.env"
    Write-Host ".env created from .env.example. Fill in OPENAI_API_KEY before running OpenAI-based jobs."
} elseif (Test-Path ".\.env") {
    Write-Host ".env already exists"
} else {
    Write-Host ".env.example not found. Create .env manually before running Module B."
}

if (-not $SkipNeo4jStart) {
    Write-Step "Starting Neo4j container"
    docker compose -f infra\docker-compose.yml up -d

    Write-Step "Checking Neo4j ports"
    docker ps --filter name=team3-neo4j --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    Write-Host "Neo4j Browser: http://localhost:7474"
    Write-Host "Neo4j Bolt URI: bolt://localhost:7687"
    Write-Host "Default user: neo4j"
    Write-Host "Default password: password"
}

Write-Step "Done"
Write-Host "Run Module B with:"
Write-Host ".\.venv\Scripts\python.exe services\module-b\src\run_to_neo4j.py"
