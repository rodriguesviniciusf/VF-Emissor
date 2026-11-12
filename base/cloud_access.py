"""Conta Supabase e licenças assinadas. Nenhuma senha/token é persistida em disco."""
from __future__ import annotations
import base64, copy, json, re, secrets, socket, time, uuid
from pathlib import Path
import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

class Offline(ValueError): pass

def normalize_config(data):
    url=str(data.get('url','')).rstrip('/')
    if not re.fullmatch(r'https://[a-z0-9]{10,40}\.supabase\.co',url):
        raise ValueError('Informe a URL HTTPS do projeto Supabase.')
    key=str(data.get('publishable_key','')).strip()
    if not key.startswith(('sb_publishable_','eyJ')) or not 30<=len(key)<=2000:
        raise ValueError('Informe somente a chave pública do projeto.')
    if key.startswith('eyJ'):
        try: payload=json.loads(base64.urlsafe_b64decode(key.split('.')[1]+'==='))
        except Exception: raise ValueError('Chave pública inválida.')
        if payload.get('role')!='anon':raise ValueError('Não use chave secreta ou service_role no aplicativo.')
    try: public=base64.b64decode(data['verification_key'],validate=True)
    except Exception:raise ValueError('Chave pública de verificação inválida.')
    if len(public)!=32:raise ValueError('A chave Ed25519 deve conter 32 bytes.')
    return dict(url=url,publishable_key=key,verification_key=base64.b64encode(public).decode())

