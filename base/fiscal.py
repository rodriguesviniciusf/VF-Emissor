"""NF-e AL/Simples 2026: A1, XML/XSD, SVRS e documentos por ambiente.
Nenhuma chamada ocorre ao importar o módulo.
"""
from __future__ import annotations
import base64, copy, hashlib, json, re, sqlite3, uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from lxml import etree as ET
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID, ObjectIdentifier
from core import Store, build_ini, calculate, document, valid_document, fmt, money, number, validate_party

NS='http://www.portalfiscal.inf.br/nfe'
DS='http://www.w3.org/2000/09/xmldsig#'
SOAP='http://www.w3.org/2003/05/soap-envelope'
HOMOLOG='https://nfe-homologacao.svrs.rs.gov.br'
PRODUCTION='https://nfe.svrs.rs.gov.br'
ENDPOINTS={'2':HOMOLOG,'1':PRODUCTION}
SERVICES={
 'status':('/ws/NfeStatusServico/NfeStatusServico4.asmx','NFeStatusServico4','nfeStatusServicoNF'),
 'send':('/ws/NfeAutorizacao/NFeAutorizacao4.asmx','NFeAutorizacao4','nfeAutorizacaoLote'),
 'query':('/ws/NfeConsulta/NfeConsulta4.asmx','NFeConsultaProtocolo4','nfeConsultaNF'),
 'receipt':('/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx','NFeRetAutorizacao4','nfeRetAutorizacaoLote'),
 'event':('/ws/recepcaoevento/recepcaoevento4.asmx','NFeRecepcaoEvento4','nfeRecepcaoEvento'),
 'inutil':('/ws/nfeinutilizacao/nfeinutilizacao4.asmx','NFeInutilizacao4','nfeInutilizacaoNF'),
}
TZ=timezone(timedelta(hours=-3))
MAX_XML=8*1024*1024


def parse_xml(data):
    if isinstance(data,str): data=data.encode('utf-8')
    if len(data)>MAX_XML: raise ValueError('XML excede o limite de 8 MB.')
    parser=ET.XMLParser(resolve_entities=False,no_network=True,load_dtd=False,huge_tree=False)
    result=ET.fromstring(data,parser)
    if result.getroottree().docinfo.doctype: raise ValueError('XML com DTD não é permitido.')
    return result


def tag(parent,name,value=None,**attrs):
    result=ET.SubElement(parent,'{'+NS+'}'+name,**{k:str(v) for k,v in attrs.items()})
    if value is not None: result.text=str(value)
    return result


def text(node,path,default=''):
    return node.findtext(path,default=default,namespaces={'n':NS}) if node is not None else default


def serialize(node): return ET.tostring(node,encoding='utf-8',xml_declaration=False)


def access_key(cnpj,series,number_,cnf,issued):
    base='27'+issued.strftime('%y%m')+cnpj+'55'+f'{int(series):03d}{int(number_):09d}'+'1'+f'{int(cnf):08d}'
    if len(base)!=43 or not base.isdigit(): raise ValueError('Dados inválidos para gerar a chave de acesso.')
    weights=[2+i%8 for i in range(43)]
    mod=sum(int(d)*w for d,w in zip(reversed(base),weights))%11
    return base+str(0 if mod<2 else 11-mod)


@dataclass(repr=False)
class A1Certificate:
    data: bytes
    password: str
    key: object
    cert: object
    cnpj: str
    fingerprint: str
    @classmethod
    def load(cls,path,password,expected_cnpj=None):
        data=Path(path).read_bytes()
        return cls.from_bytes(data,password,expected_cnpj)
    @classmethod
    def from_bytes(cls,data,password,expected_cnpj=None):
        if len(data)>4*1024*1024: raise ValueError('Arquivo de certificado muito grande.')
        try: key,cert,_=pkcs12.load_key_and_certificates(data,password.encode('utf-8') if password else None)
        except (ValueError,TypeError): raise ValueError('Não foi possível abrir o A1. Confira arquivo e senha.') from None
        if not isinstance(key,rsa.RSAPrivateKey) or cert is None: raise ValueError('O arquivo deve conter certificado A1 e chave privada RSA.')
        now=datetime.now(timezone.utc)
        if not cert.not_valid_before_utc<=now<cert.not_valid_after_utc: raise ValueError('Certificado vencido ou ainda fora da validade.')
        candidates=[]
        try:
            sans=cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            for other in sans.get_values_for_type(x509.OtherName):
                if other.type_id==ObjectIdentifier('2.16.76.1.3.3'):
                    candidates.extend(re.findall(rb'[0-9]{14}',other.value))
        except x509.ExtensionNotFound: pass
        if not candidates:
            for cn in cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME):
                candidates.extend(x.encode() for x in re.findall(r':([0-9]{14})(?:$|\s)',cn.value))
        if len(set(candidates))!=1: raise ValueError('Não foi possível identificar um único CNPJ no certificado A1.')
        cnpj=candidates[0].decode('ascii')
        if expected_cnpj and cnpj[:8]!=document(expected_cnpj)[:8]: raise ValueError('O certificado pertence a outra raiz de CNPJ. Selecione o A1 deste emitente.')
        return cls(data,password,key,cert,cnpj,cert.fingerprint(hashes.SHA256()).hex())
    def metadata(self):
        return dict(cnpj=self.cnpj,expires=self.cert.not_valid_after_utc.isoformat(),fingerprint=self.fingerprint)
    def sign(self,unsigned):
        from signxml import XMLSigner,methods,XMLVerifier,SignatureConfiguration,SignatureMethod,DigestAlgorithm
        class NFeSigner(XMLSigner):
            def check_deprecated_methods(self): pass  # RSA-SHA1 é o padrão obrigatório da NF-e 4.00.
        root=parse_xml(unsigned); inf=root.find('n:infNFe',{'n':NS})
        if inf is None: raise ValueError('XML sem infNFe.')
        pemkey=self.key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
        pemcert=self.cert.public_bytes(serialization.Encoding.PEM)
        signer=NFeSigner(method=methods.enveloped,signature_algorithm='rsa-sha1',digest_algorithm='sha1',c14n_algorithm='http://www.w3.org/TR/2001/REC-xml-c14n-20010315')
        signer.namespaces={'ds':DS}
        signed=signer.sign(root,key=pemkey,cert=pemcert,reference_uri='#'+inf.attrib['Id'])
        # Verifica integridade matemática com o certificado carregado; a cadeia ICP-Brasil será validada pela SEFAZ.
        config=SignatureConfiguration(signature_methods=frozenset({SignatureMethod.RSA_SHA1}),digest_algorithms=frozenset({DigestAlgorithm.SHA1}))
        XMLVerifier().verify(signed,x509_cert=pemcert,expect_config=config)
        result=serialize(signed); validate_schema(result); return result


def schema_path(name):
    return Path(__file__).resolve().parent/'schemas'/'nfe'/name


