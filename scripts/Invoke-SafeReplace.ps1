param(
  [Parameter(Mandatory=\True)][string]\,
  [Parameter(Mandatory=\True)][string]\
)
# Write to temp then validate
\ = "\.tmp"
Set-Content -Path \ -Value \ -Encoding UTF8
# Backup current file content
\ = Get-Content -Path \ -Raw -Encoding UTF8
Move-Item -Force -Path \ -Destination \
python scripts/check_app.py
if (\128 -ne 0) {
  Write-Error "Validation failed; restoring original file."
  Set-Content -Path \ -Value \ -Encoding UTF8
  exit 1
}
Write-Host "Validation OK; file updated."
exit 0
