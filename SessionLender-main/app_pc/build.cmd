@echo off
setlocal
cd /d "%~dp0"
set GOOS=windows
set GOARCH=amd64
set GOAMD64=v1
set CGO_ENABLED=0
if not exist build mkdir build
go build -buildvcs=false -mod=vendor -trimpath -ldflags "-s -w -H windowsgui" -o build\SessionLender.exe ./cmd/sessionlender
if errorlevel 1 (
 echo Build failed.
 pause
 exit /b 1
)
echo Ready: build\SessionLender.exe
pause
