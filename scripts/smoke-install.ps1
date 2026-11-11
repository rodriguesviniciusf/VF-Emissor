$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Version = (Get-Content (Join-Path $Root 'version.json') -Raw | ConvertFrom-Json).version
$Setup = Join-Path $Root "dist\VF-Emissor-Setup-$Version.exe"
$Install = Join-Path $env:LOCALAPPDATA 'Programs\VFEmissor'
$Data = Join-Path $env:LOCALAPPDATA 'VFEmissor\Dados'
New-Item $Data -ItemType Directory -Force | Out-Null
$Marker = Join-Path $Data 'teste-preservacao.txt'
[IO.File]::WriteAllText($Marker,'preservar dados de teste')
1..2 | ForEach-Object {
  $p = Start-Process -FilePath $Setup -ArgumentList '/S' -PassThru -Wait
  if ($p.ExitCode -ne 0) { throw 'O instalador retornou falha.' }
  if ((Get-Content $Marker -Raw) -ne 'preservar dados de teste') { throw 'O instalador alterou a pasta de dados.' }
}
if (!(Test-Path (Join-Path ([Environment]::GetFolderPath('Desktop')) 'VF Emissor.lnk'))) { throw 'Atalho da area de trabalho nao criado.' }
$TestData = Join-Path $env:RUNNER_TEMP 'vf-smoke-data'
$ServerPath = Join-Path $Install 'server.py'
$Arguments = '"{0}" --no-browser --port 8788 --data-dir "{1}"' -f $ServerPath,$TestData
$Process = Start-Process -FilePath (Join-Path $Install 'portable\python.exe') -ArgumentList $Arguments -PassThru
try {
  $Health=$null
  1..20 | ForEach-Object { if (!$Health) { Start-Sleep -Milliseconds 500;try {$Health=Invoke-RestMethod http://127.0.0.1:8788/health} catch {} } }
  if ($Health.version -ne $Version) { throw 'A instalacao nao iniciou a versao esperada.' }
} finally { Stop-Process -Id $Process.Id -ErrorAction SilentlyContinue }
