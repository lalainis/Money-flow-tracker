param(
    [string]$EnvFile = "finan.env",
    [SecureString]$DbPassword = $null,
    [switch]$PromptForPassword,
    [switch]$Rollback
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Convert-SecureStringToPlainText {
    param([SecureString]$Value)

    if (-not $Value) {
        return $null
    }

    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

function Get-EnvMap {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Env file not found: $Path"
    }

    $map = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }

        $pair = $trimmed -split "=", 2
        if ($pair.Count -ne 2) {
            continue
        }

        $key = $pair[0].Trim()
        $value = $pair[1].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $map[$key] = $value
    }

    return $map
}

function Resolve-PsqlPath {
    $cmd = Get-Command psql -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $roots = @("C:\Program Files\PostgreSQL", "C:\Program Files (x86)\PostgreSQL")
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) {
            continue
        }

        $candidates = Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName "bin\psql.exe" }

        foreach ($candidate in $candidates) {
            if (Test-Path -LiteralPath $candidate) {
                return $candidate
            }
        }
    }

    throw "psql not found. Install PostgreSQL client tools or add psql to PATH."
}

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$resolvedEnvPath = if ([System.IO.Path]::IsPathRooted($EnvFile)) {
    Resolve-Path -LiteralPath $EnvFile
} else {
    Resolve-Path -LiteralPath (Join-Path $projectRoot $EnvFile)
}

$envMap = Get-EnvMap -Path $resolvedEnvPath
if (-not $envMap.ContainsKey("DATABASE_URL") -or [string]::IsNullOrWhiteSpace($envMap["DATABASE_URL"])) {
    throw "DATABASE_URL is missing in env file: $resolvedEnvPath"
}

$databaseUrl = $envMap["DATABASE_URL"]
$psqlDatabaseUrl = $databaseUrl -replace '^postgresql\+psycopg://', 'postgresql://'
$pgAuthValue = Convert-SecureStringToPlainText -Value $DbPassword

# Extract password from DATABASE_URL when available and no explicit password was passed.
if ([string]::IsNullOrWhiteSpace($pgAuthValue)) {
    try {
        $uriSource = $psqlDatabaseUrl
        $uri = [System.Uri]$uriSource
        if (-not [string]::IsNullOrWhiteSpace($uri.UserInfo)) {
            $parts = $uri.UserInfo -split ":", 2
            if ($parts.Count -eq 2 -and -not [string]::IsNullOrWhiteSpace($parts[1])) {
                $pgAuthValue = [System.Uri]::UnescapeDataString($parts[1])
            }
        }
    }
    catch {
        # Keep silent and fall back to psql prompt if URI parsing is not possible.
    }
}

if ([string]::IsNullOrWhiteSpace($pgAuthValue) -and $PromptForPassword) {
    $securePassword = Read-Host -Prompt "Enter DB password" -AsSecureString
    $pgAuthValue = Convert-SecureStringToPlainText -Value $securePassword
}

$scriptName = if ($Rollback) { "20260708_drop_performance_indexes.sql" } else { "20260708_add_performance_indexes.sql" }
$sqlScript = Join-Path $PSScriptRoot $scriptName
if (-not (Test-Path -LiteralPath $sqlScript)) {
    throw "SQL script not found: $sqlScript"
}

$psqlPath = Resolve-PsqlPath
Write-Host "Using env file: $resolvedEnvPath"
Write-Host "Using SQL script: $sqlScript"

if (-not [string]::IsNullOrWhiteSpace($pgAuthValue)) {
    $env:PGPASSWORD = $pgAuthValue
}

try {
    & $psqlPath $psqlDatabaseUrl -f $sqlScript
    if ($LASTEXITCODE -ne 0) {
        throw "Migration command failed with exit code $LASTEXITCODE"
    }
}
finally {
    if (-not [string]::IsNullOrWhiteSpace($pgAuthValue)) {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }
    $pgAuthValue = $null
}

if ($Rollback) {
    Write-Host "Rollback completed successfully."
} else {
    Write-Host "Migration completed successfully."
}
