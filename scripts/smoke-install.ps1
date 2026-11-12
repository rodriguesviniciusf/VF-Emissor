param([string]$Repository = $env:GITHUB_REPOSITORY)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Version = (Get-Content (Join-Path $Root 'version.json') -Raw | ConvertFrom-Json).version
$Setup = Join-Path $Root "dist\VF-Emissor-Setup-$Version.exe"
$Install = Join-Path $env:LOCALAPPDATA 'Programs\VFEmissor'
$Data = Join-Path $env:LOCALAPPDATA 'VFEmissor\Dados'
$TestData = Join-Path $env:RUNNER_TEMP 'vf-smoke-data'
if (!$Repository) { $Repository = (Get-Content (Join-Path $Root 'release-channel.json') -Raw | ConvertFrom-Json).repository }
if ($Repository -ne 'rodriguesviniciusf/VF-Emissor') { throw 'O teste de atualizacao exige o repositorio do VF Emissor.' }
# Reproduz a instalacao 0.18.0 que ainda aceitava o login local por CNPJ.
$Baseline = Join-Path $env:RUNNER_TEMP 'vf-upgrade-baseline'
New-Item $Baseline -ItemType Directory -Force | Out-Null
$BaselineUrl = "https://github.com/$Repository/releases/download/v0.18.0/"
Invoke-WebRequest ($BaselineUrl + 'update-manifest.json') -OutFile (Join-Path $Baseline 'manifest.json')
$OldManifest = Get-Content (Join-Path $Baseline 'manifest.json') -Raw | ConvertFrom-Json
if ($OldManifest.version -ne '0.18.0' -or $OldManifest.asset -ne 'VF-Emissor-Setup-0.18.0.exe' -or $OldManifest.sha256 -notmatch '^[a-f0-9]{64}$') { throw 'Manifesto da versao anterior invalido.' }
$OldSetup = Join-Path $Baseline $OldManifest.asset
Invoke-WebRequest ($BaselineUrl + $OldManifest.asset) -OutFile $OldSetup
if ((Get-FileHash $OldSetup -Algorithm SHA256).Hash.ToLowerInvariant() -ne $OldManifest.sha256) { throw 'Instalador anterior falhou na verificacao de integridade.' }
$p = Start-Process -FilePath $OldSetup -ArgumentList '/S' -PassThru -Wait
if ($p.ExitCode -ne 0) { throw 'A instalacao da versao anterior falhou.' }
$Seed = @'
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from core import Store
folder=Path(sys.argv[2]);folder.mkdir(parents=True,exist_ok=True)
store=Store(folder/'vf.sqlite3')
cid=store.save('company',dict(CNPJCPF='11222333000181',xNome='Empresa anterior preservada',UF='AL',CRT='1',environment='2'))
product=store.save('product',dict(cProd='QA-ANTERIOR',xProd='Produto anterior preservado'),cid)
store.db.close()
(folder/'fixture.json').write_text(json.dumps(dict(cid=cid,product=product)))
for name,content in [('xml/preservar.xml',b'<xml>preservar XML anterior</xml>'),('certificados-protegidos/fixture.bin',b'fixture de preservacao; nao e certificado real')]:
 p=folder/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(content)
