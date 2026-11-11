"""Fluxos locais. Sem comunicação fiscal e sem alterar documentos autorizados."""
import copy, datetime, hashlib, json, secrets, uuid
from decimal import Decimal
from core import number, document

def stable(data):
    return json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':'))

def next_number(store,cid,env,series):
    co=store.get('company','',cid)
    field='production_next_number' if env=='1' else 'next_number'
    raw=str(co.get(field,'1'))
    if not raw.isdigit() or not 1<=int(raw)<=999999999:raise ValueError('Próximo número configurado inválido.')
    used=[int(raw)-1]
    for _,note in store.list('note',cid):
        if not note.get('_archived') and note.get('environment','2')==env and str(note.get('series'))==str(series) and str(note.get('number','')).isdigit():used.append(int(note['number']))
    for row in store.db.execute('SELECT number FROM fiscal_documents WHERE company=? AND environment=? AND series=?',(cid,env,int(series))):used.append(row[0])
    result=max(used)+1
    from fiscal_events import reserved_ranges,now
    ranges=reserved_ranges(store,cid,env,series)
    while any(y==now().year and start<=result<=end for y,start,end,status in ranges):result=max(end+1 for y,start,end,status in ranges if y==now().year and start<=result<=end)
    if result>999999999:raise ValueError('Numeração esgotada nesta série.')
    return str(result)

def duplicate(store,cid,note):
    # Lista de campos de negócio; identidade fiscal e autorizações não são copiadas.
    fields=('nature operation destination presence purpose has_reference references recipient_id recipient_override final payment auto_calc transport_mode freight insurance other info info_fisco purchase_order purchase_contract purchase_commitment invoice_number invoice_original invoice_discount invoice_net duplicates carrier_doc carrier_name carrier_ie carrier_address carrier_city carrier_uf vehicle_plate vehicle_uf volume_qty volume_type volume_brand volume_number net_weight gross_weight items normal_payment normal_totals normal_vnftot normal_schema_flags').split()
    result={k:copy.deepcopy(note[k]) for k in fields if k in note}
    for item in result.get('items',[]):
        if item.get('taxes'):item['taxes']['reviewed']='0'
        if item.get('rule'):item['rule']['reviewed']='0'
        if 'normal_manual_reviewed' in item:item['normal_manual_reviewed']='0'
    for key in ('normal_payment_reviewed','normal_totals_reviewed'):
        if key in note:result[key]='0'
    co=store.get('company','',cid);env=co.get('environment','2')
    series=co.get('production_series','1') if env=='1' else co.get('series','1')
    result.update(issued_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3))).isoformat(timespec='seconds'),environment=env,series=series,number=next_number(store,cid,env,series),status='RASCUNHO',cnf=f'{secrets.randbelow(100000000):08d}')
    return result

def save_recovery(store,cid,rid,note,source):
    result=dict(note=copy.deepcopy(note),source=source,stamp=datetime.datetime.now().astimezone().isoformat())
    return store.save('recovery',result,cid,rid)

def remove_recovery(store,cid,rid):
    with store.db:store.db.execute("DELETE FROM records WHERE kind='recovery' AND company=? AND id=?",(cid,rid))

def economic(snapshot):
    n=snapshot['note'];r=snapshot['recipient'] or {}
    nums=lambda v:format(number(v).normalize(),'f')
    items=[]
    for i in n.get('items',[]):
        p=i.get('product',{});rule=i.get('rule',{})
        items.append([p.get('code',''),p.get('NCM',''),p.get('unit',''),*[nums(i.get(k,0)) for k in ('quantity','price','discount')]])
    items.sort(key=stable)
    return hashlib.sha256(stable(dict(recipient=document(r.get('CNPJCPF','')),items=items,operation=n.get('operation','1'),destination=n.get('destination','1'),purpose=n.get('purpose','1'),references=n.get('references',''),expenses=[nums(n.get(k,0)) for k in ('freight','insurance','other')])).encode()).hexdigest()