def validate_schema(data,name='nfe_v4.00.xsd'):
    schema=ET.XMLSchema(ET.parse(str(schema_path(name))))
    if not schema.validate(parse_xml(data)):
        raise ValueError('XML não passou no schema: '+'; '.join(e.message for e in list(schema.error_log)[:5]))


def unsigned_schema_issues(data):
    """Confere o mesmo XSD com assinatura opcional só nesta pré-validação em memória."""
    # A assinatura é exigida no fluxo fiscal real; aqui ainda não há uso de A1.
    ns={'xs':'http://www.w3.org/2001/XMLSchema'}
    layout=ET.parse(str(schema_path('leiauteNFe_v4.00.xsd')))
    for node in layout.xpath('//xs:element[@ref]',namespaces=ns):
        if node.get('ref').split(':')[-1]=='Signature':node.set('minOccurs','0')
    # O tipo TNFe está no leiaute; usa o próprio elemento NFe declarado na cópia.
    target=ET.Element('{http://www.w3.org/2001/XMLSchema}element',name='NFe',type='TNFe')
    layout.getroot().append(target)
    schema=ET.XMLSchema(layout);root=parse_xml(data)
    if schema.validate(root):return []
    result=[]
    names={'natOp':'nature','nNF':'number','serie':'series','idDest':'destination','tpNF':'operation','finNFe':'purpose','indPres':'presence','refNFe':'references','infCpl':'info','infAdFisco':'info_fisco','xPed':'purchase_order','xCont':'purchase_contract','xNEmp':'purchase_commitment','modFrete':'transport_mode','nFat':'invoice_number','vLiq':'invoice_net','vDup':'duplicates'}
    for error in list(schema.error_log)[:50]:
        field='items'
        try:
            found=root.xpath(error.path,namespaces={'n':NS})
            node=found[0] if found else None
            if node is not None:
                local=ET.QName(node).localname;field=names.get(local,'items')
                ancestors=[node]+list(node.iterancestors())
                contexts=[ET.QName(p).localname for p in ancestors]
                if 'transporta' in contexts:field={'CNPJ':'carrier_doc','CPF':'carrier_doc','xNome':'carrier_name','IE':'carrier_ie','xEnder':'carrier_address','xMun':'carrier_city','UF':'carrier_uf'}.get(local,'carrier_name')
                if 'veicTransp' in contexts:field='vehicle_uf' if local=='UF' else 'vehicle_plate'
                if 'vol' in contexts:field={'qVol':'volume_qty','esp':'volume_type','marca':'volume_brand','nVol':'volume_number','pesoL':'net_weight','pesoB':'gross_weight'}.get(local,'volume_qty')
                if 'fat' in contexts:field={'nFat':'invoice_number','vOrig':'invoice_original','vDesc':'invoice_discount','vLiq':'invoice_net'}.get(local,'invoice_number')
                if 'dup' in contexts:field='duplicates'
                for parent in ancestors:
                    name=ET.QName(parent).localname
                    if name=='det':
                        item=int(parent.get('nItem'))-1
                        tax='cofins' if any(p.startswith('COFINS') for p in contexts) else 'pis' if any(p.startswith('PIS') for p in contexts) else 'icms'
                        item_names={'CFOP':'rule.CFOP','CSOSN':'rule.icms_code','CST':'rule.'+tax+'_code','NCM':'product.NCM','CEST':'product.CEST','vBCST':'taxes.st_base','pICMSST':'taxes.st_rate','vICMSST':'taxes.manual_st','modBCST':'taxes.st_mode','pMVAST':'taxes.st_mva','pRedBCST':'taxes.st_reduction','vBCFCPST':'taxes.fcpst_base','pFCPST':'taxes.fcpst_rate','vFCPST':'taxes.manual_fcpst','pDevol':'taxes.ipi_return_percent','vIPIDevol':'taxes.manual_ipi_return','cProd':'product.code','xProd':'product.name','uCom':'product.unit','qCom':'quantity','vUnCom':'price','vDesc':'discount','orig':'rule.origin','pICMS':'rule.icms_rate','pPIS':'rule.pis_rate','pCOFINS':'rule.cofins_rate','vBC':'manual.'+tax+'_base','vICMS':'manual.icms','vPIS':'manual.pis','vCOFINS':'manual.cofins'}
                        field='item.'+str(item)+'.'+item_names.get(local,'rule.icms_code');break
                    if name in ('emit','dest'):
                        field=('company.' if name=='emit' else 'recipient.')+local;break
        except (ValueError,IndexError):pass
        result.append((field,error.message))
    return result

