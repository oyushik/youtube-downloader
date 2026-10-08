param([string]$Python = "python", [switch]$SkipPrepare)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Python 가상환경을 만들지 못했습니다. -Python 옵션에 Python 실행 파일 경로를 지정하세요." }
}
$buildPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $buildPython -m pip install --disable-pip-version-check -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "빌드 의존성 설치 실패" }
if (-not $SkipPrepare) {
    & $buildPython prepare_runtime.py
    if ($LASTEXITCODE -ne 0) { throw "내장 실행 환경 준비 실패" }
}
& $buildPython -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "테스트 실패" }
& $buildPython -m PyInstaller --noconfirm YouTubeDownloader.spec
if ($LASTEXITCODE -ne 0) { throw "EXE 빌드 실패" }
Write-Output "완료: $PSScriptRoot\dist\YouTubeDownloader.exe"
