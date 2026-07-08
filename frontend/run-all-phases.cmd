@echo off
REM Run all E2E test phases and generate ONE consolidated HTML report

echo.
echo ========================================
echo    E2E Tests - All Phases
echo ========================================
echo.

echo Checking services...
netstat -ano | findstr ":5173" >nul
if %errorlevel% neq 0 (
    echo [ERROR] Frontend not running on :5173
    echo         Start with: npm run dev
    exit /b 1
)

netstat -ano | findstr ":8000" >nul
if %errorlevel% neq 0 (
    echo [ERROR] Backend not running on :8000
    echo         Start with: cd backend ^&^& uvicorn app.main:app --reload
    exit /b 1
)

echo [OK] Frontend running on :5173
echo [OK] Backend running on :8000
echo.

echo Running auth setup...
call npx playwright test e2e/tests/auth.setup.ts --quiet
echo [OK] Auth setup complete
echo.

echo ========================================
echo    Executing All Phases
echo ========================================
echo.
echo Phase 0: Business Intake (28 tests)
echo Phase 1: Design Builder (15 tests)
echo.
echo Total: 43 tests
echo.

REM Run Phase 0 + Phase 1 together
call npx playwright test e2e/tests/intake/business-intake-complete.spec.ts e2e/tests/designs/design-builder-simple.spec.ts --project=chromium --workers=1 --reporter=html --timeout=90000

echo.
echo ========================================
echo    Report Generated
echo ========================================
echo.
echo Location: e2e\playwright-report\index.html
echo.
echo Contents:
echo   - Phase 0: Business Intake (28 tests)
echo   - Phase 1: Design Builder (15 tests)
echo.

echo Opening report in browser...
call npx playwright show-report e2e/playwright-report

echo.
echo Done!
