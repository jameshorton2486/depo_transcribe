# ============================================
# PROJECT PATH
# ============================================
$projectPath = "C:\Users\james\PycharmProjects\depo_transcribe"

# ============================================
# FILES WE ACTUALLY NEED
# ============================================
$files = @(
    "spec_engine\emitter.py",
    "spec_engine\document_builder.py",
    "core\docx_formatter.py"
)

# ============================================
# TEMP FOLDER
# ============================================
$tempFolder = Join-Path $env:TEMP "depo_export"

if (Test-Path $tempFolder) {
    Remove-Item $tempFolder -Recurse -Force
}

New-Item -ItemType Directory -Path $tempFolder | Out-Null

# ============================================
# COPY FILES
# ============================================
foreach ($relativePath in $files) {

    $source = Join-Path $projectPath $relativePath

    if (Test-Path $source) {

        $destDir = Join-Path $tempFolder (Split-Path $relativePath -Parent)

        if (-not (Test-Path $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }

        Copy-Item $source -Destination (Join-Path $destDir (Split-Path $relativePath -Leaf))

        Write-Host "Copied: $relativePath"

    } else {

        Write-Host "Missing: $relativePath"

    }
}

# ============================================
# CREATE ZIP IN DOWNLOADS
# ============================================
$downloads = Join-Path ([Environment]::GetFolderPath("UserProfile")) "Downloads"

$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"

$zipPath = Join-Path $downloads "depo_formatting_$timestamp.zip"

Compress-Archive -Path "$tempFolder\*" -DestinationPath $zipPath -Force

# ============================================
# CLEANUP
# ============================================
Remove-Item $tempFolder -Recurse -Force

# ============================================
# OPEN DOWNLOADS
# ============================================
Start-Process $downloads

# ============================================
# DONE
# ============================================
Write-Host ""
Write-Host "======================================"
Write-Host "ZIP CREATED SUCCESSFULLY"
Write-Host "Location: $zipPath"
Write-Host "======================================"
