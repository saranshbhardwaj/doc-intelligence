# PowerShell script to run tests with different configurations

param(
    [string]$Type = "all",  # all, unit, integration, e2e
    [switch]$Coverage = $false,
    [switch]$Verbose = $false,
    [string]$File = ""
)

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Doc Intelligence Testing Framework" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Build pytest command
$pytest_cmd = "pytest"

# Add type marker
if ($Type -eq "unit") {
    $pytest_cmd += " -m unit"
    Write-Host "Running: Unit Tests" -ForegroundColor Green
} elseif ($Type -eq "integration") {
    $pytest_cmd += " -m integration"
    Write-Host "Running: Integration Tests" -ForegroundColor Green
} elseif ($Type -eq "e2e") {
    $pytest_cmd += " -m e2e"
    Write-Host "Running: End-to-End Tests" -ForegroundColor Green
} else {
    Write-Host "Running: All Tests" -ForegroundColor Green
}

# Add specific file if provided
if ($File) {
    $pytest_cmd += " $File"
    Write-Host "File: $File" -ForegroundColor Yellow
}

# Add coverage
if ($Coverage) {
    $pytest_cmd += " --cov=app --cov-report=term --cov-report=html"
    Write-Host "Coverage: Enabled" -ForegroundColor Yellow
}

# Add verbose
if ($Verbose) {
    $pytest_cmd += " -v"
}

Write-Host ""
Write-Host "Command: $pytest_cmd" -ForegroundColor Gray
Write-Host ""

# Run tests
Invoke-Expression $pytest_cmd

$exitCode = $LASTEXITCODE

# Show coverage report location if enabled
if ($Coverage -and $exitCode -eq 0) {
    Write-Host ""
    Write-Host "Coverage report generated at: htmlcov/index.html" -ForegroundColor Green
    Write-Host "Run 'start htmlcov/index.html' to view" -ForegroundColor Green
}

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "✓ All tests passed!" -ForegroundColor Green
} else {
    Write-Host "✗ Some tests failed" -ForegroundColor Red
}

exit $exitCode
