"""Regime normal: grupos tributários tipados pelo XSD e cálculos explícitos.

Não escolhe enquadramento, alíquota, benefício nem classificação tributária.
Grupos especiais sem fórmula implementada exigem cálculo manual revisado.
"""
import copy,re
from functools import lru_cache
from pathlib import Path
from decimal import Decimal
from lxml import etree as E
from core import number,money,fmt

X='http://www.w3.org/2001/XMLSchema'; N='http://www.portalfiscal.inf.br/nfe'
NS={'x':X}; SCHEMAS=Path(__file__).parent/'schemas/nfe'
GROUPS=('ICMS','IPI','II','PIS','PISST','COFINS','COFINSST','ICMSUFDest','IS','IBSCBS')
ZERO_KEYS='st_base st fcpst_base fcpst ipi_return ipi ii fcp icms_deson deson_deduct fcpst_ret difal difal_origin fcp_dest ibs cbs selective'.split()

def present(v):
    if isinstance(v,dict):return any(present(x) for x in v.values())
    if isinstance(v,list):return any(present(x) for x in v)
    return v is not None and str(v).strip()!=''

@lru_cache(maxsize=1)
def registry():
    trees=[E.parse(str(p)) for p in SCHEMAS.glob('*.xsd')]
    types={n.get('name'):n for t in trees for n in t.xpath('/x:schema/x:complexType|/x:schema/x:simpleType',namespaces=NS)}
    layout=next(t for t in trees if Path(t.docinfo.URL).name=='leiauteNFe_v4.00.xsd')
    return types,layout

def documentation(n):return ' '.join(' '.join(n.xpath('./x:annotation/x:documentation//text()',namespaces=NS)).split())
def typename(n):return (n.get('type') or '').split(':')[-1]

def type_info(n,seen=()):
    types,_=registry();t=types.get(typename(n))
    if t is None:t=n.find('x:simpleType',NS)
    result={}
    if t is None:return result
    restriction=t.find('x:restriction',NS)
    if restriction is None:return result
    base=restriction.get('base','').split(':')[-1]
    if base in types and base not in seen:
        placeholder=E.Element('{'+X+'}element',type=base);result.update(type_info(placeholder,seen+(base,)))
    enums=restriction.findall('x:enumeration',NS)
    if enums:result['enum']=[dict(value=e.get('value'),label=documentation(e) or e.get('value')) for e in enums]
    for key in ('pattern','minLength','maxLength','length','fractionDigits','minInclusive','maxInclusive'):
        v=restriction.find('x:'+key,NS)
        if v is not None:result[key]=v.get('value')
    return result

def shape(n,depth=0):
    if depth>40:raise ValueError('Estrutura tributária excede a profundidade permitida.')
    kind=E.QName(n).localname
    if kind in ('sequence','choice','all'):
        return dict(kind=kind,optional=n.get('minOccurs')=='0',children=[shape(c,depth+1) for c in n if isinstance(c.tag,str) and E.QName(c).localname in ('element','sequence','choice','all')])
    d=dict(kind='element',name=n.get('name'),label=documentation(n) or n.get('name'),optional=n.get('minOccurs')=='0',maximum=n.get('maxOccurs','1'))
    if n.get('fixed') is not None:d['fixed']=n.get('fixed')
    if n.get('default') is not None:d['default']=n.get('default')
    types,_=registry();t=n.find('x:complexType',NS)
    if t is None:t=types.get(typename(n))
    particle=None if t is None else next((c for c in t if isinstance(c.tag,str) and E.QName(c).localname in ('sequence','choice','all')),None)
    if particle is not None:d['content']=shape(particle,depth+1)
    else:d.update(type_info(n));d['type']=typename(n)
    return d

@lru_cache(maxsize=1)
def catalog():
    _,layout=registry();det=layout.xpath('//x:element[@name="det"]',namespaces=NS)[0]
    tax=det.xpath('./x:complexType/x:sequence/x:element[@name="imposto"]',namespaces=NS)[0]
    out={}
    for name in GROUPS:
        found=tax.xpath('.//x:element[@name=$name]',namespaces=NS,name=name)
        if found:out[name]=shape(found[0])
    return out

