# ===============================================
# E2E Testing - Run Single Phase with Report Archiving
# ===============================================
# This script runs a single E2E test phase and archives the report
#
# Usage:
#   .\run-phase.ps1 -Phase 1
#   .\run-phase.ps1 -Phase 2
#   .\run-phase.ps1 -Phase "all"
#
# Output:
#   - e2e/playwright-report/index.html (latest)
#   - e2e/reports-archive/phase[X]-[timestamp].html (archived)
# ===============================================

param(
    [Parameter(Mandatory=$true)]
    [string]$Phase
)

$ErrorActionPreference = "Continue"
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"

# Colors
function Write-Phase {
    param([string]$message)
    Write-Host "`n$message" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
}

function Write-Success {
    param([string]$message)
    Write-Host "✅ $message" -ForegroundColor Green
}

function Write-Info {
    param([string]$message)
    Write-Host "ℹ️  $message" -ForegroundColor Yellow
}

function Write-Error-Custom {
    param([string]$message)
    Write-Host "❌ $message" -ForegroundColor Red
}

# Create archive directory if not exists
$archiveDir = "e2e\reports-archive"
if (-not (Test-Path $archiveDir)) {
    New-Item -ItemType Directory -Path $archiveDir -Force | Out-Null
    Write-Success "Created reports archive directory: $archiveDir"
}

# Function to archive current report
function Archive-Report {
    param(
        [string]$phaseName,
        [string]$timestamp
    )
    
    $reportFile = "e2e\playwright-report\index.html"
    if (Test-Path $reportFile) {
        $archiveFile = "$archiveDir\$phaseName-$timestamp.html"
        Copy-Item $reportFile $archiveFile -Force
        Write-Success "Report archived: $archiveFile"
        Write-Info "View archived: start $archiveFile"
        return $true
    } else {
        Write-Error-Custom "Report file not found: $reportFile"
        return $false
    }
}

# Phase definitions
$phases = @{
    "1" = @{
        Name = "Phase 1: Business Intake + Design Builder"
        Tests = "e2e/tests/intake e2e/tests/designs/design-builder-simple.spec.ts"
        ArchiveName = "phase1-intake-design"
    }
    "2" = @{
        Name = "Phase 2: Cart and Commerce"
        Tests = "e2e/tests/cart-and-orders e2e/tests/catalog"
        ArchiveName = "phase2-cart-commerce"
    }
    "3" = @{
        Name = "Phase 3: Quote Management"
        Tests = "e2e/tests/quotes"
        ArchiveName = "phase3-quotes"
    }
    "4" = @{
        Name = "Phase 4: Onboarding"
        Tests = "e2e/tests/onboarding"
        ArchiveName = "phase4-onboarding"
    }
    "5" = @{
        Name = "Phase 5: Tenant Security"
        Tests = "e2e/tests/tenant-isolation"
        ArchiveName = "phase5-tenant-security"
    }
    "6" = @{
        Name = "Phase 6: Admin Operations"
        Tests = "e2e/tests/admin"
        ArchiveName = "phase6-admin-ops"
    }
    "7" = @{
        Name = "Phase 7: Auth and Billing and Vendor"
        Tests = "e2e/tests/auth e2e/tests/billing e2e/tests/vendor"
        ArchiveName = "phase7-auth-billing-vendor"
    }
    "8" = @{
        Name = "Phase 8: Navigation and Error Handling"
        Tests = "e2e/tests/navigation e2e/tests/error-handling"
        ArchiveName = "phase8-navigation-errors"
    }
    "9" = @{
        Name = "Phase 9: Public Pages"
        Tests = "e2e/tests/public"
        ArchiveName = "phase9-public"
    }
    "all" = @{
        Name = "All Tests (Consolidated)"
        Tests = ""
        ArchiveName = "all-tests-consolidated"
    }
}

# Validate phase
if (-not $phases.ContainsKey($Phase)) {
    Write-Error-Custom "Invalid phase: $Phase"
    Write-Info "Available phases: 1, 2, 3, 4, 5, 6, 7, 8, 9, all"
    exit 1
}

$selectedPhase = $phases[$Phase]

# Run phase
Write-Phase $selectedPhase.Name

if ($Phase -eq "all") {
    # Run all tests
    npx playwright test --project=chromium --workers=1
} else {
    # Run specific phase tests
    $testCommand = "npx playwright test $($selectedPhase.Tests) --project=chromium --workers=1"
    Write-Info "Running: $testCommand"
    Invoke-Expression $testCommand
}

# Archive report
if ($LASTEXITCODE -eq 0) {
    Write-Success "Tests passed!"
} else {
    Write-Info "Tests completed with failures (see report for details)"
}

Archive-Report -phaseName $selectedPhase.ArchiveName -timestamp $timestamp

# Show report
Write-Info ""
Write-Info "View latest report:"
Write-Host "  npm run e2e:report" -ForegroundColor White
Write-Info ""
Write-Info "View archived reports:"
Write-Host "  explorer $archiveDir" -ForegroundColor White
