"""VF Emissor — núcleo local, sem dependências comerciais."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import sqlite3, json, uuid, re, configparser, io, socket, datetime, secrets

VERSION = '0.8.0'
CENT = Decimal('0.01')

def number(value):
    text = str(value).strip().replace('R$', '').replace(' ', '')
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    try:
        result = Decimal(text or '0')
        if not result.is_finite(): raise ValueError('Número inválido.')
        return result
    except InvalidOperation:
        raise ValueError('Valor numérico inválido: ' + str(value))

def money(value): return number(value).quantize(CENT, rounding=ROUND_HALF_UP)
def fmt(value): return format(money(value), '.2f')
def brl(value): return 'R$ ' + format(money(value), ',.2f').replace(',', '_').replace('.', ',').replace('_', '.')
def clean(value):
    text = str(value)
    if any(c in text for c in '\r\n\x00'): raise ValueError('Campo contém quebra de linha ou caractere inválido.')
    return text

def document(value): return re.sub('[^A-Z0-9]', '', str(value).upper())
def valid_document(value):
    doc = document(value)
    if len(doc) == 14 and re.fullmatch('[A-Z0-9]{12}[0-9]{2}', doc):
        base = [ord(c)-48 for c in doc[:12]]
        for weights in ([5,4,3,2,9,8,7,6,5,4,3,2],[6,5,4,3,2,9,8,7,6,5,4,3,2]):
            rem = sum(a*b for a,b in zip(base,weights)) % 11
            base.append(0 if rem < 2 else 11-rem)
        return doc[-2:] == ''.join(map(str,base[-2:])) and len(set(doc)) > 1
    if len(doc) == 11 and doc.isdigit() and len(set(doc)) > 1:
        nums = list(map(int, doc[:9]))
        for n in (10,11):
            digit = (sum(a*b for a,b in zip(nums,range(n,1,-1)))*10)%11
            nums.append(0 if digit == 10 else digit)
        return ''.join(map(str,nums)) == doc
    return False

class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version > 4:
            self.db.close()
            raise ValueError('Este banco foi atualizado por uma versão mais nova do aplicativo.')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,kind TEXT NOT NULL,company TEXT NOT NULL,data TEXT NOT NULL,updated TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS scope ON records(kind,company);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,stamp TEXT,action TEXT,record TEXT);
        ''')
        if version == 0: self.db.execute('PRAGMA user_version=1')
    def save(self, kind, data, company='', record_id=None):
        if kind=='company':
            data=dict(data)
            if record_id is None:data.update(environment='2',production_enabled=False)
            else:data.setdefault('environment','2');data.setdefault('production_enabled',False)
        rid = record_id or uuid.uuid4().hex
        now = datetime.datetime.now().astimezone().isoformat()
        old = self.db.execute('SELECT kind,company FROM records WHERE id=?',(rid,)).fetchone()
        if old and old != (kind,company): raise ValueError('Cadastro pertence a outra empresa ou tipo.')
        with self.db:
            self.db.execute('INSERT INTO records VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated=excluded.updated', (rid,kind,company,json.dumps(data,ensure_ascii=False),now))
            self.db.execute('INSERT INTO audit(stamp,action,record) VALUES(?,?,?)',(now,'SALVAR '+kind,rid))
        return rid
    def list(self, kind, company=''):
        rows = self.db.execute('SELECT id,data FROM records WHERE kind=? AND company=? ORDER BY updated DESC',(kind,company)).fetchall()
        return [(rid,json.loads(data)) for rid,data in rows]
    def get(self, kind, company, rid):
        row = self.db.execute('SELECT data FROM records WHERE kind=? AND company=? AND id=?',(kind,company,rid)).fetchone()
        if not row: raise ValueError('Registro não encontrado nesta empresa.')
        return json.loads(row[0])
    def backup(self, dest):
        target=sqlite3.connect(dest)
        try: self.db.backup(target)
        finally: target.close()

# Perfis contemplados nesta versão: ICMS integral 00 e CSOSN 102;
# PIS/COFINS por alíquota (01/02) ou sem destaque (04..09).
def _calculate_basic(item, rule, crt):
    qty, price, discount = number(item.get('quantity',1)), number(item.get('price',0)), money(item.get('discount',0))
    if qty <= 0 or price < 0 or discount < 0: raise ValueError('Quantidade deve ser positiva; valores não podem ser negativos.')
    gross = money(qty*price)
    if discount > gross: raise ValueError('Desconto maior que o valor do produto.')
    freight,insurance,other=(money(item.get(k,0)) for k in ('freight','insurance','other'))
    if min(freight,insurance,other)<0:raise ValueError('Despesas do item não podem ser negativas.')
    base = gross-discount+freight+insurance+other
    code = rule.get('icms_code','')
    simple = str(crt) in ('1','4')
    if code not in (('101','102','103','300','400','900') if simple else ('00',)):
        raise ValueError('Use CSOSN 101/102/103/300/400/900 no Simples ou CST 00 no regime normal. ST, DIFAL, FCP e benefícios não são calculados nesta versão.')
    def rate(key):
        if not str(rule.get(key,'')).strip(): raise ValueError('Informe a alíquota de '+key+' no perfil, inclusive quando for zero.')
        value = number(rule[key])
        if value < 0 or value > 100: raise ValueError('Alíquota fora de 0 a 100%.')
        return value
    highlight=not simple or code=='900'
    icms_base = base if highlight else Decimal(0)
    icms = money(base*rate('icms_rate')/100) if highlight else Decimal(0)
    pcbase = base-icms if rule.get('exclude_icms','0') == '1' else base
    result = dict(gross=gross,discount=discount,freight=freight,insurance=insurance,other=other,net=base,icms_base=icms_base,icms=icms,pcbase=pcbase)
    result['credit_sn'] = money(base*rate('credit_rate')/100) if simple and code == '101' else Decimal(0)
    for tax in ('pis','cofins'):
        code = rule.get(tax+'_code','')
        if code in ('01','02','49','99'):
            result[tax] = money(pcbase*rate(tax+'_rate')/100)
        elif code in ('04','05','06','07','08','09'): result[tax]=Decimal(0)
        else: raise ValueError('CST de '+tax.upper()+' não implementado neste perfil.')
    result['pis_base']=pcbase;result['cofins_base']=pcbase
    if item.get('auto_calc','1')=='0':
        manual=item.get('manual',{})
        for field in ('icms_base','icms','pis_base','pis','cofins_base','cofins'):
            if not str(manual.get(field,'')).strip():raise ValueError('Cálculo manual: informe '+field+', inclusive zero.')
            result[field]=money(manual[field])
            if result[field]<0:raise ValueError('Cálculo manual não aceita valores negativos.')
        if not highlight and (result['icms_base'] or result['icms']):raise ValueError('O CSOSN selecionado não permite destaque de ICMS próprio. Confira CST/CSOSN.')
        if highlight and abs(result['icms']-money(result['icms_base']*rate('icms_rate')/100))>CENT:raise ValueError('ICMS manual diverge da base e alíquota.')
        for tax in ('pis','cofins'):
            if rule.get(tax+'_code') in ('04','05','06','07','08','09'):
                if result[tax]:raise ValueError(tax.upper()+' sem destaque não aceita imposto manual diferente de zero.')
            elif abs(result[tax]-money(result[tax+'_base']*rate(tax+'_rate')/100))>CENT:raise ValueError(tax.upper()+' manual diverge da base e alíquota.')
    return result

def calculate(item,rule,crt):
    if str(crt)=='3':
        from normal_fiscal import calculate_normal
        return calculate_normal(item,rule)
    from tax_scenarios import has_advanced,calculate_advanced,ZEROS
    if has_advanced(item,rule):return calculate_advanced(item,rule,str(crt),_calculate_basic)
    result=_calculate_basic(item,rule,crt);result.update({k:money(0) for k in ZEROS});return result

ADDRESS = ('xLgr','nro','xBairro','cMun','xMun','UF','CEP')
def validate_party(party, emitter=False):
    for key in ('xNome','CNPJCPF')+ADDRESS:
        if not str(party.get(key,'')).strip(): raise ValueError('Preencha '+key+' de '+('emitente' if emitter else 'destinatário')+'.')
    if not valid_document(party['CNPJCPF']): raise ValueError('CPF/CNPJ inválido.')
    if emitter and len(document(party['CNPJCPF'])) != 14: raise ValueError('Emitente deve ter CNPJ.')
    if emitter and not party.get('IE'): raise ValueError('Informe a inscrição estadual do emitente.')
    if not re.fullmatch('[0-9]{7}',party['cMun']): raise ValueError('Código IBGE do município deve ter 7 dígitos.')
    if not re.fullmatch('[0-9]{8}',party['CEP']): raise ValueError('CEP deve ter 8 dígitos, sem pontuação.')
    if party['UF'] not in 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split(): raise ValueError('UF inválida.')
    if not emitter and party.get('indIEDest','9') == '1' and not party.get('IE'): raise ValueError('Contribuinte precisa de IE.')

def consumer_final_error(recipient,note):
    if recipient.get('indIEDest','9')=='9' and note.get('operation','1')=='1' and note.get('destination','1')!='3' and note.get('final','0')!='1':
        return '696 — Destinatário cadastrado como não contribuinte: esta saída deve indicar consumidor final. Confira a condição fiscal do destinatário e, se correta, selecione Sim em consumidor final.'
    return ''

def build_ini(company, recipient, note):
    """Somente homologação. Não se apresenta como XML autorizado."""
    from tax_scenarios import validate_context
    # INI é uma preparação local legada. A política RTC é obrigatória no XML fiscal.
    if company.get('CRT')!='3':validate_context(company,recipient,note)
    validate_party(company,True); validate_party(recipient)
    if note.get('environment','2')=='1' and not company.get('production_enabled'):raise ValueError('Produção não habilitada para esta empresa.')
    consumer_error=consumer_final_error(recipient,note)
    if consumer_error:raise ValueError(consumer_error)
    if note.get('destination') is None and company['UF'] != recipient['UF']: raise ValueError('Esta beta contempla somente operações internas. DIFAL/interestaduais não implementados.')
    if not note.get('items'): raise ValueError('Inclua pelo menos um item.')
    if len(note['items']) > 990: raise ValueError('Limite técnico da NF-e: 990 itens; não há limite comercial de 10 itens.')
    if not 1 <= int(note['number']) <= 999999999: raise ValueError('Número da nota inválido.')
    if not 0 <= int(note['series']) <= 999: raise ValueError('Série inválida.')
    out = configparser.ConfigParser(interpolation=None); out.optionxform = str
    def section(name, data): out[name] = {key:clean(value) for key,value in data.items() if value is not None and str(value)!=''}
    section('infNFe',{'versao':'4.00'})
    section('Identificacao',dict(cNF=note['cnf'],natOp=note.get('nature','VENDA DE MERCADORIA'),mod=55,serie=note['series'],nNF=note['number'],dhEmi=note['date'],tpNF=note.get('operation','1'),idDest=note.get('destination','1'),tpAmb=note.get('environment','2'),tpImp=1,tpEmis=1,finNFe=note.get('purpose','1'),indFinal=note.get('final','0'),indPres=note.get('presence','1'),procEmi=0,cMunFG=company['cMun'],verProc='Decisao-0.1.0'))
    fields = ('CNPJCPF','xNome','IE','xLgr','nro','xCpl','xBairro','cMun','xMun','UF','CEP','Fone','Email')
    emitter = {key:company.get(key,'') for key in fields}; emitter.update(CNPJCPF=document(company['CNPJCPF']),CRT=company['CRT'],cPais=1058,xPais='BRASIL')
    section('Emitente',emitter)
    dest = {key:recipient.get(key,'') for key in fields}; dest.update(CNPJCPF=document(recipient['CNPJCPF']),xNome=recipient['xNome'] if note.get('environment','2')=='1' else 'NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL',indIEDest=recipient.get('indIEDest','9'),cPais=1058,xPais='BRASIL')
    section('Destinatario',dest)
    totals = {key:Decimal(0) for key in ('gross','discount','freight','insurance','other','net','icms_base','icms','pis','cofins','st_base','st','fcpst_base','fcpst','ipi_return')}
    for i,item in enumerate(note['items'],1):
        suffix = f'{i:03d}'; rule=item['rule']; product=item['product']
        if rule.get('reviewed') != '1': raise ValueError('Revise e aprove o perfil tributário antes de gerar a nota.')
        if rule.get('rtc_status') != 'nao_aplicavel_revisado': raise ValueError('IBS/CBS ainda não implementados nesta beta. Utilize somente cenário de homologação cuja inaplicabilidade tenha sido revisada pelo contador.')
        if not re.fullmatch('[0-9]{8}',product.get('NCM','')): raise ValueError('NCM deve ter 8 dígitos.')
        cfop=rule.get('CFOP','')
        if note.get('destination') is None:
            if cfop not in ('5101','5102'):raise ValueError('Esta beta contempla venda interna CFOP 5101/5102 sem ST.')
        else:
            prefix=('1' if note['destination']=='1' else '2') if note.get('operation','1')=='0' else ('5' if note['destination']=='1' else '6')
            if not re.fullmatch(prefix+'[0-9]{3}',cfop):raise ValueError('CFOP incompatível com tipo/destino da operação.')
            from cfop_catalog import cfop_errors
            catalog_errors=cfop_errors(cfop,note)
            if catalog_errors:raise ValueError(catalog_errors[0])
        values=calculate(item,rule,company['CRT'])
        for key in totals: totals[key]+=values[key]
        section('Produto'+suffix,dict(cProd=product['code'],cEAN=product.get('gtin') or 'SEM GTIN',cEANTrib=product.get('gtin') or 'SEM GTIN',xProd=product['name'],NCM=product['NCM'],CFOP=cfop,uCom=product['unit'],qCom=str(number(item['quantity'])),vUnCom=str(number(item['price'])),vProd=fmt(values['gross']),uTrib=product['unit'],qTrib=str(number(item['quantity'])),vUnTrib=str(number(item['price'])),vDesc=fmt(values['discount']),vFrete=fmt(values['freight']),vSeg=fmt(values['insurance']),vOutro=fmt(values['other']),indTot=1))
        icms = dict(orig=rule.get('origin','0'))
        if str(company['CRT']) in ('1','4'):
            icms['CSOSN']=rule['icms_code']
            if rule['icms_code']=='101': icms.update(pCredSN=str(number(rule['credit_rate'])),vCredICMSSN=fmt(values['credit_sn']))
        else: icms.update(CST='00',modBC=3,vBC=fmt(values['icms_base']),pICMS=str(number(rule['icms_rate'])),vICMS=fmt(values['icms']))
        if rule['icms_code'] in ('201','202','203'):
            t=item['taxes'];icms.update(modBCST=t['st_mode'],vBCST=fmt(values['st_base']),pICMSST=str(number(t['st_rate'])),vICMSST=fmt(values['st']))
            if t.get('st_mva'):icms['pMVAST']=str(number(t['st_mva']))
            if t.get('st_reduction'):icms['pRedBCST']=str(number(t['st_reduction']))
            if t.get('fcpst_enabled')=='1':icms.update(vBCFCPST=fmt(values['fcpst_base']),pFCPST=str(number(t['fcpst_rate'])),vFCPST=fmt(values['fcpst']))
            if rule['icms_code']=='201':icms.update(pCredSN=str(number(rule['credit_rate'])),vCredICMSSN=fmt(values['credit_sn']))
        section('ICMS'+suffix,icms)
        for tax in ('pis','cofins'):
            data = dict(CST=rule[tax+'_code'])
            if data['CST'] in ('01','02','49','99'): data.update(vBC=fmt(values.get(tax+'_base',values['pcbase'])),**{'p'+tax.upper():str(number(rule[tax+'_rate'])),'v'+tax.upper():fmt(values[tax])})
            section(tax.upper()+suffix,data)
    section('Total',dict(vBC=fmt(totals['icms_base']),vICMS=fmt(totals['icms']),vProd=fmt(totals['gross']),vDesc=fmt(totals['discount']),vPIS=fmt(totals['pis']),vCOFINS=fmt(totals['cofins']),vNF=fmt(totals['net']),vST=fmt(totals['st']),vBCST=fmt(totals['st_base']),vFCPST=fmt(totals['fcpst']),vIPIDevol=fmt(totals['ipi_return']),vFrete=fmt(totals['freight']),vSeg=fmt(totals['insurance']),vOutro=fmt(totals['other']),vIPI='0.00',vII='0.00'))
    section('Transportador',dict(modFrete=9))
    payment=note.get('payment','01')
    if payment not in ('01','17','90'): raise ValueError('Meio de pagamento não suportado nesta beta.')
    section('pag001',dict(tPag=payment,vPag='0.00' if payment=='90' else fmt(totals['net']),indPag=0))
    section('DadosAdicionais',dict(Complemento=note.get('info',''),InfAdFisco=note.get('info_fisco','')))
    purchase={xml:note.get(field,'') for field,xml in [('purchase_commitment','xNEmp'),('purchase_order','xPed'),('purchase_contract','xCont')]}
    if any(purchase.values()): section('Compra',purchase)
    buf=io.StringIO(); out.write(buf,space_around_delimiters=False)
    return buf.getvalue(),totals

class Monitor:
    """Cliente TCP local. Resposta ACBr termina em ETX. Nunca reenvia após timeout."""
    def __init__(self, port=3434): self.port=int(port)
    def command(self, command):
        if '\r' in command or '\n' in command: raise ValueError('Comando inválido.')
        with socket.create_connection(('127.0.0.1',self.port),timeout=5) as conn:
            conn.settimeout(1)
            # O Monitor envia uma saudação ao conectar; não confundir com resposta.
            try: conn.recv(8192)
            except socket.timeout: pass
            conn.settimeout(120)
            conn.sendall((command+'\r\n').encode('utf-8'))
            data=bytearray()
            while b'\x03' not in data:
                block=conn.recv(65536)
                if not block: raise RuntimeError('Monitor encerrou a conexão sem resposta completa. Consulte a situação antes de reenviar.')
                data.extend(block)
                if len(data)>8*1024*1024: raise RuntimeError('Resposta excedeu o limite permitido.')
            text=data.split(b'\x03',1)[0].decode('utf-8',errors='replace').strip()
            if re.search(r'(^|\n)ERRO:',text,re.I): raise RuntimeError(text)
            return text
    def generate(self, ini_path):
        target=clean(str(Path(ini_path).resolve()))
        if '"' in target: raise ValueError('Caminho inválido.')
        self.command('NFE.SetAmbiente(2)')
        return self.command(f'NFE.CriarNFe("{target}",0,1)')

def parse_authorization(xml_path, expected_doc=None):
    # Importação de XML autorizado; não é validação criptográfica da assinatura.
    from xml.etree import ElementTree as ET
    data=Path(xml_path).read_bytes()
    if len(data)>8*1024*1024 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper(): raise ValueError('XML não permitido.')
    root=ET.fromstring(data); ns={'n':'http://www.portalfiscal.inf.br/nfe'}
    inf=root.find('.//n:infNFe',ns)
    if inf is None: raise ValueError('Arquivo não contém NF-e.')
    def value(parent,key): return parent.findtext('n:'+key,default='',namespaces=ns)
    emit=inf.find('n:emit',ns)
    cnpj=value(emit,'CNPJ')
    if expected_doc and document(cnpj)!=document(expected_doc): raise ValueError('XML pertence a outro emitente. Selecione a empresa correta.')
    ide=inf.find('n:ide',ns); prot=root.find('.//n:infProt',ns)
    key=inf.attrib.get('Id','').removeprefix('NFe')
    status=value(prot,'cStat') if prot is not None else ''
    if status not in ('100','150') or len(key)!=44 or value(prot,'chNFe')!=key or not value(prot,'nProt'): raise ValueError('Importe nfeProc com protocolo de autorização e chave correspondente.')
    if value(prot,'tpAmb')!=value(ide,'tpAmb'): raise ValueError('Ambiente do protocolo diverge da nota.')
    return dict(number=value(ide,'nNF'),series=value(ide,'serie'),key=key,protocol=value(prot,'nProt'),environment=value(ide,'tpAmb'),status='IMPORTADA — protocolo informado no XML',issuer=cnpj)


def extract_catalog(xml_path):
    """Lê cadastros de um XML local. Não importa autorização nem executa conteúdo."""
    from xml.etree import ElementTree as ET
    data=Path(xml_path).read_bytes()
    if len(data)>8*1024*1024 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper(): raise ValueError('XML não permitido.')
    root=ET.fromstring(data); ns={'n':'http://www.portalfiscal.inf.br/nfe'}
    inf=root if root.tag=='{'+ns['n']+'}infNFe' else root.find('.//n:infNFe',ns)
    if inf is None: raise ValueError('XML não contém NF-e.')
    def text(node,key,default=''): return node.findtext('n:'+key,default=default,namespaces=ns) if node is not None else default
    def party(node,address_tag):
        if node is None:return None
        address=node.find('n:'+address_tag,ns)
        values={key:text(node,key) for key in ('xNome','IE','Email','CRT','indIEDest')}
        values['CNPJCPF']=text(node,'CNPJ') or text(node,'CPF')
        for key in ADDRESS+('xCpl','Fone'): values[key]=text(address,'fone' if key=='Fone' else key)
        return values
    company=party(inf.find('n:emit',ns),'enderEmit'); validate_party(company,True)
    company.update(series='1',next_number='1',port='3434')
    recipient=party(inf.find('n:dest',ns),'enderDest')
    if recipient and not valid_document(recipient['CNPJCPF']): recipient=None
    products=[]
    for det in inf.findall('n:det',ns):
        prod=det.find('n:prod',ns)
        if prod is None:continue
        gtin=text(prod,'cEAN'); gtin='' if gtin=='SEM GTIN' else gtin
        products.append(dict(code=text(prod,'cProd'),name=text(prod,'xProd'),NCM=text(prod,'NCM'),unit=text(prod,'uCom'),price=text(prod,'vUnCom','0'),gtin=gtin,profile_id=''))
    return company,recipient,products