def childnames(spec):
    if spec['kind']=='element':return [spec['name']]
    return [n for c in spec.get('children',[]) for n in childnames(c)]

def elements(spec):
    if spec['kind']=='element':return [spec]
    return [v for c in spec.get('children',[]) for v in elements(c)]

def emit_particle(parent,spec,data,path):
    children=spec.get('children',[])
    if spec.get('optional') and not any(present(data.get(n)) for n in childnames(spec)):return
    if spec['kind']=='choice':
        active=[c for c in children if any(present(data.get(n)) for n in childnames(c))]
        if len(active)>1:raise ValueError(path+': selecione somente uma alternativa de preenchimento.')
        if not active:
            if spec.get('optional'):return
            raise ValueError(path+': selecione a situação tributária ou forma de cálculo.')
        children=active
    for c in children:
        if c['kind']=='element':emit_element(parent,c,data.get(c['name']),path+'.'+c['name'])
        else:emit_particle(parent,c,data,path)

def emit_element(parent,spec,value,path):
    if not present(value):
        if spec.get('optional'):return
        raise ValueError(path+': informe '+spec['label'].split('.')[0]+'.')
    if isinstance(value,list):
        if spec.get('maximum','1')=='1':raise ValueError(path+': este grupo não aceita repetição.')
        if len(value)>1000:raise ValueError(path+': excesso de registros.')
        single=dict(spec,maximum='1')
        for v in value:emit_element(parent,single,v,path)
        return
    node=E.SubElement(parent,'{'+N+'}'+spec['name'])
    if 'content' in spec:
        if not isinstance(value,dict):raise ValueError(path+': estrutura inválida.')
        allowed=set(childnames(spec['content']))
        if set(value)-allowed:raise ValueError(path+': campo não reconhecido: '+', '.join(sorted(set(value)-allowed)))
        emit_particle(node,spec['content'],value,path)
    else:
        if isinstance(value,(dict,list,bool)):raise ValueError(path+': valor inválido.')
        v=str(value).strip()
        if spec.get('fixed') is not None and v!=spec['fixed']:raise ValueError(path+': valor fixo deve ser '+spec['fixed'])
        if spec.get('enum') and v not in [e['value'] for e in spec['enum']]:raise ValueError(path+': opção inválida.')
        if len(v)>20000 or any(ord(c)<32 for c in v):raise ValueError(path+': conteúdo inválido.')
        # Alíquotas e valores são decimais não negativos; o XSD verifica precisão/formato final.
        if spec['name'].startswith(('v','p','q','adRem')):
            n=number(v)
            if n<0:raise ValueError(path+': valor não pode ser negativo.')
            if spec['name'].startswith('p') and n>100 and spec['name'] not in ('pMVAST',):raise ValueError(path+': percentual maior que 100%.')
            v=format(n,'f')
            precision=re.search(r'\\\.\[0-9\]\{(\d+)(?:,(\d+))?\}',spec.get('pattern',''))
            if precision:
                minimum=int(precision[1]);maximum=int(precision[2] or precision[1])
                actual=max(0,-n.normalize().as_tuple().exponent)
                if actual>maximum:raise ValueError(path+': aceita até '+str(maximum)+' casas decimais.')
                v=format(n,'.'+str(max(minimum,actual))+'f')
        node.text=v

def append_groups(parent,data):
    if not isinstance(data,dict) or set(data)-set(GROUPS):raise ValueError('Grupo tributário não reconhecido.')
    if not all(present(data.get(k)) for k in ('ICMS','PIS','COFINS')):raise ValueError('Preencha ICMS, PIS e COFINS do regime normal.')
    for name in GROUPS:
        if present(data.get(name)):emit_element(parent,catalog()[name],data[name],name)

