<#
.SYNOPSIS
    Git-based application updater and restarter.
.DESCRIPTION
    Waits for the main application to exit, fetches the latest tags, checks out the specified tag,
    cleans the working directory, pulls Git LFS files if available, and restarts the application.
.PARAMETER RepoPath
    Path to the local Git repository.
.PARAMETER GitBin
    Path to the Git executable. Default is 'git'.
.PARAMETER GitLfsBin
    Path to the Git LFS executable
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

    [string]$GitBin = "git",

    [string]$GitLfsBin,

    [Parameter(Mandatory = $true)]
    [string]$TargetTag,

    [Parameter(Mandatory = $true)]
    [string]$MainScript,

    [Parameter(Mandatory = $true)]
    [string]$Python,

    [int]$Timeout = 5,

    # The remaining arguments are captured in $args.
    # We'll extract the ones after '--' as OriginalArgs.
    [Parameter(ValueFromRemainingArguments = $true)]
    [object[]]$RemainingArguments
)

# Function to write log messages with timestamp
function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] $Message"
}

# Function to run a command and check for errors
function Invoke-CommandSafe {
    param(
        [string[]]$Command,
        [string]$WorkingDirectory = $null
    )
    $cmdString = $Command -join " "
    Write-Log "Executing: $cmdString"
    try {
        if ($WorkingDirectory) {
            Push-Location $WorkingDirectory
        }
        $process = Start-Process -FilePath $Command[0] -ArgumentList $Command[1..($Command.Length-1)] -NoNewWindow -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            Write-Log "ERROR: Command returned exit code $($process.ExitCode)"
            throw "Command failed with exit code $($process.ExitCode)"
        }
    }
    catch {
        Write-Log "ERROR: $_"
        throw
    }
    finally {
        if ($WorkingDirectory) {
            Pop-Location
        }
    }
}

# Main script starts here
Write-Log "Updater started."

# 1. Wait for the main process to exit
Write-Log "Waiting $Timeout seconds before starting the update..."
Start-Sleep -Seconds $Timeout

# 2. Validate repository path
if (-not (Test-Path -Path $RepoPath -PathType Container)) {
    Write-Log "ERROR: Repository path '$RepoPath' does not exist."
    exit 1
}
if (-not (Test-Path -Path (Join-Path $RepoPath ".git") -PathType Container)) {
    Write-Log "ERROR: '$RepoPath' is not a Git repository (missing .git directory)."
    exit 1
}

# 3. Ensure Git is available
$gitPath = (Get-Command $GitBin -ErrorAction SilentlyContinue).Source
if (-not $gitPath -and -not (Test-Path $GitBin)) {
    Write-Log "ERROR: Git executable '$GitBin' not found."
    exit 1
}
$GitBin = $gitPath ?? $GitBin

# 4. Fetch all tags from origin
try {
    Invoke-CommandSafe -Command @($GitBin, "fetch", "--tags") -WorkingDirectory $RepoPath
}
catch {
    Write-Log "ERROR: Failed to fetch tags."
    exit 1
}

# 5. Checkout the target tag (force, clean, reset)
try {
    Invoke-CommandSafe -Command @($GitBin, "checkout", "-f", "tags/$TargetTag") -WorkingDirectory $RepoPath
    Invoke-CommandSafe -Command @($GitBin, "clean", "-fd") -WorkingDirectory $RepoPath
    Invoke-CommandSafe -Command @($GitBin, "reset", "--hard") -WorkingDirectory $RepoPath
}
catch {
    Write-Log "ERROR: Failed to checkout tag '$TargetTag'."
    exit 1
}

# 6. Handle Git LFS (if available)
# Check if Git LFS is installed by trying to run 'git lfs version'
$lfsAvailable = $false
try {
    $lfsCheck = Start-Process -FilePath $GitBin -ArgumentList "lfs","version" -NoNewWindow -Wait -PassThru
    $lfsAvailable = ($lfsCheck.ExitCode -eq 0)
}
catch {
    $lfsAvailable = $false
}

if ($lfsAvailable) {
    Write-Log "Git LFS detected, pulling LFS objects..."
    try {
        Invoke-CommandSafe -Command @($GitLfsBin, "pull") -WorkingDirectory $RepoPath
        Invoke-CommandSafe -Command @($GitLfsBin, "prune", "--force") -WorkingDirectory $RepoPath
    }
    catch {
        Write-Log "WARNING: Git LFS pull/prune failed (possibly LFS is not fully configured)."
    }
}
else {
    Write-Log "Git LFS not available, skipping LFS operations."
}

# 7. Extract original arguments for the main application
$originalArgs = @()
if ($RemainingArguments -and $RemainingArguments.Count -gt 0) {
    # Find the first occurrence of '--' separator and take everything after it
    $separatorIndex = [Array]::IndexOf($RemainingArguments, '--')
    if ($separatorIndex -ge 0) {
        $originalArgs = $RemainingArguments[($separatorIndex + 1)..($RemainingArguments.Count - 1)]
    }
    else {
        # No separator, assume all remaining args are for the app
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
