<#
.SYNOPSIS
    Generates a self-signed certificate, binds it to IIS, and enables HTTPS.
    Run as Administrator on Windows Server 2019.
#>

param(
    [string]$SiteName   = "AIDashboard",
    [string]$DnsName    = $env:COMPUTERNAME,
    [int]   $HttpsPort  = 443,
    [string]$SitePath   = "C:\inetpub\AIDashboard"
)

Import-Module WebAdministration -ErrorAction Stop

# ── 1. Create self-signed cert ─────────────────────────────────────────────
Write-Host "[1/5] Creating self-signed certificate for '$DnsName' ..." -ForegroundColor Cyan
$cert = New-SelfSignedCertificate `
    -DnsName $DnsName, "localhost" `
    -CertStoreLocation "Cert:\LocalMachine\My" `
    -FriendlyName "AI Dashboard Intranet" `
    -NotAfter (Get-Date).AddYears(5) `
    -KeyAlgorithm RSA `
    -KeyLength 2048 `
    -HashAlgorithm SHA256

$thumbprint = $cert.Thumbprint
Write-Host "  Thumbprint: $thumbprint" -ForegroundColor Green

# ── 2. Trust the cert on this machine ──────────────────────────────────────
Write-Host "[2/5] Adding certificate to Trusted Root store ..." -ForegroundColor Cyan
$store = New-Object System.Security.Cryptography.X509Certificates.X509Store(
    "Root", "LocalMachine")
$store.Open("ReadWrite")
$store.Add($cert)
$store.Close()

# ── 3. Ensure the IIS site exists ──────────────────────────────────────────
Write-Host "[3/5] Configuring IIS site '$SiteName' ..." -ForegroundColor Cyan
if (-not (Test-Path $SitePath)) {
    New-Item -ItemType Directory -Path $SitePath -Force | Out-Null
}

if (-not (Get-Website -Name $SiteName -ErrorAction SilentlyContinue)) {
    New-Website -Name $SiteName `
        -PhysicalPath $SitePath `
        -Port 80 `
        -Force | Out-Null
}

# ── 4. Add HTTPS binding ───────────────────────────────────────────────────
Write-Host "[4/5] Binding HTTPS on port $HttpsPort ..." -ForegroundColor Cyan
$existing = Get-WebBinding -Name $SiteName -Protocol "https" -Port $HttpsPort -ErrorAction SilentlyContinue
if (-not $existing) {
    New-WebBinding -Name $SiteName -Protocol "https" -Port $HttpsPort -IPAddress "*" -SslFlags 0
}

$binding = Get-Item "IIS:\SslBindings\0.0.0.0!$HttpsPort" -ErrorAction SilentlyContinue
if ($binding) { Remove-Item "IIS:\SslBindings\0.0.0.0!$HttpsPort" -Force }
New-Item "IIS:\SslBindings\0.0.0.0!$HttpsPort" -Value $cert | Out-Null

# ── 5. Add HTTP → HTTPS redirect rule ──────────────────────────────────────
Write-Host "[5/5] Adding HTTP → HTTPS redirect ..." -ForegroundColor Cyan
$filterPath = "system.webServer/rewrite/rules"
$sitePath   = "IIS:\Sites\$SiteName"

# Remove old redirect rule if it exists
$rules = Get-WebConfigurationProperty -Filter $filterPath -PSPath $sitePath -Name "Collection" -ErrorAction SilentlyContinue
$oldRule = $rules | Where-Object { $_.name -eq "HTTP to HTTPS" }
if ($oldRule) {
    Clear-WebConfiguration -Filter "$filterPath/rule[@name='HTTP to HTTPS']" -PSPath $sitePath
}

Add-WebConfigurationProperty -Filter $filterPath -PSPath $sitePath -Name "." -Value @{
    name          = "HTTP to HTTPS"
    stopProcessing = "true"
}
Set-WebConfigurationProperty -Filter "$filterPath/rule[@name='HTTP to HTTPS']/match" `
    -PSPath $sitePath -Name "url" -Value "(.*)"
Add-WebConfigurationProperty -Filter "$filterPath/rule[@name='HTTP to HTTPS']/conditions" `
    -PSPath $sitePath -Name "." -Value @{
        input   = "{HTTPS}"
        pattern = "^OFF$"
    }
Set-WebConfigurationProperty -Filter "$filterPath/rule[@name='HTTP to HTTPS']/action" `
    -PSPath $sitePath -Name "type" -Value "Redirect"
Set-WebConfigurationProperty -Filter "$filterPath/rule[@name='HTTP to HTTPS']/action" `
    -PSPath $sitePath -Name "url" -Value "https://{HTTP_HOST}/{R:1}"
Set-WebConfigurationProperty -Filter "$filterPath/rule[@name='HTTP to HTTPS']/action" `
    -PSPath $sitePath -Name "redirectType" -Value "Permanent"

Write-Host "`n✅  HTTPS configured! Access: https://$DnsName" -ForegroundColor Green
Write-Host "   To trust this cert on client machines, export it and install in their Trusted Root CA store." -ForegroundColor Yellow
