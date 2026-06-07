<#
.SYNOPSIS
    Git-based application updater and restarter.
.DESCRIPTION
    Waits for the main application to exit, fetches the latest tags, checks out the specified tag,
    cleans the working directory, pulls Git LFS files if available, and restarts the application.
    All log messages are written to both the console and a file in the repository's logs folder.
    The script stops immediately on the first error.
.PARAMETER RepoPath
    Path to the local Git repository.
.PARAMETER GitBin
    Path to the Git executable. Default is 'git'.
.PARAMETER GitLfsBin
    Path to the Git LFS executable (optional).
.PARAMETER TargetTag
    Target tag to checkout (e.g., v1.2.3).
.PARAMETER MainScript
    Path to the main application script that will be restarted.
.PARAMETER Python
    Path to the Python interpreter.
.PARAMETER Timeout
    Delay in seconds before starting the update. Default is 5.
.PARAMETER OriginalArgs
    Additional arguments passed after '--' that will be forwarded to the main script.
.EXAMPLE
    updater.ps1 -RepoPath "C:\MyApp" -TargetTag "v1.3.0" -MainScript "C:\MyApp\main.py" -Python "python" -Timeout 5 -- --debug
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$RepoPath,

    [Parameter(Mandatory = $true)]
    [string]$TargetTag,

    [Parameter(Mandatory = $true)]
    [string]$MainScript,

    [Parameter(Mandatory = $true)]
    [string]$Python,

    [string]$GitBin = "git",

    [string]$GitLfsBin,

    [int]$Timeout = 5,

    [Parameter(ValueFromRemainingArguments = $true)]
    [object[]]$RemainingArguments
)
# Stop script on any error
$ErrorActionPreference = "Stop"

# ---------- Logging setup ----------
$LogDir = Join-Path $RepoPath "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$LogFile = Join-Path $LogDir "updates.log"

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $fullMessage = "[$timestamp] $Message"
    Write-Host $fullMessage
    $fullMessage | Out-File -FilePath $LogFile -Append -Encoding utf8
}

# ---------- Safe command runner ----------
function Invoke-CommandSafe {
    param(
        [string[]]$Command,
        [string]$WorkingDirectory = $null
    )
    $cmdString = $Command -join " "
    Write-Log "Executing: $cmdString"

    $prevCwd = Get-Location
    try {
        if ($WorkingDirectory) {
            Set-Location $WorkingDirectory
        }
        $proc = Start-Process -FilePath $Command[0] -ArgumentList $Command[1..($Command.Length-1)] `
                              -NoNewWindow -Wait -PassThru
        if ($proc.ExitCode -ne 0) {
            throw "Command failed with exit code $($proc.ExitCode)"
        }
    }
    finally {
        if ($WorkingDirectory) {
            Set-Location $prevCwd
        }
    }
}

# ---------- Main script ----------
Write-Log "Updater started."
Write-Log "Log file: $LogFile"

# 1. Wait for the main process to exit
Write-Log "Waiting $Timeout seconds before starting the update..."
Start-Sleep -Seconds $Timeout

# 2. Validate repository path
if (-not (Test-Path -Path $RepoPath -PathType Container)) {
    throw "Repository path '$RepoPath' does not exist."
}
if (-not (Test-Path -Path (Join-Path $RepoPath ".git") -PathType Container)) {
    throw "'$RepoPath' is not a Git repository (missing .git directory)."
}

# 3. Resolve Git executable
$resolvedGit = Get-Command $GitBin -ErrorAction SilentlyContinue
if ($resolvedGit) {
    $GitBin = $resolvedGit.Source
}
elseif (-not (Test-Path $GitBin)) {
    throw "Git executable not found: '$GitBin'"
}
Write-Log "Using Git: $GitBin"

# 4. Fetch all tags from origin
Invoke-CommandSafe -Command @($GitBin, "fetch", "--tags") -WorkingDirectory $RepoPath

# 5. Checkout the target tag (force, clean, reset)
Invoke-CommandSafe -Command @($GitBin, "checkout", "-f", "tags/$TargetTag") -WorkingDirectory $RepoPath
Invoke-CommandSafe -Command @($GitBin, "clean", "-fd") -WorkingDirectory $RepoPath
Invoke-CommandSafe -Command @($GitBin, "reset", "--hard") -WorkingDirectory $RepoPath

# 6. Handle Git LFS (Исправленная логика)
$lfsAvailable = $false
try {
    $lfsCheck = Start-Process -FilePath $GitBin -ArgumentList "lfs","version" -NoNewWindow -Wait -PassThru
    $lfsAvailable = ($lfsCheck.ExitCode -eq 0)
} catch { }

if ($lfsAvailable) {
    Write-Log "Git LFS detected, pulling LFS objects..."
    Invoke-CommandSafe -Command @($GitBin, "lfs", "pull") -WorkingDirectory $RepoPath
    Invoke-CommandSafe -Command @($GitBin, "lfs", "prune", "--force") -WorkingDirectory $RepoPath
} elseif (-not [string]::IsNullOrEmpty($GitLfsBin) -and (Test-Path $GitLfsBin)) {
    Write-Log "Using explicit Git LFS binary, pulling LFS objects..."
    Invoke-CommandSafe -Command @($GitLfsBin, "pull") -WorkingDirectory $RepoPath
    Invoke-CommandSafe -Command @($GitLfsBin, "prune", "--force") -WorkingDirectory $RepoPath
} else {
    Write-Log "Git LFS not available, skipping LFS operations."
}

# 7. Extract original arguments for the main application
$originalArgs = @()
if ($RemainingArguments -and $RemainingArguments.Count -gt 0) {
    $separatorIndex = [Array]::IndexOf($RemainingArguments, '--')
    if ($separatorIndex -ge 0) {
        $originalArgs = $RemainingArguments[($separatorIndex + 1)..($RemainingArguments.Count - 1)]
    } else {
        $originalArgs = $RemainingArguments
    }
}

# 8. Restart the main application
$cmdArgs = @($Python, $MainScript) + $originalArgs
$cmdString = $cmdArgs -join " "
Write-Log "Restarting application: $cmdString"
Start-Process -FilePath $Python -ArgumentList ($cmdArgs[1..($cmdArgs.Count-1)]) -NoNewWindow

Write-Log "Updater finished successfully."
exit 0