def similar(store,cid,snapshot,source=None):
    key=economic(snapshot);env=snapshot['note'].get('environment','2');matches=[]
    rows=store.db.execute("SELECT id,source,status,snapshot,series,number,signed_xml FROM fiscal_documents WHERE company=? AND environment=? AND status NOT IN ('REJEITADA','DENEGADA','CANCELADA')",(cid,env)).fetchall()
    for rid,other_source,status,raw,series,num,xml in rows:
        if source and source==other_source:continue
        if economic(json.loads(raw))==key:matches.append(dict(id=rid,status=status,series=series,number=num,digest=hashlib.sha256(xml).hexdigest()))
    return sorted(matches,key=lambda d:d['id'])

def approval_token(snapshot,matches):
    return hashlib.sha256(stable([economic(snapshot),matches]).encode()).hexdigest()

def check_duplicates(store,cid,snapshot,source=None):
    matches=similar(store,cid,snapshot,source)
    if not matches:return
    if any(m['status'] not in ('AUTORIZADA',) for m in matches):
        raise ValueError('Possível duplicidade: operação semelhante já reservada, em processamento ou incerta. Consulte a nota existente antes de criar outra.')
    n=snapshot['note']
    if n.get('duplicate_approval')!=approval_token(snapshot,matches) or len(n.get('duplicate_reason','').strip())<15:
        raise ValueError('Possível duplicidade: há nota autorizada com destinatário e itens iguais. Confira o documento existente e registre uma justificativa para uma nova operação legítima.')

def preview_html(company,recipient,note):
    from html import escape as e
    from core import calculate,brl,money
    esc=lambda v:e(str(v))
    total=money(0);rows=[]
    for i in note.get('items',[]):
        try:amount=calculate(i,i['rule'],company['CRT'])['net'];total+=amount;formatted=brl(amount)
        except (ValueError,KeyError):formatted='PENDENTE — validar tributação'
        rows.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in [i.get('product',{}).get('name',''),i.get('quantity',''),i.get('price',''),i.get('rule',{}).get('CFOP',''),formatted])+'</tr>')
    return '<h1>Conferência da NF-e</h1><p>PRÉVIA — NÃO É DANFE E NÃO AUTORIZA A NOTA</p><p>'+esc(company.get('xNome',''))+' · '+esc(company.get('CNPJCPF',''))+'</p><p>Destinatário: '+esc((recipient or {}).get('xNome','Não selecionado'))+'</p><p>'+esc(note.get('nature',''))+' · Série/número '+esc(note.get('series',''))+'/'+esc(note.get('number',''))+' · '+('PRODUÇÃO' if note.get('environment')=='1' else 'HOMOLOGAÇÃO')+'</p><table border="1" cellspacing="0" cellpadding="7"><tr><th>Produto</th><th>Quantidade</th><th>Unitário</th><th>CFOP</th><th>Total</th></tr>'+''.join(rows)+'</table><h2>Total '+esc(brl(total))+'</h2><p>Informações: '+esc(note.get('info',''))+'</p>'


def operation_profile(store,cid,note,recipient):
    criteria=dict(profile_operation=note.get('operation','1'),profile_destination=note.get('destination','1'),profile_purpose=note.get('purpose','1'),profile_recipient=(recipient or {}).get('indIEDest','9'))
    matches=[]
    for rid,rule in store.list('rule',cid):
        specified={k:str(rule.get(k,'')) for k in criteria if str(rule.get(k,'')).strip()}
        if not specified:continue
        if rule.get('reviewed')=='1' and all(criteria[k]==v for k,v in specified.items()):matches.append((len(specified),rid,rule))
    if not matches:raise ValueError('Nenhum perfil revisado corresponde à operação. Configure os critérios nos perfis tributários.')
    best=max(x[0] for x in matches);matches=[m for m in matches if m[0]==best]
    if len(matches)!=1:raise ValueError('Mais de um perfil corresponde à operação com a mesma prioridade. Defina critérios mais específicos.')
    return copy.deepcopy(matches[0][2])
