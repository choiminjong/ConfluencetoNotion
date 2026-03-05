$env:UV_NATIVE_TLS = "true"

# 1) uv 미설치 시 자동 설치
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[init] uv가 설치되어 있지 않습니다. 설치를 시작합니다..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
Write-Host "[init] uv version: $(uv --version)"

# 2) .env 파일 복사
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "[init] .env.example -> .env 복사 완료. 값을 수정해주세요."
    } else {
        Write-Host "[init] .env.example이 없습니다. 수동으로 .env를 생성해주세요."
        exit 1
    }
}

# 3) uv sync (.python-version 기준 Python 자동 다운로드 + 가상환경 + 패키지 설치)
uv sync

# 4) 완료 안내
Write-Host ""
Write-Host "====================================="
Write-Host "  설치 완료!"
Write-Host "====================================="
Write-Host ""
Write-Host "다음 단계:"
Write-Host "  1. .env 파일을 열어 환경변수를 설정하세요"
Write-Host "  2. VS Code: Ctrl+Shift+P -> 'Python: Select Interpreter'"
Write-Host "     -> .venv\Scripts\python.exe 선택"
Write-Host "  3. python -m pipeline.run 으로 실행"
