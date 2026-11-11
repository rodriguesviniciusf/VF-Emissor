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
  $Cities = Invoke-RestMethod http://127.0.0.1:8788/municipios.json
  if ($Cities.municipalities.Count -lt 5571) { throw 'Catalogo offline incompleto no instalador.' }
  $Assistance = Invoke-WebRequest http://127.0.0.1:8788/assistance-ui.js
  if ($Assistance.Content -notmatch 'function editorPayload') { throw 'Interface de recuperacao ausente na instalacao.' }
  $Simple = Invoke-WebRequest http://127.0.0.1:8788/simple-ui.js
  if ($Simple.Content -notmatch 'function renderSimple') { throw 'Modo Simples ausente na instalacao.' }
  $SimpleStyle = Invoke-WebRequest http://127.0.0.1:8788/simple.css
  if ($SimpleStyle.StatusCode -ne 200) { throw 'Visual do Modo Simples ausente.' }
  $Ncm = Invoke-WebRequest http://127.0.0.1:8788/ncm-ui.js
  if ($Ncm.Content -notmatch 'function attachNcmFields') { throw 'Consulta NCM ausente na instalacao.' }
  $NcmStyle = Invoke-WebRequest http://127.0.0.1:8788/ncm.css
  if ($NcmStyle.StatusCode -ne 200) { throw 'Visual NCM ausente.' }
  & (Join-Path $Install 'portable\python.exe') -c "import sys;sys.path.insert(0,r'$Install\base');import ncm_catalog as n;c=n.local(r'$TestData');assert len(c.leaves)>10000;assert c.lookup('03061710')['description']=='Inteiros';print('NCM offline no instalador OK')"
  if ($LASTEXITCODE) { throw 'Catalogo NCM offline ausente ou incompleto no instalador.' }
} finally { Stop-Process -Id $Process.Id -ErrorAction SilentlyContinue }
