# NetCatChanger: publish this folder to GitHub (Windows)
# Copyright (C) 2026 Just Edit (Arnaud Augst), GPL-3.0-or-later
#
# Started by push_github.cmd (double-click it). GitHub then becomes EXACTLY
# this folder: files added, changed AND removed. (The GitHub web upload
# deletes nothing: never use it.)
#
#  1. reads the version in version.json and package.json: they must agree;
#  2. clones the GitHub repository into a temporary folder (your own folder
#     is never touched by git);
#  3. refuses if this version is not strictly greater than the one on GitHub;
#  4. copies this folder over the clone, keeping GitHub's version.json as
#     long as the Release vX.Y.Z and its installer are not published:
#     version.json is what tells users an update exists, so it goes LAST;
#  5. lists the changes and waits for "y"; then commits and pushes.
#     Never a forced push.
#
# Once the Release is published with its installer, run it again: it then
# sends version.json alone.
#
# Test runs: PUSH_REPO_URL=<url> uses another repository, PUSH_RELEASE=yes|no
# answers "is the Release published?" without asking GitHub.

# 'Continue', not 'Stop': Windows PowerShell 5.1 turns anything git writes
# on stderr (progress, hints) into a fatal error under 'Stop'. Every git call
# is checked through its exit code instead, and file operations below ask
# for -ErrorAction Stop themselves.
$ErrorActionPreference = 'Continue'

