param(
    [Parameter(Mandatory = $true)]
    [string]$Bundle
)

$ErrorActionPreference = "Stop"
$files = Get-ChildItem -LiteralPath $Bundle -Recurse -File | Where-Object {
    $_.Extension -in ".exe", ".dll", ".pyd"
}

if (-not $files) {
    throw "Windows native bundle contains no signable executable or library"
}

foreach ($file in $files) {
    $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
    if ($signature.Status -ne "Valid") {
        throw "Invalid Authenticode signature for $($file.FullName): $($signature.Status)"
    }
    if ($null -eq $signature.TimeStamperCertificate) {
        throw "Authenticode signature is not timestamped: $($file.FullName)"
    }
}

Write-Output "Verified Authenticode signatures and timestamps for $($files.Count) files."
