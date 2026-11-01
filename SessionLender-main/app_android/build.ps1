param([string]$ServerUrl = 'https://sessionlender.vercel.app')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$serverUri = [Uri]$ServerUrl
if (!$serverUri.IsAbsoluteUri -or $serverUri.Scheme -ne 'https' -or $serverUri.AbsolutePath -ne '/' -or $serverUri.Query -or $serverUri.Fragment -or $serverUri.UserInfo) {
    throw 'Provide the HTTPS origin of the deployment, for example https://your-project.vercel.app'
}
$gradleVersion = '8.9'
$gradleExe = Join-Path $PSScriptRoot ".tools\gradle-$gradleVersion\bin\gradle.bat"
if (!(Test-Path $gradleExe)) {
    New-Item -ItemType Directory -Force '.tools' | Out-Null
    $archive = Join-Path $PSScriptRoot '.tools\gradle.zip'
    $url = "https://services.gradle.org/distributions/gradle-$gradleVersion-bin.zip"
    Invoke-WebRequest $url -OutFile $archive
    $expected = (Invoke-RestMethod "$url.sha256").Trim()
    if ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected.ToLowerInvariant()) { throw 'Gradle checksum mismatch' }
    Expand-Archive $archive -DestinationPath '.tools' -Force
}
& $gradleExe --no-daemon "-PserverUrl=$ServerUrl" assembleDebug
if ($LASTEXITCODE -ne 0) { throw 'Android build failed. Check JDK 17 and Android SDK 35.' }
Write-Host 'APK: app\build\outputs\apk\debug\app-debug.apk'
