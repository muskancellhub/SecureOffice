# ============================================================
# COMPLETE E2E TEST SUITE RUNNER
# ============================================================
# Runs all E2E tests in sequence to validate entire system
# Generates ONE consolidated HTML report with all results
# ============================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SecureOffice E2E Test Suite" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if backend is running
Write-Host "🔍 Checking if backend is running..." -ForegroundColor Yellow
$backendRunning = $false
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 3 -UseBasicParsing -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        $backendRunning = $true
        Write-Host "✅ Backend is running" -ForegroundColor Green
    }
} catch {
    Write-Host "❌ Backend is NOT running" -ForegroundColor Red
    Write-Host "   Please start backend server first:" -ForegroundColor Yellow
    Write-Host "   cd backend && python -m uvicorn app.main:app --reload --port 8000" -ForegroundColor Yellow
    exit 1
}

# Check if frontend is running
Write-Host "🔍 Checking if frontend is running..." -ForegroundColor Yellow
$frontendRunning = $false
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5173" -TimeoutSec 3 -UseBasicParsing -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        $frontendRunning = $true
        Write-Host "✅ Frontend is running" -ForegroundColor Green
    }
} catch {
    Write-Host "❌ Frontend is NOT running" -ForegroundColor Red
    Write-Host "   Please start frontend server first:" -ForegroundColor Yellow
    Write-Host "   cd frontend && npm run dev" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Starting Test Execution" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Test phases in order
$testPhases = @(
    @{
        Name = "Phase 1: Authentication Tests"
        Path = "e2e/tests/auth/"
        Skip = @("auth.setup.ts")
        EstimatedTime = "2 min"
    },
    @{
        Name = "Phase 2: Business Intake Tests"
        Path = "e2e/tests/intake/"
        Skip = @()
        EstimatedTime = "5 min"
    },
    @{
        Name = "Phase 3: Network Design Tests"
        Path = "e2e/tests/designs/design-builder-simple.spec.ts"
        Skip = @()
        EstimatedTime = "3 min"
    },
    @{
        Name = "Phase 4: Design History Tests"
        Path = "e2e/tests/designs/design-history.spec.ts"
        Skip = @()
        EstimatedTime = "2 min"
    },
    @{
        Name = "Phase 5: AI Design Quality Tests"
        Path = "e2e/tests/designs/ai-design-quality.spec.ts"
        Skip = @()
        EstimatedTime = "5 min"
    },
    @{
        Name = "Phase 6: AI Design Consistency Tests"
        Path = "e2e/tests/designs/ai-design-consistency.spec.ts"
        Skip = @()
        EstimatedTime = "8 min"
    },
    @{
        Name = "Phase 7: AI Hallucination Tests"
        Path = "e2e/tests/designs/ai-design-hallucination.spec.ts"
        Skip = @()
        EstimatedTime = "7 min"
    },
    @{
        Name = "Phase 8: Cart & Commerce Tests"
        Path = "e2e/tests/cart-and-orders/"
        Skip = @()
        EstimatedTime = "3 min"
    },
    @{
        Name = "Phase 9: Billing Tests (Stripe)"
        Path = "e2e/tests/billing/billing-flow.spec.ts"
        Skip = @()
        EstimatedTime = "1 min"
    },
    @{
        Name = "Phase 10: Admin Functions Tests"
        Path = "e2e/tests/admin/"
        Skip = @()
        EstimatedTime = "3 min"
    }
)

# Calculate total estimated time
$totalMinutes = 0
foreach ($phase in $testPhases) {
    $minutes = [int]($phase.EstimatedTime -replace '[^\d]', '')
    $totalMinutes += $minutes
}

Write-Host "📊 Test Suite Overview:" -ForegroundColor Cyan
Write-Host "   Total Phases: $($testPhases.Count)" -ForegroundColor White
Write-Host "   Estimated Time: ~$totalMinutes minutes" -ForegroundColor White
Write-Host ""

# Confirm before starting
$confirmation = Read-Host "🚀 Ready to start full E2E test suite? (y/n)"
if ($confirmation -ne 'y' -and $confirmation -ne 'Y') {
    Write-Host "Test execution cancelled." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "▶️  Starting tests..." -ForegroundColor Green
Write-Host ""

# Build the test command with all test paths
$testPaths = @()
foreach ($phase in $testPhases) {
    $testPaths += $phase.Path
}

# Run all tests in one command (generates single HTML report)
$testPathsString = $testPaths -join " "

Write-Host "🧪 Executing: npx playwright test $testPathsString --project=chromium --workers=2 --reporter=html" -ForegroundColor Cyan
Write-Host ""

npx playwright test $testPathsString --project=chromium --workers=2 --reporter=html

$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Test Execution Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($exitCode -eq 0) {
    Write-Host "✅ All tests PASSED!" -ForegroundColor Green
} else {
    Write-Host "⚠️  Some tests FAILED (exit code: $exitCode)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "📊 View detailed HTML report:" -ForegroundColor Cyan
Write-Host "   npx playwright show-report" -ForegroundColor White
Write-Host ""
Write-Host "📁 Report location:" -ForegroundColor Cyan
Write-Host "   frontend/e2e/playwright-report/index.html" -ForegroundColor White
Write-Host ""

exit $exitCode
