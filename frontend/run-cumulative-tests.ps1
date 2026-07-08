# ========================================
# Cumulative E2E Test Runner
# ========================================
# This script runs ALL completed phases together to create
# ONE consolidated HTML report that accumulates results
#
# Usage:
#   .\run-cumulative-tests.ps1
#
# It will automatically detect completed phases and run them all

param(
    [switch]$SkipPhase0,
    [switch]$SkipPhase1,
    [switch]$SkipPhase2,
    [switch]$AddPhase,
    [string]$PhasePath
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Cumulative E2E Test Runner" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Define phase paths
$completedPhases = @()

# Phase 0: Business Intake (COMPLETED)
if (-not $SkipPhase0) {
    $completedPhases += "e2e/tests/intake/business-intake-complete.spec.ts"
}

# Phase 1: Design Builder (Check if file exists and has tests)
$phase1Path = "e2e/tests/designs/design-builder-complete.spec.ts"
if ((Test-Path $phase1Path) -and -not $SkipPhase1) {
    $content = Get-Content $phase1Path -Raw
    if ($content -match "test\(") {
        $completedPhases += $phase1Path
        Write-Host "✅ Phase 1: Design Builder - INCLUDED" -ForegroundColor Green
    } else {
        Write-Host "⏭️  Phase 1: Design Builder - File exists but no tests yet" -ForegroundColor Yellow
    }
}

# Phase 2: Cart & Orders (Check if tests exist)
$phase2Path = "e2e/tests/cart-and-orders/"
if ((Test-Path $phase2Path) -and -not $SkipPhase2) {
    $testFiles = Get-ChildItem -Path $phase2Path -Filter "*.spec.ts" -ErrorAction SilentlyContinue
    if ($testFiles.Count -gt 0) {
        $completedPhases += $phase2Path
        Write-Host "✅ Phase 2: Cart & Orders - INCLUDED" -ForegroundColor Green
    }
}

# Add custom phase if specified
if ($AddPhase -and $PhasePath) {
    if (Test-Path $PhasePath) {
        $completedPhases += $PhasePath
        Write-Host "✅ Custom Phase: $PhasePath - INCLUDED" -ForegroundColor Green
    } else {
        Write-Host "❌ Custom Phase: $PhasePath - NOT FOUND" -ForegroundColor Red
        exit 1
    }
}

# Display what will be run
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Phases to Run (Cumulative):" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
$phaseNum = 0
foreach ($phase in $completedPhases) {
    $phaseNum++
    Write-Host "  $phaseNum. $phase" -ForegroundColor White
}

Write-Host "`n⚠️  NOTE: This will re-run ALL phases to create ONE consolidated report" -ForegroundColor Yellow
Write-Host "   Previous phase results will NOT vanish - they'll be included!`n" -ForegroundColor Yellow

# Confirm
$response = Read-Host "Continue? (Y/N)"
if ($response -ne "Y" -and $response -ne "y") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0
}

# Check services
Write-Host "`n[1/3] Checking services..." -ForegroundColor Yellow
try {
    $backend = Invoke-WebRequest -Uri "http://localhost:8000" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
    Write-Host "      ✅ Backend running on port 8000" -ForegroundColor Green
} catch {
    Write-Host "      ❌ Backend NOT running - please start it first" -ForegroundColor Red
    Write-Host "         cd ..\backend && uvicorn app.main:app --reload`n" -ForegroundColor White
    exit 1
}

try {
    $frontend = Invoke-WebRequest -Uri "http://localhost:5173" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
    Write-Host "      ✅ Frontend running on port 5173`n" -ForegroundColor Green
} catch {
    Write-Host "      ❌ Frontend NOT running - please start it first" -ForegroundColor Red
    Write-Host "         npm run dev`n" -ForegroundColor White
    exit 1
}

# Build test command
Write-Host "[2/3] Running cumulative tests..." -ForegroundColor Yellow
Write-Host "      This creates ONE index.html with ALL phase results`n" -ForegroundColor White

$testCommand = "npx playwright test $($completedPhases -join ' ') --project=chromium --reporter=html"

Write-Host "Executing: $testCommand`n" -ForegroundColor Cyan
Invoke-Expression $testCommand

# Verify report
Write-Host "`n[3/3] Verifying cumulative report..." -ForegroundColor Yellow

if (Test-Path "e2e\playwright-report\index.html") {
    Write-Host "      ✅ Cumulative report generated!`n" -ForegroundColor Green
    
    $reportPath = Resolve-Path "e2e\playwright-report\index.html"
    
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "✅ CUMULATIVE REPORT GENERATED!" -ForegroundColor Green
    Write-Host "========================================`n" -ForegroundColor Green
    
    Write-Host "📄 Report Location:" -ForegroundColor Yellow
    Write-Host "   $reportPath`n" -ForegroundColor White
    
    Write-Host "📊 Report Contains:" -ForegroundColor Yellow
    foreach ($phase in $completedPhases) {
        Write-Host "   ✅ $phase" -ForegroundColor Green
    }
    
    Write-Host "`n🌐 View Report:" -ForegroundColor Yellow
    Write-Host "   start e2e\playwright-report\index.html" -ForegroundColor Cyan
    Write-Host "   OR" -ForegroundColor White
    Write-Host "   npx playwright show-report e2e/playwright-report`n" -ForegroundColor Cyan
    
} else {
    Write-Host "      ❌ Report not generated - check errors above`n" -ForegroundColor Red
    exit 1
}

Write-Host "========================================`n" -ForegroundColor Cyan
