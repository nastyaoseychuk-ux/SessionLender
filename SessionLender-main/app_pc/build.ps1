$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $env:GOOS = 'windows'
    $env:GOARCH = 'amd64'
    $env:GOAMD64 = 'v1'
    $env:CGO_ENABLED = '0'
    New-Item -ItemType Directory -Force -Path '.\build' | Out-Null
    go build -buildvcs=false -mod=vendor -trimpath -ldflags '-s -w -H windowsgui' -o '.\build\SessionLender.exe' '.\cmd\sessionlender'
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    Write-Host 'Ready: build\SessionLender.exe'
} finally {
    Pop-Location
}
