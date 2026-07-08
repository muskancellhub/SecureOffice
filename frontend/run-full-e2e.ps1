# SecureOffice - Complete E2E Test Suite Runner
# Runs all tests from start to finish with ONE consolidated report

Write-Host ""
Write-Host "🚀 SecureOffice - Full System E2E Test" -ForegroundColor Green
Write-Host "═══════════════════════════════════════" -ForegroundColor Green
Write-Host ""

# Check if backend is running
Write-Host "🔍 Checking prerequisites..." -ForegroundColor Cyan
try {
    $backend = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
    Write-Host "  ✅ Backend running on :8000" -ForegroundColor Green
} catch {
    Write-Host "  ❌ Backend NOT running on :8000" -ForegroundColor Red
    Write-Host "     Start it with: cd backend && uvicorn app.main:app --reload --port 8000" -ForegroundColor Yellow
    exit 1
}

# Check if frontend is running
try {
    $frontend = Invoke-WebRequest -Uri "http://localhost:5173" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
    Write-Host "  ✅ Frontend running on :5173" -ForegroundColor Green
} catch {
    Write-Host "  ❌ Frontend NOT running on :5173" -ForegroundColor Red
    Write-Host "     Start it with: npm run dev" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "📊 Test Coverage:" -ForegroundColor Cyan
Write-Host "  • Authentication & Signup" -ForegroundColor White
Write-Host "  • Business Intake (AI)" -ForegroundColor White
Write-Host "  • Network Design Generation" -ForegroundColor White
Write-Host "  • AI Design Quality & Validation" -ForegroundColor White
Write-Host "  • Cart & Commerce" -ForegroundColor White
Write-Host "  • Billing (Stripe baseline)" -ForegroundColor White
Write-Host "  • Admin Functions" -ForegroundColor White
Write-Host ""
Write-Host "⏱️  Expected Duration: 40-50 minutes" -ForegroundColor Yellow
Write-Host "📈 Expected Tests: ~100 tests" -ForegroundColor Yellow
Write-Host ""

# Run all tests
Write-Host "🧪 Running complete test suite..." -ForegroundColor Cyan
Write-Host ""

npx playwright test --project=chromium --reporter=html

# Check exit code
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "════════════════════════════════════════" -ForegroundColor Green
    Write-Host "  ✅ ALL TESTS PASSED!" -ForegroundColor Green
    Write-Host "════════════════════════════════════════" -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "════════════════════════════════════════" -ForegroundColor Yellow
    Write-Host "  ⚠️  SOME TESTS FAILED" -ForegroundColor Yellow
    Write-Host "════════════════════════════════════════" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Check the HTML report for details" -ForegroundColor White
    Write-Host ""
}

Write-Host "📊 Report Location: playwright-report\index.html" -ForegroundColor Cyan
Write-Host "🌐 Opening report in browser..." -ForegroundColor Cyan
Write-Host ""

# Open report
npx playwright show-report