def build_unsigned(company,recipient,note):
    """Vendas internas AL, CRT 1, emissão em 2026, sem ST/benefícios/IBS/CBS."""
    company=copy.deepcopy(company); recipient=copy.deepcopy(recipient)
    for role,party in [('Emitente',company),('Destinatário',recipient)]:
        party['UF']=str(party.get('UF','')).strip().upper()
        party['cMun']=str(party.get('cMun','')).strip()
        try: validate_party(party,role=='Emitente')
        except ValueError as exc: raise ValueError(f'{role}: {exc}') from exc
        if role=='Emitente' and party['UF']!='AL':raise ValueError(f"Emitente: UF cadastrada {party['UF']}. A transmissão está configurada para AL.")
        from note_validation import UF_IBGE
        if role=='Destinatário' and note.get('destination','1')=='1' and party['UF']!='AL':raise ValueError(f"Destinatário: UF cadastrada {party['UF']}. Selecione operação interestadual quando aplicável.")
        if not party['cMun'].startswith(UF_IBGE.get(party['UF'],'?')):raise ValueError(f"{role}: código IBGE {party['cMun']} incompatível com UF {party['UF']}.")
    expected='1' if recipient['UF']==company['UF'] else '2'
    if note.get('destination','1')!=expected:raise ValueError('Destino da operação incompatível com as UFs.')
    if note.get('purpose','1') not in ('1','2','3','4') or note.get('operation','1') not in ('0','1'):raise ValueError('Tipo/finalidade da operação inválido.')
    references=[v.strip() for v in str(note.get('references','')).replace(';',',').split(',') if v.strip()]
    if note.get('purpose','1') in ('2','4') and not references:raise ValueError('Informe a chave da NF-e referenciada.')
    from normal_fiscal import effective_payment
    if note.get('purpose','1') in ('3','4') and effective_payment(note)!='90':raise ValueError('Ajuste/devolução exige pagamento 90 — sem pagamento.')
    if references:
        from note_validation import validate_note
        errors=[e for e in validate_note(company,recipient,note,False) if e.field in ('references','has_reference')]
        if errors:raise ValueError(errors[0].message)
    if company.get('CRT') not in ('1','3'): raise ValueError('Selecione CRT 1 ou CRT 3.')
    normal=company.get('CRT')=='3'
    cnpj=document(company['CNPJCPF'])
    if not re.fullmatch('[0-9]{14}',cnpj): raise ValueError('CNPJ alfanumérico ainda não implementado no envio.')
    issued=datetime.fromisoformat(note['issued_at'])
    if issued.tzinfo is None or issued.year!=2026: raise ValueError('Este leiaute de transmissão cobre emissão em 2026; requer atualização para 2027.')
    if note.get('environment','2') not in ('1','2'):raise ValueError('Ambiente inválido.')
    if note.get('environment','2')=='1' and not company.get('production_enabled'):raise ValueError('Produção não habilitada para esta empresa.')
    if not (normal and note.get('normal_payment')) and note.get('payment','01') not in ('01','17','90'): raise ValueError('Pagamento não suportado.')
    if note.get('final','0') not in ('0','1') or note.get('presence','1') not in ('0','1','2','3','5','9'): raise ValueError('Indicadores de consumidor/presença inválidos.')
    # Reaproveita as validações e o cálculo da preparação local. O enquadramento
    # sem IBS/CBS é restrito ao CRT 1/2026; não exige digitar uma falsa dispensa.
    checked=copy.deepcopy(note)
    checked['date']=issued.strftime('%d/%m/%Y %H:%M:%S')
    for item in checked.get('items',[]): item['rule']['rtc_status']='nao_aplicavel_revisado'
    for item in checked.get('items',[]):
        if number(item['quantity']) != number(item['quantity']).quantize(number('0.0001')):
            raise ValueError('Quantidade aceita até quatro casas decimais.')
        if number(item['price']) != number(item['price']).quantize(number('0.0000000001')):
            raise ValueError('Preço unitário aceita até dez casas decimais.')
    from tax_scenarios import validate_context
    validate_context(company,recipient,note)
    if normal:
        from normal_fiscal import aggregate_totals
        totals=aggregate_totals(company,recipient,note)
    else:_,totals=build_ini(company,recipient,checked)
    key=access_key(cnpj,note['series'],note['number'],note['cnf'],issued)
    root=ET.Element('{'+NS+'}NFe',nsmap={None:NS})
    inf=tag(root,'infNFe',Id='NFe'+key,versao='4.00'); ide=tag(inf,'ide')
    values=[('cUF','27'),('cNF',f"{int(note['cnf']):08d}"),('natOp',note.get('nature','VENDA DE MERCADORIA')),('mod','55'),('serie',int(note['series'])),('nNF',int(note['number'])),('dhEmi',issued.isoformat(timespec='seconds')),('tpNF',note.get('operation','1')),('idDest',note.get('destination','1')),('cMunFG',note.get('cMunFG') or company['cMun']),('tpImp','1'),('tpEmis','1'),('cDV',key[-1]),('tpAmb',note.get('environment','2')),('finNFe',note.get('purpose','1')),('indFinal',note.get('final','0')),('indPres',note.get('presence','1')),('procEmi','0'),('verProc','VF-Web-'+json.loads((Path(__file__).resolve().parent.parent/'version.json').read_text(encoding='utf-8'))['version'])]
    for k,v in values: tag(ide,k,v)
    if key in references:raise ValueError('A NF-e não pode referenciar a si mesma. Importe o XML da nota de origem correta.')
    for reference in references:tag(tag(ide,'NFref'),'refNFe',reference)
    def address(parent,name,party):
        node=tag(parent,name)
        for field in ('xLgr','nro','xCpl','xBairro','cMun','xMun','UF','CEP'):
            if party.get(field):tag(node,field,party[field])
        tag(node,'cPais','1058'); tag(node,'xPais','BRASIL')
        phone=re.sub(r'\D','',party.get('Fone',''))
        if phone:tag(node,'fone',phone)
    emit=tag(inf,'emit'); tag(emit,'CNPJ',cnpj); tag(emit,'xNome',company['xNome']);
    if company.get('fantasia'):tag(emit,'xFant',company['fantasia'])
    address(emit,'enderEmit',company)
    tag(emit,'IE',re.sub(r'\D','',company['IE']))
    if company.get('IM'):tag(emit,'IM',company['IM'])
    if company.get('CNAE'):tag(emit,'CNAE',re.sub(r'\D','',company['CNAE']))
    tag(emit,'CRT',company['CRT'])
    dest=tag(inf,'dest'); doc=document(recipient['CNPJCPF']); tag(dest,'CPF' if len(doc)==11 else 'CNPJ',doc)
    tag(dest,'xNome',recipient['xNome'] if note.get('environment','2')=='1' else 'NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL'); address(dest,'enderDest',recipient)
    indicator=recipient.get('indIEDest','9'); tag(dest,'indIEDest',indicator)
    if indicator=='1':tag(dest,'IE',re.sub(r'\D','',recipient['IE']))
    if recipient.get('Email'): tag(dest,'email',recipient['Email'])
    authorized=[document(v) for v in re.split(r'[,;\s]+',note.get('authorized_xml','')) if v]
    if len(authorized)>10 or any(not valid_document(v) for v in authorized):raise ValueError('CPF/CNPJ autorizado a acessar XML inválido.')
    for doc in dict.fromkeys(authorized):tag(tag(inf,'autXML'),'CPF' if len(doc)==11 else 'CNPJ',doc)
    for idx,item in enumerate(note['items'],1):
        prod=item['product']; rule=item['rule']; amounts=calculate(item,rule,company['CRT'])
        if not re.fullmatch('[0-8]',rule.get('origin','0')): raise ValueError('Origem do produto inválida.')
        if not prod.get('name') or not prod.get('code') or not prod.get('unit'):raise ValueError('Preencha código, descrição e unidade do produto.')
        det=tag(inf,'det',nItem=idx); p=tag(det,'prod'); gtin=prod.get('gtin') or 'SEM GTIN'
        for k,v in [('cProd',prod['code']),('cEAN',gtin),('xProd',prod['name']),('NCM',prod['NCM']),('CFOP',rule['CFOP']),('uCom',prod['unit']),('qCom',format(number(item['quantity']),'.4f')),('vUnCom',format(number(item['price']),'.10f')),('vProd',fmt(amounts['gross'])),('cEANTrib',gtin),('uTrib',prod['unit']),('qTrib',format(number(item['quantity']),'.4f')),('vUnTrib',format(number(item['price']),'.10f'))]:tag(p,k,v)
        if prod.get('CEST'):
            cest=ET.Element('{'+NS+'}CEST');cest.text=prod['CEST'];p.insert(next(i for i,child in enumerate(p) if child.tag=='{'+NS+'}CFOP'),cest)
        if amounts['freight']:tag(p,'vFrete',fmt(amounts['freight']))
        if amounts['insurance']:tag(p,'vSeg',fmt(amounts['insurance']))
        if amounts['discount']:tag(p,'vDesc',fmt(amounts['discount']))
        if amounts['other']:tag(p,'vOutro',fmt(amounts['other']))
        tag(p,'indTot','1')
        tax=tag(det,'imposto')
        if normal:
            from normal_fiscal import append_groups,normalized
            append_groups(tax,normalized(item,rule)[0])
        else:
            group=tag(tax,'ICMS'); code=rule['icms_code']
            icms=tag(group,'ICMSSN201' if code=='201' else 'ICMSSN202' if code in ('202','203') else 'ICMSSN900' if code=='900' else 'ICMSSN101' if code=='101' else 'ICMSSN102')
            tag(icms,'orig',rule.get('origin','0')); tag(icms,'CSOSN',code)
            if code=='900':
                for k,v in [('modBC','3'),('vBC',fmt(amounts['icms_base'])),('pICMS',format(number(rule['icms_rate']),'.4f')),('vICMS',fmt(amounts['icms']))]:tag(icms,k,v)
            if code in ('201','202','203'):
                t=item['taxes'];tag(icms,'modBCST',t['st_mode'])
                if t.get('st_mva'):tag(icms,'pMVAST',format(number(t['st_mva']),'.4f'))
                if t.get('st_reduction'):tag(icms,'pRedBCST',format(number(t['st_reduction']),'.4f'))
                for k,v in [('vBCST',fmt(amounts['st_base'])),('pICMSST',format(number(t['st_rate']),'.4f')),('vICMSST',fmt(amounts['st']))]:tag(icms,k,v)
                if t.get('fcpst_enabled')=='1':
                    for k,v in [('vBCFCPST',fmt(amounts['fcpst_base'])),('pFCPST',format(number(t['fcpst_rate']),'.4f')),('vFCPST',fmt(amounts['fcpst']))]:tag(icms,k,v)
            if code in ('101','201'):tag(icms,'pCredSN',format(number(rule['credit_rate']),'.4f'));tag(icms,'vCredICMSSN',fmt(amounts['credit_sn']))
            for name in ('PIS','COFINS'):
                lower=name.lower(); code=rule[lower+'_code']; grp=tag(tax,name)
                child=tag(grp,name+('Aliq' if code in ('01','02') else 'NT' if code in ('04','05','06','07','08','09') else 'Outr'))
                tag(child,'CST',code)
                if code in ('01','02','49','99'):
                    tag(child,'vBC',fmt(amounts.get(lower+'_base',amounts['pcbase']))); tag(child,'p'+name,format(number(rule[lower+'_rate']),'.4f')); tag(child,'v'+name,fmt(amounts[lower]))
        if normal and item.get('normal_ipi_return_enabled')=='1':
            devol=tag(det,'impostoDevol');tag(devol,'pDevol',fmt(item['normal_ipi_return_percent']));tag(tag(devol,'IPI'),'vIPIDevol',fmt(amounts['ipi_return']))
        if item.get('taxes',{}).get('ipi_return_enabled')=='1':
            t=item['taxes'];devol=tag(det,'impostoDevol');tag(devol,'pDevol',format(number(t['ipi_return_percent']),'.2f'));tag(tag(devol,'IPI'),'vIPIDevol',fmt(amounts['ipi_return']));tag(det,'infAdProd',t['ipi_reason'])
        inf_ad = item.get('infAdProd') or item.get('product', {}).get('infAdProd')
        if inf_ad and det.find('{'+NS+'}infAdProd') is None:
            tag(det, 'infAdProd', re.sub(r'[\r\n\x00]+', ' ', str(inf_ad)).strip()[:500])
    total=tag(inf,'total'); icmstot=tag(total,'ICMSTot')
    values=[('vBC',totals['icms_base']),('vICMS',totals['icms']),('vICMSDeson',totals.get('icms_deson',0)),('vFCP',totals.get('fcp',0)),('vBCST',totals['st_base']),('vST',totals['st']),('vFCPST',totals['fcpst']),('vFCPSTRet',totals.get('fcpst_ret',0)),('vProd',totals['gross']),('vFrete',totals['freight']),('vSeg',totals['insurance']),('vDesc',totals['discount']),('vII',totals.get('ii',0)),('vIPI',totals.get('ipi',0)),('vIPIDevol',totals['ipi_return']),('vPIS',totals['pis']),('vCOFINS',totals['cofins']),('vOutro',totals['other']),('vNF',totals['net'])]
    if normal:
        from normal_fiscal import emit_particle,total_catalog,append_rtc_totals
        data={k:fmt(v) for k,v in values}
        for field in ('qBCMono','vICMSMono','qBCMonoReten','vICMSMonoReten','qBCMonoRet','vICMSMonoRet'):
            if field in totals:data[field]=format(totals[field],'f')
        if totals.get('difal') or totals.get('fcp_dest'):
            data.update(vFCPUFDest=fmt(totals.get('fcp_dest',0)),vICMSUFDest=fmt(totals.get('difal',0)),vICMSUFRemet=fmt(totals.get('difal_origin',0)))
        emit_particle(icmstot,total_catalog()['ICMSTot']['content'],data,'Totais de ICMS')
        append_rtc_totals(total,note)
    else:
        for k,v in values:tag(icmstot,k,fmt(v))
    from note_finance import finance_errors,append_transport_and_billing
    financial_errors=finance_errors(note)
    if financial_errors:raise ValueError(financial_errors[0][1])
    append_transport_and_billing(inf,note,tag,fmt)
    if normal and note.get('normal_payment'):
        from normal_fiscal import emit_element,total_catalog
        emit_element(inf,total_catalog()['pag'],note['normal_payment'],'Pagamento')
    else:
        payment=tag(tag(inf,'pag'),'detPag'); tag(payment,'indPag','1' if note.get('duplicates') else '0');tag(payment,'tPag',note.get('payment','01'));tag(payment,'vPag','0.00' if note.get('payment')=='90' else fmt(note['normal_vnftot'] if normal and note.get('normal_vnftot') else totals['net']))
    extra_fields=[('info','Informações complementares',5000),('info_fisco','Informações ao Fisco',2000),
                  ('purchase_commitment','Nota de empenho',22),('purchase_order','Pedido de compra',60),('purchase_contract','Contrato',60)]
    extra={}
    for field,label,limit in extra_fields:
        value=str(note.get(field,'')).strip()
        if len(value)>limit:raise ValueError(f'{label}: limite de {limit} caracteres.')
        if any(ord(char)<32 for char in value):raise ValueError(f'{label}: remova quebras de linha e caracteres de controle.')
        extra[field]=value
    if extra['info'] or extra['info_fisco']:
        additional=tag(inf,'infAdic')
        if extra['info_fisco']:tag(additional,'infAdFisco',extra['info_fisco'])
        if extra['info']:tag(additional,'infCpl',extra['info'])
    if any(extra[k] for k in ('purchase_commitment','purchase_order','purchase_contract')):
        purchase=tag(inf,'compra')
        for field,name in [('purchase_commitment','xNEmp'),('purchase_order','xPed'),('purchase_contract','xCont')]:
            if extra[field]:tag(purchase,name,extra[field])
    return serialize(root),key,totals