def default_groups(code='00',origin='0',icms_rate='0',pis_code='99',pis_rate='0',cofins_code='99',cofins_rate='0'):
    group='ICMS40' if code in ('40','41','50') else 'ICMS'+code
    icms=dict(orig=origin,CST=code)
    if code in ('00','10','20','51','70','90'):icms.update(modBC='3',pICMS=icms_rate)
    if code in ('20','70'):icms['pRedBC']='0'
    def pc(name,code,rate):
        child=name+('Aliq' if code in ('01','02') else 'NT' if code in ('04','05','06','07','08','09') else 'Qtde' if code=='03' else 'Outr')
        return {child:dict(CST=code,**({} if child.endswith('NT') else {'p'+name:rate}))}
    return dict(ICMS={group:icms},PIS=pc('PIS',pis_code,pis_rate),COFINS=pc('COFINS',cofins_code,cofins_rate))

def normal_groups(item,rule):
    if 'normal_groups' in item:return copy.deepcopy(item['normal_groups'])
    if 'normal_groups' in rule:return copy.deepcopy(rule['normal_groups'])
    return default_groups(rule.get('icms_code','00'),rule.get('origin','0'),rule.get('icms_rate','0'),rule.get('pis_code','99'),rule.get('pis_rate','0'),rule.get('cofins_code','99'),rule.get('cofins_rate','0'))

def walk(data):
    if isinstance(data,dict):
        yield data
        for v in data.values():yield from walk(v)
    elif isinstance(data,list):
        for v in data:yield from walk(v)

def amount(d,key,default=0):return number(d.get(key,default))
def put(d,key,value):d[key]=fmt(value)
def ratecalc(d,base,rate,value):
    if present(d.get(rate)):
        if not present(d.get(base)):raise ValueError('Informe a base '+base+' para calcular '+value+'.')
        put(d,value,money(amount(d,base)*amount(d,rate)/100))

