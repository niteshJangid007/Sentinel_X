# Builds SentinelX.apk from the sources in this folder using the Android SDK.
# Usage: powershell -ExecutionPolicy Bypass -File build_apk.ps1

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$base = Join-Path $env:LOCALAPPDATA 'apkbuild'
$sdk = Join-Path $base 'sdk'
$jdk = (Get-ChildItem (Join-Path $base 'jdk') -Directory | Select-Object -First 1).FullName
$bt = Join-Path $sdk 'build-tools\35.0.0'
$androidJar = Join-Path $sdk 'platforms\android-34\android.jar'

$env:JAVA_HOME = $jdk
$env:PATH = "$jdk\bin;$bt;$env:PATH"

$out = Join-Path $root 'build'
Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $out, (Join-Path $out 'gen'), (Join-Path $out 'classes'), (Join-Path $out 'dex') | Out-Null

Write-Host '[1/6] compiling resources'
& (Join-Path $bt 'aapt2.exe') compile --dir (Join-Path $root 'res') -o (Join-Path $out 'res.zip')
if ($LASTEXITCODE -ne 0) { throw 'aapt2 compile failed' }

Write-Host '[2/6] linking resources and manifest'
& (Join-Path $bt 'aapt2.exe') link -o (Join-Path $out 'base.apk') `
    -I $androidJar `
    --manifest (Join-Path $root 'AndroidManifest.xml') `
    (Join-Path $out 'res.zip') `
    --java (Join-Path $out 'gen') `
    --min-sdk-version 24 --target-sdk-version 34 `
    --version-code 1 --version-name 1.0
if ($LASTEXITCODE -ne 0) { throw 'aapt2 link failed' }

Write-Host '[3/6] compiling java'
$sources = @()
$sources += (Get-ChildItem (Join-Path $root 'src') -Recurse -Filter '*.java').FullName
$sources += (Get-ChildItem (Join-Path $out 'gen') -Recurse -Filter '*.java').FullName
& (Join-Path $jdk 'bin\javac.exe') -source 17 -target 17 -encoding UTF-8 `
    -classpath $androidJar -d (Join-Path $out 'classes') $sources
if ($LASTEXITCODE -ne 0) { throw 'javac failed' }

Write-Host '[4/6] dexing'
& (Join-Path $jdk 'bin\jar.exe') cf (Join-Path $out 'classes.jar') -C (Join-Path $out 'classes') .
& (Join-Path $bt 'd8.bat') --lib $androidJar --min-api 24 --output (Join-Path $out 'dex') (Join-Path $out 'classes.jar')
if ($LASTEXITCODE -ne 0) { throw 'd8 failed' }

Write-Host '[5/6] packaging'
Copy-Item (Join-Path $out 'base.apk') (Join-Path $out 'unsigned.apk') -Force
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open((Join-Path $out 'unsigned.apk'), 'Update')
$dex = Join-Path $out 'dex\classes.dex'
if (-not (Test-Path $dex)) { throw 'classes.dex missing' }
[System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $dex, 'classes.dex', 'Optimal') | Out-Null
$zip.Dispose()

& (Join-Path $bt 'zipalign.exe') -f 4 (Join-Path $out 'unsigned.apk') (Join-Path $out 'aligned.apk')
if ($LASTEXITCODE -ne 0) { throw 'zipalign failed' }

Write-Host '[6/6] signing'
$keystore = Join-Path $base 'sentinelx-debug.keystore'
if (-not (Test-Path $keystore)) {
    & (Join-Path $jdk 'bin\keytool.exe') -genkeypair -v `
        -keystore $keystore -alias sentinelx -storepass sentinelx -keypass sentinelx `
        -keyalg RSA -keysize 2048 -validity 10000 -dname 'CN=SentinelX, O=SentinelX, C=IN'
    if ($LASTEXITCODE -ne 0) { throw 'keytool failed' }
}

$apk = Join-Path $root 'SentinelX.apk'
& (Join-Path $bt 'apksigner.bat') sign --ks $keystore --ks-pass pass:sentinelx --key-pass pass:sentinelx `
    --out $apk (Join-Path $out 'aligned.apk')
if ($LASTEXITCODE -ne 0) { throw 'apksigner failed' }

& (Join-Path $bt 'apksigner.bat') verify $apk
Write-Host ''
Write-Host ('APK ready: ' + $apk)
Get-Item $apk | Select-Object Name, Length