SVRS_CA_FINGERPRINTS=(
    '6e0bff069a26994c15de2c4888cc54af84882e5495b7fbf66be9ccffec7489f6',
    '08fc942d5176e568acbef9c595f36a20de6acf9ea30c6f5fcedd48216ed5b070',
)


def svrs_trust_chain():
    """Somente CAs oficiais verificadas; nunca confia em certificados do erro TLS."""
    from cryptography.hazmat.primitives.asymmetric import padding
    path=Path(__file__).resolve().parent/'trust'/'svrs-ssl-chain.pem'
    if not path.is_file():raise RuntimeError('Cadeia TLS da SVRS ausente no pacote. Atualize o executável completo.')
    certs=x509.load_pem_x509_certificates(path.read_bytes())
    actual=tuple(cert.fingerprint(hashes.SHA256()).hex() for cert in certs)
    if actual!=SVRS_CA_FINGERPRINTS:raise RuntimeError('O recurso de confiança TLS não corresponde à cadeia oficial desta versão.')
    now=datetime.now(timezone.utc)
    for cert in certs:
        if not cert.not_valid_before_utc<=now<cert.not_valid_after_utc:raise RuntimeError('A cadeia TLS da SVRS está fora da validade. Confira o relógio do Windows e as atualizações do emissor.')
        if not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:raise RuntimeError('Recurso TLS não contém uma autoridade certificadora válida.')
    root,intermediate=certs
    if root.subject!=root.issuer or intermediate.issuer!=root.subject:raise RuntimeError('Vínculo inválido na cadeia TLS.')
    for cert in certs:root.public_key().verify(cert.signature,cert.tbs_certificate_bytes,padding.PKCS1v15(),cert.signature_hash_algorithm)
    return b''.join(cert.public_bytes(serialization.Encoding.PEM) for cert in certs).decode('ascii')


