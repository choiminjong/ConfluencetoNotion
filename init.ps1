$env:UV_NATIVE_TLS = "true"
$env:UV_PYTHON_PREFERENCE = "only-system"

if (-not (Test-Path ".env")) {
    if (Test-Path ".env copy.example") {
        Copy-Item ".env copy.example" ".env"
        Write-Host "[init] .env 파일이 없어서 .env copy.example을 복사했습니다. 값을 확인해주세요."
    } else {
        Write-Host "[init] .env 파일과 .env copy.example 모두 없습니다. 수동으로 생성해주세요."
        exit 1
    }
}

uv sync
