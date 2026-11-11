"""Eventos modelo 55/AL. Assinatura, reserva, envio explícito e retorno correlacionado."""
import copy,datetime,hashlib,json,re,secrets,sqlite3,uuid
from pathlib import Path
from lxml import etree as ET
from cryptography.hazmat.primitives import serialization
from core import document,valid_document
from fiscal import NS,DS,TZ,tag,text,parse_xml,serialize,SefazTransport,FiscalStore,validate_schema
KINDS={'110111':('event_cancel','eventoCancNFe_v1.00.xsd','envEventoCancNFe_v1.00.xsd','retEnvEventoCancNFe_v1.00.xsd','procEventoCancNFe_v1.00.xsd'),'110110':('event_cce','CCe_v1.00.xsd','envCCe_v1.00.xsd','retEnvCCe_v1.00.xsd','procCCeNFe_v1.00.xsd')}

def now():return datetime.datetime.now(TZ)
def ensure_event_schema(store):
    if store.db.execute('PRAGMA user_version').fetchone()[0]>=4:return
    p=store.path.parent/'backups';p.mkdir(exist_ok=True);store.backup(p/('antes-eventos-'+uuid.uuid4().hex+'.sqlite3'))
    try:
        store.db.executescript('''BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS fiscal_events(id TEXT PRIMARY KEY,company TEXT NOT NULL,document TEXT NOT NULL,environment TEXT NOT NULL,kind TEXT NOT NULL,identity TEXT NOT NULL,sequence INTEGER NOT NULL,year INTEGER,series INTEGER,start_number INTEGER,end_number INTEGER,status TEXT NOT NULL,signed_xml BLOB NOT NULL,response_xml BLOB,proc_xml BLOB,reason TEXT NOT NULL DEFAULT '',created TEXT NOT NULL,updated TEXT NOT NULL,UNIQUE(company,environment,identity));
        CREATE INDEX IF NOT EXISTS event_scope ON fiscal_events(company,environment,document);
        CREATE TABLE IF NOT EXISTS event_history(id INTEGER PRIMARY KEY,event TEXT NOT NULL,stamp TEXT NOT NULL,action TEXT NOT NULL,details TEXT NOT NULL,data BLOB);
        PRAGMA user_version=4;COMMIT;''')
    except Exception:store.db.rollback();raise

def schema_event(kind,index,data):
    folder,name=KINDS[kind][0],KINDS[kind][index]
    schema=ET.XMLSchema(ET.parse(str(Path(__file__).parent/'schemas'/folder/name)))
    if not schema.validate(parse_xml(data)):raise ValueError('Evento inválido no XSD: '+'; '.join(e.message for e in list(schema.error_log)[:3]))

def verify_signature(root,certificate):
    from signxml import XMLVerifier,SignatureConfiguration,SignatureMethod,DigestAlgorithm
    cfg=SignatureConfiguration(signature_methods=frozenset({SignatureMethod.RSA_SHA1}),digest_algorithms=frozenset({DigestAlgorithm.SHA1}))
    verified=XMLVerifier().verify(root,x509_cert=certificate.cert.public_bytes(serialization.Encoding.PEM),expect_config=cfg)
    return verified.signed_xml

def sign(root,id_,certificate):
    from signxml import XMLSigner,methods
    class RequiredSigner(XMLSigner):
        def check_deprecated_methods(self):pass
    signer=RequiredSigner(method=methods.enveloped,signature_algorithm='rsa-sha1',digest_algorithm='sha1',c14n_algorithm='http://www.w3.org/TR/2001/REC-xml-c14n-20010315');signer.namespaces={'ds':DS}
    key=certificate.key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    signed=signer.sign(root,key=key,cert=certificate.cert.public_bytes(serialization.Encoding.PEM),reference_uri='#'+id_)
    verified=verify_signature(signed,certificate)
    if verified.get('Id')!=id_:raise ValueError('Assinatura não corresponde ao evento.')
    return serialize(signed)