def create_tls_adapter(certificate):
    """A1 do cliente + raízes públicas e cadeia oficial da SVRS, com hostname ativo."""
    import certifi,ssl
    from requests_pkcs12 import Pkcs12Adapter
    adapter=Pkcs12Adapter(pkcs12_data=certificate.data,pkcs12_password=certificate.password,max_retries=0)
    adapter.ssl_context.load_verify_locations(cafile=certifi.where())
    adapter.ssl_context.load_verify_locations(cadata=svrs_trust_chain())
    if adapter.ssl_context.verify_mode!=ssl.CERT_REQUIRED or not adapter.ssl_context.check_hostname:
        adapter.close()
        raise RuntimeError('A conexão exige validação de certificado e hostname.')
    return adapter


class SefazTransport:
    """mTLS em memória, validação TLS ativa, sem redirect ou repetição automática."""
    def __init__(self,certificate): self.certificate=certificate
    def request(self,operation,payload):
        import requests
        environments=set(parse_xml(payload).xpath('//*[local-name()="tpAmb"]/text()'))
        if len(environments)!=1 or next(iter(environments)) not in ENDPOINTS:raise ValueError('Payload sem ambiente único e válido.')
        endpoint=ENDPOINTS[next(iter(environments))]
        path,service,method=SERVICES[operation]
        ws='http://www.portalfiscal.inf.br/nfe/wsdl/'+service
        envelope=ET.Element('{'+SOAP+'}Envelope',nsmap={None:SOAP})
        body=ET.SubElement(envelope,'{'+SOAP+'}Body'); message=ET.SubElement(body,'{'+ws+'}nfeDadosMsg',nsmap={None:ws})
        message.append(parse_xml(payload)); data=serialize(envelope)
        # Revalida o documento no contexto do envelope: mudança de namespaces não
        # pode alterar a assinatura do infNFe.
        if operation=='send':
            from signxml import XMLVerifier,SignatureConfiguration,SignatureMethod,DigestAlgorithm
            nfe=message.find('n:enviNFe/n:NFe',{'n':NS})
            cfg=SignatureConfiguration(signature_methods=frozenset({SignatureMethod.RSA_SHA1}),digest_algorithms=frozenset({DigestAlgorithm.SHA1}))
            XMLVerifier().verify(nfe,x509_cert=self.certificate.cert.public_bytes(serialization.Encoding.PEM),expect_config=cfg)
        if operation in ('event','inutil'):
            from fiscal_events import verify_signature
            target=message.find('n:envEvento/n:evento',{'n':NS}) if operation=='event' else message.find('n:inutNFe',{'n':NS})
            if target is None:raise ValueError('Assinatura do evento ausente.')
            verify_signature(target,self.certificate)
        with requests.Session() as session:
            session.trust_env=False
            session.mount(endpoint,create_tls_adapter(self.certificate))
            headers={'Content-Type':'application/soap+xml; charset=utf-8; action="'+ws+'/'+method+'"'}
            with session.post(endpoint+path,data=data,headers=headers,timeout=(10,45),verify=True,allow_redirects=False,stream=True) as response:
                if response.status_code!=200:raise RuntimeError('SEFAZ retornou HTTP '+str(response.status_code)+'. Consulte a nota antes de qualquer nova tentativa.')
                content=bytearray()
                for block in response.iter_content(65536):
                    content.extend(block)
                    if len(content)>MAX_XML:raise ValueError('Resposta da SEFAZ excedeu o limite.')
                parse_xml(bytes(content)); return bytes(content)


def payload(name,**values):
    node=ET.Element('{'+NS+'}'+name,nsmap={None:NS},versao='4.00')
    for k,v in values.items():tag(node,k,v)
    return serialize(node)


def unpack_response(data,expected_key=None,expected_environment='2'):
    root=parse_xml(data)
    faults=root.xpath('//*[local-name()="Fault"]')
    if faults:raise RuntimeError('Falha SOAP retornada pela SEFAZ. Nenhum reenvio automático foi feito.')
    roots=root.xpath('//*[namespace-uri()=$ns and (local-name()="retEnviNFe" or local-name()="retConsReciNFe" or local-name()="retConsSitNFe" or local-name()="retConsStatServ")]',ns=NS)
    if len(roots)!=1: raise ValueError('Resposta fiscal ausente ou ambígua.')
    ret=roots[0]
    if text(ret,'n:tpAmb')!=expected_environment:raise ValueError('Resposta pertence a outro ambiente fiscal.')
    result=dict(environment=expected_environment,code=text(ret,'n:cStat'),reason=text(ret,'n:xMotivo'),receipt=text(ret,'n:infRec/n:nRec'),protocol='',proc_xml=None,root_type=ET.QName(ret).localname)
    prots=ret.findall('n:protNFe',{'n':NS})
    if len(prots)>1:raise ValueError('Resposta contém mais de um protocolo para envio unitário.')
    if prots:
        inf=prots[0].find('n:infProt',{'n':NS})
        if text(inf,'n:tpAmb')!=expected_environment:raise ValueError('Protocolo de outro ambiente.')
        key=text(inf,'n:chNFe')
        if expected_key and key!=expected_key:raise ValueError('Protocolo não corresponde à chave enviada.')
        cancelled = result['code'] in ('101','151','155')
        result.update(code=result['code'] if cancelled else text(inf,'n:cStat'),reason=result['reason'] if cancelled else text(inf,'n:xMotivo'),protocol=text(inf,'n:nProt'),key=key,prot_xml=serialize(prots[0]),digest=text(inf,'n:digVal'))
    elif expected_key and text(ret,'n:chNFe') and text(ret,'n:chNFe')!=expected_key:raise ValueError('Consulta retornou outra chave.')
    return result


