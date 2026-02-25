$env:UV_NATIVE_TLS = "true"
$env:UV_PYTHON_PREFERENCE = "only-system"

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "[init] .env 파일이 없어서 .env.example을 복사했습니다. 값을 확인해주세요."
    } else {
        Write-Host "[init] .env 파일과 .env.example 모두 없습니다. 수동으로 생성해주세요."
        exit 1
    }
}

uv sync
