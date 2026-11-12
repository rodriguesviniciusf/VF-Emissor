"""AL -> todas as UFs. Valida contexto e auxilia parâmetros após confirmação.

Não determina alíquota interna/FCP por NCM, benefício, ST nem obrigação de GNRE.
Fontes e alcance: REGRAS-INTERESTADUAIS.md.
"""
import copy,re
from datetime import date
from decimal import Decimal
from core import number,money
from cfop_catalog import catalog,cfop_errors

UFS='AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PE PI PR RJ RN RO RR RS SC SE SP TO'.split()
IMPORTED={'1','2','3','8'}
# E16a-30, NT 2025.001 v1.03, p.9 (substitui a relação antiga do MOC).
NO_EXEMPT_IE=set('AL AM BA CE DF ES GO MG MS MT PB PE RJ RN RS SE SP'.split())
EXEMPT_CODES={'40','41','103','300','400'}

def rate(origin):
    if str(origin) not in set('012345678'):raise ValueError('Confira a origem da mercadoria antes de calcular a alíquota interestadual.')
    return '4.00' if str(origin) in IMPORTED else '12.00'

def item_context(co,rec,note,item):
    from normal_fiscal import normal_groups,normalized
    rule=item.get('rule',{});normal=co.get('CRT')=='3';groups=normal_groups(item,rule) if normal else {}
    branch,icms=next(iter(groups.get('ICMS',{}).items()),('',{}))
    if normal:
        try:groups=normalized(item,rule)[0];branch,icms=next(iter(groups.get('ICMS',{}).items()),('',{}))
        except (ValueError,KeyError,TypeError):pass  # motor reporta os campos de cálculo incompletos
    code=str(icms.get('CST',rule.get('icms_code','')));origin=str(icms.get('orig',rule.get('origin','0')))
    cfop=str(rule.get('CFOP',''));record=catalog().get(cfop,{})
    interstate=co.get('UF','').strip().upper()!=rec.get('UF','').strip().upper()
    eligible=interstate and note.get('final','0')=='1' and rec.get('indIEDest','9')=='9'
    old_return=note.get('purpose','1')=='4' and any(re.fullmatch(r'[0-9]{44}',k.strip()) and int(k.strip()[2:4])<16 for k in str(note.get('references','')).split(','))
    exempt=not normal or note.get('operation','1')!='1' or branch=='ICMSPart' or code in EXEMPT_CODES or note.get('purpose','1') in ('2','3') or old_return or record.get('indRetor')=='1' or record.get('indRemes')=='1' or cfop in ('6552','6922','6929')
    return dict(interstate=interstate,eligible=eligible,difal_required=eligible and not exempt,branch=branch,icms=icms,groups=groups,code=code,origin=origin,cfop=cfop,record=record)

