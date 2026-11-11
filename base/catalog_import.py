"""Importação assistida de cadastros, sem sobrescrever registros existentes."""
import csv,io,re,unicodedata,uuid,json,datetime,zipfile
from pathlib import Path
from core import valid_document,document,number

def normalize(v):return ''.join(c for c in unicodedata.normalize('NFKD',str(v).lower()) if not unicodedata.combining(c)).replace(' ','').replace('/','').replace('_','')
ALIASES={'codigo':'code','descricao':'name','nome':'name','ncm':'NCM','unidade':'unit','preco':'price','razaosocial':'xNome','cpfcnpj':'CNPJCPF','cnpj':'CNPJCPF','cpf':'CNPJCPF','ie':'IE','logradouro':'xLgr','numero':'nro','complemento':'xCpl','bairro':'xBairro','ibge':'cMun','municipio':'xMun','uf':'UF','cep':'CEP','telefone':'Fone','email':'Email','indiedest':'indIEDest','gtin':'gtin'}

def read_rows(path):
    path=Path(path)
    if path.stat().st_size>10*1024*1024:raise ValueError('Planilha excede 10 MB.')
    if path.suffix.lower()=='.csv':
        data=path.read_text('utf-8-sig');sample=data[:8192]
        try:delimiter=csv.Sniffer().sniff(sample,delimiters=';,\t').delimiter
        except csv.Error:delimiter=';'
        rows=list(csv.reader(io.StringIO(data),delimiter=delimiter))
    elif path.suffix.lower()=='.xlsx':
        with zipfile.ZipFile(path) as z:
            if sum(i.file_size for i in z.infolist())>100*1024*1024 or len(z.infolist())>10000:raise ValueError('XLSX excede o limite descompactado.')
        import openpyxl
        wb=openpyxl.load_workbook(path,read_only=True,data_only=False,keep_links=False)
        try:
            rows=[]
            for row in wb.active.iter_rows():
                if any(c.data_type=='f' for c in row):raise ValueError('Remova fórmulas da planilha antes de importar.')
                rows.append(['' if c.value is None else str(c.value) for c in row])
                if len(rows)>10001:raise ValueError('Limite de 10.000 cadastros.')
        finally:wb.close()
    else:raise ValueError('Selecione CSV UTF-8 ou XLSX.')
    if not rows or len(rows)>10001:raise ValueError('Planilha vazia ou acima de 10.000 cadastros.')
    return rows

def validate_row(kind,data):
    errors=[]
    if kind=='product':
        for k in ('code','name','NCM','unit','price'):
            if not data.get(k,'').strip():errors.append('Informe '+k)
        if not re.fullmatch('[0-9]{8}',data.get('NCM','')):errors.append('NCM deve ter 8 dígitos (preserve zeros à esquerda)')
        try:
            if number(data.get('price',''))<0:errors.append('Preço negativo')
        except ValueError:errors.append('Preço inválido')
    elif kind=='recipient':
        if not data.get('xNome'):errors.append('Informe razão social / nome')
        if not valid_document(data.get('CNPJCPF','')):errors.append('CPF/CNPJ inválido (preserve zeros à esquerda)')
        for k in ('xLgr','nro','xBairro','cMun','xMun','UF','CEP'):
            if not data.get(k):errors.append('Informe '+k)
        if not re.fullmatch('[0-9]{7}',data.get('cMun','')):errors.append('Código IBGE deve ter 7 dígitos')
        if not re.fullmatch('[0-9]{8}',document(data.get('CEP',''))):errors.append('CEP deve ter 8 dígitos')
        if data.get('UF','') not in 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split():errors.append('UF inválida')
        if data.get('indIEDest','9') not in ('1','2','9'):errors.append('indIEDest deve ser 1, 2 ou 9')
        if data.get('indIEDest')=='1' and not data.get('IE'):errors.append('Contribuinte precisa de IE')
    else:raise ValueError('Tipo de cadastro não permitido.')
    return errors

def preview(store,cid,kind,path):
    rows=read_rows(path);headers=rows[0];allowed={'product':('code','name','NCM','unit','price','gtin'),'recipient':('xNome','CNPJCPF','IE','xLgr','nro','xCpl','xBairro','cMun','xMun','UF','CEP','Fone','Email','indIEDest')}[kind]
    mapping=[v if v in allowed else ALIASES.get(normalize(v),'') for v in headers]
    mapped=[v for v in mapping if v]
    if len(mapped)!=len(set(mapped)):raise ValueError('Há colunas duplicadas para o mesmo campo.')
    key='code' if kind=='product' else 'CNPJCPF';canonical=(lambda x:str(x).casefold()) if kind=='product' else document
    existing={canonical(p.get(key,'')) for _,p in store.list(kind,cid)};seen=set();result=[]
    for line,row in enumerate(rows[1:],2):
        if not any(str(v).strip() for v in row):continue
        data={k:str(v).strip() for k,v in zip(mapping,row) if k in allowed}
        if kind=='recipient':data.setdefault('indIEDest','9');data['CNPJCPF']=document(data.get('CNPJCPF',''));data['CEP']=document(data.get('CEP',''));data['UF']=data.get('UF','').upper()
        errors=validate_row(kind,data);identity=canonical(data.get(key,''))
        if identity in existing:errors.append('Cadastro já existe: não será sobrescrito')
        if identity in seen:errors.append('Cadastro duplicado na planilha')
        seen.add(identity);result.append(dict(line=line,data=data,errors=errors))
    return result

def apply_import(store,cid,kind,rows):
    store.get('company','',cid)
    if not rows or any(r['errors'] for r in rows):raise ValueError('Corrija todos os erros da prévia antes de importar.')
    key='code' if kind=='product' else 'CNPJCPF';canonical=(lambda x:str(x).casefold()) if kind=='product' else document
    now=datetime.datetime.now().astimezone().isoformat();ids=[]
    with store.db:
        store.db.execute('UPDATE records SET updated=updated WHERE 0')
        existing={canonical(p.get(key,'')) for _,p in store.list(kind,cid)}
        for row in rows:
            d=row['data'];identity=canonical(d.get(key,''))
            if validate_row(kind,d) or identity in existing:raise ValueError('Cadastros mudaram ou linha inválida. Gere outra prévia.')
            existing.add(identity);rid=uuid.uuid4().hex;ids.append(rid)
            store.db.execute('INSERT INTO records VALUES(?,?,?,?,?)',(rid,kind,cid,json.dumps(d,ensure_ascii=False),now));store.db.execute('INSERT INTO audit(stamp,action,record) VALUES(?,?,?)',(now,'IMPORTAR '+kind,rid))
    return ids
