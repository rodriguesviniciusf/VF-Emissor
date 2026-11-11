"""Prévia e importação atômica de CSV/XLSX ou cadastros extraídos de uma NF-e."""
import csv,io,json,re,uuid,zipfile,unicodedata
from datetime import datetime
from pathlib import Path
from core import document,valid_document,number
from fiscal import parse_xml,text,NS

FIELDS=dict(product=['code','name','NCM','unit','price','gtin','CEST'],recipient=['xNome','CNPJCPF','IE','indIEDest','xLgr','nro','xCpl','xBairro','cMun','xMun','UF','CEP','Fone','Email'])
FIELDS['supplier']=FIELDS['recipient']
SHEETS=dict(product='Produtos',recipient='Clientes',supplier='Fornecedores')
def norm(value):return ''.join(c for c in unicodedata.normalize('NFD',str(value).casefold()) if c.isalnum() and not unicodedata.combining(c))
ALIASES={norm(k):v for k,v in {'codigo':'code','codigo proprio':'code','descricao':'name','nome do produto':'name','unidade':'unit','preco':'price','preco unitario':'price','razao social':'xNome','nome':'xNome','cpfcnpj':'CNPJCPF','cnpjcpf':'CNPJCPF','cnpj':'CNPJCPF','cpf':'CNPJCPF','logradouro':'xLgr','endereco':'xLgr','numero':'nro','complemento':'xCpl','bairro':'xBairro','ibge':'cMun','codigo ibge':'cMun','municipio':'xMun','estado':'UF','telefone':'Fone','email':'Email','ie':'IE','indicador ie':'indIEDest','cep':'CEP','ncm':'NCM','gtin':'gtin','cest':'CEST'}.items()}

ALIASES.update({norm(k):k for values in FIELDS.values() for k in values})

def validate(kind,data):
    errors=[]
    if kind=='product':
        if not data.get('code'):errors.append('Código obrigatório')
        if not data.get('name'):errors.append('Descrição obrigatória')
        if not re.fullmatch(r'\d{8}',data.get('NCM','')):errors.append('NCM deve ter 8 dígitos')
        if not data.get('unit') or len(data['unit'])>6:errors.append('Unidade obrigatória, até 6 caracteres')
        if not str(data.get('price','')).strip():errors.append('Preço obrigatório; informe zero quando aplicável')
        try:
            if number(data.get('price',''))<0:errors.append('Preço negativo')
        except ValueError:errors.append('Preço inválido')
    else:
        if not data.get('xNome'):errors.append('Nome/razão social obrigatório')
        if not valid_document(data.get('CNPJCPF','')):errors.append('CPF/CNPJ inválido; preserve zeros à esquerda')
        if data.get('UF') and data['UF'] not in 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split():errors.append('UF inválida')
        for k,size in [('CEP',8),('cMun',7)]:
            if data.get(k) and not re.fullmatch(r'\d{'+str(size)+'}',data[k]):errors.append(k+' deve ter '+str(size)+' dígitos')
        if data.get('indIEDest','9') not in ('1','2','9'):errors.append('Indicador de IE deve ser 1, 2 ou 9')
        if data.get('indIEDest')=='1' and not data.get('IE'):errors.append('Contribuinte precisa de IE')
    if any(len(str(v))>1000 or '\x00' in str(v) for v in data.values()):errors.append('Campo muito longo ou inválido')
    return errors

def canonical(kind,data):return str(data.get('code','')).casefold() if kind=='product' else document(data.get('CNPJCPF',''))

def read_sheet(raw,filename,kind):
    if len(raw)>8*1024*1024:raise ValueError('A planilha deve ter até 8 MB.')
    if str(filename).lower().endswith('.csv'):
        try:data=raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:data=raw.decode('cp1252')
            except UnicodeDecodeError:raise ValueError('Salve o CSV em UTF-8.')
        try:delimiter=csv.Sniffer().sniff(data[:8192],delimiters=';,\t').delimiter
        except csv.Error:delimiter=';'
        result=[]
        for row in csv.reader(io.StringIO(data),delimiter=delimiter):
            result.append(row)
            if len(result)>10001:raise ValueError('Máximo de 10.000 cadastros por arquivo.')
        return result
    if not str(filename).lower().endswith('.xlsx'):raise ValueError('Use CSV, XLSX ou XML de NF-e.')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if sum(i.file_size for i in z.infolist())>60*1024*1024 or len(z.infolist())>10000:raise ValueError('XLSX excede o limite descompactado.')
    import openpyxl
    wb=openpyxl.load_workbook(io.BytesIO(raw),read_only=True,data_only=False,keep_links=False)
    try:
        sheet=wb[SHEETS[kind]] if SHEETS[kind] in wb.sheetnames else wb.active
        result=[]
        for row in sheet.iter_rows():
            if len(row)>150:raise ValueError('Máximo de 150 colunas.')
            if any(c.data_type=='f' for c in row):raise ValueError('Remova as fórmulas antes de importar.')
            result.append(['' if c.value is None else str(c.value) for c in row])
            if len(result)>10001:raise ValueError('Máximo de 10.000 cadastros por arquivo.')
        return result
    finally:wb.close()

