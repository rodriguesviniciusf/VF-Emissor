"""Consultas pontuais de CEP/CNPJ a provedores fixos, sem salvar cadastros."""
import copy,json,re,threading,time,urllib.error,urllib.request
from collections import OrderedDict
from datetime import datetime,timezone
from core import valid_document
from locality_catalog import canonical_address
CACHE=OrderedDict();LAST={};GUARD=threading.Lock();MAX_RESPONSE=512*1024
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def identifier(kind,value):
    raw=str(value).strip()
    if kind=='cep':
        if not re.fullmatch(r'\d{5}-?\d{3}',raw):raise ValueError('Informe um CEP com oito dígitos.')
        return raw.replace('-','')
    if kind=='cnpj':
        if not re.fullmatch(r'[0-9./\- ]{14,24}',raw):raise ValueError('A consulta pública aceita CNPJ numérico. Para outro formato, preencha o cadastro manualmente.')
        value=re.sub(r'\D','',raw)
        if len(value)!=14 or not valid_document(value):raise ValueError('Confira os dígitos do CNPJ antes de consultar.')
        return value
    raise ValueError('Tipo de consulta inválido.')
def read_json(url):
    req=urllib.request.Request(url,headers={'User-Agent':'VF-Emissor/0.15.0','Accept':'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=8) as response:raw=response.read(MAX_RESPONSE+1)
        if len(raw)>MAX_RESPONSE:raise ValueError('Resposta da consulta excedeu o limite. Preencha manualmente.')
        data=json.loads(raw)
        if not isinstance(data,dict):raise ValueError('Resposta cadastral inválida. Preencha manualmente.')
        return data
    except urllib.error.HTTPError as exc:
        if exc.code==404:raise ValueError('Cadastro não encontrado no serviço público. Confira o número ou preencha manualmente.') from None
        if exc.code==429:raise ValueError('O serviço limitou as consultas. Aguarde e tente novamente ou preencha manualmente.') from None
        raise ValueError('Serviço de consulta indisponível. Seus dados foram preservados; tente novamente ou preencha manualmente.') from None
    except (OSError,UnicodeError,json.JSONDecodeError):raise ValueError('Não foi possível consultar agora. Verifique a internet ou preencha manualmente.') from None

def clean(value,limit=160):return '' if value is None else ''.join(c for c in str(value).strip() if ord(c)>=32)[:limit]
def mapped(kind,key,data):
    if kind=='cep':
        if data.get('erro'):raise ValueError('CEP não encontrado. Confira o número ou preencha manualmente.')
        if re.sub(r'\D','',str(data.get('cep','')))!=key:raise ValueError('O serviço retornou um CEP diferente. Preencha manualmente.')
        fields={t:clean(data.get(s)) for s,t in [('logradouro','xLgr'),('bairro','xBairro'),('localidade','xMun'),('uf','UF')]};fields['CEP']=key;meta={};code=data.get('ibge','')
    else:
        if re.sub(r'\D','',str(data.get('cnpj','')))!=key:raise ValueError('O serviço retornou um CNPJ diferente. Preencha manualmente.')
        fields={t:clean(data.get(s)) for s,t in [('razao_social','xNome'),('nome_fantasia','fantasia'),('bairro','xBairro'),('municipio','xMun'),('uf','UF'),('numero','nro'),('complemento','xCpl'),('ddd_telefone_1','Fone'),('email','Email')]}
        fields['CNPJCPF']=key;fields['xLgr']=clean(' '.join(str(data.get(k) or '').strip() for k in ('descricao_tipo_de_logradouro','logradouro')))
        cep=re.sub(r'\D','',str(data.get('cep','')))
        if len(cep)==8:fields['CEP']=cep
        meta={'Situação cadastral':clean(data.get('descricao_situacao_cadastral')),'CNAE principal':clean(data.get('cnae_fiscal')),'Descrição do CNAE':clean(data.get('cnae_fiscal_descricao'),250)};code=data.get('codigo_municipio_ibge','')
    fields['UF']=fields.get('UF','').upper()
    if fields['UF'] not in 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR RJ RN RO RR RS SC SE SP TO'.split():raise ValueError('UF não reconhecida na consulta. Preencha o cadastro manualmente.')
    return dict(fields=canonical_address({k:v for k,v in fields.items() if v},str(code or '')),details={k:v for k,v in meta.items() if v})
def lookup(kind,value,scope='registration'):
    key=identifier(kind,value);cache_key=(str(scope),kind,key);now=time.monotonic()
    with GUARD:
        cached=CACHE.get(cache_key)
        if cached and cached['expires']>now:
            result=copy.deepcopy(cached['result']);result['cached']=True;return result
        if now-LAST.get(kind,-999)<(3 if kind=='cnpj' else 1):raise ValueError('Aguarde alguns segundos antes de fazer outra consulta.')
        LAST[kind]=now
    url='https://viacep.com.br/ws/'+key+'/json/' if kind=='cep' else 'https://brasilapi.com.br/api/cnpj/v1/'+key
    result=dict(mapped(kind,key,read_json(url)),provider='ViaCEP' if kind=='cep' else 'BrasilAPI / Minha Receita',queried_at=datetime.now(timezone.utc).isoformat(),cached=False)
    with GUARD:
        CACHE[cache_key]=dict(expires=now+(86400 if kind=='cnpj' else 30*86400),result=copy.deepcopy(result));CACHE.move_to_end(cache_key)
        while len(CACHE)>128:CACHE.popitem(last=False)
    return result
