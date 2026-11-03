param([switch]$AcceptAndroidLicenses)
$ErrorActionPreference = 'Stop'
$toolRoot = Join-Path (Split-Path $PSScriptRoot -Parent) '.qa/android-tools'
New-Item -ItemType Directory -Path $toolRoot -Force | Out-Null
function Download-Verified($Uri, $Destination, $Hash, $Algorithm = 'SHA256') {
    if (!(Test-Path -LiteralPath $Destination)) { Invoke-WebRequest -Uri $Uri -OutFile $Destination -UseBasicParsing }
    if ((Get-FileHash -LiteralPath $Destination -Algorithm $Algorithm).Hash.ToLower() -ne $Hash.ToLower()) { throw "Download checksum mismatch: $Destination" }
}
$jdkFolder = Get-ChildItem -LiteralPath $toolRoot -Directory -Filter 'jdk-*' | Select-Object -First 1
if (!$jdkFolder) {
    $asset = Invoke-RestMethod 'https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=windows&vendor=eclipse'
    $package = $asset[0].binary.package
    Download-Verified $package.link (Join-Path $toolRoot 'jdk.zip') $package.checksum
    Expand-Archive -LiteralPath (Join-Path $toolRoot 'jdk.zip') -DestinationPath $toolRoot
    $jdkFolder = Get-ChildItem -LiteralPath $toolRoot -Directory -Filter 'jdk-*' | Select-Object -First 1
}
$env:JAVA_HOME = $jdkFolder.FullName
$env:ANDROID_HOME = Join-Path $toolRoot 'sdk'
$env:ANDROID_USER_HOME = Join-Path $toolRoot 'android-user'
$env:GRADLE_USER_HOME = Join-Path $toolRoot 'gradle-cache'
$env:PATH = "$env:JAVA_HOME/bin;$env:PATH"
$manager = Join-Path $env:ANDROID_HOME 'cmdline-tools/latest/bin/sdkmanager.bat'
if (!(Test-Path -LiteralPath (Join-Path $env:ANDROID_HOME 'cmdline-tools/latest/.installed'))) {
    [xml]$repository = (Invoke-WebRequest 'https://dl.google.com/android/repository/repository2-3.xml' -UseBasicParsing).Content
    $archive = $repository.SelectNodes("//*[local-name()='remotePackage' and @path='cmdline-tools;latest']/*[local-name()='archives']/*[local-name()='archive']") | Where-Object { $_.'host-os' -eq 'windows' }
    $checksum = $archive.complete.checksum.InnerText
    $algorithm = if ($checksum.Length -eq 40) {'SHA1'} else {'SHA256'}
    Download-Verified ('https://dl.google.com/android/repository/' + $archive.complete.url) (Join-Path $toolRoot 'sdk-tools.zip') $checksum $algorithm
    # JDK ZIP extraction supports the long Maven paths that Windows PowerShell's
    # Expand-Archive cannot handle. Extract directly into the final SDK tree.
    $cmdRoot = Join-Path $env:ANDROID_HOME 'cmdline-tools'
    New-Item -ItemType Directory -Path $cmdRoot -Force | Out-Null
    Push-Location -LiteralPath $cmdRoot
    try {
        & (Join-Path $env:JAVA_HOME 'bin/jar.exe') --extract --file (Join-Path $toolRoot 'sdk-tools.zip')
        if ($LASTEXITCODE -ne 0) { throw 'Android command line tools extraction failed.' }
    } finally { Pop-Location }
    $extracted = [IO.Path]::GetFullPath((Join-Path $cmdRoot 'cmdline-tools'))
    $latest = [IO.Path]::GetFullPath((Join-Path $cmdRoot 'latest'))
    if (!$extracted.StartsWith($toolRoot) -or !$latest.StartsWith($toolRoot)) { throw 'Unexpected SDK target.' }
    if (Test-Path -LiteralPath $latest) { [IO.Directory]::Move($latest, (Join-Path $cmdRoot ('previous-' + [guid]::NewGuid().ToString('N')))) }
    [IO.Directory]::Move($extracted, $latest)
    New-Item -ItemType File -Path (Join-Path $latest '.installed') | Out-Null
}
if (!(Test-Path -LiteralPath (Join-Path $toolRoot 'gradle-8.13/bin/gradle.bat'))) {
    $hashResponse = (Invoke-WebRequest 'https://services.gradle.org/distributions/gradle-8.13-bin.zip.sha256' -UseBasicParsing).Content
    $gradleHash = if ($hashResponse -is [byte[]]) { [Text.Encoding]::UTF8.GetString($hashResponse).Trim() } else { $hashResponse.Trim() }
    Download-Verified 'https://services.gradle.org/distributions/gradle-8.13-bin.zip' (Join-Path $toolRoot 'gradle.zip') $gradleHash
    Expand-Archive -LiteralPath (Join-Path $toolRoot 'gradle.zip') -DestinationPath $toolRoot
}
if ($AcceptAndroidLicenses) {
    @('y','y','y','y','y','y','y','y','y','y') | & $manager "--sdk_root=$env:ANDROID_HOME" --licenses
    if ($LASTEXITCODE -ne 0) { throw 'Android SDK license acceptance failed.' }
    & $manager "--sdk_root=$env:ANDROID_HOME" 'platform-tools' 'platforms;android-36' 'build-tools;35.0.0'
    if ($LASTEXITCODE -ne 0) { throw 'Android SDK installation failed.' }
} else {
    Write-Output 'Build tools downloaded. Android platform installation awaits SDK license acceptance.'
}
Write-Output "Android build tools: $toolRoot"