class Access:
    def __init__(self,root,data_dir,transport=None):
        self.root=Path(root);self.folder=Path(data_dir)/'acesso';self.folder.mkdir(parents=True,exist_ok=True)
        self.marker=self.folder/'ativado';self.config_file=self.folder/'public-config.json'
        self.config={};self.transport=transport or requests.Session();self.leases={};self.anchors={}
        config=self.config_file if self.config_file.exists() else self.root/'commercial-config.json'
        if config.exists():
            try:self.config=normalize_config(json.loads(config.read_text(encoding='utf-8')))
            except Exception as exc:raise ValueError('Configuração comercial inválida. Contate o suporte.') from exc
            self.marker.touch(exist_ok=True)
        elif self.marker.exists():raise ValueError('Configuração de acesso ausente. Restaure a configuração; os dados fiscais foram preservados.')
        identity=self.folder/'installation.json'
        if identity.exists():self.installation=str(uuid.UUID(json.loads(identity.read_text(encoding='utf-8'))['id']))
        else:
            self.installation=str(uuid.uuid4());identity.write_text(json.dumps({'id':self.installation}),encoding='utf-8')
        self.label=socket.gethostname()[:100]
    @property
    def enabled(self):return bool(self.config)
    def configure(self,data):
        if self.enabled:raise ValueError('O acesso comercial já está configurado. Contate o suporte para mudar o projeto.')
        config=normalize_config(data)
        path=self.config_file.with_suffix('.tmp');path.write_text(json.dumps(config),encoding='utf-8');path.replace(self.config_file)
        self.config=config;self.marker.touch();return {'ok':True}
    def request(self,path,payload=None,token=None,method='POST'):
        if not self.enabled:raise ValueError('O acesso por e-mail ainda não foi configurado.')
        headers={'apikey':self.config['publishable_key'],'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        try:
            response=self.transport.request(method,self.config['url']+path,json=payload,headers=headers,timeout=10,allow_redirects=False)
        except requests.RequestException as exc:raise Offline('Sem conexão com o serviço de acesso. Tente novamente.') from exc
        if response.status_code in (429,500,502,503,504):raise Offline('Serviço de acesso temporariamente indisponível. Tente novamente.')
        if not 200<=response.status_code<300:
            if path.startswith('/auth/'):
                message='Não foi possível entrar. Confira o e-mail e a senha ou contate o suporte.'
            else:
                try:message=str(response.json().get('error') or response.json().get('message') or '')[:350]
                except Exception:message=''
                message=message or 'O serviço recusou esta operação. Entre novamente ou contate o suporte.'
            raise ValueError(message)
        try:return response.json()
        except Exception as exc:raise ValueError('Resposta inválida do serviço de acesso.') from exc
    def signup(self,p):
        email=str(p.get('email','')).strip().lower();password=str(p.get('password',''));name=str(p.get('name','')).strip()
        from core import valid_document,document
        cnpj=document(p.get('cnpj',''));company_name=str(p.get('company_name','')).strip()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(email)>254:raise ValueError('Informe um e-mail válido.')
        if len(password)<10 or len(password)>128:raise ValueError('Use uma senha de 10 a 128 caracteres.')
        if not 2<=len(name)<=200 or not 2<=len(company_name)<=200 or len(cnpj)!=14 or not valid_document(cnpj):raise ValueError('Confira o nome, CNPJ e razão social.')
        self.request('/auth/v1/signup',{'email':email,'password':password,'data':{'name':name}})
        session=self.login({'email':email,'password':password})
        self.rpc(session,'vf_request_company',{'cnpj_value':cnpj,'company_name':company_name})
        session['profile']=None
        return session
    def recover(self,p):
        code=str(p.get('code','')).strip();password=str(p.get('password',''))
        if not 30<=len(code)<=300 or not 10<=len(password)<=128:raise ValueError('Confira o código fornecido pelo suporte e use senha de 10 a 128 caracteres.')
        d=self.request('/auth/v1/verify',{'token_hash':code,'type':'recovery'})
        self.request('/auth/v1/user',{'password':password},d['access_token'],method='PUT')
        return {'ok':True,'message':'Senha alterada. Entre novamente.'}
    def login(self,p):
        data=self.request('/auth/v1/token?grant_type=password',{'email':str(p.get('email','')).strip().lower(),'password':str(p.get('password',''))})
        if not data.get('access_token') or not data.get('refresh_token'):raise ValueError('Confira a configuração de autenticação do projeto.')
        session={'access_token':data['access_token'],'refresh_token':data['refresh_token'],'token_until':time.time()+int(data.get('expires_in',3600)),
                 'user_id':data['user']['id'],'expires':time.time()+12*3600,'cid':'','license_id':'','profile':None,'profile_at':0}
        self.profile(session,force=True);return session
    def token(self,session):
        if time.time()>session['expires']:raise ValueError('Sessão encerrada. Entre novamente.')
        if time.time()>=session['token_until']-60:
            d=self.request('/auth/v1/token?grant_type=refresh_token',{'refresh_token':session['refresh_token']})
            session.update(access_token=d['access_token'],refresh_token=d['refresh_token'],token_until=time.time()+int(d.get('expires_in',3600)))
        return session['access_token']
    def rpc(self,session,name,payload=None):return self.request('/rest/v1/rpc/'+name,payload or {},self.token(session))
    def profile(self,session,force=False):
        if force or not session.get('profile') or time.monotonic()-session.get('profile_at',0)>30:
            try:
                session['profile']=self.rpc(session,'vf_client_state');session['profile_at']=time.monotonic()
            except Offline:
                if not session.get('profile'):raise
        return copy.deepcopy(session['profile'])
    def verify(self,envelope,session,license_id):
        try:
            raw=base64.b64decode(envelope['payload'],validate=True);signature=base64.b64decode(envelope['signature'],validate=True)
            Ed25519PublicKey.from_public_bytes(base64.b64decode(self.config['verification_key'])).verify(signature,raw)
            data=json.loads(raw)
            if data.get('version')!=1 or data['sub']!=session['user_id'] or data['installation_id']!=self.installation or data['license_id']!=license_id or data.get('read') is not True:
                raise ValueError()
            if not re.fullmatch('[0-9]{14}',data['cnpj']):raise ValueError()
            if not 0<=data['emit_until']-data['issued_at']<=72*3600+5:raise ValueError()
            if data['issued_at']>time.time()+300:raise ValueError('Confira o relógio do computador.')
            return data
        except Exception as exc:raise ValueError('Licença inválida ou relógio incorreto. Conecte à internet e contate o suporte.') from exc
    def lease(self,session,license_id,force=False):
        key=(session['user_id'],license_id);cached=self.leases.get(key);offline=False
        if force or cached is None or time.monotonic()-self.anchors[key][1]>300:
            try:
                envelope=self.request('/functions/v1/vf-license',{'action':'license','license_id':license_id,'installation_id':self.installation,'label':self.label},self.token(session))
                data=self.verify(envelope,session,license_id)
                self.leases[key]=envelope;self.anchors[key]=(data['issued_at'],time.monotonic());cached=envelope
            except Offline:
                if cached is None:raise
                offline=True
            except ValueError:
                self.leases.pop(key,None);self.anchors.pop(key,None);raise
        data=self.verify(cached,session,license_id);issued,mono=self.anchors[key]
        now=max(time.time(),issued+time.monotonic()-mono)
        data.update(offline=offline,can_emit=data.get('emit') is True and now<data['emit_until'])
        return data
    def require(self,session,cnpj,emitting=False):
        if not session or not session.get('license_id'):raise ValueError('Entre na sua conta e selecione uma empresa liberada.')
        data=self.lease(session,session['license_id'],force=emitting)
        if data['cnpj']!=cnpj:raise ValueError('Esta empresa não pertence à licença selecionada.')
        if emitting and not data['can_emit']:raise ValueError('Novas emissões bloqueadas. Confira a aprovação e o vencimento com o suporte. Consultas, XML e backups continuam disponíveis.')
        return data
