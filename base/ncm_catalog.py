"""Consulta local da tabela NCM vigente publicada pela Receita/Siscomex.

A fonte contém a árvore vigente, não um histórico de códigos extintos/futuros.
Ausência em uma cópia antiga não prova invalidade na data da emissão.
"""
from __future__ import annotations
import gzip, hashlib, html, json, os, re, tempfile, threading, time, unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse

SOURCE = 'https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json?perfil=PUBLICO'
PAGE = 'https://www.gov.br/receitafederal/pt-br/assuntos/aduana-e-comercio-exterior/classificacao-fiscal-de-mercadorias/download-ncm-nomenclatura-comum-do-mercosul'
BUNDLE = Path(__file__).parent/'assets/ncm.json.gz'
LIMIT = 12*1024*1024
TZ = timezone(timedelta(hours=-3))
_cache = {}
_attempts = {}
_refresh_lock = threading.Lock()

def today(): return datetime.now(TZ).date()
def normalize(value):
    value = str(value).strip()
    if not re.fullmatch(r'(?:[0-9]{8}|[0-9]{4}\.[0-9]{2}\.[0-9]{2})', value):
        raise ValueError('Informe o NCM completo com oito dígitos.')
    return value.replace('.', '')

def plain(value):
    return ' '.join(html.unescape(re.sub(r'<[^>]*>', '', str(value))).split()).lstrip('- ').rstrip(':').strip()

def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value).casefold()) if not unicodedata.combining(c))

def parse_official(raw):
    if len(raw)>LIMIT: raise ValueError('Tabela NCM acima do limite permitido.')
    source = json.loads(raw)
    match = re.fullmatch(r'Vigente em (\d{2}/\d{2}/\d{4})', source.get('Data_Ultima_Atualizacao_NCM', ''))
    if not match: raise ValueError('Data de referência da tabela NCM não reconhecida.')
    reference = datetime.strptime(match[1], '%d/%m/%Y').date()
    if reference>today()+timedelta(days=1): raise ValueError('Tabela NCM com referência futura inesperada.')
    rows=[];seen=set()
    for value in source['Nomenclaturas']:
        formatted=str(value['Codigo']);code=formatted.replace('.', '')
        if not re.fullmatch(r'[0-9]{2}|[0-9]{4,8}', code) or code in seen: raise ValueError('Código duplicado ou inválido na tabela NCM.')
        seen.add(code)
        start=datetime.strptime(value['Data_Inicio'], '%d/%m/%Y').date().isoformat()
        end=datetime.strptime(value['Data_Fim'], '%d/%m/%Y').date().isoformat()
        description=plain(value['Descricao'])
        if not description or start>end: raise ValueError('Descrição ou vigência inválida na tabela NCM.')
        act=' '.join(str(value.get(k, '')) for k in ('Tipo_Ato_Ini','Numero_Ato_Ini','Ano_Ato_Ini')).strip()
        rows.append([code,formatted,description,start,end,act])
    if len(rows)<10000 or sum(len(r[0])==8 for r in rows)<9000: raise ValueError('Tabela NCM incompleta; a cópia anterior foi preservada.')
    return dict(format=1,reference_date=reference.isoformat(),act=plain(source.get('Ato','')),
                source_url=SOURCE,retrieved_at=datetime.now(TZ).isoformat(timespec='seconds'),
                source_sha256=hashlib.sha256(raw).hexdigest(),rows=rows)

def packed(data): return gzip.compress(json.dumps(data, ensure_ascii=False, separators=(',',':')).encode(), mtime=0)

