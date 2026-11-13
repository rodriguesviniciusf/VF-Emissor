"""VF Emissor local — dados persistentes e cofre A1 protegido pelo Windows."""
from __future__ import annotations
import argparse, base64, copy, csv, hashlib, io, json, mimetypes, os, secrets, sqlite3, sys, tempfile, time, traceback, zipfile
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'base'))
from core import Store, calculate, number, money, document, valid_document, validate_party
from fiscal import FiscalStore, FiscalService, A1Certificate, build_unsigned, unsigned_schema_issues, parse_xml, text, NS, TZ, render_danfe, validate_schema
from fiscal_events import EventStore, EventService
from note_validation import validate_note
from vf_workflow import next_number, duplicate, preview_html
import editor_recovery
import simple_mode
import ncm_catalog,nature_catalog
import interstate

VERSION = json.loads((ROOT/'version.json').read_text(encoding='utf-8'))['version']
RUN_TOKEN = secrets.token_urlsafe(32)
CSRF = secrets.token_urlsafe(32)
CERTS = {}
STORE = None
PREVIEW = False
ALLOW_REMOTE = False
SESSIONS = {}
VAULT_ERRORS = {}
HTTPD = None
ACCESS = None
ACCESS_STORE = None

def access_manager():
    global ACCESS,ACCESS_STORE
    if ACCESS is None or ACCESS_STORE is not STORE:
        from cloud_access import Access
        ACCESS=Access(ROOT,STORE.path.parent);ACCESS_STORE=STORE
    return ACCESS

def access_state(session):
    manager=access_manager()
    state=dict(version=VERSION,authenticated=False,cid='',companies=[],csrf=CSRF,preview=PREVIEW,
               access=dict(enabled=True,account=None,license=None))
    if not session or 'user_id' not in session:return state
    profile=manager.profile(session);state['access']['account']=profile
    if session.get('cid'):
        license=manager.require(session,company(session['cid'])['CNPJCPF'])
        state.update(get_state(session['cid']));state['access']=dict(enabled=True,account=profile,license=license)
    return state

def access_action(p,session):
    manager=access_manager();cmd=p.get('action')
    if cmd=='configure':
        result=manager.configure(p['config']);SESSIONS.clear();return result,None
    if cmd in ('login','signup'):
        new_session=manager.login(p) if cmd=='login' else manager.signup(p)
        token=secrets.token_urlsafe(32);SESSIONS[token]=new_session
        return dict(ok=True),token
    if cmd=='finish_recovery':return manager.recover(p),None
    if not session or 'user_id' not in session:raise ValueError('Entre com seu e-mail e senha.')
    if cmd=='home':session.update(cid='',license_id='');return dict(ok=True),None
    if cmd=='profile':return manager.profile(session,force=True),None
    if cmd=='request_company':
        result=manager.rpc(session,'vf_request_company',{'cnpj_value':document(p.get('cnpj','')),'company_name':p.get('name','')})
        session['profile']=None
        return result,None
    if cmd=='select':
        license=manager.lease(session,str(p['id']),force=True)
        cid=next((co['_id'] for co in rows('company') if document(co['CNPJCPF'])==license['cnpj']),None)
        created=not bool(cid)
        if not cid:
            cid=STORE.save('company',dict(CNPJCPF=license['cnpj'],xNome=license['name'],UF='AL',CRT='1',environment='2',
                production_enabled=False,series='1',next_number='1',production_series='1',production_next_number='1'),'')
        session.update(cid=cid,license_id=license['license_id'])
        return dict(ok=True,cid=cid,created=created),None
    raise ValueError('Ação de acesso desconhecida.')

def guard_access(p,session):
    if not session or 'user_id' not in session or not session.get('cid'):raise ValueError('Selecione uma empresa aprovada em Minhas empresas.')
    cid=session['cid'];co=company(cid)
    emitting=p.get('action') in ('prepare','send','inutil_prepare')
    if p.get('action')=='event_send':
        emitting=EventStore(STORE).get(cid,p.get('id','')).get('kind')=='INUT'
    access_manager().require(session,co['CNPJCPF'],emitting=emitting)
    if p.get('cid') and p['cid']!=cid:raise ValueError('A empresa mudou. Atualize a tela antes de continuar.')
    if p.get('action')=='save_catalog' and p.get('kind')=='company':
        if p.get('id')!=cid or document(p.get('data',{}).get('CNPJCPF',''))!=document(co['CNPJCPF']):
            raise ValueError('Adicione ou solicite outro CNPJ pela tela Minhas empresas.')
    if p.get('action')=='import_legacy':raise ValueError('A importação inicial é feita antes de ativar o acesso comercial.')
    p['cid']=cid

def hash_password(password: str, salt: str | None = None) -> str:
    if not salt: salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return f"{salt}:{h}"

def verify_password(stored_hash: str, password: str) -> bool:
    if not stored_hash: return True
    if ':' not in stored_hash: return False
    salt, h = stored_hash.split(':', 1)
    computed = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return secrets.compare_digest(computed, h)

def handle_login(p):
    raw_cnpj = str(p.get('cnpj', '')).strip()
    password = str(p.get('password', '')).strip()
    clean_cnpj = document(raw_cnpj)
    if not clean_cnpj: raise ValueError('Informe o CNPJ da empresa.')
    matched = None
    for co in rows('company'):
        if document(co.get('CNPJCPF', '')) == clean_cnpj:
            matched = co
            break
    if not matched: raise ValueError('Nenhuma empresa encontrada com este CNPJ. Cadastre a empresa primeiro.')
    stored = matched.get('password_hash')
    if stored:
        if not password or not verify_password(stored, password):
            raise ValueError('Senha incorreta para esta empresa.')
    else:
        if password:
            matched['password_hash'] = hash_password(password)
            STORE.save('company', matched, '', matched['_id'])
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = {'cid': matched['_id'], 'expires': time.time() + 86400}
    return dict(ok=True, token=token, cid=matched['_id'], name=matched.get('fantasia') or matched.get('xNome'))

def clean_record(data):
    return {k: v for k, v in data.items() if not k.startswith('_')}

def rows(kind, cid=''):
    return [dict(data, _id=rid) for rid, data in STORE.list(kind, cid) if not data.get('_archived')]

def company(cid):
    data = STORE.get('company', '', cid)
    return dict(data, _id=cid)

def note(cid, rid):
    return STORE.get('note', cid, rid)