def assemble_process(signed_xml,result):
    if result.get('code') not in ('100','150') or not result.get('protocol') or not result.get('prot_xml'):raise ValueError('Não há protocolo de autorização para montar nfeProc.')
    nfe=parse_xml(signed_xml); key=nfe.find('n:infNFe',{'n':NS}).attrib['Id'][3:]
    if key!=result.get('key'):raise ValueError('Chave do protocolo não corresponde ao XML.')
    if text(nfe,'n:infNFe/n:ide/n:tpAmb')!=result.get('environment','2'):raise ValueError('Ambientes de XML e protocolo divergem.')
    digest=nfe.findtext('ds:Signature/ds:SignedInfo/ds:Reference/ds:DigestValue',namespaces={'ds':DS})
    if not result.get('digest') or result['digest']!=digest:raise ValueError('Digest do protocolo não corresponde à assinatura enviada.')
    proc=ET.Element('{'+NS+'}nfeProc',nsmap={None:NS},versao='4.00');proc.append(nfe);proc.append(parse_xml(result['prot_xml']))
    result_xml=serialize(proc);validate_schema(result_xml,'procNFe_v4.00.xsd');return result_xml


class FiscalStore:
    """Estado fiscal separado dos cadastros 0.1; XML e reserva são atômicos."""
    def __init__(self,store):
        self.store=store;self.db=store.db
        if self.db.execute('PRAGMA user_version').fetchone()[0]<2:
            backups=store.path.parent/'backups';backups.mkdir(exist_ok=True)
            store.backup(backups/('antes-0.2-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3'))
            self.db.executescript('''
            CREATE TABLE IF NOT EXISTS fiscal_documents(
              id TEXT PRIMARY KEY, company TEXT NOT NULL, source TEXT NOT NULL,
              cnpj TEXT NOT NULL, environment TEXT NOT NULL CHECK(environment='2'),
              series INTEGER NOT NULL, number INTEGER NOT NULL, access_key TEXT NOT NULL UNIQUE,
              status TEXT NOT NULL, snapshot TEXT NOT NULL, signed_xml BLOB NOT NULL,
              response_xml BLOB, proc_xml BLOB, receipt TEXT NOT NULL DEFAULT '',
              protocol TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
              created TEXT NOT NULL, updated TEXT NOT NULL,
              UNIQUE(cnpj,environment,series,number), UNIQUE(company,source));
            CREATE TABLE IF NOT EXISTS fiscal_history(
              id INTEGER PRIMARY KEY, document TEXT NOT NULL, stamp TEXT NOT NULL,
              action TEXT NOT NULL, details TEXT NOT NULL DEFAULT '', data BLOB);

            ''')
        from environment_migration import migrate_environments
        migrate_environments(self.store)
        from fiscal_events import ensure_event_schema
        ensure_event_schema(self.store)
    def _history(self,rid,action,details='',data=None):
        self.db.execute('INSERT INTO fiscal_history(document,stamp,action,details,data) VALUES(?,?,?,?,?)',(rid,datetime.now(TZ).isoformat(),action,details,data))
    def get(self,company,rid):
        cur=self.db.execute('SELECT * FROM fiscal_documents WHERE company=? AND id=?',(company,rid));row=cur.fetchone()
        if not row:raise ValueError('Documento não pertence à empresa ativa.')
        return dict(zip((d[0] for d in cur.description),row))
    def list(self,company):
        cur=self.db.execute('SELECT * FROM fiscal_documents WHERE company=? ORDER BY created DESC',(company,)); keys=[d[0] for d in cur.description]
        return [dict(zip(keys,row)) for row in cur.fetchall()]
    def list_metadata(self,company):
        cursor=self.db.execute('SELECT id,company,cnpj,environment,series,number,access_key,status,reason,created,updated FROM fiscal_documents WHERE company=? ORDER BY created DESC',(company,))
        columns=[d[0] for d in cursor.description]
        return [dict(zip(columns,row)) for row in cursor.fetchall()]
    def sync_archive(self,company,rid):
        from invoice_archive import archive_document
        return archive_document(self.store.path.parent/'notas-fiscais',self.get(company,rid))
    def _archive_best_effort(self,company,rid):
        try:self.sync_archive(company,rid)
        except Exception as exc:
            import logging
            logging.error('Arquivo local pendente para %s: %s',rid,exc)
            try:
                with self.db:self._history(rid,'ARQUIVO_PENDENTE',str(exc))
            except sqlite3.Error:pass
    def draft_for_correction(self,company,rid):
        """Devolve dados de edição de uma rejeição ou revisão preparada, sem alterar o fiscal."""
        doc=self.get(company,rid)
        if doc['status'] not in ('REJEITADA','PREPARADA') or doc['proc_xml']:
            raise ValueError('Somente notas rejeitadas ou preparadas podem ser corrigidas. Para situação incerta ou em processamento, consulte a SEFAZ primeiro. Notas autorizadas não podem ser editadas.')
        co=self.store.get('company','',company)
        if document(co['CNPJCPF'])!=doc['cnpj']:raise ValueError('O CNPJ do emitente diverge do documento rejeitado.')
        original=json.loads(doc['snapshot'])['note']
        try:note=self.store.get('note',company,doc['source'])
        except ValueError:note=copy.deepcopy(original)
        note.update(series=str(doc['series']),number=str(doc['number']),cnf=original['cnf'],status='RASCUNHO',environment=doc['environment'])
        return copy.deepcopy(note)

    def prepare(self,company,source,snapshot,signed_xml,key):
        from fiscal_events import check_number_available
        check_number_available(self.store,company,snapshot['note'])
        cnpj=document(snapshot['company']['CNPJCPF']);note=snapshot['note'];environment=note.get('environment','2');now=datetime.now(TZ).isoformat();rid=uuid.uuid4().hex
        # Sempre verifica que os bytes reservados representam o mesmo emitente/ambiente/chave.
        inf=parse_xml(signed_xml).find('n:infNFe',{'n':NS})
        if inf is None or inf.attrib.get('Id')!='NFe'+key or text(inf,'n:ide/n:tpAmb')!=environment or text(inf,'n:emit/n:CNPJ')!=cnpj:raise ValueError('XML não corresponde à reserva fiscal.')
        existing=self.db.execute('SELECT id,status,series,number FROM fiscal_documents WHERE company=? AND source=?',(company,source)).fetchone()
        if existing and existing[1] in ('REJEITADA','PREPARADA'):
            rid=existing[0]
            if (int(note['series']),int(note['number']))!=existing[2:]:
                raise ValueError('A correção da rejeição deve manter a mesma série e número.')
            with self.db:
                self.db.execute('UPDATE fiscal_documents SET status=status WHERE 0')
                from vf_workflow import check_duplicates
                check_duplicates(self.store,company,snapshot,source)
                previous=self.get(company,rid)
                if previous['status']!=existing[1]:raise ValueError('A situação fiscal mudou. Recarregue o documento.')
                if previous['environment']!=environment:raise ValueError('Uma nota existente não pode mudar de ambiente.')
                if previous['cnpj']!=cnpj:raise ValueError('A correção deve manter o CNPJ do emitente original.')
                if previous['proc_xml']:raise ValueError('Documento com protocolo de autorização não pode ser corrigido como rejeitado.')
                changed=self.db.execute("UPDATE fiscal_documents SET access_key=?,status='PREPARADA',snapshot=?,signed_xml=?,response_xml=NULL,receipt='',protocol='',reason='',updated=? WHERE company=? AND id=? AND status=? AND signed_xml=?",(key,json.dumps(snapshot,ensure_ascii=False),signed_xml,now,company,rid,existing[1],previous['signed_xml'])).rowcount
                if changed!=1:raise ValueError('Situação do documento mudou; consulte antes de corrigir.')
                self._history(rid,'CORRECAO_REJEICAO' if existing[1]=='REJEITADA' else 'REVISAO_ANTES_ENVIO',previous['reason'],previous['signed_xml'])
            self._archive_best_effort(company,rid)
            return rid
        try:
            with self.db:
                self.db.execute('UPDATE fiscal_documents SET status=status WHERE 0')
                from vf_workflow import check_duplicates
                check_duplicates(self.store,company,snapshot,source)
                self.db.execute('INSERT INTO fiscal_documents(id,company,source,cnpj,environment,series,number,access_key,status,snapshot,signed_xml,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(rid,company,source,cnpj,environment,int(note['series']),int(note['number']),key,'PREPARADA',json.dumps(snapshot,ensure_ascii=False),signed_xml,now,now))
                self._history(rid,'PREPARADA','XML assinado e número reservado.')
        except sqlite3.IntegrityError:raise ValueError('Já existe documento fiscal preparado com este rascunho ou esta série/número. Consulte a aba Homologação SEFAZ; não crie outro envio.') from None
        self._archive_best_effort(company,rid)
        return rid
    def assert_sendable(self,company,rid):
        """Validação offline final: nenhum estado de envio é iniciado nesta etapa."""
        doc=self.get(company,rid)
        if doc['status'] not in ('PREPARADA','NAO_LOCALIZADA'):
            raise ValueError('Esta nota não está pronta para envio. Consulte a situação fiscal.')
        snapshot=json.loads(doc['snapshot']);note=copy.deepcopy(snapshot['note'])
        from vf_workflow import check_duplicates
        check_duplicates(self.store,company,snapshot,doc['source'])
        from fiscal_events import check_number_available
        check_number_available(self.store,company,note)
        current_company=self.store.get('company','',company)
        if current_company.get('CRT')!=snapshot['company'].get('CRT'):raise ValueError('O regime tributário da empresa mudou após a assinatura. Revise e assine novamente.')
        if current_company.get('environment','2')!=doc['environment']:raise ValueError('A nota pertence a outro ambiente. Selecione o ambiente correspondente nas configurações antes de enviar.')
        if doc['environment']=='1' and not current_company.get('production_enabled'):raise ValueError('Produção desativada para esta empresa.')
        if document(current_company['CNPJCPF'])!=doc['cnpj']:raise ValueError('O emitente da sessão não corresponde à nota reservada.')
        note.setdefault('nature','VENDA DE MERCADORIA')
        from note_validation import validate_note
        issues=validate_note(snapshot['company'],snapshot['recipient'],note)
        if issues:raise ValueError('Envio bloqueado pela validação local:\n'+'\n'.join(i.message for i in issues[:15]))
        validate_schema(doc['signed_xml'])
        inf=parse_xml(doc['signed_xml']).find('n:infNFe',{'n':NS})
        expected_xml,_,_=build_unsigned(snapshot['company'],snapshot['recipient'],note)
        def shape(node):
            return (node.tag,tuple(sorted(node.attrib.items())),(node.text or '').strip(),tuple(shape(c) for c in node if not c.tag.endswith('}verProc')))
        expected_inf=parse_xml(expected_xml).find('n:infNFe',{'n':NS})
        if shape(inf)!=shape(expected_inf):raise ValueError('O XML assinado diverge dos dados reservados. Revise e assine novamente.')
        from core import consumer_final_error
        actual=dict(operation=text(inf,'n:ide/n:tpNF'),destination=text(inf,'n:ide/n:idDest'),final=text(inf,'n:ide/n:indFinal'))
        consumer_error=consumer_final_error({'indIEDest':text(inf,'n:dest/n:indIEDest')},actual)
        if consumer_error:raise ValueError('Envio bloqueado: '+consumer_error)
        for field,path,default in [('final','indFinal','0'),('operation','tpNF','1'),('destination','idDest','1'),('purpose','finNFe','1')]:
            if text(inf,'n:ide/n:'+path)!=str(note.get(field,default)):raise ValueError('O XML assinado diverge do rascunho reservado. Edite e assine novamente antes de enviar.')
        try:current=self.store.get('note',company,doc['source'])
        except ValueError:current=None
        if current is not None:
            def comparable(data):
                result=copy.deepcopy(data)
                for field in ('issued_at','date','status'):result.pop(field,None)
                result.setdefault('nature','VENDA DE MERCADORIA')
                return result
            if comparable(current)!=comparable(snapshot['note']):raise ValueError('O rascunho foi alterado após a assinatura. Abra Editar / corrigir e assine novamente antes de enviar.')
        return doc

    def begin_send(self,company,rid,expected_xml=None):
        if expected_xml is None:expected_xml=self.get(company,rid)['signed_xml']
        with self.db:
            self.db.execute('UPDATE fiscal_documents SET status=status WHERE 0')
            doc=self.get(company,rid)
            from vf_workflow import check_duplicates
            check_duplicates(self.store,company,json.loads(doc['snapshot']),doc['source'])
            changed=self.db.execute("UPDATE fiscal_documents SET status='ENVIANDO',updated=? WHERE company=? AND id=? AND status IN ('PREPARADA','NAO_LOCALIZADA') AND signed_xml=?",(datetime.now(TZ).isoformat(),company,rid,expected_xml)).rowcount
            if changed!=1:raise ValueError('Este documento não pode ser reenviado. Consulte sua situação primeiro.')
            self._history(rid,'ENVIANDO','Estado persistido antes da comunicação; nenhum reenvio automático.')
    def uncertain(self,company,rid):
        with self.db:
            self.db.execute("UPDATE fiscal_documents SET status='INCERTA',reason=?,updated=? WHERE company=? AND id=? AND status NOT IN ('AUTORIZADA','CANCELADA')",('Falha de comunicação ou resposta inválida. Consulte a chave antes de reenviar.',datetime.now(TZ).isoformat(),company,rid))
            self._history(rid,'INCERTA')
    def apply_response(self,company,rid,data):
        doc=self.get(company,rid);result=unpack_response(data,doc['access_key'],doc['environment']);code=result['code'];proc=None
        if code in ('100','150'):
            proc=assemble_process(doc['signed_xml'],result);status='AUTORIZADA'
        elif code in ('101','151','155'):status='CANCELADA'
        elif code in ('110','301','302','303'):status='DENEGADA'
        elif code=='217':status='NAO_LOCALIZADA'
        elif code in ('103','105','104'):status='PROCESSANDO'
        elif code in ('106','108','109','204','539','656','999'):status='INCERTA'
        elif result['root_type']=='retConsSitNFe':status='INCERTA'
        else:status='REJEITADA'
        if doc['status']=='CANCELADA' and status!='CANCELADA':raise ValueError('Nota cancelada não pode voltar a autorizada por retorno anterior. Cancelamento preservado.')
        # Uma resposta sem protocolo não pode apagar uma autorização já confirmada.
        if doc['status'] in ('AUTORIZADA','CANCELADA') and status not in ('AUTORIZADA','CANCELADA'):raise ValueError('Retorno divergente de documento finalizado; situação anterior preservada.')
        receipt=result.get('receipt') or doc['receipt'];protocol=result.get('protocol') or doc['protocol']
        with self.db:
            self.db.execute('UPDATE fiscal_documents SET status=status WHERE 0')
            latest=self.get(company,rid)
            if latest['status']=='CANCELADA' and status!='CANCELADA':raise ValueError('Cancelamento registrado durante a consulta; retorno anterior descartado.')
            if latest['status']=='AUTORIZADA' and status not in ('AUTORIZADA','CANCELADA'):raise ValueError('Autorização mais recente preservada.')
            self.db.execute('UPDATE fiscal_documents SET status=?,response_xml=?,proc_xml=COALESCE(?,proc_xml),receipt=?,protocol=?,reason=?,updated=? WHERE company=? AND id=?',(status,data,proc,receipt,protocol,code+' — '+result['reason'],datetime.now(TZ).isoformat(),company,rid))
            self._history(rid,status,code+' — '+result['reason'],data)
            if status=='AUTORIZADA':
                company_data=self.store.get('company','',company)
                series_field='production_series' if doc['environment']=='1' else 'series'
                number_field='production_next_number' if doc['environment']=='1' else 'next_number'
                if int(company_data.get(series_field,'1'))==doc['series']:
                    company_data[number_field]=str(max(int(company_data.get(number_field,'1')),doc['number']+1))
                    # Sem commit intermediário: autorização e incremento ficam na mesma transação.
                    self.db.execute('UPDATE records SET data=?,updated=? WHERE id=? AND kind=? AND company=?',(json.dumps(company_data,ensure_ascii=False),datetime.now(TZ).isoformat(),company,'company',''))
        self._archive_best_effort(company,rid)
        return status


class FiscalService:
    def __init__(self,store,certificate,transport=None):
        self.store=store;self.certificate=certificate;self.transport=transport or SefazTransport(certificate)
    def _doc(self,company,rid):
        doc=self.store.get(company,rid)
        if self.certificate.cnpj[:8]!=doc['cnpj'][:8]:raise ValueError('A1 não corresponde à raiz do emitente.')
        return doc
    def status(self,environment='2'):
        ret=self.transport.request('status',payload('consStatServ',tpAmb=environment,cUF='27',xServ='STATUS'))
        result=unpack_response(ret,expected_environment=environment);return result['code']+' — '+result['reason']
    def send(self,company,rid):
        doc=self._doc(company,rid);self.store.assert_sendable(company,rid)
        from signxml import XMLVerifier,SignatureConfiguration,SignatureMethod,DigestAlgorithm
        cfg=SignatureConfiguration(signature_methods=frozenset({SignatureMethod.RSA_SHA1}),digest_algorithms=frozenset({DigestAlgorithm.SHA1}))
        XMLVerifier().verify(parse_xml(doc['signed_xml']),x509_cert=self.certificate.cert.public_bytes(serialization.Encoding.PEM),expect_config=cfg)
        self.store.begin_send(company,rid,doc['signed_xml'])
        envi=ET.Element('{'+NS+'}enviNFe',nsmap={None:NS},versao='4.00')
        tag(envi,'idLote',datetime.now(TZ).strftime('%y%m%d%H%M%S'));tag(envi,'indSinc','1');envi.append(parse_xml(doc['signed_xml']))
        try:
            result=self.transport.request('send',serialize(envi))
            return self.store.apply_response(company,rid,result)
        except Exception:
            self.store.uncertain(company,rid);raise
    def query(self,company,rid):
        doc=self._doc(company,rid)
        result=self.transport.request('query',payload('consSitNFe',tpAmb=doc['environment'],xServ='CONSULTAR',chNFe=doc['access_key']))
        return self.store.apply_response(company,rid,result)
    def receipt(self,company,rid):
        doc=self._doc(company,rid)
        if not re.fullmatch('[0-9]{15}',doc['receipt']):raise ValueError('Não há recibo de lote válido; consulte pela chave.')
        result=self.transport.request('receipt',payload('consReciNFe',tpAmb=doc['environment'],nRec=doc['receipt']))
        return self.store.apply_response(company,rid,result)


def render_danfe(xml_data, is_preview=False):
    """Renderização local; nunca envia XML a serviços de PDF."""
    from brazilfiscalreport.danfe import Danfe, DanfeConfig, FooterStamp
    root=parse_xml(xml_data)
    inf=root.find('n:NFe/n:infNFe',{'n':NS}) if ET.QName(root).localname=='nfeProc' else root.find('n:infNFe',{'n':NS})
    if inf is None:raise ValueError('XML não contém NF-e.')
    environment=text(inf,'n:ide/n:tpAmb')
    if environment not in ('1','2'):raise ValueError('Ambiente inválido para DANFE.')
    if environment=='1' and not is_preview:
        prot=root.find('n:protNFe/n:infProt',{'n':NS})
        if ET.QName(root).localname!='nfeProc' or prot is None or text(prot,'n:cStat') not in ('100','150') or text(prot,'n:tpAmb')!=environment or text(prot,'n:chNFe')!=inf.get('Id','')[3:]:
            raise ValueError('DANFE de produção exige XML com protocolo de autorização correspondente.')
        validate_schema(xml_data,'procNFe_v4.00.xsd')
    # Preserva tpAmb: o renderizador usa esse campo também para o nome do destinatário.
    # A prévia é identificada separadamente, sem alterar XML, ambiente ou protocolo.
    config=DanfeConfig(footer_stamp=FooterStamp(text='PREVIA DO DANFE - SEM AUTORIZACAO DE USO')) if is_preview else None
    return bytes(Danfe(xml=serialize(root).decode('utf-8'),config=config).output())
