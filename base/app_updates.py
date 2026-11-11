"""Releases públicas do GitHub. Instalador fixo, HTTPS e conferência SHA-256."""
import hashlib,json,os,re,subprocess,sys,tempfile,time,urllib.error,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path

MAX_INSTALLER=250*1024*1024

def version_number(value):
    match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-beta)?',str(value))
    if not match:raise ValueError('Versão de atualização inválida.')
    return tuple(map(int,match.groups()))

def repository(value):
    value=str(value).strip().removeprefix('https://github.com/').rstrip('/')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}',value) or value.split('/')[1] in ('.','..'):raise ValueError('Informe o repositório no formato dono/repositorio.')
    return value

def read_json(path,default):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return default

def write_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);fd,name=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

class ReleaseUpdater:
    def __init__(self,root,data_dir,version):self.root=Path(root);self.data=Path(data_dir);self.version=version
    def configuration(self):return read_json(self.data/'sistema/atualizacoes.json',read_json(self.root/'release-channel.json',{}))
    def configure(self,repo):
        repo=repository(repo);write_json(self.data/'sistema/atualizacoes.json',dict(repository=repo,automatic=True));return repo
    def status(self):return read_json(self.data/'sistema/atualizacao-status.json',{})
    def status_write(self,**data):write_json(self.data/'sistema/atualizacao-status.json',dict(checked_at=datetime.now(timezone.utc).isoformat(),**data))
    def _open(self,url,timeout=6):
        req=urllib.request.Request(url,headers={'User-Agent':'VF-Emissor-Updater/'+self.version,'Accept':'application/vnd.github+json' if url.startswith('https://api.github.com/') else 'application/octet-stream'})
        return urllib.request.urlopen(req,timeout=timeout)
    def _json(self,url):
        with self._open(url) as r:
            raw=r.read(2*1024*1024+1)
            if len(raw)>2*1024*1024:raise ValueError('Resposta de atualização excede o limite.')
            return json.loads(raw)
    def check(self):
        repo=self.configuration().get('repository','')
        if not repo:return dict(configured=False,available=False,current=self.version)
        repo=repository(repo)
        try:
            release=self._json('https://api.github.com/repos/'+repo+'/releases/latest')
            if release.get('draft') or release.get('prerelease'):raise ValueError('A publicação não é uma versão estável.')
            tag=release['tag_name'];v=version_number(tag);version='.'.join(map(str,v))
            if v<=version_number(self.version):
                self.status_write(message='O programa está atualizado.',version=version);return dict(configured=True,available=False,current=self.version,version=version)
            name='VF-Emissor-Setup-'+version+'.exe'
            assets={x['name']:x for x in release.get('assets',[])}
            installer=assets.get(name);manifest=assets.get('update-manifest.json')
            if not installer or not manifest:raise ValueError('A versão publicada não possui o instalador e o manifesto esperados.')
            prefix='https://github.com/'+repo+'/releases/download/'+urllib.parse.quote(tag,safe='')+'/'
            if installer.get('browser_download_url')!=prefix+name or manifest.get('browser_download_url')!=prefix+'update-manifest.json':raise ValueError('Endereço do instalador não corresponde ao repositório configurado.')
            metadata=self._json(manifest['browser_download_url']);size=int(metadata.get('size',0));digest=metadata.get('sha256','')
            if metadata.get('format')!=1 or metadata.get('version')!=version or metadata.get('asset')!=name or not re.fullmatch('[a-f0-9]{64}',digest) or not 0<size<=MAX_INSTALLER or installer.get('size')!=size:raise ValueError('Manifesto de atualização inválido.')
            if installer.get('digest') and installer['digest']!='sha256:'+digest:raise ValueError('Hash do GitHub difere do manifesto publicado.')
            result=dict(configured=True,available=True,current=self.version,version=version,name=name,url=installer['browser_download_url'],sha256=digest,size=size,notes=str(release.get('body') or '')[:6000])
            self.status_write(message='Atualização disponível: '+version,version=version);return result
        except urllib.error.HTTPError as e:
            message='Ainda não há uma versão pública com instalador nesse repositório.' if e.code==404 else 'GitHub indisponível para a verificação agora.'
            self.status_write(error=message);raise ValueError(message) from e
        except (OSError,ValueError,KeyError,TypeError) as e:
            self.status_write(error='Não foi possível verificar a atualização. A versão instalada pode continuar sendo usada.');raise ValueError('Não foi possível conferir a atualização. Verifique o repositório e tente novamente.') from e
    def download(self,release):
        # Não aceita informações fornecidas pelo navegador: o chamador usa somente check().
        name=release['name'];version=release['version'];repo=repository(self.configuration()['repository'])
        if name!='VF-Emissor-Setup-'+version+'.exe' or not release['url'].startswith('https://github.com/'+repo+'/releases/download/'):raise ValueError('Instalador inválido.')
        folder=self.data.parent/'Cache/atualizacoes';folder.mkdir(parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(dir=folder,suffix='.part');total=0;sha=hashlib.sha256();started=time.monotonic()
        try:
            with os.fdopen(fd,'wb') as output,self._open(release['url'],timeout=20) as r:
                host=urllib.parse.urlparse(r.geturl()).hostname
                if host not in ('github.com','objects.githubusercontent.com','release-assets.githubusercontent.com'):raise ValueError('Origem do download não reconhecida.')
                while True:
                    chunk=r.read(1024*256)
                    if not chunk:break
                    total+=len(chunk)
                    if total>release['size'] or total>MAX_INSTALLER or time.monotonic()-started>180:raise ValueError('O download excedeu o limite ou o prazo.')
                    output.write(chunk);sha.update(chunk)
                output.flush();os.fsync(output.fileno())
            if total!=release['size'] or sha.hexdigest()!=release['sha256']:raise ValueError('O instalador baixado não passou na conferência de integridade.')
            with open(temp,'rb') as stream:
                if stream.read(2)!=b'MZ':raise ValueError('O arquivo baixado não é um instalador Windows.')
            target=folder/name;os.replace(temp,target);return target
        finally:
            if os.path.exists(temp):os.unlink(temp)

def launch_installer(installer,pid):
    if sys.platform!='win32':raise ValueError('O instalador é executado somente no Windows.')
    path=str(Path(installer).resolve()).replace("'","''")
    command=f"Wait-Process -Id {int(pid)} -ErrorAction SilentlyContinue; Start-Process -FilePath '{path}' -ArgumentList '/S','/RESTARTAPP'"
    subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],creationflags=0x08000000,close_fds=True)