def vault():
    from certificate_vault import CertificateVault
    return CertificateVault(STORE.path.parent/'certificados-protegidos')

def certificate(cid):
    value=CERTS.get(cid)
    if value and time.time()<=value[1]:return value[0]
    CERTS.pop(cid,None)
    if not PREVIEW and vault().exists(cid):
        try:
            raw,password=vault().load(cid,company(cid)['CNPJCPF'])
            cert=A1Certificate.from_bytes(raw,password,company(cid)['CNPJCPF'])
            CERTS[cid]=(cert,time.time()+3600);VAULT_ERRORS.pop(cid,None);return cert
        except (ValueError,OSError):
            VAULT_ERRORS[cid]='Não foi possível abrir o A1 salvo. Selecione o certificado novamente nesta conta do Windows.'
    raise ValueError(VAULT_ERRORS.get(cid,'Carregue o certificado A1 em Configurações.'))


def totals(co, n):
    result = {}; errors = []
    for index, item in enumerate(n.get('items', [])):
        try:
            amounts = calculate(item, item['rule'], co.get('CRT', '1'))
            for k, v in amounts.items(): result[k] = money(result.get(k, 0)) + v
        except (ValueError, KeyError) as exc: errors.append(f'Item {index+1}: {exc}')
    return {k: str(v) for k, v in result.items()}, errors

def snapshot(cid, n):
    co = company(cid)
    rec = STORE.get('recipient', cid, n.get('recipient_id', ''))
    return dict(company=co, recipient=rec, note=n)

def checked_snapshot(cid, n):
    snap = snapshot(cid, n)
    issues = validate_note(snap['company'], snap['recipient'], n)
    if issues: raise ValueError('\n'.join(i.message for i in issues[:20]))
    ncm=ncm_catalog.check_note(STORE.path.parent,n)
    if ncm['issues']:raise ValueError('\n'.join(i['message'] for i in ncm['issues'][:20]))
    return snap

def editable(cid, rid):
    d = STORE.db.execute('SELECT status FROM fiscal_documents WHERE company=? AND source=?', (cid, rid)).fetchone()
    if d and d[0] not in ('PREPARADA', 'REJEITADA'):
        raise ValueError('O documento já foi transmitido. Consulte a situação fiscal; ele não pode ser alterado.')

def get_state(cid=''):
    all_companies = rows('company')
    if not cid and all_companies and PREVIEW and os.environ.get('VF_PREVIEW_LOGIN')!='1': cid = all_companies[0]['_id']
    from normal_fiscal import catalog,total_catalog
    if not cid:
        return dict(version=VERSION, authenticated=False, companies=[], cid='', csrf=CSRF, preview=PREVIEW, tax_schema=catalog(), total_schema=total_catalog(), has_companies=len(all_companies)>0)
    co = company(cid); fs = FiscalStore(STORE)
    from web_settings import load_settings
    co['settings']=load_settings(STORE,cid)
    co.pop('password_hash',None)
    state = dict(version=VERSION, authenticated=True, companies=[co], cid=cid, csrf=CSRF, preview=PREVIEW, tax_schema=catalog(), total_schema=total_catalog(), rtc_table=json.loads((ROOT/'base/rtc_catalog.json').read_text(encoding='utf-8')))
    documents = []
    fiscal_by_source = {d['source']: d for d in fs.list(cid)}
    for n in rows('note', cid):
        d = fiscal_by_source.get(n['_id']); historical=json.loads(d['snapshot']) if d else None; values, errors = totals(historical['company'] if historical else co,historical['note'] if historical else n)
        try: recipient = STORE.get('recipient', cid, n.get('recipient_id', '')).get('xNome', '')
        except ValueError: recipient = ''
        documents.append(dict(n, _edit_revision=editor_recovery.revision({k:v for k,v in n.items() if k!='_id'}), _total=str(money((historical['note'] if historical else n).get('normal_vnftot') or values.get('net','0'))), _errors=errors, _recipient=recipient,
            _fiscal_id=d['id'] if d else '', _status=d['status'] if d else 'RASCUNHO',
            _key=d['access_key'] if d else '', _reason=d['reason'] if d else ''))
    events = []
    for env in ('1', '2'):
        for e in EventStore(STORE).list(cid, env):
            public={k: v for k, v in e.items() if not isinstance(v, bytes) and k not in ('snapshot',)}
            root=parse_xml(e['signed_xml'])
            public['content']=' '.join(root.xpath('//*[local-name()="xCorrecao" or local-name()="xJust"]/text()'))
            events.append(public)
    if not PREVIEW and vault().exists(cid):
        try:certificate(cid)
        except ValueError:pass
    c = CERTS.get(cid)
    if c and c[1] < time.time(): CERTS.pop(cid, None); c = None
    return dict(state, company=co, recipients=rows('recipient', cid), products=rows('product', cid),
        **__import__('business_runtime').state(STORE,cid,co.get('environment','2')), rules=rows('rule', cid), documents=documents, events=events, received=rows('received', cid),
        certificate=dict(c[0].metadata(), session_expires=c[1]) if c else None,
        certificate_saved=vault().exists(cid),certificate_error=VAULT_ERRORS.get(cid,''),
        editing_drafts=editor_recovery.list_copies(STORE,cid,co.get('environment','2')),
        simple_config=simple_mode.public_state(STORE,cid),
        natures=nature_catalog.listing(STORE,cid),ncm_status=ncm_catalog.local(STORE.path.parent).status(),interstate_settings=interstate.load(STORE,cid),
        storage=dict(data_dir=str(STORE.path.parent),xml_dir=str(STORE.path.parent/'notas-fiscais'/co['CNPJCPF'])),
        updates=dict(repository=updater().configuration().get('repository',''),automatic=True,status=updater().status()))