def check_certificate(certificate,cnpj):
    if certificate.cnpj!=cnpj:raise ValueError('A1 não corresponde ao emitente do evento.')
    current=now().astimezone(datetime.timezone.utc)
    if not certificate.cert.not_valid_before_utc<=current<certificate.cert.not_valid_after_utc:raise ValueError('Certificado fora da validade.')

def checked_text(value,minimum,maximum):
    value=str(value).strip()
    if not minimum<=len(value)<=maximum or any(ord(c)<32 for c in value):raise ValueError('Texto deve ter '+str(minimum)+' a '+str(maximum)+' caracteres, sem quebras de linha.')
    return value

def build_event(doc,kind,seq,content,certificate,when=None):
    if kind not in KINDS:raise ValueError('Evento não suportado.')
    if doc['status']!='AUTORIZADA' or not doc['proc_xml']:raise ValueError('Evento exige NF-e autorizada com XML/protocolo registrado.')
    check_certificate(certificate,doc['cnpj']);content=checked_text(content,15,255 if kind=='110111' else 1000)
    if not 1<=seq<=(1 if kind=='110111' else 20):raise ValueError('Sequência de evento inválida.')
    when=when or now();id_='ID'+kind+doc['access_key']+f'{seq:02d}'
    root=ET.Element('{'+NS+'}evento',nsmap={None:NS},versao='1.00');inf=tag(root,'infEvento',Id=id_)
    for k,v in [('cOrgao','27'),('tpAmb',doc['environment']),('CNPJ',doc['cnpj']),('chNFe',doc['access_key']),('dhEvento',when.isoformat(timespec='seconds')),('tpEvento',kind),('nSeqEvento',seq),('verEvento','1.00')]:tag(inf,k,v)
    detail=tag(inf,'detEvento',versao='1.00');tag(detail,'descEvento','Cancelamento' if kind=='110111' else 'Carta de Correcao')
    if kind=='110111':
        if not re.fullmatch('[0-9]{15}',doc['protocol']):raise ValueError('Protocolo de autorização inválido.')
        tag(detail,'nProt',doc['protocol']);tag(detail,'xJust',content)
    else:
        tag(detail,'xCorrecao',content)
        schema=ET.parse(str(Path(__file__).parent/'schemas/event_cce/leiauteCCe_v1.00.xsd'))
        literal=schema.xpath('//xs:element[@name="xCondUso"]//xs:enumeration/@value',namespaces={'xs':'http://www.w3.org/2001/XMLSchema'})[-1];tag(detail,'xCondUso',literal)
    data=sign(root,id_,certificate);schema_event(kind,1,data);return data

def build_inutil(company,environment,year,series,start,end,reason,certificate):
    cnpj=document(company['CNPJCPF']);check_certificate(certificate,cnpj)
    if company.get('UF')!='AL' or not valid_document(cnpj):raise ValueError('Inutilização disponível somente para emitente AL com CNPJ válido.')
    if environment not in ('1','2') or year!=now().year:raise ValueError('Selecione o ambiente e o ano corrente. Anos anteriores exigem análise específica.')
    if not 0<=series<=999 or not 1<=start<=end<=999999999 or end-start>=10000:raise ValueError('Faixa inválida (máximo 10.000 números).')
    reason=checked_text(reason,15,255);id_='ID27'+str(year)[-2:]+cnpj+'55'+f'{series:03d}{start:09d}{end:09d}'
    root=ET.Element('{'+NS+'}inutNFe',nsmap={None:NS},versao='4.00');inf=tag(root,'infInut',Id=id_)
    for k,v in [('tpAmb',environment),('xServ','INUTILIZAR'),('cUF','27'),('ano',str(year)[-2:]),('CNPJ',cnpj),('mod','55'),('serie',series),('nNFIni',start),('nNFFin',end),('xJust',reason)]:tag(inf,k,v)
    data=sign(root,id_,certificate);validate_schema(data,'inutNFe_v4.00.xsd');return data

def reserved_ranges(store,cid,environment,series):
    return store.db.execute("SELECT year,start_number,end_number,status FROM fiscal_events WHERE company=? AND environment=? AND kind='INUT' AND series=? AND status NOT IN ('REJEITADO','DESCARTADO')",(cid,environment,int(series))).fetchall()