def normalized(item,rule):
    groups=normal_groups(item,rule)
    qty=number(item.get('quantity',1));price=number(item.get('price',0));discount=money(item.get('discount',0))
    if qty<=0 or price<0 or discount<0:raise ValueError('Quantidade deve ser positiva e valores não negativos.')
    gross=money(qty*price)
    if discount>gross:raise ValueError('Desconto maior que o valor do produto.')
    expenses={k:money(item.get(k,0)) for k in ('freight','insurance','other')}
    if min(expenses.values())<0:raise ValueError('Despesas não podem ser negativas.')
    base=gross-discount+sum(expenses.values(),money(0))
    auto=item.get('normal_auto','1')=='1'
    if auto:
        ipi=groups.get('IPI',{}).get('IPITrib',{})
        if ipi:
            if present(ipi.get('pIPI')):
                if item.get('normal_auto_base','1')=='1':put(ipi,'vBC',base)
                ratecalc(ipi,'vBC','pIPI','vIPI')
            elif present(ipi.get('vUnid')):
                if not present(ipi.get('qUnid')):ipi['qUnid']=str(qty)
                put(ipi,'vIPI',amount(ipi,'qUnid')*amount(ipi,'vUnid'))
        icms_children=groups.get('ICMS',{})
        if len(icms_children)!=1:raise ValueError('Selecione um único grupo ICMS.')
        name,icms=next(iter(icms_children.items()));code=str(icms.get('CST',''))
        if name in ('ICMS02','ICMS15','ICMS53','ICMS61','ICMSPart','ICMSST'):
            raise ValueError('Grupo especial de combustíveis/partilha/repasse: selecione cálculo manual e confira os campos específicos.')
        if code in ('00','10','20','51','70','90') or name=='ICMSPart':
            if item.get('normal_auto_base','1')=='1' and icms.get('modBC','3')!='3':raise ValueError('Para esta modalidade de base ICMS, selecione bases manuais e informe o valor conferido. A base automática usa o valor da operação.')
            icmsbase=base+(amount(ipi,'vIPI') if rule.get('icms_include_ipi')=='1' else money(0))
            if item.get('normal_auto_base','1')=='1':put(icms,'vBC',icmsbase*(100-amount(icms,'pRedBC'))/100)
            ratecalc(icms,'vBC','pICMS','vICMS')
            if code=='51':
                operation=amount(icms,'vICMS');deferred=money(operation*amount(icms,'pDif')/100)
                put(icms,'vICMSOp',operation);put(icms,'vICMSDif',deferred);put(icms,'vICMS',operation-deferred)
        if present(icms.get('pFCP')):
            if name!='ICMS00' and (not present(icms.get('vBCFCP')) or item.get('normal_auto_base','1')=='1'):put(icms,'vBCFCP',amount(icms,'vBC'))
            put(icms,'vFCP',amount(icms,'vBC' if name=='ICMS00' else 'vBCFCP')*amount(icms,'pFCP')/100)
        if present(icms.get('pICMSST')):
            if item.get('normal_st_base_mode')=='formula':
                mode=icms.get('modBCST','4');stbase=base+amount(ipi,'vIPI')
                if mode=='4':
                    if amount(icms,'pMVAST')<0:raise ValueError('MVA não pode ser negativa.')
                    stbase=stbase*(100+amount(icms,'pMVAST'))/100
                elif mode=='5':
                    unit=number(item.get('normal_st_unit_value',''))
                    if unit<=0:raise ValueError('Informe o preço unitário de pauta maior que zero.')
                    stbase=qty*unit
                elif mode!='6':raise ValueError('Use base ST manual para esta modalidade.')
                reduction=amount(icms,'pRedBCST')
                if not 0<=reduction<=100:raise ValueError('Redução da base ST deve ficar entre 0 e 100%.')
                put(icms,'vBCST',stbase*(100-reduction)/100)
            if not present(icms.get('vBCST')):raise ValueError('Informe a base final de ICMS ST conferida.')
            deduction=number(item['normal_st_deduction'] if present(item.get('normal_st_deduction')) else icms.get('vICMS',0))
            value=money(amount(icms,'vBCST')*amount(icms,'pICMSST')/100)-money(deduction)
            if value<0:raise ValueError('ICMS ST negativo: confira base, alíquota e dedução.')
            put(icms,'vICMSST',value)
        if item.get('normal_st_base_mode')=='formula' and present(icms.get('pFCPST')):put(icms,'vBCFCPST',amount(icms,'vBCST'))
        ratecalc(icms,'vBCFCPST','pFCPST','vFCPST')
        ratecalc(icms,'vBCFCPSTRet','pFCPSTRet','vFCPSTRet')
        if present(icms.get('pICMSEfet')):
            if item.get('normal_auto_base','1')=='1':put(icms,'vBCEfet',base*(100-amount(icms,'pRedBCEfet'))/100)
            ratecalc(icms,'vBCEfet','pICMSEfet','vICMSEfet')
        for name in ('PIS','COFINS'):
            for group in (groups.get(name,{}),groups.get(name+'ST',{})):
                values=list(group.values()) if name in groups and group is groups.get(name) else [group]
                for pc in values:
                    if not isinstance(pc,dict):continue
                    if present(pc.get('p'+name)):
                        if item.get('normal_auto_base','1')=='1':put(pc,'vBC',base-(amount(icms,'vICMS') if rule.get('exclude_icms')=='1' else 0))
                        ratecalc(pc,'vBC','p'+name,'v'+name)
                    elif present(pc.get('vAliqProd')):
                        if not present(pc.get('qBCProd')):pc['qBCProd']=str(qty)
                        put(pc,'v'+name,amount(pc,'qBCProd')*amount(pc,'vAliqProd'))
        difal=groups.get('ICMSUFDest',{})
        if difal:
            if item.get('normal_auto_base','1')=='1':put(difal,'vBCUFDest',base)
            if item.get('normal_auto_base','1')=='1' or not present(difal.get('vBCFCPUFDest')):put(difal,'vBCFCPUFDest',amount(difal,'vBCUFDest'))
            ratecalc(difal,'vBCFCPUFDest','pFCPUFDest','vFCPUFDest')
            if all(present(difal.get(k)) for k in ('pICMSUFDest','pICMSInter','pICMSInterPart')):
                value=money(amount(difal,'vBCUFDest')*(amount(difal,'pICMSUFDest')-amount(difal,'pICMSInter'))/100)
                if value<0:raise ValueError('Alíquota interna menor que a interestadual no DIFAL.')
                put(difal,'vICMSUFDest',value*amount(difal,'pICMSInterPart')/100);put(difal,'vICMSUFRemet',value-amount(difal,'vICMSUFDest'))
        rtc=groups.get('IBSCBS',{}).get('gIBSCBS',{})
        if rtc:
            if item.get('normal_auto_base','1')=='1':put(rtc,'vBC',base)
            for branch,rate,target in (('gIBSUF','pIBSUF','vIBSUF'),('gIBSMun','pIBSMun','vIBSMun'),('gCBS','pCBS','vCBS')):
                part=rtc.get(branch,{})
                if not part:continue
                effective=amount(part,rate)
                if part.get('gRed'):
                    effective=effective*(100-amount(part['gRed'],'pRedAliq'))/100
                    part['gRed']['pAliqEfet']=format(effective.quantize(Decimal('.0001')),'f')
                tax=money(amount(rtc,'vBC')*effective/100)
                if part.get('gDif'):put(part['gDif'],'vDif',tax*amount(part['gDif'],'pDif')/100)
                put(part,target,tax-amount(part.get('gDif',{}),'vDif')-amount(part.get('gDevTrib',{}),'vDevTrib'))
            if rtc.get('gIBSUF') or rtc.get('gIBSMun'):put(rtc,'vIBS',amount(rtc.get('gIBSUF',{}),'vIBSUF')+amount(rtc.get('gIBSMun',{}),'vIBSMun'))
    return groups,dict(qty=qty,gross=gross,discount=discount,base=base,**expenses)

