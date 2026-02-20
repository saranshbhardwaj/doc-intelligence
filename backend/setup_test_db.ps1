# PowerShell script to set up PostgreSQL test database

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  PostgreSQL Test Database Setup" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
$dockerRunning = docker ps 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Docker is not running. Please start Docker first." -ForegroundColor Red
    exit 1
}

Write-Host "✓ Docker is running" -ForegroundColor Green

# Check if db container exists
$dbContainer = docker ps -a --filter "name=docint-postgres" --format "{{.Names}}"
if (-not $dbContainer) {
    Write-Host "✗ PostgreSQL container 'docint-postgres' not found. Please run 'docker-compose up -d' first." -ForegroundColor Red
    exit 1
}

Write-Host "✓ PostgreSQL container found" -ForegroundColor Green

# Check if db container is running
$dbRunning = docker ps --filter "name=docint-postgres" --format "{{.Names}}"
if (-not $dbRunning) {
    Write-Host "Starting PostgreSQL container..." -ForegroundColor Yellow
    docker start docint-postgres
    Start-Sleep -Seconds 3
}

Write-Host "✓ PostgreSQL container is running" -ForegroundColor Green
Write-Host ""

# Create test database
Write-Host "Creating test database 'docint_test'..." -ForegroundColor Yellow

$createDbResult = docker exec -i docint-postgres psql -U docint -d docint -c "CREATE DATABASE docint_test;" 2>&1

if ($createDbResult -match "already exists") {
    Write-Host "✓ Test database already exists" -ForegroundColor Green
} elseif ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Test database created successfully" -ForegroundColor Green
} else {
    Write-Host "✗ Failed to create test database" -ForegroundColor Red
    Write-Host $createDbResult -ForegroundColor Red
    exit 1
}

# Verify test database exists
Write-Host "Verifying test database..." -ForegroundColor Yellow
$verifyResult = docker exec -i docint-postgres psql -U docint -c "\l docint_test" 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Test database verified" -ForegroundColor Green
} else {
    Write-Host "✗ Failed to verify test database" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "You can now run tests with:" -ForegroundColor White
Write-Host "  pytest -m unit" -ForegroundColor Cyan
Write-Host "  pytest -m integration" -ForegroundColor Cyan
Write-Host "  pytest --cov=app" -ForegroundColor Cyan
Write-Host ""
