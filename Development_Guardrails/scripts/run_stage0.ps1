# Runs verified, real Stage 0 scripts on Windows. Does not download anything.
# Example from complete package root:
# powershell -ExecutionPolicy Bypass -File .\Development_Guardrails\scripts\run_stage0.ps1 -BlenderPath 'C:\Program Files\Blender Foundation\Blender 5.3\blender.exe'
param(
  [Parameter(Mandatory=$true)][string]$BlenderPath,
  [string[]]$ScanRoot = @(),
  [string]$OutputDir = 'evidence'
)
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$kitRoot = (Resolve-Path (Join-Path $scriptDir '..')).Path
$packageRoot = (Resolve-Path (Join-Path $kitRoot '..')).Path
$starter = Join-Path $packageRoot 'Stage0_Starter'
if (-not (Test-Path (Join-Path $starter 'tools\audit_local.py'))) { throw 'Extract the combined package: Stage0_Starter folder missing.' }
if (-not (Test-Path -PathType Leaf $BlenderPath)) { throw "Blender executable missing: $BlenderPath" }
if (-not [System.IO.Path]::IsPathRooted($OutputDir)) { $OutputDir = Join-Path $packageRoot $OutputDir }
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$audit = Join-Path $OutputDir 'preflight.json'
$smoke = Join-Path $OutputDir 'mpfb_smoke'
$auditArgs = @('-3', (Join-Path $starter 'tools\audit_local.py'), '--blender', $BlenderPath, '--output', $audit)
foreach ($root in $ScanRoot) { $auditArgs += @('--scan-root', $root) }
& py @auditArgs
if ($LASTEXITCODE -ne 0) { throw "Environment audit failed: $LASTEXITCODE" }
& py -3 (Join-Path $starter 'tools\run_mpfb_smoke.py') --blender $BlenderPath --outdir $smoke
$smokeExit = $LASTEXITCODE
# Collect evidence even when real MPFB smoke fails; this intentionally yields blocked statuses.
& py -3 (Join-Path $kitRoot 'tools\collect_p0.py') --evidence-dir $OutputDir --audit $audit --smoke-dir $smoke
$collectExit = $LASTEXITCODE
& py -3 (Join-Path $kitRoot 'tools\verify_gate.py') --gate P0_SPIKE --evidence-dir $OutputDir
$gateExit = $LASTEXITCODE
Write-Host "Smoke result: $smokeExit | Collection: $collectExit | Gate: $gateExit"
Write-Host 'Reports and file paths may reveal local information; inspect before sharing.'
if ($smokeExit -ne 0 -or $collectExit -ne 0 -or $gateExit -ne 0) { exit 1 }