def xml_rows(raw,kind,party=''):
    root=parse_xml(raw)
    if root.tag not in ('{'+NS+'}NFe','{'+NS+'}nfeProc'):raise ValueError('Selecione um XML de NF-e, modelo 55.')
    inf=root.find('n:NFe/n:infNFe',{'n':NS}) if root.tag.endswith('nfeProc') else root.find('n:infNFe',{'n':NS})
    if inf is None or text(inf,'n:ide/n:mod')!='55':raise ValueError('XML sem identificação de NF-e modelo 55.')
    if kind=='product':
        return [dict(code=text(p,'n:cProd'),name=text(p,'n:xProd'),NCM=text(p,'n:NCM'),unit=text(p,'n:uCom'),price=text(p,'n:vUnCom'),gtin='' if text(p,'n:cEAN')=='SEM GTIN' else text(p,'n:cEAN'),CEST=text(p,'n:CEST')) for p in inf.findall('n:det/n:prod',{'n':NS})]
    party=party or ('emit' if kind=='supplier' else 'dest')
    if party not in ('emit','dest'):raise ValueError('Escolha emitente ou destinatário.')
    node=inf.find('n:'+party,{'n':NS})
    if node is None:raise ValueError('XML não contém o participante selecionado.')
    data={k:text(node,'n:'+k) for k in ('xNome','IE','Email')};data['Email']=text(node,'n:email')
    data.update(CNPJCPF=text(node,'n:CNPJ') or text(node,'n:CPF'),indIEDest=text(node,'n:indIEDest') or ('2' if text(node,'n:IE').upper()=='ISENTO' else '1' if text(node,'n:IE') else '9'))
    address=node.find('n:ender'+('Emit' if party=='emit' else 'Dest'),{'n':NS})
    if address is not None:
        data.update({k:text(address,'n:'+k) for k in ('xLgr','nro','xCpl','xBairro','cMun','xMun','UF','CEP')});data['Fone']=text(address,'n:fone')
    return [data]

def preview(store,cid,kind,raw,filename,party=''):
    if kind not in FIELDS:raise ValueError('Tipo de cadastro inválido.')
    store.get('company','',cid)
    if str(filename).lower().endswith('.xml'):records=xml_rows(raw,kind,party);offset=1
    else:
        grid=read_sheet(raw,filename,kind)
        if not grid:raise ValueError('Planilha vazia.')
        allowed=FIELDS[kind];mapping=[v if v in allowed else ALIASES.get(norm(v),'') for v in grid[0]]
        if kind=='product':mapping=['name' if x=='xNome' else x for x in mapping]
        mapped=[v for v in mapping if v in allowed]
        if len(mapped)!=len(set(mapped)):raise ValueError('Há colunas duplicadas para o mesmo campo.')
        if not mapped:raise ValueError('Nenhuma coluna reconhecida. Use a planilha exemplo.')
        records=[{k:str(v).strip() for k,v in zip(mapping,row) if k in allowed} for row in grid[1:] if any(str(v).strip() for v in row)];offset=2
    if not records or len(records)>10000:raise ValueError('Arquivo vazio ou acima de 10.000 cadastros.')
    existing={canonical(kind,r) for _,r in store.list(kind,cid)};seen=set();result=[]
    for idx,data in enumerate(records,offset):
        data={k:str(v).strip() for k,v in data.items() if k in FIELDS[kind]}
        if kind!='product':
            data['CNPJCPF']=document(data.get('CNPJCPF',''));data['CEP']=document(data.get('CEP',''));data['UF']=data.get('UF','').upper();data.setdefault('indIEDest','9')
        else:
            if str(data.get('price','')).strip():
                try:data['price']=str(number(data['price']))
                except ValueError:pass
        identity=canonical(kind,data);duplicate=identity in existing or identity in seen;seen.add(identity)
        result.append(dict(line=idx,data=data,errors=validate(kind,data),duplicate=duplicate))
    return result

def apply(store,cid,kind,plan,allow_partial=False):
    store.get('company','',cid)
    if kind not in FIELDS or not plan:raise ValueError('Prévia inválida.')
    if any(r['errors'] and not r['duplicate'] for r in plan) and not allow_partial:raise ValueError('Corrija os erros ou marque a importação apenas das linhas válidas.')
    existing={canonical(kind,r) for _,r in store.list(kind,cid)};created=[];skipped=0;stamp=datetime.now().astimezone().isoformat()
    with store.db:
        store.db.execute('UPDATE records SET updated=updated WHERE 0')
        for r in plan:
            data=r['data'];key=canonical(kind,data)
            if validate(kind,data) or key in existing:skipped+=1;continue
            rid=uuid.uuid4().hex;store.db.execute('INSERT INTO records VALUES(?,?,?,?,?)',(rid,kind,cid,json.dumps(data,ensure_ascii=False),stamp));store.db.execute('INSERT INTO audit(stamp,action,record) VALUES(?,?,?)',(stamp,'IMPORTAR '+kind,rid));created.append(rid);existing.add(key)
    return dict(created=len(created),skipped=skipped,ids=created)