'@
& (Join-Path $Install 'portable\python.exe') -c $Seed (Join-Path $Install 'base') $TestData
if ($LASTEXITCODE) { throw 'Falha ao preparar dados de teste da versao anterior.' }
$OldArguments = '"{0}" --no-browser --port 8789 --data-dir "{1}"' -f (Join-Path $Install 'server.py'),$TestData
$OldProcess = Start-Process -FilePath (Join-Path $Install 'portable\python.exe') -ArgumentList $OldArguments -PassThru
try {
  $OldHealth=$null
  1..20 | ForEach-Object { if (!$OldHealth) { Start-Sleep -Milliseconds 500;try {$OldHealth=Invoke-RestMethod http://127.0.0.1:8789/health} catch {} } }
  if ($OldHealth.version -ne '0.18.0') { throw 'O teste nao iniciou a versao anterior real.' }
  Invoke-WebRequest http://127.0.0.1:8789/ -SessionVariable PreviousWeb | Out-Null
  Invoke-RestMethod http://127.0.0.1:8789/api/login -Method Post -ContentType 'application/json' -Body '{"cnpj":"11222333000181","password":""}' -WebSession $PreviousWeb | Out-Null
  $OldState = Invoke-RestMethod http://127.0.0.1:8789/api/state -WebSession $PreviousWeb
  if (!$OldState.authenticated) { throw 'O cenario anterior precisava permitir o login local.' }
} finally { Stop-Process -Id $OldProcess.Id -ErrorAction SilentlyContinue }
New-Item $Data -ItemType Directory -Force | Out-Null
$Marker = Join-Path $Data 'teste-preservacao.txt'
[IO.File]::WriteAllText($Marker,'preservar dados de teste')
1..2 | ForEach-Object {
  $p = Start-Process -FilePath $Setup -ArgumentList '/S' -PassThru -Wait
  if ($p.ExitCode -ne 0) { throw 'O instalador retornou falha.' }
  if ((Get-Content $Marker -Raw) -ne 'preservar dados de teste') { throw 'O instalador alterou a pasta de dados.' }
}
if (!(Test-Path (Join-Path ([Environment]::GetFolderPath('Desktop')) 'VF Emissor.lnk'))) { throw 'Atalho da area de trabalho nao criado.' }
$ServerPath = Join-Path $Install 'server.py'
$Arguments = '"{0}" --no-browser --port 8788 --data-dir "{1}"' -f $ServerPath,$TestData
$Process = Start-Process -FilePath (Join-Path $Install 'portable\python.exe') -ArgumentList $Arguments -PassThru
try {
  $Health=$null
  1..20 | ForEach-Object { if (!$Health) { Start-Sleep -Milliseconds 500;try {$Health=Invoke-RestMethod http://127.0.0.1:8788/health} catch {} } }
  if ($Health.version -ne $Version) { throw 'A instalacao nao iniciou a versao esperada.' }
  if (!(Test-Path (Join-Path $Install 'commercial-config.json'))) { throw 'O instalador nao ativou a configuracao comercial.' }
  Invoke-WebRequest http://127.0.0.1:8788/ -WebSession $PreviousWeb | Out-Null
  $NewState = Invoke-RestMethod http://127.0.0.1:8788/api/state -WebSession $PreviousWeb
  if (!$NewState.access.enabled -or $NewState.authenticated -or $NewState.companies.Count -ne 0) { throw 'Uma sessao ou empresa anterior ignorou o novo acesso.' }
  try {
    Invoke-RestMethod http://127.0.0.1:8788/api/login -Method Post -ContentType 'application/json' -Body '{"cnpj":"11222333000181","password":""}' -WebSession $PreviousWeb | Out-Null
    throw 'O login anterior por CNPJ continuou permitindo acesso.'
  } catch { if ([int]$_.Exception.Response.StatusCode -ne 400) { throw 'A nova versao nao bloqueou corretamente o login anterior.' } }
  if (!(Test-Path (Join-Path $TestData 'acesso\public-config.json'))) { throw 'A configuracao de acesso nao foi persistida nos dados.' }
  $Preserved = @'
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from core import Store
folder=Path(sys.argv[2]);fixture=json.loads((folder/'fixture.json').read_text());db=Store(folder/'vf.sqlite3')
assert db.get('company','',fixture['cid'])['xNome']=='Empresa anterior preservada'
assert db.get('product',fixture['cid'],fixture['product'])['xProd']=='Produto anterior preservado'
db.db.close()
assert (folder/'xml/preservar.xml').read_bytes()==b'<xml>preservar XML anterior</xml>'
assert (folder/'certificados-protegidos/fixture.bin').read_bytes()==b'fixture de preservacao; nao e certificado real'
print('Upgrade real 0.18: acesso antigo bloqueado; empresa, produto, XML e cofre preservados')
'@
  & (Join-Path $Install 'portable\python.exe') -c $Preserved (Join-Path $Install 'base') $TestData
  if ($LASTEXITCODE) { throw 'Os dados anteriores nao foram preservados na atualizacao.' }
  $Cities = Invoke-RestMethod http://127.0.0.1:8788/municipios.json
  if ($Cities.municipalities.Count -lt 5571) { throw 'Catalogo offline incompleto no instalador.' }
  $Assistance = Invoke-WebRequest http://127.0.0.1:8788/assistance-ui.js
  if ($Assistance.Content -notmatch 'function editorPayload') { throw 'Interface de recuperacao ausente na instalacao.' }
  $Simple = Invoke-WebRequest http://127.0.0.1:8788/simple-ui.js
  if ($Simple.Content -notmatch 'function renderSimple') { throw 'Modo Simples ausente na instalacao.' }
  $SimpleStyle = Invoke-WebRequest http://127.0.0.1:8788/simple.css
  if ($SimpleStyle.StatusCode -ne 200) { throw 'Visual do Modo Simples ausente.' }
  $Interstate = Invoke-WebRequest http://127.0.0.1:8788/interstate-ui.js
  if ($Interstate.Content -notmatch 'function decorateInterstate') { throw 'Assistente interestadual ausente.' }
  $InterstateStyle = Invoke-WebRequest http://127.0.0.1:8788/interstate.css
  if ($InterstateStyle.StatusCode -ne 200) { throw 'Visual interestadual ausente.' }
  $Access = Invoke-WebRequest http://127.0.0.1:8788/access-ui.js
  if ($Access.Content -notmatch 'function accessHome') { throw 'Interface de acesso ausente.' }
  $Portal = Invoke-WebRequest http://127.0.0.1:8788/gestao/
  if ($Portal.Content -notmatch 'id="app"') { throw 'Painel de acesso ausente.' }
  $PortalAuth = Invoke-WebRequest http://127.0.0.1:8788/gestao/auth.js
  if ($PortalAuth.Content -notmatch 'createRecovery') { throw 'Recuperacao de acesso ausente no painel.' }
  $Ncm = Invoke-WebRequest http://127.0.0.1:8788/ncm-ui.js
  if ($Ncm.Content -notmatch 'function attachNcmFields') { throw 'Consulta NCM ausente na instalacao.' }
  $NcmStyle = Invoke-WebRequest http://127.0.0.1:8788/ncm.css
  if ($NcmStyle.StatusCode -ne 200) { throw 'Visual NCM ausente.' }
  & (Join-Path $Install 'portable\python.exe') -c "import sys;sys.path.insert(0,r'$Install\base');import ncm_catalog as n;c=n.local(r'$TestData');assert len(c.leaves)>10000;assert c.lookup('03061710')['description']=='Inteiros';print('NCM offline no instalador OK')"
  if ($LASTEXITCODE) { throw 'Catalogo NCM offline ausente ou incompleto no instalador.' }
} finally { Stop-Process -Id $Process.Id -ErrorAction SilentlyContinue }