def save_catalog(p):
    kind = p['kind']; cid = p.get('cid', ''); data = clean_record(p['data']); rid = p.get('id') or None
    if kind not in ('company', 'recipient', 'supplier', 'product', 'rule'): raise ValueError('Tipo de cadastro inválido.')
    if kind == 'company':
        cid = ''
        if not valid_document(data.get('CNPJCPF', '')) or len(document(data['CNPJCPF'])) != 14: raise ValueError('Informe um CNPJ válido.')
        if not data.get('xNome', '').strip(): raise ValueError('Informe a razão social.')
        data['CNPJCPF'] = document(data['CNPJCPF'])
        for existing in rows('company'):
            if existing['_id'] != rid and document(existing['CNPJCPF']) == data['CNPJCPF']: raise ValueError('Já existe uma empresa com esse CNPJ.')
        old = company(rid) if rid else {}
        if old and document(old['CNPJCPF']) != data['CNPJCPF'] and (STORE.list('note', rid) or FiscalStore(STORE).list(rid)):
            raise ValueError('O CNPJ de uma empresa com documentos não pode ser alterado. Cadastre outra empresa.')
        data['production_enabled'] = bool(old.get('production_enabled', False))
        if p.get('enable_production'):
            if p.get('ack') != 'PRODUÇÃO': raise ValueError('Digite PRODUÇÃO para habilitar o ambiente real.')
            validate_party(data, True)
            if data.get('UF') != 'AL' or data.get('CRT') not in ('1','3'): raise ValueError('O conector atual contempla AL / CRT 1 e CRT 3.')
            if not str(data.get('production_next_number', '')).isdigit(): raise ValueError('Confira a próxima numeração em produção.')
            data['production_enabled'] = True
        if data.get('environment') == '1' and not data['production_enabled']: raise ValueError('Habilite a produção antes de trocar o ambiente.')
        if not old: data['environment'] = '2'
        data.setdefault('series', '1'); data.setdefault('next_number', '1')
        data.setdefault('production_series', '1'); data.setdefault('production_next_number', '1')
        raw_pw = data.pop('password', None)
        if raw_pw and str(raw_pw).strip():
            data['password_hash'] = hash_password(str(raw_pw).strip())
        elif old.get('password_hash'):
            data['password_hash'] = old['password_hash']
    else:
        company(cid)
        if kind in ('recipient','supplier'):
            if not data.get('xNome', '').strip() or not valid_document(data.get('CNPJCPF', '')): raise ValueError('Preencha nome e CPF/CNPJ válido.')
            data['CNPJCPF'] = document(data['CNPJCPF'])
        if kind in ('product','recipient','supplier'):
            identity='code' if kind=='product' else 'CNPJCPF'
            key=str(data.get(identity,'')).casefold() if kind=='product' else document(data.get(identity,''))
            for existing in rows(kind,cid):
                other=str(existing.get(identity,'')).casefold() if kind=='product' else document(existing.get(identity,''))
                if key and key==other and existing['_id']!=rid:raise ValueError('Já existe um cadastro com esse '+identity+' nesta empresa.')
        if kind == 'product':
            import re
            if not data.get('name', '').strip() or not data.get('code', '').strip(): raise ValueError('Preencha código e nome do produto.')
            if not re.fullmatch('[0-9]{8}', data.get('NCM', '')): raise ValueError('NCM deve ter oito dígitos.')
            if number(data.get('price', 0)) < 0: raise ValueError('Preço inválido.')
        if kind == 'rule' and not data.get('name', '').strip(): raise ValueError('Informe o nome da tributação.')
        if kind=='rule' and company(cid).get('CRT')=='3':
            from normal_fiscal import normal_groups,default_groups
            data['crt']='3';groups=normal_groups({},data)
            old=STORE.get('rule',cid,rid) if rid else {}
            if old and 'normal_groups' in data:
                if data.get('icms_code')!=old.get('icms_code'):
                    groups['ICMS']=default_groups(data.get('icms_code','00'),data.get('origin','0'),data.get('icms_rate','0'))['ICMS']
                else:
                    icms=next(iter(groups.get('ICMS',{}).values()),{})
                    icms['orig']=data.get('origin',icms.get('orig','0'))
                    if 'pICMS' in icms:icms['pICMS']=data.get('icms_rate',icms['pICMS'])
                for tax in ('PIS','COFINS'):
                    field=tax.lower()
                    if data.get(field+'_code')!=old.get(field+'_code'):
                        groups[tax]=default_groups(pis_code=data.get('pis_code','99'),pis_rate=data.get('pis_rate','0'),cofins_code=data.get('cofins_code','99'),cofins_rate=data.get('cofins_rate','0'))[tax]
                    else:
                        child=next(iter(groups.get(tax,{}).values()),{})
                        if 'p'+tax in child:child['p'+tax]=data.get(field+'_rate',child['p'+tax])
            data['normal_groups']=groups
    return dict(id=STORE.save(kind, data, cid, rid))

def save_note(p):
    cid = p['cid']; co = company(cid); rid = p.get('id') or None
    n = clean_record(p['data'])
    problems=simple_mode.verify(STORE,cid,n,partial=True)
    if problems:raise ValueError(problems[0]['message'])
    attempt_id=simple_mode.existing_attempt(STORE,cid,n)
    if attempt_id and rid and attempt_id!=rid:raise ValueError('Esta edição já pertence a outro rascunho. Reabra a nota existente.')
    rid=rid or attempt_id
    env = n.get('environment', co.get('environment', '2'))
    if env not in ('1', '2'): raise ValueError('Ambiente inválido.')
    if env == '1' and not co.get('production_enabled'): raise ValueError('Produção ainda não habilitada.')
    if rid:
        old = note(cid, rid); editable(cid, rid)
        if env != old.get('environment', '2'): raise ValueError('O ambiente de um rascunho salvo não pode ser alterado. Duplique para o outro ambiente.')
        n['cnf'] = old['cnf']
        if not n.get('number'):n['number']=old['number']
    else:
        n['cnf'] = f'{secrets.randbelow(100000000):08d}'
        n['number'] = next_number(STORE, cid, env, n.get('series', '1')) if not n.get('number') else str(n['number'])
    if not str(n.get('number', '')).isdigit() or not 1 <= int(n['number']) <= 999999999: raise ValueError('Número inválido.')
    if not str(n.get('series', '')).isdigit() or not 0 <= int(n['series']) <= 999: raise ValueError('Série inválida.')
    for existing in rows('note', cid):
        if existing['_id'] != rid and existing.get('environment', '2') == env and int(existing.get('series', 1)) == int(n['series']) and int(existing.get('number', 0)) == int(n['number']):
            raise ValueError('Já existe um rascunho com a mesma série e número neste ambiente.')
    if len(n.get('items', [])) > 990: raise ValueError('Máximo de 990 itens.')
    n.update(environment=env, status='RASCUNHO')
    stamp = n.get('issued_at') or datetime.now(TZ).isoformat(timespec='seconds')
    parsed = datetime.fromisoformat(stamp)
    n['issued_at'] = (parsed.replace(tzinfo=TZ) if parsed.tzinfo is None else parsed).isoformat(timespec='seconds')
    rid=STORE.save('note', n, cid, rid)
    return dict(id=rid,number=n['number'],revision=editor_recovery.revision(n))

