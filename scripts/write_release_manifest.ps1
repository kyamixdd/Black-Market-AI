param(
    [Parameter(Mandatory = $true)][string]$InstallerPath,
    [Parameter(Mandatory = $true)][string]$OutputDirectory
)
$ErrorActionPreference = "Stop"

$installer = Get-Item -LiteralPath $InstallerPath
$tauriConfigPath = Join-Path $PSScriptRoot "..\\blackmarket-desktop\\src-tauri\\tauri.conf.json"
$tauriConfig = Get-Content -LiteralPath $tauriConfigPath -Raw | ConvertFrom-Json
$version = [string]$tauriConfig.version
if ($version -notmatch '^\\d+\\.\\d+\\.\\d+(?:[-+][0-9A-Za-z.-]+)?$') {
    throw "Tauri app version is invalid: '$version'."
}
$expectedNamePattern = "_$([regex]::Escape($version))_x64-setup\\.exe$"
if ($installer.Name -notmatch $expectedNamePattern) {
    throw "Installer filename '$($installer.Name)' does not match Tauri version '$version'."
}

$hash = (Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$signature = Get-AuthenticodeSignature -FilePath $installer.FullName
$commit = if ($env:GITHUB_SHA) { $env:GITHUB_SHA } else { "local-uncommitted" }
$branch = if ($env:GITHUB_REF_NAME) { $env:GITHUB_REF_NAME } else { "local" }
$runId = if ($env:GITHUB_RUN_ID) { $env:GITHUB_RUN_ID } else { $null }
$manifest = [ordered]@{
    product = "BlackMarket AI"
    version = $version
    installer = $installer.Name
    installerBytes = $installer.Length
    installerSha256 = $hash
    sourceCommit = $commit
    sourceBranch = $branch
    workflowRunId = $runId
    workflowRunUrl = if ($runId -and $env:GITHUB_SERVER_URL -and $env:GITHUB_REPOSITORY) { "$($env:GITHUB_SERVER_URL)/$($env:GITHUB_REPOSITORY)/actions/runs/$runId" } else { $null }
    generatedUtc = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
    signatureStatus = [string]$signature.Status
    signerSubject = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { $null }
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$manifestPath = Join-Path $OutputDirectory "release-manifest.json"
$checksumPath = Join-Path $OutputDirectory "installer.sha256"
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding utf8
"$hash  $($installer.Name)" | Set-Content -LiteralPath $checksumPath -Encoding ascii
Write-Host "Installer metadata:"
Write-Host "  Version: $version"
Write-Host "  SHA-256: $hash"
Write-Host "  Signature: $($signature.Status)"
Write-Host "  Commit: $commit"
