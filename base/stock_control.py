"""Estoque opcional, movimentos imutáveis e idempotentes por empresa/ambiente."""
import hashlib,json,uuid
from datetime import datetime
from decimal import Decimal
from core import number
from fiscal import FiscalStore,parse_xml,text,NS
from business_config import load

def identity(*values):return hashlib.sha256('|'.join(map(str,values)).encode()).hexdigest()
def clean_qty(value):
    qty=number(value)
    if abs(qty)>Decimal('1000000000000') or qty.as_tuple().exponent < -8:raise ValueError('Quantidade/fator fora do limite de oito casas decimais.')
    return qty

def xml_items(raw):
    root=parse_xml(raw);inf=root.find('n:NFe/n:infNFe',{'n':NS})
    if inf is None:raise ValueError('XML processado sem itens de NF-e.')
    return [dict(line=int(det.get('nItem',i+1)),code=text(det,'n:prod/n:cProd'),name=text(det,'n:prod/n:xProd'),NCM=text(det,'n:prod/n:NCM'),unit=text(det,'n:prod/n:uCom'),quantity=text(det,'n:prod/n:qCom'),gtin=text(det,'n:prod/n:cEAN')) for i,det in enumerate(inf.findall('n:det',{'n':NS}))]

def movement(store,cid,env,product,qty,source,source_id,line,label,reverse=False):
    store.get('product',cid,product);qty=clean_qty(qty)
    if env not in ('1','2'):raise ValueError('Ambiente inválido.')
    rid='stock-'+identity(cid,env,source,source_id,line,'reverse' if reverse else 'original')
    data=dict(environment=env,product_id=product,quantity=str(qty),source=source,source_id=source_id,line=line,label=label,reverse=reverse,stamp=datetime.now().astimezone().isoformat())
    with store.db:
        changed=store.db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?)',(rid,'stock_move',cid,json.dumps(data,ensure_ascii=False),data['stamp'])).rowcount
        if changed:store.db.execute('INSERT INTO audit(stamp,action,record) VALUES(?,?,?)',(data['stamp'],'MOVIMENTAR ESTOQUE',rid))
    return rid

def manual(store,cid,env,product,qty,reason):
    if load(store,cid)['stock_enabled']!='1':raise ValueError('Ative o estoque nas configurações desta empresa.')
    if len(str(reason).strip())<10:raise ValueError('Descreva o motivo do ajuste, com pelo menos 10 caracteres.')
    qty=clean_qty(qty)
    if not qty:raise ValueError('Informe uma quantidade diferente de zero.')
    return movement(store,cid,env,product,qty,'AJUSTE',uuid.uuid4().hex,0,str(reason).strip()[:500])

def mapping_id(cid,source,rid,line):return 'stockmap-'+identity(cid,source,rid,line)
def set_mapping(store,cid,source,rid,line,product,factor):
    if source=='SAIDA':FiscalStore(store).get(cid,rid)
    elif source=='ENTRADA':store.get('received',cid,rid)
    else:raise ValueError('Origem inválida.')
    factor=clean_qty(factor)
    if factor<=0:raise ValueError('O fator de conversão deve ser positivo.')
    store.get('product',cid,product)
    for _,m in store.list('stock_move',cid):
        if m['source']==source and m['source_id']==rid and m['line']==int(line):raise ValueError('Item já movimentado. Use ajuste para corrigir o saldo, preservando o histórico.')
    store.save('stock_mapping',dict(product_id=product,factor=str(factor),source=source,source_id=rid,line=int(line)),cid,mapping_id(cid,source,rid,int(line)))

def product_match(products,item,incoming):
    products=[(pid,p) for pid,p in products if not p.get('_archived')]
    gtin=item.get('gtin','');hits=[]
    if gtin and gtin!='SEM GTIN':hits=[(pid,p) for pid,p in products if (p.get('gtin') or p.get('EAN'))==gtin]
    if not hits and not incoming:hits=[(pid,p) for pid,p in products if str(p.get('code','')).casefold()==item['code'].casefold()]
    if len(hits)==1 and hits[0][1].get('unit','').casefold()==item['unit'].casefold():return dict(product_id=hits[0][0],factor='1')
    return None

def reconcile(store,cid):
    config=load(store,cid)
    if config['stock_enabled']!='1':return []
    products=store.list('product',cid);old={}
    for _,m in store.list('stock_move',cid):old[(m['source'],m['source_id'],m['line'],m.get('reverse',False))]=m
    sources=[];pending=[]
    for d in FiscalStore(store).list(cid):
        if d['status'] not in ('AUTORIZADA','CANCELADA') or not d['proc_xml']:continue
        if d['id'] in config['stock_baseline'] and not any(k[0]=='SAIDA' and k[1]==d['id'] for k in old):continue
        root=parse_xml(d['proc_xml']);op=text(root,'n:NFe/n:infNFe/n:ide/n:tpNF')
        # Saídas emitidas reduzem estoque; entradas emitidas precisam de vínculo explícito.
        sources.append(dict(id=d['id'],source='SAIDA',env=d['environment'],number=str(d['number']),cancelled=d['status']=='CANCELADA',items=xml_items(d['proc_xml']),sign=1 if op=='0' else -1,incoming=False))
    for rid,doc in store.list('received',cid):
        if doc.get('direction')!='recebida' or not doc.get('stock_enabled'):continue
        sources.append(dict(id=rid,source='ENTRADA',env=doc['environment'],number=doc.get('number',''),cancelled=doc.get('cancelled',False),items=doc.get('items',[]),sign=int(doc.get('stock_sign',1)),incoming=True))
    for src in sources:
        for item in src['items']:
            line=int(item['line']);key=(src['source'],src['id'],line,False);previous=old.get(key)
            if src['cancelled']:
                if previous:movement(store,cid,src['env'],previous['product_id'],-number(previous['quantity']),src['source'],src['id'],line,'Estorno por cancelamento da NF-e '+src['number'],True)
                continue
            if previous:continue
            try:link=store.get('stock_mapping',cid,mapping_id(cid,src['source'],src['id'],line))
            except ValueError:link=product_match(products,item,src['incoming'])
            if not link:
                pending.append(dict(source=src['source'],id=src['id'],environment=src['env'],number=src['number'],**item));continue
            try:
                qty=clean_qty(item['quantity'])*clean_qty(link['factor'])*src['sign']
                movement(store,cid,src['env'],link['product_id'],qty,src['source'],src['id'],line,'NF-e '+src['number']+' · '+item['unit']+' × '+link['factor'])
            except ValueError as e:pending.append(dict(source=src['source'],id=src['id'],environment=src['env'],number=src['number'],error=str(e),**item))
    return pending

def state(store,cid,env):
    pending=reconcile(store,cid);balances={};moves=[]
    for rid,m in store.list('stock_move',cid):
        if m['environment']!=env:continue
        balances[m['product_id']]=balances.get(m['product_id'],Decimal(0))+number(m['quantity']);moves.append(dict(m,id=rid))
    products=[dict(p,id=pid,balance=str(balances.get(pid,0))) for pid,p in store.list('product',cid) if not p.get('_archived') or pid in balances]
    return dict(enabled=load(store,cid)['stock_enabled']=='1',products=products,movements=sorted(moves,key=lambda m:m['stamp'],reverse=True)[:300],pending=[p for p in pending if p['environment']==env])