def import_xml(p):
    cid = p['cid']; co = company(cid)
    raw = base64.b64decode(p['data'], validate=True); root = parse_xml(raw)
    if root.tag != '{'+NS+'}nfeProc': raise ValueError('Importe XML NF-e processado, com protocolo de autorização.')
    validate_schema(raw, 'procNFe_v4.00.xsd')
    inf = root.find('n:NFe/n:infNFe', {'n': NS}); prot = root.find('n:protNFe/n:infProt', {'n': NS})
    if inf is None or prot is None or text(prot, 'n:cStat') not in ('100', '150'): raise ValueError('XML sem protocolo de autorização válido.')
    key = inf.get('Id', '')[3:]
    if text(prot, 'n:chNFe') != key or text(prot, 'n:tpAmb') != text(inf, 'n:ide/n:tpAmb'): raise ValueError('Protocolo não corresponde à nota.')
    emitter = text(inf, 'n:emit/n:CNPJ'); dest = text(inf, 'n:dest/n:CNPJ') or text(inf, 'n:dest/n:CPF')
    if document(co['CNPJCPF']) not in (emitter, dest): raise ValueError('XML não pertence ao emitente nem ao destinatário desta empresa.')
    for previous in rows('received',cid):
        if previous.get('key')!=key:continue
        target=STORE.path.parent/'xml-importados'/cid/(previous['_id']+'.xml')
        if target.exists():raise ValueError('Esse XML já foi importado.')
        from invoice_archive import atomic_write
        atomic_write(target,raw,immutable=True)
        return dict(id=previous['_id'],repaired=True,message='Arquivo XML local reposto. O cadastro e os movimentos de estoque existentes foram preservados.')
    rec = dict(key=key, number=text(inf, 'n:ide/n:nNF'), series=text(inf, 'n:ide/n:serie'), environment=text(inf, 'n:ide/n:tpAmb'),
        issued_at=text(inf, 'n:ide/n:dhEmi'), issuer=text(inf, 'n:emit/n:xNome'), recipient=text(inf, 'n:dest/n:xNome'),
        total=text(inf,'n:total/n:vNFTot') or text(inf, 'n:total/n:ICMSTot/n:vNF'), direction='emitida' if emitter == document(co['CNPJCPF']) else 'recebida',
        status='XML IMPORTADO — autorização declarada no arquivo; sem consulta à SEFAZ')
    rid = STORE.save('received', rec, cid)
    folder = STORE.path.parent / 'xml-importados' / cid; folder.mkdir(parents=True, exist_ok=True)
    (folder / (rid + '.xml')).write_bytes(raw)
    return dict(id=rid, message='XML importado. O aplicativo não confirmou a situação atual na SEFAZ.')