def check_number_available(store,cid,note):
    year=datetime.datetime.fromisoformat(note['issued_at']).year if note.get('issued_at') else now().year
    for y,start,end,status in reserved_ranges(store,cid,note.get('environment','2'),note['series']):
        if y==year and start<=int(note['number'])<=end:raise ValueError('Número abrangido por inutilização registrada ou pendente. Consulte Eventos fiscais.')

class EventStore:
    def __init__(self,store):self.store=store;self.db=store.db;ensure_event_schema(store)
    def get(self,cid,rid):
        cur=self.db.execute('SELECT * FROM fiscal_events WHERE company=? AND id=?',(cid,rid));row=cur.fetchone()
        if not row:raise ValueError('Evento não pertence à empresa da sessão.')
        return dict(zip([d[0] for d in cur.description],row))
    def list(self,cid,env):
        cur=self.db.execute('SELECT id FROM fiscal_events WHERE company=? AND environment=? ORDER BY created DESC',(cid,env));return [self.get(cid,r[0]) for r in cur.fetchall()]
    def history(self,rid,action,details='',data=None):self.db.execute('INSERT INTO event_history(event,stamp,action,details,data) VALUES(?,?,?,?,?)',(rid,now().isoformat(),action,details,data))
    def doc(self,cid,rid):return FiscalStore(self.store).get(cid,rid)
    def company(self,cid,env):
        co=self.store.get('company','',cid)
        if co.get('environment','2')!=env:raise ValueError('Ative o ambiente correspondente ao evento nas configurações.')
        if env=='1' and not co.get('production_enabled'):raise ValueError('Produção desativada.')
        return co
    def prepare(self,cid,doc_id,kind,content,certificate,acknowledged=False,allow_late=False):
        doc=self.doc(cid,doc_id);self.company(cid,doc['environment'])
        if not acknowledged:raise ValueError('Confirme as condições de uso do evento.')
        if kind=='110111':
            auth=ET.fromstring(doc['proc_xml']).find('n:protNFe/n:infProt',{'n':NS}) if doc['proc_xml'] else None
            stamp=text(auth,'n:dhRecbto')
            if not stamp:raise ValueError('Data de autorização ausente.')
            if now()-datetime.datetime.fromisoformat(stamp)>datetime.timedelta(hours=24) and not allow_late:raise ValueError('Cancelamento após 24 horas: exige revisão e confirmação de tratamento extemporâneo conforme SEFAZ AL.')
        with self.db:
            self.db.execute('UPDATE fiscal_events SET updated=updated WHERE 0')
            if self.db.execute("SELECT 1 FROM fiscal_events WHERE company=? AND document=? AND kind<>? AND status IN ('ENVIANDO','INCERTO','PENDENTE')",(cid,doc_id,kind)).fetchone():raise ValueError('Outro evento da nota está pendente ou incerto. Consulte antes de continuar.')
            previous=self.db.execute('SELECT id,status,sequence FROM fiscal_events WHERE company=? AND document=? AND kind=? ORDER BY sequence DESC LIMIT 1',(cid,doc_id,kind)).fetchone()
            if previous and previous[1] in ('ENVIANDO','INCERTO','PENDENTE'):raise ValueError('Há evento pendente ou incerto. Consulte antes de preparar outro.')
            if kind=='110111' and previous and previous[1]=='REGISTRADO':raise ValueError('Cancelamento já registrado.')
            revise=previous and previous[1] in ('PREPARADO','REJEITADO','DESCARTADO')
            seq=previous[2] if revise else (previous[2]+1 if previous else 1)
            data=build_event(doc,kind,seq,content,certificate);identity=kind+':'+doc['access_key']+':'+str(seq);rid=previous[0] if revise else uuid.uuid4().hex;stamp=now().isoformat()
            if revise:
                old=self.get(cid,rid);self.history(rid,'REVISAO',old['reason'],old['signed_xml']);self.db.execute("UPDATE fiscal_events SET signed_xml=?,response_xml=NULL,proc_xml=NULL,status='PREPARADO',reason='',updated=? WHERE id=?",(data,stamp,rid))
            else:self.db.execute('INSERT INTO fiscal_events(id,company,document,environment,kind,identity,sequence,status,signed_xml,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(rid,cid,doc_id,doc['environment'],kind,identity,seq,'PREPARADO',data,stamp,stamp))
            self.history(rid,'PREPARADO','Condições confirmadas; nenhum envio realizado.',data)
        self.archive(cid,rid);return rid
    def check_range(self,cid,env,year,series,start,end,exclude=None):
        if self.db.execute('SELECT 1 FROM fiscal_documents WHERE company=? AND environment=? AND series=? AND number BETWEEN ? AND ?',(cid,env,series,start,end)).fetchone():raise ValueError('Faixa contém número reservado ou emitido no aplicativo.')
        for _,note in self.store.list('note',cid):
            if note.get('environment','2')==env and str(note.get('series'))==str(series) and str(note.get('number','')).isdigit() and start<=int(note['number'])<=end:raise ValueError('Faixa contém rascunho/XML importado. Confira os números existentes.')
        if self.db.execute("SELECT 1 FROM fiscal_events WHERE company=? AND environment=? AND kind='INUT' AND year=? AND series=? AND start_number<=? AND end_number>=? AND status NOT IN ('REJEITADO','DESCARTADO') AND id<>?",(cid,env,year,series,end,start,exclude or '')).fetchone():raise ValueError('Faixa sobrepõe inutilização registrada ou pendente.')
    def prepare_inutil(self,cid,year,series,start,end,reason,certificate,acknowledged=False):
        co=self.store.get('company','',cid);env=co.get('environment','2');self.company(cid,env)
        if not acknowledged:raise ValueError('Confirme que conferiu o histórico completo de numeração, inclusive outros emissores.')
        data=build_inutil(co,env,year,series,start,end,reason,certificate);identity=f'INUT:{year}:{series}:{start}:{end}';stamp=now().isoformat()
        with self.db:
            self.db.execute('UPDATE fiscal_events SET updated=updated WHERE 0');self.check_range(cid,env,year,series,start,end)
            old=self.db.execute('SELECT id,status FROM fiscal_events WHERE company=? AND environment=? AND identity=?',(cid,env,identity)).fetchone()
            if old and old[1] not in ('REJEITADO','DESCARTADO'):raise ValueError('Pedido de inutilização já existe.')
            rid=old[0] if old else uuid.uuid4().hex
            if old:
                prev=self.get(cid,rid);self.history(rid,'REVISAO',prev['reason'],prev['signed_xml']);self.db.execute("UPDATE fiscal_events SET signed_xml=?,response_xml=NULL,proc_xml=NULL,status='PREPARADO',reason='',updated=? WHERE id=?",(data,stamp,rid))
            else:self.db.execute('INSERT INTO fiscal_events(id,company,document,environment,kind,identity,sequence,year,series,start_number,end_number,status,signed_xml,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(rid,cid,'',env,'INUT',identity,1,year,series,start,end,'PREPARADO',data,stamp,stamp))
            self.history(rid,'PREPARADO','Histórico externo confirmado pelo usuário.',data)
        self.archive(cid,rid);return rid
    def archive(self,cid,rid):
        try:
            e=self.get(cid,rid);cnpj=document(self.store.get('company','',cid)['CNPJCPF']);p=self.store.path.parent/'notas-fiscais'/cnpj/('producao' if e['environment']=='1' else 'homologacao')/'eventos'/rid;p.mkdir(parents=True,exist_ok=True)
            for name,field in [('assinado.xml','signed_xml'),('retorno.xml','response_xml'),('processado.xml','proc_xml')]:
                if e[field]:(p/(hashlib.sha256(e[field]).hexdigest()[:12]+'-'+name)).write_bytes(e[field])
        except Exception:
            import logging;logging.exception('Arquivamento de evento pendente')
    def discard(self,cid,rid):
        with self.db:
            changed=self.db.execute("UPDATE fiscal_events SET status='DESCARTADO',updated=? WHERE company=? AND id=? AND status='PREPARADO'",(now().isoformat(),cid,rid)).rowcount
            if changed!=1:raise ValueError('Somente pedido preparado e nunca enviado pode ser descartado. Incertos continuam protegidos.')
            self.history(rid,'DESCARTADO','Pedido local descartado antes de transmitir; XML e histórico preservados.')
    def begin(self,cid,rid,certificate):
        e=self.get(cid,rid);co=self.company(cid,e['environment']);check_certificate(certificate,document(co['CNPJCPF']));verify_signature(parse_xml(e['signed_xml']),certificate)
        if e['kind']=='INUT':
            validate_schema(e['signed_xml'],'inutNFe_v4.00.xsd')
            inf=parse_xml(e['signed_xml']).find('n:infInut',{'n':NS});expected=dict(tpAmb=e['environment'],ano=str(e['year'])[-2:],serie=str(e['series']),nNFIni=str(e['start_number']),nNFFin=str(e['end_number']),CNPJ=document(co['CNPJCPF']),mod='55',cUF='27')
            if any(text(inf,'n:'+k)!=v for k,v in expected.items()):raise ValueError('Pedido assinado diverge da faixa reservada.')
        else:
            schema_event(e['kind'],1,e['signed_xml']);inf=parse_xml(e['signed_xml']).find('n:infEvento',{'n':NS});doc=self.doc(cid,e['document']);expected=dict(tpAmb=e['environment'],chNFe=doc['access_key'],CNPJ=doc['cnpj'],tpEvento=e['kind'],nSeqEvento=str(e['sequence']),cOrgao='27')
            if any(text(inf,'n:'+k)!=v for k,v in expected.items()):raise ValueError('Evento assinado diverge da reserva.')
        with self.db:
            self.db.execute('UPDATE fiscal_events SET updated=updated WHERE 0')
            if e['kind']=='INUT':
                if e['year']!=now().year:raise ValueError('Pedido de ano anterior exige nova análise; não será transmitido automaticamente.')
                self.check_range(cid,e['environment'],e['year'],e['series'],e['start_number'],e['end_number'],rid)
            elif self.doc(cid,e['document'])['status']!='AUTORIZADA':raise ValueError('Nota não está mais autorizada. Recarregue a situação.')
            changed=self.db.execute("UPDATE fiscal_events SET status='ENVIANDO',updated=? WHERE company=? AND id=? AND status='PREPARADO' AND signed_xml=?",(now().isoformat(),cid,rid,e['signed_xml'])).rowcount
            if changed!=1:raise ValueError('Evento não pode ser reenviado. Consulte o retorno primeiro.')
            self.history(rid,'ENVIANDO','Estado persistido antes da comunicação.')
        return e
    def uncertain(self,cid,rid,message,data=None):
        with self.db:
            self.db.execute("UPDATE fiscal_events SET status='INCERTO',reason=?,response_xml=COALESCE(?,response_xml),updated=? WHERE company=? AND id=? AND status NOT IN ('REGISTRADO')",(message,data,now().isoformat(),cid,rid));self.history(rid,'INCERTO',message,data)
        self.archive(cid,rid)
    def apply(self,cid,rid,data,from_query=False,imported=False):
        e=self.get(cid,rid);root=parse_xml(data)
        if e['status']=='REGISTRADO':raise ValueError('Evento já finalizado; retorno anterior preservado.')
        if e['status'] not in ('ENVIANDO','INCERTO','PENDENTE'):raise ValueError('Não há comunicação pendente para aplicar este retorno.')
        if e['kind']=='INUT':
            roots=root.xpath('//*[local-name()="retInutNFe" and namespace-uri()=$ns]',ns=NS)
            if len(roots)!=1:raise ValueError('Retorno de inutilização ausente ou ambíguo.')
            ret=roots[0];validate_schema(serialize(ret),'retInutNFe_v4.00.xsd');inf=ret.find('n:infInut',{'n':NS});code=text(inf,'n:cStat')
            expected=dict(tpAmb=e['environment'],cUF='27',ano=str(e['year'])[-2:],CNPJ=document(self.store.get('company','',cid)['CNPJCPF']),mod='55',serie=str(e['series']),nNFIni=str(e['start_number']),nNFFin=str(e['end_number']))
            if any(text(inf,'n:'+k)!=v for k,v in expected.items()):raise ValueError('Retorno não corresponde à faixa/emitente/ambiente solicitados.')
            status='REGISTRADO' if code=='102' else 'INCERTO' if code in ('256','563','108','109','999') else 'REJEITADO'
            proc=None
            if status=='REGISTRADO':
                if not re.fullmatch('[0-9]{15}',text(inf,'n:nProt')):raise ValueError('Protocolo de inutilização ausente.')
                p=ET.Element('{'+NS+'}ProcInutNFe',nsmap={None:NS},versao='4.00');p.append(parse_xml(e['signed_xml']));p.append(copy.deepcopy(ret));proc=serialize(p);validate_schema(proc,'procInutNFe_v4.00.xsd')
        else:
            roots=root.xpath('//*[local-name()="retEnvEvento" and namespace-uri()=$ns]',ns=NS)
            if len(roots)!=1:raise ValueError('Retorno de evento ausente ou ambíguo.')
            ret=roots[0];schema_event(e['kind'],3,serialize(ret))
            if text(ret,'n:tpAmb')!=e['environment'] or text(ret,'n:cOrgao')!='27':raise ValueError('Lote pertence a outro ambiente/órgão.')
            if text(ret,'n:cStat')!='128':raise ValueError('Lote não processado: '+text(ret,'n:cStat')+' '+text(ret,'n:xMotivo'))
            events=ret.findall('n:retEvento',{'n':NS})
            if len(events)!=1:raise ValueError('Retorno deve conter exatamente um evento.')
            returned=events[0];inf=returned.find('n:infEvento',{'n':NS});request=parse_xml(e['signed_xml']).find('n:infEvento',{'n':NS})
            for k in ('tpAmb','cOrgao','chNFe','tpEvento','nSeqEvento'):
                if text(inf,'n:'+k)!=text(request,'n:'+k):raise ValueError('Retorno não corresponde ao evento enviado: '+k)
            code=text(inf,'n:cStat');status='REGISTRADO' if code=='135' or code=='155' and e['kind']=='110111' else 'PENDENTE' if code=='136' else 'INCERTO' if code in ('573','108','109','999') else 'REJEITADO';proc=None
            if status in ('REGISTRADO','PENDENTE'):
                if not re.fullmatch('[0-9]{15}',text(inf,'n:nProt')):raise ValueError('Protocolo de evento ausente.')
                p=ET.Element('{'+NS+'}procEventoNFe',nsmap={None:NS},versao='1.00');p.append(parse_xml(e['signed_xml']));p.append(copy.deepcopy(returned));proc=serialize(p);schema_event(e['kind'],4,proc)
        reason=code+' — '+text(inf,'n:xMotivo')
        with self.db:
            changed=self.db.execute("UPDATE fiscal_events SET status=?,response_xml=?,proc_xml=?,reason=?,updated=? WHERE company=? AND id=? AND signed_xml=? AND status<>'REGISTRADO'",(status,data,proc,reason,now().isoformat(),cid,rid,e['signed_xml'])).rowcount
            if changed!=1:raise ValueError('Evento mudou durante a comunicação.')
            if imported:self.history(rid,'RETORNO_IMPORTADO','Procedência oficial declarada pelo usuário; validação local de schema/correlação, sem consulta online.',data)
            elif from_query:self.history(rid,'COMPROVANTE_CONSULTADO','Comprovante reconciliado pela consulta de protocolo.',data)
            self.history(rid,status,reason,data)
            if status=='REGISTRADO' and e['kind']=='110111':
                self.db.execute("UPDATE fiscal_documents SET status='CANCELADA',reason=?,updated=? WHERE company=? AND id=? AND status='AUTORIZADA'",(reason,now().isoformat(),cid,e['document']));FiscalStore(self.store)._history(e['document'],'CANCELADA',reason,proc)
        self.archive(cid,rid)
        if e['document']:FiscalStore(self.store)._archive_best_effort(cid,e['document'])
        return status

class EventService:
    def __init__(self,events,certificate,transport=None):self.events=events;self.certificate=certificate;self.transport=transport or SefazTransport(certificate)
    def send(self,cid,rid):
        e=self.events.begin(cid,rid,self.certificate)
        try:
            if e['kind']=='INUT':operation='inutil';body=e['signed_xml']
            else:
                operation='event';env=ET.Element('{'+NS+'}envEvento',nsmap={None:NS},versao='1.00');tag(env,'idLote','1');env.append(parse_xml(e['signed_xml']));body=serialize(env);schema_event(e['kind'],2,body)
            data=self.transport.request(operation,body);return self.events.apply(cid,rid,data)
        except Exception:
            self.events.uncertain(cid,rid,'Falha de comunicação/retorno. Consulte antes de qualquer nova tentativa.',locals().get('data'));raise
    def query(self,cid,rid):
        e=self.events.get(cid,rid)
        if e['kind']=='INUT':raise ValueError('Consulta automática de inutilização indisponível neste serviço. Confira a consulta oficial SEFAZ antes de qualquer novo pedido; a faixa permanece protegida.')
        self.events.company(cid,e['environment']);co=self.events.store.get('company','',cid);check_certificate(self.certificate,document(co['CNPJCPF']))
        d=self.events.doc(cid,e['document']);from fiscal import payload
        data=self.transport.request('query',payload('consSitNFe',tpAmb=e['environment'],xServ='CONSULTAR',chNFe=d['access_key']))
        root=parse_xml(data);matches=[];request=parse_xml(e['signed_xml']);inf=request.find('n:infEvento',{'n':NS})
        for proc in root.xpath('//*[local-name()="procEventoNFe" and namespace-uri()=$ns]',ns=NS):
            ev=proc.find('n:evento',{'n':NS});i=ev.find('n:infEvento',{'n':NS}) if ev is not None else None
            if i is not None and i.get('Id')==inf.get('Id'):matches.append(proc)
        if len(matches)!=1:
            with self.events.db:self.events.history(rid,'CONSULTA_SEM_COMPROVANTE','A consulta não trouxe comprovante correlacionado. Estado preservado.',data)
            raise ValueError('A consulta não trouxe comprovante correlacionado. Nenhum reenvio foi liberado.')
        proc=matches[0];returned_event=proc.find('n:evento',{'n':NS})
        def signature_values(node):return tuple(node.findtext(p,namespaces={'ds':DS}) for p in ('ds:Signature/ds:SignedInfo/ds:Reference/ds:DigestValue','ds:Signature/ds:SignatureValue'))
        if signature_values(returned_event)!=signature_values(request):raise ValueError('Consulta retornou outro conteúdo de evento.')
        import base64
        from signxml import XMLVerifier,SignatureConfiguration,SignatureMethod,DigestAlgorithm
        from cryptography import x509
        cert=x509.load_der_x509_certificate(base64.b64decode(request.findtext('ds:Signature/ds:KeyInfo/ds:X509Data/ds:X509Certificate',namespaces={'ds':DS})))
        cfg=SignatureConfiguration(signature_methods=frozenset({SignatureMethod.RSA_SHA1}),digest_algorithms=frozenset({DigestAlgorithm.SHA1}))
        XMLVerifier().verify(returned_event,x509_cert=cert.public_bytes(serialization.Encoding.PEM),expect_config=cfg)
        ret=proc.find('n:retEvento',{'n':NS});env=ET.Element('{'+NS+'}retEnvEvento',nsmap={None:NS},versao='1.00')
        for k,v in [('idLote','1'),('tpAmb',e['environment']),('verAplic','CONSULTA'),('cOrgao','27'),('cStat','128'),('xMotivo','Lote processado')]:tag(env,k,v)
        env.append(copy.deepcopy(ret));return self.events.apply(cid,rid,serialize(env),True)