def calculate_normal(item,rule,*,validate=True):
    groups,b=normalized(item,rule)
    # Montagem tipada também detecta estruturas desconhecidas e alternativas conflitantes.
    if validate:
        scratch=E.Element('{'+N+'}imposto');append_groups(scratch,groups)
    values={k:money(0) for k in ZERO_KEYS};icms=next(iter(groups['ICMS'].values()))
    if item.get('normal_auto','1')!='1':
        def checked(actual,expected,label):
            if abs(money(actual)-money(expected))>Decimal('.01'):raise ValueError(label+': valor manual diverge da base e alíquota.')
        code=icms.get('CST')
        if code in ('00','10','20','70','90') and all(present(icms.get(k)) for k in ('vBC','pICMS','vICMS')):checked(icms['vICMS'],amount(icms,'vBC')*amount(icms,'pICMS')/100,'ICMS')
        if code=='51' and all(present(icms.get(k)) for k in ('vICMSOp','vICMSDif','vICMS')):checked(icms['vICMS'],amount(icms,'vICMSOp')-amount(icms,'vICMSDif'),'ICMS diferido')
        for name in ('PIS','COFINS'):
            for pc in walk(groups.get(name,{})):
                if present(pc.get('v'+name)) and present(pc.get('p'+name)):checked(pc['v'+name],amount(pc,'vBC')*amount(pc,'p'+name)/100,name)
                if present(pc.get('v'+name)) and present(pc.get('vAliqProd')):checked(pc['v'+name],amount(pc,'qBCProd')*amount(pc,'vAliqProd'),name)
    def sumfield(group,key):return sum((money(d[key]) for d in walk(group) if key in d),money(0))
    values.update(icms_base=money(icms.get('vBC',0)),icms=money(icms.get('vICMS',0)),st_base=money(icms.get('vBCST',0)),st=money(icms.get('vICMSST',0)),fcpst_base=money(icms.get('vBCFCPST',0)),fcpst=money(icms.get('vFCPST',0)),fcp=money(icms.get('vFCP',0)),fcpst_ret=money(icms.get('vFCPSTRet',0)),icms_deson=money(icms.get('vICMSDeson',0)),deson_deduct=money(icms.get('vICMSDeson',0)) if icms.get('indDeduzDeson')=='1' else money(0),ipi=sumfield(groups.get('IPI',{}),'vIPI'),ii=money(groups.get('II',{}).get('vII',0)),pis=sumfield(groups.get('PIS',{}),'vPIS'),cofins=sumfield(groups.get('COFINS',{}),'vCOFINS'),pis_base=sumfield(groups.get('PIS',{}),'vBC'),cofins_base=sumfield(groups.get('COFINS',{}),'vBC'),credit_sn=money(0))
    for key in ('qBCMono','vICMSMono','qBCMonoReten','vICMSMonoReten','qBCMonoRet','vICMSMonoRet'):
        if present(icms.get(key)):values[key]=number(icms[key])
    for branch,key,target in [('ICMSUFDest','vICMSUFDest','difal'),('ICMSUFDest','vICMSUFRemet','difal_origin'),('ICMSUFDest','vFCPUFDest','fcp_dest'),('IBSCBS','vIBS','ibs'),('IBSCBS','vCBS','cbs'),('IS','vIS','selective')]:values[target]=sumfield(groups.get(branch,{}),key)
    pcst=money(0)
    for group,field,flag in [('PISST','vPIS','indSomaPISST'),('COFINSST','vCOFINS','indSomaCOFINSST')]:
        if groups.get(group,{}).get(flag)=='1':pcst+=money(groups[group].get(field,0))
    if item.get('normal_ipi_return_enabled')=='1':
        percent=number(item.get('normal_ipi_return_percent',''));original=money(item.get('normal_ipi_original',''))
        if not 0<percent<=100 or original<0:raise ValueError('Confira percentual e valor original do IPI devolvido.')
        values['ipi_return']=money(original*percent/100)
    values.update({k:b[k] for k in ('gross','discount','freight','insurance','other')})
    values['net']=b['base']+values['st']+values['fcpst']+values['ipi']+values['ipi_return']+values['ii']-values['deson_deduct']+pcst
    values['pcbase']=b['base']-(values['icms'] if rule.get('exclude_icms')=='1' else money(0));return values