def issues(co,rec,note):
    if not co or not rec:return []
    out=[];contexts=[]
    def add(field,message):out.append(dict(field=field,message=message))
    for ix,item in enumerate(note.get('items',[])):
        try:c=item_context(co,rec,note,item)
        except (ValueError,KeyError,TypeError):continue
        contexts.append(c);base=f'item.{ix}.normal_groups.';icms=c['icms'];g=c['groups'];difal=g.get('ICMSUFDest',{})
        special=c['record'].get('indRetor')=='1' or c['record'].get('indAnula')=='1' or c['record'].get('title','').startswith('Anulação') or c['cfop'] in ('6118','6119','6122','6123') or c['branch']=='ICMSPart'
        imported_exception=c['origin'] in IMPORTED and c['code'] not in ('00','10','20','70','90')
        if c['interstate'] and note.get('operation','1')=='1' and note.get('purpose','1')=='1' and not special and not imported_exception and icms.get('pICMS') not in (None,''):
            try:
                maximum=number(rate(c['origin']))
                if number(icms['pICMS'])>maximum:
                    add(base+'ICMS.'+c['branch']+'.pICMS',f'Item {ix+1}: ICMS próprio acima do limite interestadual AL → {rec.get("UF")}: {maximum}%. Confira origem, benefício e perfil fiscal (693/663).')
            except ValueError:pass
        if c['difal_required'] and not difal:
            add(base+'ICMSUFDest.pICMSUFDest',f'Item {ix+1}: informe o DIFAL para consumidor final não contribuinte em {rec.get("UF")} (694). Use Preparar operação interestadual ou confira a aba DIFAL.')
        if difal:
            if not c['eligible']:
                add(base+'ICMSUFDest',f'Item {ix+1}: DIFAL informado fora de operação interestadual para consumidor final não contribuinte (695). Confira o grupo e os indicadores reais da operação.')
            try:
                actual=number(difal.get('pICMSInter',''));expected=number(rate(c['origin']))
                if actual and actual!=expected and note.get('purpose','1')=='1' and c['record'].get('indRetor')!='1':
                    add(base+'ICMSUFDest.pICMSInter',f'Item {ix+1}: alíquota interestadual do DIFAL incompatível com AL e a origem da mercadoria. Confira {expected}% (697/698).')
                if note.get('purpose','1')=='1' and c['record'].get('indRetor')!='1' and number(difal.get('pICMSInterPart',''))!=100:
                    add(base+'ICMSUFDest.pICMSInterPart',f'Item {ix+1}: a partilha para emissão normal em 2026 deve ser 100% para o destino (699).')
                if all(str(difal.get(k,'')).strip() for k in ('vBCUFDest','pICMSUFDest','pICMSInter','vICMSUFDest','vICMSUFRemet','pICMSInterPart')):
                    value=money(number(difal['vBCUFDest'])*(number(difal['pICMSUFDest'])-actual)/100)
                    expected_dest=money(value*number(difal['pICMSInterPart'])/100)
                    for field,calculated in [('vICMSUFDest',expected_dest),('vICMSUFRemet',value-expected_dest)]:
                        if abs(money(difal[field])-calculated)>Decimal('.01'):add(base+'ICMSUFDest.'+field,f'Item {ix+1}: valor de {field} diverge da base, alíquotas e partilha do DIFAL.')
                if all(str(difal.get(k,'')).strip() for k in ('vBCFCPUFDest','pFCPUFDest','vFCPUFDest')):
                    expected_fcp=money(number(difal['vBCFCPUFDest'])*number(difal['pFCPUFDest'])/100)
                    if abs(money(difal['vFCPUFDest'])-expected_fcp)>Decimal('.01'):add(base+'ICMSUFDest.vFCPUFDest',f'Item {ix+1}: FCP do destino diverge da base e alíquota (793).')
            except ValueError:pass
    if rec.get('indIEDest','9')=='2' and rec.get('UF','').upper() in NO_EXEMPT_IE and contexts:
        def positive(v):
            try:return number(v)>0
            except ValueError:return False
        st=any(positive(c['icms'].get('vICMSST',0)) or str(c['icms'].get('vICMSSTRet','')).strip() for c in contexts)
        if co.get('CRT')=='1':
            from core import calculate
            for item in note.get('items',[]):
                try:st=st or calculate(item,item['rule'],'1').get('st',0)>0
                except (ValueError,KeyError):pass
        if not st and not all(c['code'] in EXEMPT_CODES for c in contexts):add('recipient.indIEDest',f'805: {rec["UF"]} não admite este destinatário como contribuinte isento de IE neste contexto. Confira a situação cadastral real; não altere o indicador apenas para autorizar a nota.')
    return out

def validate(co,rec,note):
    found=issues(co,rec,note)
    if found:raise ValueError('\n'.join(i['message'] for i in found[:15]))

def load(store,cid):
    store.get('company','',cid)
    try:return store.get('interstate_settings',cid,'interstate-'+cid)
    except ValueError:return dict(rates={})