class Catalog:
    def __init__(self, data):
        self.meta={k:v for k,v in data.items() if k!='rows'}
        if data.get('format')!=1 or data.get('source_url')!=SOURCE: raise ValueError('Catálogo NCM não reconhecido.')
        date.fromisoformat(data['reference_date'])
        self.rows={r[0]:r for r in data['rows']}
        if len(self.rows)<10000: raise ValueError('Catálogo NCM incompleto.')
        self.leaves=[r for r in self.rows.values() if len(r[0])==8]
        self.search_rows=[(r,norm(' '.join(v[2] for v in self.hierarchy(r[0])))) for r in self.leaves]

    def hierarchy(self, code):
        return [self.rows[code[:n]] for n in (2,4,5,6,7,8) if code[:n] in self.rows]

    def status(self):
        return dict(self.meta, stale=self.meta['reference_date']!=today().isoformat(), count=len(self.leaves), official_page=PAGE)

    def lookup(self, value, issued_on=None):
        code=normalize(value);day=date.fromisoformat(str(issued_on)[:10]) if issued_on else today()
        row=self.rows.get(code);meta=self.status();reference=date.fromisoformat(meta['reference_date'])
        result=dict(code=code,formatted=code[:4]+'.'+code[4:6]+'.'+code[6:],table=meta,checked_date=day.isoformat(),hierarchy=[])
        if row:
            result.update(description=row[2],start=row[3],end=row[4],act=row[5],
                          hierarchy=[dict(code=r[0],formatted=r[1],description=r[2]) for r in self.hierarchy(code)])
        if day>reference or (not row and day!=reference) or (row and not row[3]<=day.isoformat()<=row[4] and day!=reference):
            return dict(result,status='unverified',message='Vigência não confirmada para esta data. A tabela disponível contém somente os códigos vigentes na sua data de referência.')
        if not row: return dict(result,status='not_found',message='NCM não consta na tabela oficial vigente. Confira o código e a classificação antes de emitir.')
        if day.isoformat()<row[3]: return dict(result,status='not_started',message='NCM ainda não vigente na data de emissão.')
        if day.isoformat()>row[4]: return dict(result,status='expired',message='NCM fora de vigência na data de emissão.')
        return dict(result,status='valid_cached' if meta['stale'] else 'valid',message='Código encontrado e vigente no período informado pela tabela.' if not meta['stale'] else 'Código encontrado na cópia local. Atualize a tabela para confirmar a vigência atual.')

    def search(self, query):
        words=norm(str(query).strip()).split()
        if not words or len(str(query))>120: return []
        digits=re.sub(r'[^0-9]', '', str(query)) if re.fullmatch(r'[0-9. ]+', str(query)) else ''
        hits=[]
        for row,description in self.search_rows:
            if (digits and row[0].startswith(digits)) or (not digits and all(w in description for w in words)):
                hits.append(dict(code=row[0],formatted=row[1],description=row[2],context=' › '.join(r[2] for r in self.hierarchy(row[0])[1:])))
                if len(hits)==30: break
        return hits

def _load(path):
    stamp=path.stat().st_mtime_ns;key=str(path)
    if key in _cache and _cache[key][0]==stamp: return _cache[key][1]
    with gzip.open(path,'rb') as stream: raw=stream.read(LIMIT+1)
    if len(raw)>LIMIT: raise ValueError('Catálogo NCM acima do limite.')
    value=Catalog(json.loads(raw));_cache[key]=(stamp,value);return value

def local(data_dir):
    bundled=_load(BUNDLE);cache=Path(data_dir)/'ncm-catalog/ncm.json.gz'
    try:
        downloaded=_load(cache)
        if downloaded.meta['reference_date']>=bundled.meta['reference_date']: return downloaded
    except (OSError,ValueError,KeyError,TypeError,IndexError): pass
    return bundled

def refresh(data_dir, force=False):
    key=str(Path(data_dir).resolve());current=local(data_dir)
    if not force and (not current.status()['stale'] or time.monotonic()-_attempts.get(key,0)<3600): return current.status()
    if not _refresh_lock.acquire(blocking=False): return dict(current.status(),message='Atualização da tabela já em andamento.')
    try:
        if force and time.monotonic()-_attempts.get(key,0)<60: return dict(current.status(),message='Aguarde um minuto entre consultas à fonte oficial.')
        _attempts[key]=time.monotonic()
        request=Request(SOURCE, headers={'Accept':'application/json','User-Agent':'VF-Emissor-NCM/1.0'})
        with urlopen(request,timeout=10) as response:
            target=urlparse(response.geturl())
            if target.scheme!='https' or target.hostname!='portalunico.siscomex.gov.br': raise ValueError('Endereço inesperado na atualização NCM.')
            raw=response.read(LIMIT+1)
        data=parse_official(raw);Catalog(data)
        if data['reference_date']<current.meta['reference_date']: raise ValueError('A fonte retornou uma tabela anterior à cópia local.')
        target=Path(data_dir)/'ncm-catalog/ncm.json.gz';target.parent.mkdir(parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(dir=target.parent,suffix='.tmp')
        try:
            with os.fdopen(fd,'wb') as stream: stream.write(packed(data));stream.flush();os.fsync(stream.fileno())
            os.replace(temp,target)
        finally:
            if os.path.exists(temp): os.unlink(temp)
        return dict(local(data_dir).status(),message='Tabela oficial NCM atualizada.')
    except Exception:
        return dict(current.status(),error='Não foi possível atualizar na fonte oficial. A última tabela local foi preservada; confira sua data de referência.')
    finally: _refresh_lock.release()

def check_note(data_dir, note):
    catalog=local(data_dir);issues=[];warnings=[]
    for index,item in enumerate(note.get('items',[])):
        try: result=catalog.lookup(item.get('product',{}).get('NCM',''),note.get('issued_at'))
        except ValueError: continue  # formato já validado pelo motor fiscal
        entry=dict(field=f'item.{index}.product.NCM',message=f'Item {index+1} · NCM {result["formatted"]}: {result["message"]} Tabela: {catalog.meta["reference_date"]}.')
        if result['status'] in ('not_found','expired','not_started'): issues.append(entry)
        elif result['status'] in ('unverified','valid_cached'): warnings.append(entry)
    return dict(issues=issues,warnings=warnings)