def validate_context(company,recipient,note):
    if company.get('CRT')!='3':return
    policy=company.get('rtc_policy','definir')
    if policy not in ('informar','sem_informacao_revisada'):raise ValueError('Configure a aplicabilidade de IBS/CBS da empresa e registre a revisão fiscal.')
    if policy=='sem_informacao_revisada' and len(company.get('rtc_reason','').strip())<15:raise ValueError('Registre a fundamentação para a emissão sem IBS/CBS nesta empresa.')
    for idx,item in enumerate(note.get('items',[]),1):
        rule=item.get('rule',{});groups=normal_groups(item,rule)
        if rule.get('reviewed')!='1':raise ValueError(f'Item {idx}: confira e aprove a tributação.')
        if policy=='informar' and not present(groups.get('IBSCBS')):raise ValueError(f'Item {idx}: informe IBS/CBS conforme a configuração da empresa.')
        if policy=='sem_informacao_revisada' and present(groups.get('IBSCBS')):raise ValueError('A empresa está configurada para emissão sem IBS/CBS. Revise a configuração antes de informar esses tributos.')
        if present(groups.get('ICMSUFDest')) and not (note.get('destination')=='2' and note.get('final')=='1' and recipient.get('indIEDest')=='9'):raise ValueError('DIFAL de consumidor final exige operação interestadual para não contribuinte consumidor final.')
        code=next(iter(groups.get('ICMS',{}).values()),{}).get('CST','')
        if str(code) not in ('00','02','10','15','20','30','40','41','50','51','53','60','61','70','90'):raise ValueError('CST do regime normal inválido.')
        if item.get('normal_auto','1')!='1' and item.get('normal_manual_reviewed')!='1':raise ValueError('Confirme a revisão dos cálculos manuais do regime normal.')
        if item.get('taxes'):raise ValueError('Remova os campos do Simples Nacional antes de usar o regime normal.')
        if item.get('normal_ipi_return_enabled')=='1':
            if note.get('purpose')!='4' or not note.get('references'):raise ValueError('IPI devolvido exige nota de devolução com documento referenciado.')
            if present(groups.get('IPI')):raise ValueError('Selecione IPI normal ou IPI devolvido para este item, após conferir seu enquadramento.')
        calculate_normal(item,rule)
    validate_payments(note)