def save(store,cid,p):
    data=load(store,cid);uf=str(p.get('uf','')).upper()
    if uf not in UFS or uf=='AL':raise ValueError('Selecione uma UF de destino diferente de AL.')
    if p.get('remove') is True:data['rates'].pop(uf,None)
    else:
        if p.get('reviewed') is not True:raise ValueError('Confirme a revisão das alíquotas e da referência legal.')
        r={k:str(p.get(k,'')).strip() for k in ('internal','fcp','start','end','reference')}
        if not r['internal'] or not r['fcp'] or not 0<number(r['internal'])<=100 or not 0<=number(r['fcp'])<=100:raise ValueError('Informe ICMS interno e FCP conferidos, inclusive FCP zero quando aplicável.')
        for k in ('internal','fcp'):
            v=number(r[k])
            if v!=v.quantize(Decimal('.0001')):raise ValueError('Alíquotas aceitam até quatro casas decimais.')
            r[k]=str(v)
        date.fromisoformat(r['start'])
        if r['end'] and date.fromisoformat(r['end'])<date.fromisoformat(r['start']):raise ValueError('Fim anterior ao início de vigência.')
        if not 15<=len(r['reference'])<=500:raise ValueError('Registre a fonte/fundamentação das alíquotas com 15 a 500 caracteres.')
        data['rates'][uf]=r
    store.save('interstate_settings',data,cid,'interstate-'+cid);return data

def prepare_item(co,rec,note,item,p):
    if co.get('UF')!='AL' or rec.get('UF') not in UFS or rec['UF']=='AL':raise ValueError('Selecione um destinatário de outra UF para preparar uma operação AL → Brasil.')
    if note.get('destination')!='2' or note.get('operation','1')!='1' or note.get('purpose','1')!='1':raise ValueError('Este assistente atende saída interestadual normal. Confira destino, tipo e finalidade da nota.')
    cfop=str(p.get('cfop',''));errors=cfop_errors(cfop,note)
    if not re.fullmatch('6[0-9]{3}',cfop) or errors:raise ValueError('Confira o CFOP interestadual: '+('; '.join(errors) or 'deve começar com 6.'))
    out=copy.deepcopy(item);out.setdefault('rule',{})['CFOP']=cfop
    if co.get('CRT')=='3':
        from normal_fiscal import normal_groups
        out['normal_groups']=normal_groups(out,out['rule']);branch,icms=next(iter(out['normal_groups']['ICMS'].items()))
        if branch=='ICMSPart':raise ValueError('Grupo de partilha especial: confira manualmente o item.')
        interstate_rate=rate(icms.get('orig',out['rule'].get('origin','0')))
        if 'pICMS' in icms:icms['pICMS']=interstate_rate;out['rule']['icms_rate']=interstate_rate
        ctx=item_context(co,rec,note,out)
        if ctx['difal_required'] or out['normal_groups'].get('ICMSUFDest'):
            if p.get('rates_reviewed') is not True:raise ValueError('Confira as alíquotas internas e o FCP para esta mercadoria e UF antes de aplicar o DIFAL.')
            internal=str(p.get('internal','')).strip();fcp=str(p.get('fcp','')).strip()
            if not internal or not fcp or not number(interstate_rate)<=number(internal)<=100 or not 0<=number(fcp)<=100:raise ValueError('Confira a alíquota interna (sem somar FCP), a interestadual e o FCP do produto.')
            if out.get('normal_auto','1')!='1' or out.get('normal_auto_base','1')!='1':raise ValueError('Bases ou valores manuais: preencha e confira o DIFAL diretamente na aba do item.')
            out['normal_groups']['ICMSUFDest']=dict(pICMSUFDest=str(number(internal)),pFCPUFDest=str(number(fcp)),pICMSInter=interstate_rate,pICMSInterPart='100.00')
    out['rule']['reviewed']='0'
    return dict(item=out,message='Parâmetros aplicados somente ao item em edição. Confira a tributação e marque a revisão antes de salvar; nenhuma nota foi transmitida.')
