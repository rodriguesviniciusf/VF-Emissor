param([string]$Repository = $env:GITHUB_REPOSITORY)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Version = (Get-Content version.json -Raw | ConvertFrom-Json).version
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'Versao invalida em version.json' }
if ($Repository -and $Repository -notmatch '^[A-Za-z0-9-]+/[A-Za-z0-9_.-]+$') { throw 'Repositorio invalido' }
$PublicAccess = Join-Path $Root 'deployment\public-access.json'
if (!(Test-Path $PublicAccess)) { throw 'A configuracao publica de acesso deve acompanhar todo instalador.' }
& (Join-Path $Root 'portable\python.exe') -c "import json,sys;sys.path.insert(0,'base');from cloud_access import normalize_config;normalize_config(json.load(open('deployment/public-access.json',encoding='utf-8')))"
if ($LASTEXITCODE) { throw 'Configuracao publica de acesso invalida. Instalador nao sera gerado.' }
Copy-Item $PublicAccess (Join-Path $Root 'commercial-config.json') -Force
if ($Repository) { @{ repository=$Repository; automatic=$true } | ConvertTo-Json | Set-Content release-channel.json -Encoding UTF8 }
# Gera JSON sem BOM para leitura consistente no Python embarcado.
if ($Repository) { [IO.File]::WriteAllText((Join-Path $Root 'release-channel.json'), (@{ repository=$Repository; automatic=$true } | ConvertTo-Json), (New-Object Text.UTF8Encoding($false))) }
$Compiler = Get-Command makensis.exe -ErrorAction SilentlyContinue
if (!$Compiler) { $Nsis = Join-Path ${env:ProgramFiles(x86)} 'NSIS\makensis.exe' } else { $Nsis = $Compiler.Source }
if (!(Test-Path $Nsis)) { throw 'Instale o NSIS (choco install nsis) antes de compilar.' }
$Dist = Join-Path $Root 'dist'
New-Item $Dist -ItemType Directory -Force | Out-Null
$Output = Join-Path $Dist "VF-Emissor-Setup-$Version.exe"
& $Nsis "/DVERSION=$Version" "/DSOURCE=$Root" "/DOUTPUT=$Output" (Join-Path $Root 'installer\vf-emissor.nsi')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao compilar instalador.' }
$File = Get-Item $Output
$Manifest = @{format=1;version=$Version;asset=$File.Name;size=$File.Length;sha256=(Get-FileHash $Output -Algorithm SHA256).Hash.ToLowerInvariant()}
[IO.File]::WriteAllText((Join-Path $Dist 'update-manifest.json'), ($Manifest | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
Write-Output $Output