def effective_payment(note):
    payment=note.get('normal_payment')
    if present(payment):
        rows=payment.get('detPag',[])
        if isinstance(rows,dict):rows=[rows]
        if rows and all(row.get('tPag')=='90' for row in rows):return '90'
        return rows[0].get('tPag','') if rows else ''
    return note.get('payment','01')

def validate_payments(note):
    payment=note.get('normal_payment')
    if not present(payment):return
    if note.get('normal_payment_reviewed')!='1':raise ValueError('Confira e aprove os pagamentos detalhados da nota.')
    holder=E.Element('{'+N+'}holder');emit_element(holder,total_catalog()['pag'],payment,'Pagamento')
    rows=payment.get('detPag',[])
    if isinstance(rows,dict):rows=[rows]
    if not rows:raise ValueError('Informe ao menos uma forma de pagamento.')
    if any(r.get('tPag')=='90' for r in rows):
        if len(rows)!=1 or money(rows[0].get('vPag',0))!=0:raise ValueError('Sem pagamento exige um único registro com valor zero.')
    else:
        total=money(note['normal_vnftot']) if present(note.get('normal_vnftot')) else sum((calculate_normal(i,i['rule'])['net'] for i in note.get('items',[])),money(0))
        value=sum((money(r.get('vPag',0)) for r in rows),money(0))-money(payment.get('vTroco',0))
        if value!=total:raise ValueError('A soma dos pagamentos menos o troco deve coincidir com o total da nota.')

def aggregate_totals(company,recipient,note):
    validate_context(company,recipient,note)
    from cfop_catalog import cfop_errors
    totals={}
    if not 1<=len(note.get('items',[]))<=990:raise ValueError('Inclua de 1 a 990 itens.')
    for item in note['items']:
        errors=cfop_errors(item['rule'].get('CFOP',''),note)
        if errors:raise ValueError(errors[0])
        for k,v in calculate_normal(item,item['rule']).items():totals[k]=totals.get(k,money(0))+v
    return totals

@lru_cache(maxsize=1)
def total_catalog():
    _,layout=registry()
    result={}
    for name in ('ICMSTot','ISTot','IBSCBSTot','pag'):
        candidates=layout.xpath('//x:element[@name=$name]',namespaces=NS,name=name)
        if candidates:result[name]=shape(candidates[0])
    return result

def append_rtc_totals(total,note):
    active=any(present(normal_groups(i,i['rule']).get('IBSCBS')) or present(normal_groups(i,i['rule']).get('IS')) for i in note['items'])
    if not active:return
    if note.get('normal_totals_reviewed')!='1':raise ValueError('Confira e aprove os totais de IBS/CBS e IS da nota.')
    if not present(note.get('normal_vnftot')):raise ValueError('Informe e confira o valor total da nota com a reforma tributária.')
    data=note.get('normal_totals',{})
    source=[normalized(i,i['rule'])[0] for i in note['items']]
    def nested(o,path):
        for k in path.split('.'):
            if not isinstance(o,dict):return None
            o=o.get(k)
        return o
    for path,sourcepath in [('IBSCBSTot.vBCIBSCBS','IBSCBS.gIBSCBS.vBC'),('IBSCBSTot.gIBS.vIBS','IBSCBS.gIBSCBS.vIBS'),('IBSCBSTot.gCBS.vCBS','IBSCBS.gIBSCBS.gCBS.vCBS'),('ISTot.vIS','IS.vIS')]:
        supplied=nested(data,path)
        amounts=[nested(g,sourcepath) for g in source]
        if supplied is not None and any(v is not None for v in amounts):
            if money(supplied)!=sum((money(v) for v in amounts if v is not None),money(0)):raise ValueError('Total de '+path+' diverge da soma dos itens.')
    for group,totalname in [('IS','ISTot'),('IBSCBS','IBSCBSTot')]:
        if any(present(normal_groups(i,i['rule']).get(group)) for i in note['items']):
            if not present(data.get(totalname)):raise ValueError('Informe os totais de '+group+'.')
            emit_element(total,total_catalog()[totalname],data[totalname],totalname)
    if present(note.get('normal_vnftot')):
        E.SubElement(total,'{'+N+'}vNFTot').text=fmt(note['normal_vnftot'])