def action(p):
    cmd = p['action']; cid = p.get('cid', '')
    if cmd in ('interstate_save_settings','interstate_prepare_item'):
        co=company(cid)
        if cmd=='interstate_save_settings':
            from business_runtime import LOCK
            with LOCK:return dict(settings=interstate.save(STORE,cid,p))
        n=p['note'];rec=STORE.get('recipient',cid,n.get('recipient_id',''))
        return interstate.prepare_item(co,rec,n,p['item'],p)
    if cmd in ('nature_save','nature_delete'):
        company(cid)
        from business_runtime import LOCK
        with LOCK:
            if cmd=='nature_save':return dict(id=nature_catalog.save_nature(STORE,cid,p['name'],p.get('id') or None))
            return nature_catalog.remove(STORE,cid,p['id'])
    if cmd in ('ncm_lookup','ncm_search','ncm_refresh'):
        company(cid)
        if cmd=='ncm_refresh':return ncm_catalog.refresh(STORE.path.parent,force=True)
        catalog=ncm_catalog.local(STORE.path.parent)
        if cmd=='ncm_search':return dict(results=catalog.search(p.get('query','')),table=catalog.status())
        return catalog.lookup(p.get('code',''),p.get('issued_on'))
    if cmd in ('simple_config_save','simple_resolve','simple_review'):
        company(cid)
        from business_runtime import LOCK
        with LOCK:
            if cmd=='simple_config_save':return dict(config=simple_mode.save(STORE,cid,p))
            if cmd=='simple_resolve':return dict(note=simple_mode.resolve(STORE,cid,p))
            n=p['note'];validation=action(dict(action='validate',cid=cid,note=n));issues=validation['issues'];values,errors=totals(company(cid),n)
            return dict(issues=issues,warnings=validation.get('warnings',[]),totals=values,errors=errors,review_hash=simple_mode.review_hash(n) if not issues and not errors else '')
    if cmd=='lookup_public':
        from public_lookup import lookup
        return lookup(p['kind'],p.get('value',''),cid or 'registration')
    if cmd in ('editor_save','editor_list','editor_restore','editor_drop'):
        co=company(cid)
        from business_runtime import LOCK
        with LOCK:
            if cmd=='editor_save':return editor_recovery.save(STORE,cid,p)
            if cmd=='editor_list':return dict(copies=editor_recovery.list_copies(STORE,cid,co.get('environment','2')))
            if cmd=='editor_restore':return editor_recovery.restore(STORE,cid,p['id'],p.get('as_new') is True)
            return editor_recovery.drop(STORE,cid,p['id'],p.get('version'))
    from business_runtime import COMMANDS,action as business_action
    if cmd in COMMANDS:
        value=business_action(STORE,p,PREVIEW,import_xml)
        if cmd=='restore_apply':CERTS.pop(cid,None);VAULT_ERRORS.pop(cid,None)
        return value
    if cmd == 'save_catalog': return save_catalog(p)
    if cmd == 'save_note': return save_note(p)
    if cmd == 'shutdown':
        if PREVIEW or HTTPD is None:raise ValueError('Encerre pelo aplicativo instalado no Windows.')
        import threading
        threading.Timer(0.5,HTTPD.shutdown).start()
        return dict(ok=True)
    if cmd == 'search_products':
        import unicodedata
        def norm(s):return ''.join(c for c in unicodedata.normalize('NFD',str(s).casefold()) if not unicodedata.combining(c))
        query=norm(p.get('query',''));products=rows('product',cid)
        products=[x for x in products if query in norm(' '.join(str(x.get(k,'')) for k in ('code','name','NCM','gtin','unit')))]
        return dict(products=sorted(products,key=lambda x:(norm(x.get('name','')),str(x.get('code','')))))
    if cmd == 'save_update_repository':
        company(cid);return dict(repository=updater().configure(p['repository']))
    if cmd == 'check_updates':
        company(cid);return updater().check()
    if cmd == 'open_xml_folder':
        if PREVIEW or sys.platform!='win32':raise ValueError('Abra a pasta pelo aplicativo instalado no Windows.')
        folder=STORE.path.parent/'notas-fiscais'/company(cid)['CNPJCPF'];folder.mkdir(parents=True,exist_ok=True);os.startfile(str(folder));return dict(ok=True)
    if cmd == 'import_legacy':
        if PREVIEW:raise ValueError('Importe os dados pelo aplicativo instalado no Windows.')
        from desktop_storage import import_legacy,has_companies
        if has_companies(STORE.path):raise ValueError('A instalação já possui empresas. A importação inicial não substitui dados existentes.')
        target=STORE.path.parent;STORE.db.close()
        try:count=import_legacy(p['source'],target)
        finally:
            globals()['STORE']=Store(target/'vf.sqlite3');FiscalStore(STORE);EventStore(STORE)
        return dict(ok=True,companies=count)

    if cmd == 'save_settings':
        company(cid)
        from web_settings import save_settings
        return dict(settings=save_settings(STORE,cid,p['section'],p['data']))
    if cmd == 'delete_note':
        rid = p['id']
        note(cid, rid)
        f = STORE.db.execute('SELECT status FROM fiscal_documents WHERE company=? AND source=?', (cid, rid)).fetchone()
        if f:
            if f[0] in ('AUTORIZADA', 'CANCELADA', 'DENEGADA'):
                raise ValueError('Documento com validade fiscal na SEFAZ não pode ser excluído.')
            if f[0] == 'PREPARADA':
                STORE.db.execute('DELETE FROM fiscal_documents WHERE company=? AND source=?', (cid, rid))
            else:
                raise ValueError('Documento com retorno da SEFAZ não pode ser excluído.')
        with STORE.db:
            STORE.db.execute("DELETE FROM records WHERE kind='note' AND company=? AND id=?", (cid, rid))
            STORE.db.execute("INSERT INTO audit(stamp,action,record) VALUES(?,?,?)", (datetime.now().astimezone().isoformat(), 'EXCLUIR note', rid))
        return dict(ok=True)
    if cmd == 'archive':
        kind = p['kind']
        if kind not in ('product', 'recipient', 'supplier', 'rule', 'note'): raise ValueError('Não é possível arquivar esse registro.')
        if kind == 'note':
            if STORE.db.execute('SELECT 1 FROM fiscal_documents WHERE company=? AND source=?',(cid,p['id'])).fetchone(): raise ValueError('Documento fiscal não pode ser arquivado como rascunho.')
            d = note(cid, p['id'])
        else: d = STORE.get(kind, cid, p['id'])
        d['_archived'] = True; STORE.save(kind, d, cid, p['id']); return dict(ok=True)
    if cmd == 'new_note':
        co = company(cid); env = co.get('environment', '2'); series = co.get('production_series' if env == '1' else 'series', '1')
        from web_settings import new_note_defaults
        return dict(note=dict(new_note_defaults(STORE,cid),environment=env,series=series,number='',has_reference='0',references='',items=[],issued_at=datetime.now(TZ).isoformat(timespec='seconds')))
    if cmd == 'duplicate': return dict(note=duplicate(STORE, cid, note(cid, p['id'])))
    if cmd == 'normal_calculate':
        from normal_fiscal import normalized,calculate_normal
        i=p['item'];groups,_=normalized(i,i['rule']);values=calculate_normal(i,i['rule'],validate=False)
        return dict(groups=groups,totals={k:str(v) for k,v in values.items()})
    if cmd == 'calculate':
        value, errors = totals(company(cid), p['note']); return dict(totals=value, errors=errors)
    if cmd == 'validate':
        n = copy.deepcopy(p['note']); co = company(cid)
        if not n.get('number'):n['number']=next_number(STORE,cid,n.get('environment','2'),n.get('series','1'))
        n.setdefault('cnf','00000000')
        stamp=datetime.fromisoformat(n.get('issued_at') or datetime.now(TZ).isoformat())
        n['issued_at']=(stamp.replace(tzinfo=TZ) if stamp.tzinfo is None else stamp).isoformat(timespec='seconds')
        try: rec = STORE.get('recipient', cid, n.get('recipient_id', ''))
        except ValueError: rec = {}
        issues = validate_note(co, rec, n)
        ncm=ncm_catalog.check_note(STORE.path.parent,n)
        return dict(issues=simple_mode.verify(STORE,cid,p['note'])+[dict(field=i.field, message=i.message) for i in issues]+ncm['issues'],warnings=ncm['warnings'])
    if cmd == 'load_certificate':
        if PREVIEW: raise ValueError('Carregue seu certificado somente no aplicativo local do Windows.')
        raw = base64.b64decode(p['data'], validate=True)
        if len(raw) > 4*1024*1024: raise ValueError('Certificado muito grande.')
        cert = A1Certificate.from_bytes(raw, p['password'], company(cid)['CNPJCPF'])
        if p.get('remember',True):vault().save(cid,company(cid)['CNPJCPF'],raw,p['password'])
        else:vault().remove(cid)
        CERTS[cid] = (cert, time.time()+3600);VAULT_ERRORS.pop(cid,None)
        return dict(metadata=cert.metadata(),saved=vault().exists(cid))
    if cmd == 'forget_certificate':
        CERTS.pop(cid,None);vault().remove(cid);VAULT_ERRORS.pop(cid,None);return dict(ok=True)
    if cmd == 'import_xml': return import_xml(p)
    if cmd == 'prepare':
        n = note(cid, p['id'])
        problems=simple_mode.verify(STORE,cid,n)
        if problems:raise ValueError(problems[0]['message'])
        if n.get('simple_mode',{}).get('active') and p.get('simple_review_hash')!=simple_mode.review_hash(n):raise ValueError('Confira novamente o resumo do Modo Simples antes de emitir.')
        snap = checked_snapshot(cid, n)
        cert = certificate(cid); unsigned, key, _ = build_unsigned(snap['company'], snap['recipient'], n)
        signed = cert.sign(unsigned)
        fid = FiscalStore(STORE).prepare(cid, p['id'], snap, signed, key)
        return dict(fiscal_id=fid, key=key, status='PREPARADA')
    if cmd in ('send', 'query', 'sefaz_status', 'event_send', 'event_query'):
        if PREVIEW: raise ValueError('A comunicação SEFAZ está disponível no pacote local do Windows.')
        cert = certificate(cid); fs = FiscalStore(STORE); svc = FiscalService(fs, cert)
        if cmd == 'sefaz_status': return dict(message=svc.status(company(cid).get('environment','2')))
        if cmd == 'query':
            result=svc.query(cid,p['id']);__import__('business_runtime').after_change(STORE,cid);return dict(status=result)
        if cmd == 'send':
            d = fs.get(cid, p['id'])
            if p.get('ack_key') != d['access_key']: raise ValueError('Revise e confirme a chave e o resumo antes de transmitir.')
            ncm=ncm_catalog.check_note(STORE.path.parent,json.loads(d['snapshot'])['note'])
            if ncm['issues'] and d['status']=='PREPARADA':raise ValueError(ncm['issues'][0]['message'])
            result=svc.send(cid,p['id']);__import__('business_runtime').after_change(STORE,cid);return dict(status=result)
        es = EventService(EventStore(STORE), cert)
        if cmd == 'event_query':
            result=es.query(cid,p['id']);__import__('business_runtime').after_change(STORE,cid);return dict(status=result)
        if p.get('ack') is not True: raise ValueError('Confirme o envio do evento.')
        result=es.send(cid,p['id']);__import__('business_runtime').after_change(STORE,cid);return dict(status=result)
    if cmd == 'event_prepare':
        cert = certificate(cid); es = EventStore(STORE)
        if p['kind'] not in ('110110','110111'): raise ValueError('Evento inválido.')
        rid = es.prepare(cid, p['id'], p['kind'], p['content'], cert, acknowledged=p.get('ack') is True)
        return dict(id=rid)
    if cmd == 'inutil_prepare':
        cert = certificate(cid)
        rid = EventStore(STORE).prepare_inutil(cid, int(p['year']), int(p['series']), int(p['start']), int(p['end']), p['reason'], cert, acknowledged=p.get('ack') is True)
        return dict(id=rid)
    raise ValueError('Ação desconhecida.')