function Say($msg, $color = 'Gray') { Write-Host $msg -ForegroundColor $color }
function Done($code) { Write-Host ''; Read-Host 'Press Enter to close' | Out-Null; exit $code }
function Stop-Push($msg) { Say "[X] $msg" Red; Done 1 }
# core.autocrlf=false: the files go to GitHub byte for byte (build_windows.cmd
# must keep its Windows line endings, the other files their Unix ones).
# (Named GitRun, not Git: PowerShell ignores case, and a function called Git
# would call itself instead of git.exe.)
$GitExe = $null
function GitRun { & $GitExe --no-pager -c core.autocrlf=false -c core.quotepath=off @args }

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$GitExe = (Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
if (-not $GitExe) {
    Stop-Push 'git is not installed: https://git-scm.com/download/win'
}

# -- 1. Versions --
if (-not (Test-Path 'version.json')) { Stop-Push 'version.json is missing.' }
if (-not (Test-Path 'package.json')) { Stop-Push 'package.json is missing.' }
$vj  = Get-Content 'version.json' -Raw | ConvertFrom-Json
$pkg = Get-Content 'package.json' -Raw | ConvertFrom-Json
$Version = "$($vj.version)"
if ($Version -notmatch '^\d+\.\d+\.\d+$') { Stop-Push "version.json: no valid version (found '$Version')." }
if ($Version -ne "$($pkg.version)") { Stop-Push "version.json says $Version but package.json says $($pkg.version)." }

$RepoUrl = $env:PUSH_REPO_URL
if (-not $RepoUrl -and $pkg.repository -and "$($pkg.repository.url)" -match '^https://github\.com/') { $RepoUrl = "$($pkg.repository.url)" }
if (-not $RepoUrl -and "$($vj.url)" -match '^(https://github\.com/[^/]+/[^/]+)') { $RepoUrl = $Matches[1] }
if (-not $RepoUrl) { Stop-Push 'No GitHub address in package.json or version.json.' }
$Slug = ''
if ($RepoUrl -match '^https://github\.com/([^/]+/[^/.]+)') { $Slug = $Matches[1] }

Say ''
Say "NetCatChanger $Version -> $RepoUrl" White
Say ''

# -- 2. Temporary clone --
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ('ncc-push-' + [guid]::NewGuid().ToString('N'))
$Repo = Join-Path $Tmp 'repo'
New-Item -ItemType Directory -Path $Tmp -ErrorAction Stop | Out-Null
try {
    Say 'Reading GitHub...'
    GitRun clone --quiet $RepoUrl $Repo
    if ($LASTEXITCODE -ne 0) { Stop-Push "Could not clone $RepoUrl (connection or GitHub login)." }

    # -- 3. Strictly newer than GitHub --
    $Remote = '0.0.0'
    $rv = Join-Path $Repo 'version.json'
    if (Test-Path $rv) {
        try { $Remote = "$((Get-Content $rv -Raw | ConvertFrom-Json).version)" } catch { $Remote = '0.0.0' }
    }
    if ($Remote -notmatch '^\d+\.\d+\.\d+$') { $Remote = '0.0.0' }
    if ([version]$Version -le [version]$Remote) {
        Stop-Push "GitHub is already at ${Remote}: this folder ($Version) must carry a higher version."
    }

    # -- 4. Copy, version.json last --
    $Released = $env:PUSH_RELEASE
    if (-not $Released) {
        $Released = 'no'
        if ($Slug) {
            foreach ($tag in @("v$Version", $Version)) {
                try {
                    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$Slug/releases/tags/$tag" -UseBasicParsing -TimeoutSec 20
                    if (-not $rel.draft -and @($rel.assets).Count -gt 0) { $Released = 'yes'; break }
                } catch {}
            }
        }
    }

    # Everything in the clone except .git is replaced by this folder.
    try {
        Get-ChildItem -LiteralPath $Repo -Force | Where-Object { $_.Name -ne '.git' } |
            Remove-Item -Recurse -Force -ErrorAction Stop
        $skip = @('.git', 'node_modules', 'dist', '.DS_Store', 'Thumbs.db')
        Get-ChildItem -LiteralPath $Root -Force | Where-Object { $skip -notcontains $_.Name } |
            Copy-Item -Destination $Repo -Recurse -Force -ErrorAction Stop
    } catch { Stop-Push "Could not copy the folder: $($_.Exception.Message)" }

    $HeldBack = $false
    if ($Released -ne 'yes') {
        GitRun -C $Repo cat-file -e HEAD:version.json 2>$null
        if ($LASTEXITCODE -eq 0) {
            GitRun -C $Repo checkout --quiet HEAD -- version.json
            $HeldBack = $true
        }
    }

    # -- 5. Show, confirm, push --
    GitRun -C $Repo add -A
    GitRun -C $Repo diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Say 'Nothing to send: GitHub already matches this folder.' Green
        if ($HeldBack) { Say "version.json ($Version) is waiting for the Release v$Version with its installer." Yellow }
        Done 0
    }

    Say 'Changes that will be sent:' White
    GitRun -C $Repo diff --cached --stat=100 | Select-Object -Last 60 | ForEach-Object { Say $_ }
    GitRun -C $Repo diff --cached --name-status | ForEach-Object {
        if ($_ -match '^D\s+(.+)$') { Say "  removed: $($Matches[1])" Red }
    }
    Say ''
    if ($HeldBack) {
        Say "version.json stays at $Remote on GitHub until the Release v$Version and its installer are published." Yellow
    } else {
        Say "version.json goes to ${Version}: users will be told an update exists."
    }
    Say ''
    $answer = Read-Host 'Send these changes to GitHub? (y/n)'
    if ($answer -ne 'y') { Say 'Nothing sent.'; Done 0 }

    $changed = @(GitRun -C $Repo diff --cached --name-only)
    $msg = if ($changed.Count -eq 1 -and $changed[0] -eq 'version.json') { "NetCatChanger ${Version}: version.json" } else { "NetCatChanger $Version" }
    GitRun -C $Repo commit --quiet -m $msg
    if ($LASTEXITCODE -ne 0) { Stop-Push 'Commit failed (git user.name / user.email set?).' }
    GitRun -C $Repo push --quiet origin HEAD
    if ($LASTEXITCODE -ne 0) { Stop-Push 'Push refused by GitHub. Nothing was forced.' }

    Say ''
    Say '[OK] Sent to GitHub.' Green
    if ($HeldBack) {
        Say "Next: publish the Release v$Version with NetCatChanger-Setup-$Version.exe, then run this script again to send version.json."
    }
    Done 0
}
finally {
    Remove-Item -LiteralPath $Tmp -Recurse -Force -ErrorAction SilentlyContinue
}
