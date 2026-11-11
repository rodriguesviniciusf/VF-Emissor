"""Rateio explícito de despesas e dados opcionais de transporte/cobrança."""
import copy,datetime,re
from core import money,number,valid_document,document

AMOUNTS=('freight','insurance','other')
def allocate_expenses(items,note):
    result=copy.deepcopy(items)
    weights=[max(money(0),money(number(i.get('quantity',1))*number(i.get('price',0)))-money(i.get('discount',0))) for i in items]
    total=sum(weights,money(0))
    for key in AMOUNTS:
        value=money(note.get(key,0))
        if value<0:raise ValueError(key+': valor não pode ser negativo.')
        used=money(0)
        for index,item in enumerate(result):
            part=value-used if index==len(result)-1 else money(value*(weights[index]/total if total else number(1)/len(result)))
            item[key]=format(part,'.2f');used+=part
    return result

def finance_errors(note):
    errors=[]
    for key in AMOUNTS:
        try:
            if number(note.get(key,0))<0:raise ValueError()
        except ValueError:errors.append((key,'Informe um valor não negativo em '+key+'.'))
    mode=note.get('transport_mode','9')
    if mode not in ('0','1','2','3','4','9'):errors.append(('transport_mode','Modalidade de frete inválida.'))
    try:
        if mode=='9' and money(note.get('freight',0)):errors.append(('transport_mode','Há valor de frete: confira a modalidade do transporte.'))
    except ValueError:pass
    if mode=='9' and any(note.get(k) for k in ('carrier_doc','carrier_name','vehicle_plate','volume_qty')):errors.append(('transport_mode','Há dados de transporte: selecione a modalidade correspondente.'))
    if note.get('carrier_doc') and not valid_document(note['carrier_doc']):errors.append(('carrier_doc','CPF/CNPJ da transportadora inválido.'))
    if note.get('vehicle_plate') and not re.fullmatch('[A-Z0-9]{7}',note['vehicle_plate'].upper()):errors.append(('vehicle_plate','Placa deve conter 7 letras/números, sem hífen.'))
    if note.get('vehicle_plate') and not re.fullmatch('[A-Z]{2}',note.get('vehicle_uf','')):errors.append(('vehicle_uf','Informe a UF do veículo.'))
    for key in ('volume_qty','net_weight','gross_weight'):
        if note.get(key):
            try:
                if number(note[key])<0 or (key=='volume_qty' and number(note[key])!=int(number(note[key]))):raise ValueError()
            except ValueError:errors.append((key,'Quantidade/peso inválido.'))
    try:
        if note.get('gross_weight') and note.get('net_weight') and number(note['gross_weight'])<number(note['net_weight']):errors.append(('gross_weight','Peso bruto não pode ser menor que peso líquido.'))
    except ValueError:pass
    if note.get('invoice_number'):
        try:
            original=money(note.get('invoice_original',0));discount=money(note.get('invoice_discount',0));net=money(note.get('invoice_net',0))
            if min(original,discount,net)<0 or original-discount!=net:errors.append(('invoice_net','Fatura: valor líquido deve ser original menos desconto.'))
        except ValueError:errors.append(('invoice_original','Fatura: confira os valores.'))
    if note.get('duplicates'):
        try:
            rows=parse_duplicates(note['duplicates'])
            if not note.get('invoice_number'):errors.append(('invoice_number','Duplicatas exigem dados da fatura.'))
            elif sum((money(r[2]) for r in rows),money(0))!=money(note.get('invoice_net',0)):errors.append(('duplicates','A soma das duplicatas deve coincidir com o valor líquido da fatura.'))
        except ValueError as exc:errors.append(('duplicates',str(exc)))
    return errors

def parse_duplicates(text):
    rows=[]
    for entry in text.split(';'):
        if not entry.strip():continue
        parts=[p.strip() for p in entry.split('|')]
        if len(parts)!=3 or not re.fullmatch('[0-9]{3}',parts[0]):raise ValueError('Duplicatas: use 001|AAAA-MM-DD|valor;002|AAAA-MM-DD|valor.')
        try:datetime.date.fromisoformat(parts[1])
        except ValueError:raise ValueError('Data de vencimento da duplicata inválida.')
        if money(parts[2])<=0:raise ValueError('Valor da duplicata deve ser positivo.')
        rows.append(parts)
    if len(rows)>120:raise ValueError('Limite de 120 duplicatas.')
    if len({r[0] for r in rows})!=len(rows):raise ValueError('Números de duplicatas não podem se repetir.')
    return rows

def append_transport_and_billing(inf,note,tag,fmt):
    transport=tag(inf,'transp');mode=note.get('transport_mode','9');tag(transport,'modFrete',mode)
    if mode!='9':
        if note.get('carrier_doc') or note.get('carrier_name'):
            carrier=tag(transport,'transporta')
            if note.get('carrier_doc'):
                doc=document(note['carrier_doc']);tag(carrier,'CPF' if len(doc)==11 else 'CNPJ',doc)
            for field,name in [('carrier_name','xNome'),('carrier_ie','IE'),('carrier_address','xEnder'),('carrier_city','xMun'),('carrier_uf','UF')]:
                if note.get(field):tag(carrier,name,note[field])
        if note.get('vehicle_plate'):
            vehicle=tag(transport,'veicTransp');tag(vehicle,'placa',note['vehicle_plate'].upper());tag(vehicle,'UF',note['vehicle_uf'])
        if any(note.get(k) for k in ('volume_qty','volume_type','net_weight','gross_weight')):
            volume=tag(transport,'vol')
            for field,name in [('volume_qty','qVol'),('volume_type','esp'),('volume_brand','marca'),('volume_number','nVol'),('net_weight','pesoL'),('gross_weight','pesoB')]:
                if note.get(field):tag(volume,name,format(number(note[field]),'.3f') if field in ('net_weight','gross_weight') else str(int(number(note[field]))) if field=='volume_qty' else note[field])
    if note.get('invoice_number'):
        billing=tag(inf,'cobr');invoice=tag(billing,'fat')
        for name,value in [('nFat',note['invoice_number']),('vOrig',fmt(note.get('invoice_original',0))),('vDesc',fmt(note.get('invoice_discount',0))),('vLiq',fmt(note.get('invoice_net',0)))]:tag(invoice,name,value)
        for row in parse_duplicates(note.get('duplicates','')):
            duplicate=tag(billing,'dup');tag(duplicate,'nDup',row[0]);tag(duplicate,'dVenc',row[1]);tag(duplicate,'vDup',fmt(row[2]))
