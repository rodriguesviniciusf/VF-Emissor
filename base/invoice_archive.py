"""Arquivo local e exportação de NF-e confirmadas; o banco continua sendo a fonte oficial do app."""
from pathlib import Path
import csv,hashlib,io,json,os,re,tempfile,zipfile
from lxml import etree as ET

NS={'n':'http://www.portalfiscal.inf.br/nfe'}

def atomic_write(file,data,immutable=False):
    file=Path(file);file.parent.mkdir(parents=True,exist_ok=True)
    if file.exists():
        old=file.read_bytes()
        if old==data:return
        if immutable:raise ValueError('Já existe um arquivo diferente para a mesma nota: '+str(file))
    handle,name=tempfile.mkstemp(prefix='.vf-',suffix='.tmp',dir=file.parent)
    try:
        with os.fdopen(handle,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(name,file)
    finally:
        if os.path.exists(name):os.unlink(name)

def archive_path(root,doc):
    cnpj=doc['cnpj'];key=doc['access_key']
    if not re.fullmatch('[0-9]{14}',cnpj) or not re.fullmatch('[0-9]{44}',key):raise ValueError('Identificação inválida para arquivar XML.')
    if doc['environment'] not in ('1','2'):raise ValueError('Ambiente inválido para arquivo.')
    month='20'+key[2:4]+'-'+key[4:6]
    return Path(root)/cnpj/('producao' if doc['environment']=='1' else 'homologacao')/month

def archive_document(root,doc):
    folder=archive_path(root,doc);key=doc['access_key'];files=[]
    digest=hashlib.sha256(doc['signed_xml']).hexdigest()[:16]
    signed=folder/'assinadas'/(key+'-'+digest+'-assinado.xml')
    atomic_write(signed,doc['signed_xml'],immutable=True);files.append(signed)
    if doc.get('response_xml'):
        response=folder/'retornos'/(key+'-'+hashlib.sha256(doc['response_xml']).hexdigest()[:16]+'-retorno.xml')
        atomic_write(response,doc['response_xml'],immutable=True);files.append(response)
    if doc['status'] in ('AUTORIZADA','CANCELADA') and doc.get('proc_xml'):
        validate_issued_xml(doc)
        output=folder/'emitidas'/(key+'-procNFe.xml')
        atomic_write(output,doc['proc_xml'],immutable=True);files.append(output)
    metadata={key:doc.get(key) for key in ('cnpj','environment','series','number','access_key','status','protocol','reason','updated')}
    atomic_write(folder/(key+'-situacao.json'),json.dumps(metadata,ensure_ascii=False,indent=2).encode('utf-8'))
    return files

def validate_issued_xml(doc):
    if doc['status'] not in ('AUTORIZADA','CANCELADA') or not doc.get('proc_xml'):raise ValueError('A nota não tem autorização registrada.')
    parser=ET.XMLParser(resolve_entities=False,no_network=True)
    root=ET.fromstring(doc['proc_xml'],parser)
    inf=root.find('n:NFe/n:infNFe',NS);protocol=root.find('n:protNFe/n:infProt',NS)
    if inf is None or protocol is None:raise ValueError('XML autorizado incompleto.')
    key=doc['access_key']
    if inf.get('Id')!='NFe'+key or protocol.findtext('n:chNFe',namespaces=NS)!=key:raise ValueError('Chave divergente no XML autorizado.')
    if protocol.findtext('n:cStat',namespaces=NS) not in ('100','150'):raise ValueError('O XML não contém protocolo de autorização.')
    if inf.findtext('n:ide/n:tpAmb',namespaces=NS)!=doc['environment'] or protocol.findtext('n:tpAmb',namespaces=NS)!=doc['environment']:raise ValueError('Ambiente divergente no XML.')
    return inf

def issued_metadata(fiscal,company,period='',state='AUTORIZADA',environment=None):
    query="SELECT id,cnpj,environment,series,number,access_key,status,protocol,updated,json_extract(snapshot,'$.recipient.xNome') AS recipient FROM fiscal_documents WHERE company=? AND proc_xml IS NOT NULL AND status IN ('AUTORIZADA','CANCELADA')"
    args=[company]
    if environment:
        query+=' AND environment=?';args.append(environment)
    if period:
        if not re.fullmatch('[0-9]{4}-[0-9]{2}',period) or not 1<=int(period[5:])<=12:raise ValueError('Período inválido. Use AAAA-MM.')
        query+=' AND substr(access_key,3,4)=?';args.append(period[2:4]+period[5:])
    if state in ('AUTORIZADA','CANCELADA'):query+=' AND status=?';args.append(state)
    query+=' ORDER BY access_key DESC'
    cursor=fiscal.db.execute(query,args);columns=[d[0] for d in cursor.description]
    return [dict(zip(columns,row)) for row in cursor.fetchall()]

def export_issued(fiscal,company,ids,target,include_pdf=False,archive_root=None):
    ids=list(dict.fromkeys(ids))
    if not ids:raise ValueError('Nenhuma nota emitida selecionada.')
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    handle,temp=tempfile.mkstemp(prefix='.vf-export-',suffix='.zip',dir=target.parent);os.close(handle)
    records=[];csv_buffer=io.StringIO(newline='')
    writer=csv.writer(csv_buffer,delimiter=';')
    writer.writerow(['Chave','Numero','Serie','Emissao','Destinatario','Total','Situacao','Protocolo','Ambiente'])
    try:
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as package:
            for rid in ids:
                doc=fiscal.get(company,rid);inf=validate_issued_xml(doc);key=doc['access_key']
                path=doc['cnpj']+'/'+('producao' if doc['environment']=='1' else 'homologacao')+'/20'+key[2:4]+'-'+key[4:6]+'/'+key
                package.writestr(path+'-procNFe.xml',doc['proc_xml'])
                if include_pdf:
                    from fiscal import render_danfe
                    package.writestr(path+('-DANFE.pdf' if doc['environment']=='1' else '-DANFE-HOMOLOGACAO.pdf'),render_danfe(doc['proc_xml']))
                snapshot=json.loads(doc['snapshot'])
                writer.writerow([key,doc['number'],doc['series'],inf.findtext('n:ide/n:dhEmi',namespaces=NS),snapshot.get('recipient',{}).get('xNome',''),inf.findtext('n:total/n:ICMSTot/n:vNF',namespaces=NS),doc['status'],doc['protocol'],'PRODUCAO' if doc['environment']=='1' else 'HOMOLOGACAO'])
                records.append(dict(key=key,environment=doc['environment'],status=doc['status'],sha256=hashlib.sha256(doc['proc_xml']).hexdigest()))
                if archive_root:
                    try:archive_document(archive_root,doc)
                    except (OSError,ValueError):pass
            package.writestr('resumo.csv',('\ufeff'+csv_buffer.getvalue()).encode('utf-8'))
            package.writestr('manifesto.json',json.dumps(dict(ambientes=sorted({r['environment'] for r in records}),notas=records),ensure_ascii=False,indent=2).encode('utf-8'))
        os.replace(temp,target)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return dict(path=str(target),count=len(records))

def sync_company_archive(fiscal,company,archive_root):
    cursor=fiscal.db.execute('SELECT id FROM fiscal_documents WHERE company=? ORDER BY created',(company,))
    ids=[r[0] for r in cursor.fetchall()];errors=[]
    for rid in ids:
        try:archive_document(archive_root,fiscal.get(company,rid))
        except (OSError,ValueError) as exc:errors.append(str(exc))
    return dict(count=len(ids)-len(errors),errors=errors)
