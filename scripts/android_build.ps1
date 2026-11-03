param([string[]]$Tasks = @('assembleDebug','testDebugUnitTest','lintDebug'))
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$toolRoot = Join-Path $projectRoot '.qa/android-tools'
$env:JAVA_HOME = (Get-ChildItem -LiteralPath $toolRoot -Directory -Filter 'jdk-*' | Select-Object -First 1).FullName
$env:ANDROID_HOME = Join-Path $toolRoot 'sdk'
$env:ANDROID_USER_HOME = Join-Path $toolRoot 'android-user'
$env:GRADLE_USER_HOME = Join-Path $toolRoot 'gradle-cache'
$env:PATH = "$env:JAVA_HOME/bin;$env:PATH"
$sdkProperty = 'sdk.dir=' + $env:ANDROID_HOME.Replace('\','/')
Set-Content -LiteralPath (Join-Path $projectRoot 'android/local.properties') -Value $sdkProperty -Encoding ASCII
& (Join-Path $toolRoot 'gradle-8.13/bin/gradle.bat') -p (Join-Path $projectRoot 'android') --console=plain @Tasks
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
