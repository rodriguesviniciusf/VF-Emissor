"""Cenários explícitos CRT1: ST/FCP-ST e IPI devolvido. Sem enquadramento automático."""
import copy,re
from decimal import Decimal
from core import number,money
ST_CODES=('201','202','203')
ZEROS=('st_base','st','fcpst_base','fcpst','ipi_return')
class TaxError(ValueError):
    def __init__(self,field,message):super().__init__(message);self.field=field

def required(data,key,rate=False):
    if not str(data.get(key,'')).strip():raise TaxError(key,'Informe '+key+', inclusive se for zero.')
    try:v=number(data[key])
    except ValueError:raise TaxError(key,'Valor inválido em '+key) from None
    if v<0 or (rate and v>100):raise TaxError(key,'Valor fora do intervalo permitido: '+key)
    if rate and v!=v.quantize(Decimal('0.0001')):raise TaxError(key,'Percentual aceita até quatro casas decimais: '+key)
    return v if rate else money(v)

def has_advanced(item,rule):return rule.get('icms_code') in ST_CODES or any(str(v).strip() and str(v)!='0' for k,v in item.get('taxes',{}).items() if k not in ('reviewed','legal_reference'))

def calculate_advanced(item,rule,crt,basic):
    t=item.get('taxes',{});code=rule.get('icms_code')
    if crt!='1':raise TaxError('reviewed','Os novos cenários contemplam CRT 1.')
    if t.get('difal_enabled')=='1':raise TaxError('difal_enabled','DIFAL no XML não habilitado para este enquadramento. Use somente o simulador independente.')
    if t.get('ipi_code'):raise TaxError('ipi_code','IPI tributado normal não habilitado no emissor CRT 1. IPI devolvido possui campos próprios.')
    if t.get('reviewed')!='1' or len(t.get('legal_reference','').strip())<15:raise TaxError('reviewed','Revise o enquadramento e registre a fundamentação dos tributos adicionais (mínimo 15 caracteres).')
    mapped=copy.deepcopy(rule)
    if code in ST_CODES:mapped['icms_code']='101' if code=='201' else '102'
    result=basic(item,mapped,crt);result.update({k:money(0) for k in ZEROS})
    if code in ST_CODES:
        if not re.fullmatch('[0-9]{7}',item.get('product',{}).get('CEST','')):raise TaxError('CEST','ST: informe CEST com 7 dígitos no item.')
        mode=t.get('st_mode','')
        if mode not in ('0','1','2','3','4','5','6'):raise TaxError('st_mode','Selecione a modalidade de base ST.')
        base=required(t,'st_base');rate=required(t,'st_rate',True);deduction=required(t,'st_deduction')
        if mode=='4':
            if not str(t.get('st_mva','')).strip():raise TaxError('st_mva','Informe a MVA oficial; a base ST final deve ser conferida separadamente.')
            mva=number(t['st_mva'])
            if not 0<=mva<=999 or mva!=mva.quantize(Decimal('0.0001')):raise TaxError('st_mva','MVA deve ficar entre 0 e 999%.')
        if str(t.get('st_reduction','')).strip():required(t,'st_reduction',True)
        value=money(base*rate/100)-deduction
        if value<0:raise TaxError('st_deduction','Dedução maior que o débito ST. Não é permitido transformar a diferença em crédito.')
        result.update(st_base=base,st=value)
        if t.get('fcpst_enabled')=='1':
            fb=required(t,'fcpst_base');fr=required(t,'fcpst_rate',True)
            result.update(fcpst_base=fb,fcpst=money(fb*fr/100))
    elif t.get('fcpst_enabled')=='1' or any(str(t.get(k,'')).strip() for k in ('st_base','st_rate','st_deduction','st_mode','st_mva','st_reduction','fcpst_base','fcpst_rate')):raise TaxError('st_mode','Dados ST/FCP-ST exigem CSOSN 201, 202 ou 203 neste escopo.')
    if t.get('ipi_return_enabled')=='1':
        if code in ST_CODES:raise TaxError('ipi_return_enabled','Combinação ST + IPI devolvido ainda não homologada neste escopo.')
        original=required(t,'ipi_original_value');percent=required(t,'ipi_return_percent',True)
        if percent!=percent.quantize(Decimal('0.01')):raise TaxError('ipi_return_percent','Percentual devolvido aceita até duas casas decimais.')
        if percent<=0:raise TaxError('ipi_return_percent','Percentual devolvido deve ser maior que zero e até 100%.')
        if not re.fullmatch('[0-9]{44}',t.get('ipi_origin_key','')):raise TaxError('ipi_origin_key','Importe a nota original para vincular o IPI devolvido.')
        if len(t.get('ipi_reason','').strip())<15 or len(t.get('ipi_reason',''))>500:raise TaxError('ipi_reason','Informe o motivo da devolução, entre 15 e 500 caracteres.')
        result['ipi_return']=money(original*percent/100)
    if item.get('auto_calc','1')=='0':
        for key in ('st','fcpst','ipi_return'):
            if result[key] or str(t.get('manual_'+key,'')).strip():
                entered=required(t,'manual_'+key)
                if entered!=result[key]:raise TaxError('manual_'+key,'Valor manual de '+key+' diverge do cálculo das bases/percentuais.')
    result['net']+=result['st']+result['fcpst']+result['ipi_return'];return result

def validate_context(company,recipient,note):
    if company.get('CRT')=='3':
        from normal_fiscal import validate_context as normal_context
        normal_context(company,recipient,note);return
    for index,item in enumerate(note.get('items',[])):
        rule=item.get('rule',{});t=item.get('taxes',{})
        def fail(field,message):
            error=TaxError(field,message);error.item_index=index;raise error
        if not has_advanced(item,rule):continue
        if note.get('environment','2')!='2':fail('reviewed','Os novos cenários ST/FCP-ST/IPI devolvido estão habilitados somente em homologação nesta versão.')
        if rule.get('icms_code') in ST_CODES:
            if note.get('operation','1')!='1' or note.get('purpose','1')!='1' or (recipient or {}).get('indIEDest')!='1':fail('st_mode','ST novo: somente saída normal para destinatário contribuinte, sem combinações de devolução/ajuste.')
        if t.get('ipi_return_enabled')=='1':
            refs=str(note.get('references','')).replace(';',',').split(',')
            if note.get('purpose')!='4' or note.get('operation')!='1' or t.get('ipi_origin_key') not in refs:fail('ipi_origin_key','IPI devolvido exige saída de devolução e referência à nota original importada.')

def simulate_difal(base,internal,interstate,fcp):
    b=number(base);a=number(internal);i=number(interstate);f=number(fcp)
    if b<0 or not 0<=i<=a<=100 or not 0<=f<=100:raise ValueError('Confira base e percentuais; alíquota interna deve ser igual ou maior que a interestadual.')
    return dict(difal=money(b*(a-i)/100),fcp=money(b*f/100))