def updater():
    from app_updates import ReleaseUpdater
    return ReleaseUpdater(ROOT,STORE.path.parent,VERSION)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass
    def valid_host(self):
        if PREVIEW or ALLOW_REMOTE: return True
        host = self.headers.get('Host', '').split(':')[0]
        return host in ('127.0.0.1', 'localhost', '[::1]')
    def authorized(self):
        cookie = SimpleCookie()
        try: cookie.load(self.headers.get('Cookie', ''))
        except Exception: return False
        value = cookie.get('vf_session')
        return value and secrets.compare_digest(value.value, RUN_TOKEN)
    def get_company_session(self):
        cookie = SimpleCookie()
        try: cookie.load(self.headers.get('Cookie', ''))
        except Exception: return None
        v = cookie.get('vf_company_session')
        if not v: return None
        sess = SESSIONS.get(v.value)
        if not sess: return None
        if sess['expires'] < time.time():
            SESSIONS.pop(v.value, None)
            return None
        return sess['cid']
    def get_access_session(self):
        cookie=SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''))
        except Exception:return None
        value=cookie.get('vf_company_session');sess=SESSIONS.get(value.value) if value else None
        if not sess or sess.get('expires',0)<time.time():return None
        return sess
    def reply(self, data, mime='application/json; charset=utf-8', status=200, filename=None, session=False, portal=False):
        if not isinstance(data, bytes): data = json.dumps(data, ensure_ascii=False).encode('utf8')
        self.send_response(status)
        self.send_header('Content-Type', mime); self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store'); self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer'); self.send_header('X-Frame-Options', 'DENY')
        connect="'self' https://*.supabase.co" if portal else "'self'"
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src "+connect+"; frame-ancestors 'none'; form-action 'self'")
        if filename: self.send_header('Content-Disposition', 'attachment; filename="'+filename+'"')
        if session: self.send_header('Set-Cookie', 'vf_session='+RUN_TOKEN+'; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if not self.valid_host(): return self.reply(dict(error='Host inválido.'), status=403)
        u = urlparse(self.path); q = parse_qs(u.query)
        try:
            if u.path=='/gestao/config.json':
                if not access_manager().enabled:return self.reply(dict(error='Configuração pendente.'),status=404)
                return self.reply(access_manager().config)
            if u.path in ('/gestao/','/gestao/app.js','/gestao/auth.js','/gestao/style.css','/gestao/favicon.svg'):
                f=ROOT/'portal'/('index.html' if u.path=='/gestao/' else u.path.split('/')[-1])
                return self.reply(f.read_bytes(),mimetypes.guess_type(f)[0] or 'text/plain',portal=True)
            if u.path=='/municipios.json':return self.reply((ROOT/'base/assets/municipios.json').read_bytes())
            if u.path in ('/', '/motion-ui.js','/premium.css', '/access-ui.js','/access.css', '/interstate-ui.js', '/interstate.css', '/ncm-ui.js', '/ncm.css', '/simple-ui.js', '/simple.css', '/assistance-ui.js', '/assistance.css', '/app.js', '/normal-ui.js', '/product-ui.js', '/settings-ui.js', '/desktop-ui.js', '/workspace-ui.js', '/workspace.css', '/business-ui.js', '/business.css', '/style.css', '/favicon.svg'):
                f = ROOT/'static'/('index.html' if u.path=='/' else u.path[1:])
                return self.reply(f.read_bytes(), mimetypes.guess_type(f)[0] or 'text/plain', session=u.path=='/')
            if u.path == '/health': return self.reply(dict(app='VF Emissor Web', version=VERSION))
            if not self.authorized(): return self.reply(dict(error='Reabra a página do aplicativo.'), status=401)
            if access_manager().enabled:
                session=self.get_access_session()
                if u.path=='/api/state':return self.reply(access_state(session))
                if not session or 'user_id' not in session or not session.get('cid'):raise ValueError('Entre e selecione uma empresa aprovada.')
                access_manager().require(session,company(session['cid'])['CNPJCPF'])
            active_cid = self.get_company_session()
            if not active_cid and PREVIEW:
                active_cid = q.get('cid', [''])[0]
            if u.path == '/api/state':
                state=get_state(active_cid or '');state['access']=dict(enabled=False)
                return self.reply(state)
            cid = active_cid or ''
            if u.path == '/api/download':
                kind=q['kind'][0]; rid=q.get('id',[''])[0]
                if not cid:raise ValueError('Entre na empresa para baixar seus documentos.')
                if kind == 'backup':
                    from company_backup import backup_company
                    from business_runtime import LOCK
                    with LOCK:data=backup_company(STORE,cid,company(cid)['CNPJCPF'],vault().path(cid))
                    return self.reply(data,'application/zip',filename='VF-Backup-'+company(cid)['CNPJCPF']+'-'+datetime.now(TZ).strftime('%Y%m%d-%H%M%S')+'.zip')
                company(cid)
                if kind=='model_xlsx':return self.reply((ROOT/'templates/modelo-cadastros.xlsx').read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',filename='VF-Modelo-Cadastros.xlsx')
                if kind=='model_csv':
                    from catalog_wizard import FIELDS
                    if rid not in FIELDS:raise ValueError('Modelo inválido.')
                    data=(';'.join(FIELDS[rid])+'\r\n').encode('utf-8-sig')
                    return self.reply(data,'text/csv; charset=utf-8',filename='modelo-'+rid+'.csv')
                if kind=='accounting':
                    from accounting_package import build
                    period=q.get('month',[''])[0];env=q.get('environment',[company(cid).get('environment','2')])[0]
                    data,_=build(STORE,cid,period,env)
                    return self.reply(data,'application/zip',filename='VF-Contabilidade-'+company(cid)['CNPJCPF']+'-'+period+'-'+('producao' if env=='1' else 'homologacao')+'.zip')
                if kind=='backup_saved':
                    from company_recovery import backup_root
                    if Path(rid).name!=rid or not rid.endswith('.zip') or not __import__('re').fullmatch(r'[a-zA-Z0-9-]+\.zip',rid):raise ValueError('Backup inválido.')
                    file=backup_root(STORE,cid)/rid
                    if file.is_symlink():raise ValueError('Backup inválido.')
                    return self.reply(file.read_bytes(),'application/zip',filename=rid)
                if kind=='preview':
                    snap=snapshot(cid,note(cid,rid))
                    return self.reply(('<!doctype html><meta charset="utf-8"><title>Conferência NF-e</title><style>body{font:14px Arial;margin:40px;color:#243c3c}table{border-collapse:collapse;width:100%}</style>'+preview_html(snap['company'],snap['recipient'],snap['note'])).encode(),'text/html; charset=utf-8')
                if kind=='danfe_preview':
                    d=None
                    try: d=FiscalStore(STORE).get(cid,rid)
                    except ValueError: pass
                    if d and d.get('proc_xml'):
                        return self.reply(render_danfe(d['proc_xml']),'application/pdf',filename=d.get('access_key',rid)+'-DANFE.pdf')
                    if d and d.get('signed_xml'):
                        return self.reply(render_danfe(d['signed_xml'],is_preview=True),'application/pdf',filename=d.get('access_key',rid)+'-DANFE-PREVIA.pdf')
                    co=company(cid); n=copy.deepcopy(note(cid,rid))
                    rec=STORE.get('recipient',cid,n.get('recipient_id',''))
                    if not n.get('number'): n['number']=next_number(STORE,cid,n.get('environment','2'),n.get('series','1'))
                    n.setdefault('cnf','00000000')
                    stamp=datetime.fromisoformat(n.get('issued_at') or datetime.now(TZ).isoformat())
                    n['issued_at']=(stamp.replace(tzinfo=TZ) if stamp.tzinfo is None else stamp).isoformat(timespec='seconds')
                    unsigned,key,_=build_unsigned(co,rec,n)
                    return self.reply(render_danfe(unsigned,is_preview=True),'application/pdf',filename='DANFE-PREVIA-'+str(n.get('number','rascunho'))+'.pdf')
                if kind=='received_xml':
                    STORE.get('received',cid,rid)
                    data=(STORE.path.parent/'xml-importados'/cid/(rid+'.xml')).read_bytes()
                    return self.reply(data,'application/xml',filename=rid+'.xml')
                if kind=='csv':
                    output=io.StringIO(); w=csv.writer(output,delimiter=';'); w.writerow(['Número','Série','Destinatário','Emissão','Total','Situação','Ambiente'])
                    for n in get_state(cid)['documents']:
                        values=[n.get('number',''),n.get('series',''),n['_recipient'],n.get('issued_at',''),n['_total'],n['_status'],n.get('environment','2')]
                        w.writerow(["'"+str(v) if str(v).startswith(('=','+','-','@','\t','\r')) else v for v in values])
                    return self.reply(output.getvalue().encode('utf-8-sig'),'text/csv',filename='notas-fiscais.csv')
                if kind=='event_xml':
                    ev=EventStore(STORE).get(cid,rid)
                    return self.reply(ev['proc_xml'] or ev['signed_xml'],'application/xml',filename='evento-'+rid+'.xml')
                d=FiscalStore(STORE).get(cid,rid)
                if kind=='xml':return self.reply(d['proc_xml'] or d['signed_xml'],'application/xml',filename=d['access_key']+('-autorizado.xml' if d['proc_xml'] else '-assinado.xml'))
                if kind=='danfe':
                    if d['status']!='AUTORIZADA' or not d['proc_xml']: raise ValueError('DANFE disponível somente após autorização confirmada. Use a conferência para rascunhos.')
                    return self.reply(render_danfe(d['proc_xml']),'application/pdf',filename=d['access_key']+'-DANFE.pdf')
            return self.reply(dict(error='Recurso não encontrado.'),status=404)
        except (ValueError,KeyError,FileNotFoundError) as exc: return self.reply(dict(error=str(exc)),status=400)
        except Exception:
            traceback.print_exc(); return self.reply(dict(error='Falha interna. Consulte o console do aplicativo.'),status=500)
    def do_POST(self):
        if not self.valid_host() or not self.authorized(): return self.reply(dict(error='Sessão inválida.'),status=403)
        origin=self.headers.get('Origin')
        if origin and urlparse(origin).netloc != self.headers.get('Host'): return self.reply(dict(error='Origem inválida.'),status=403)
        if self.path=='/api/access':
            if self.headers.get('Sec-Fetch-Site')=='cross-site' or not secrets.compare_digest(self.headers.get('X-VF-CSRF',''),CSRF):return self.reply(dict(error='Recarregue a página.'),status=403)
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=8192:raise ValueError('Solicitação de acesso muito grande.')
                p=json.loads(self.rfile.read(size))
                if p.get('action')=='configure' and rows('company') and not self.get_company_session():raise ValueError('Entre em uma empresa local antes de ativar o novo acesso.')
                value,token=access_action(p,self.get_access_session())
                if token:
                    # Não devolver o token Supabase nem o cookie de sessão no JSON.
                    self.send_response(200);raw=json.dumps(value,ensure_ascii=False).encode('utf-8')
                    self.send_header('Set-Cookie','vf_company_session='+token+'; HttpOnly; SameSite=Strict; Path=/')
                    self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store')
                    self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
                return self.reply(value)
            except (ValueError,KeyError,TypeError) as exc:return self.reply(dict(error=str(exc)),status=400)
            except Exception:return self.reply(dict(error='Não foi possível concluir o acesso. Contate o suporte.'),status=500)
        if self.path == '/api/login':
            try:
                if access_manager().enabled:raise ValueError('Use seu e-mail e senha na nova tela de acesso.')
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=8192:raise ValueError('Solicitação de acesso muito grande.')
                p=json.loads(self.rfile.read(size))
                res=handle_login(p)
                cookie_hdr = 'vf_company_session=' + res['token'] + '; HttpOnly; SameSite=Lax; Path=/'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Set-Cookie', cookie_hdr)
                self.send_header('Cache-Control', 'no-store')
                data = json.dumps(res, ensure_ascii=False).encode('utf8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers(); self.wfile.write(data)
                return
            except (ValueError, KeyError) as exc: return self.reply(dict(error=str(exc)), status=400)
            except Exception: traceback.print_exc(); return self.reply(dict(error='Erro no login.'), status=500)
        if self.path == '/api/logout':
            cookie = SimpleCookie()
            try: cookie.load(self.headers.get('Cookie', ''))
            except Exception: pass
            v = cookie.get('vf_company_session')
            if v and v.value in SESSIONS: SESSIONS.pop(v.value, None)
            cookie_hdr = 'vf_company_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Set-Cookie', cookie_hdr)
            self.send_header('Cache-Control', 'no-store')
            data = json.dumps(dict(ok=True), ensure_ascii=False).encode('utf8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers(); self.wfile.write(data)
            return
        if self.path != '/api/action': return self.reply(dict(error='Recurso não encontrado.'),status=404)
        if self.headers.get('Sec-Fetch-Site') == 'cross-site' or not secrets.compare_digest(self.headers.get('X-VF-CSRF',''),CSRF): return self.reply(dict(error='Recarregue a página.'),status=403)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=12*1024*1024: raise ValueError('Arquivo/requisição excede 12 MB.')
            p=json.loads(self.rfile.read(size))
            session_cid = self.get_company_session()
            registering=p.get('action')=='save_catalog' and p.get('kind')=='company' and not p.get('id')
            importing=p.get('action')=='import_legacy'
            if access_manager().enabled:
                guard_access(p,self.get_access_session())
                expected_company=self.headers.get('X-VF-Company','')
                if expected_company and expected_company!=p['cid']:return self.reply(dict(error='A empresa mudou. Atualize a tela.'),status=409)
            elif not PREVIEW:
                if not session_cid and not (registering or importing or p.get('action') in ('shutdown','lookup_public')):return self.reply(dict(error='Entre na empresa para continuar.'),status=401)
                if session_cid and p.get('action')=='save_catalog' and p.get('kind')=='company' and p.get('id') and p['id']!=session_cid:return self.reply(dict(error='Cadastro pertence a outra empresa.'),status=403)
                expected_company=self.headers.get('X-VF-Company','')
                if session_cid and ((expected_company and expected_company!=session_cid) or (str(p.get('action','')).startswith(('editor_','simple_')) and p.get('cid')!=session_cid)):
                    return self.reply(dict(error='A empresa foi alterada em outro acesso. Recarregue a página antes de continuar; nenhuma edição foi gravada em outra empresa.'),status=409)
                p['cid']=session_cid or ''
            elif session_cid:p['cid']=session_cid
            value=action(p); self.reply(value)
        except (ValueError,KeyError,TypeError,sqlite3.IntegrityError) as exc: self.reply(dict(error=str(exc)),status=400)
        except Exception:
            # Nunca registrar corpo da requisição: pode conter a senha do A1.
            traceback.print_exc(); self.reply(dict(error='Falha interna. Consulte o console do aplicativo.'),status=500)

def main():
    global STORE, PREVIEW, ALLOW_REMOTE, HTTPD
    parser=argparse.ArgumentParser()
    parser.add_argument('--preview',action='store_true')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--allow-remote',action='store_true',help='Permitir conexões remotas / rede local')
    parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','8787')))
    from desktop_storage import data_directory,migrate_bundled
    parser.add_argument('--data-dir',default=str(data_directory(ROOT)))
    parser.add_argument('--host',default=os.environ.get('VF_HOST','127.0.0.1'))
    parser.add_argument('--strictPort',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args();PREVIEW=args.preview
    ALLOW_REMOTE=args.allow_remote or os.environ.get('VF_ALLOW_REMOTE') == '1' or args.host != '127.0.0.1'
    if not PREVIEW:migrate_bundled(ROOT,Path(args.data_dir))
    STORE=Store(Path(args.data_dir)/'vf.sqlite3'); FiscalStore(STORE);EventStore(STORE)
    host=args.host if (PREVIEW or ALLOW_REMOTE) else '127.0.0.1'
    try: server=HTTPServer((host,args.port),Handler)
    except OSError:
        print('A porta está ocupada. Abra http://127.0.0.1:'+str(args.port)+' ou encerre a outra instância.');return 1
    print('VF Emissor Web '+VERSION+' — http://127.0.0.1:'+str(args.port),flush=True)
    print('Dados locais: '+str(STORE.path.parent),flush=True)
    HTTPD=server
    if not args.no_browser and not PREVIEW:
        import webbrowser, threading
        threading.Timer(0.8,lambda:webbrowser.open('http://127.0.0.1:'+str(args.port))).start()
    import threading
    maintenance_stop=threading.Event()
    if not PREVIEW:__import__('business_runtime').start_maintenance(STORE.path.parent,maintenance_stop)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: maintenance_stop.set();CERTS.clear();server.server_close();STORE.db.close()
    return 0

if __name__=='__main__':sys.exit(main())
