<#
.SYNOPSIS
    Startup script for SMS Web Viewer.
.DESCRIPTION
    Checks for the existence and validity of the .env file and Google OAuth credentials
    before launching the Docker container.
#>

$EnvFile = "$PSScriptRoot\.env"
$LogPrefix = "[SETUP]"

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "$timestamp $LogPrefix $Message"
}

Write-Log "Checking configuration..."

$needsCreation = $false
$needsUpdate = $false

if (-not (Test-Path $EnvFile)) {
    Write-Log "The .env file is missing."
    $needsCreation = $true
} else {
    $content = Get-Content $EnvFile -Raw
    if ($content -notmatch "GCP_CLIENT_ID=.*[a-zA-Z0-9]") {
        Write-Log "GCP_CLIENT_ID is missing or malformed in the .env file."
        $needsUpdate = $true
    }
    if ($content -notmatch "GCP_CLIENT_SECRET=.*[a-zA-Z0-9]") {
        Write-Log "GCP_CLIENT_SECRET is missing or malformed in the .env file."
        $needsUpdate = $true
    }
}

if ($needsCreation) {
    Write-Log "Creating a new .env template file..."
    $Template = @"
# Google OAuth2 Credentials (REQUIRED)
GCP_CLIENT_ID=""
GCP_CLIENT_SECRET=""

# The redirect URI must match exactly what you put in Google Cloud Console
OAUTH_REDIRECT_URI="http://localhost:8000/api/auth/callback"

# Optional Sync settings
SYNC_SCHEDULE="0 2 * * *"
DEFAULT_COUNTRY_CODE="US"
"@
    Set-Content -Path $EnvFile -Value $Template
    Write-Log "Created .env file at $EnvFile"
    Write-Host ""
    Write-Host "======================================================================" -ForegroundColor Yellow
    Write-Host " ACTION REQUIRED: Please edit the .env file and add your GCP" -ForegroundColor Yellow
    Write-Host " Client ID and Secret before continuing." -ForegroundColor Yellow
    Write-Host "======================================================================" -ForegroundColor Yellow
    exit 1
} elseif ($needsUpdate) {
    Write-Log "Your .env file exists but the Google OAuth credentials appear to be empty or malformed."
    Write-Host ""
    Write-Host "======================================================================" -ForegroundColor Yellow
    Write-Host " ACTION REQUIRED: Please open $EnvFile and ensure" -ForegroundColor Yellow
    Write-Host " GCP_CLIENT_ID and GCP_CLIENT_SECRET have valid values." -ForegroundColor Yellow
    Write-Host "======================================================================" -ForegroundColor Yellow
    exit 1
} else {
    Write-Log "Configuration looks good! GCP credentials found."
}

Write-Log "Starting SMS Web Viewer via Docker Compose..."
docker-compose up -d

if ($LASTEXITCODE -eq 0) {
    Write-Log "Application started successfully! Access it at http://localhost:8000"
} else {
    Write-Log "Failed to start the application. Check docker-compose logs."
}
