"""Descrições de operação, sem substituir CFOP/finalidade/tributação dos itens."""
import hashlib,json
from datetime import datetime
from core import clean
DEFAULT_NATURES=(
 'VENDA DE MERCADORIA','VENDA DE PRODUÇÃO DO ESTABELECIMENTO','COMPRA DE MERCADORIAS',
 'DEVOLUÇÃO DE MERCADORIA','REMESSA PARA CONSERTO','RETORNO DE CONSERTO',
 'REMESSA PARA DEMONSTRAÇÃO','RETORNO DE DEMONSTRAÇÃO','TRANSFERÊNCIA DE MERCADORIAS',
 'NF-E COMPLEMENTAR','NF-E DE AJUSTE',
)
def marker_id(company):return 'natures-'+hashlib.sha256(company.encode()).hexdigest()

def listing(store,company):
    store.get('company','',company)
    marker=marker_id(company)
    try:store.get('nature_config',company,marker)
    except ValueError:
        names={p['name'].casefold() for _,p in store.list('nature',company)}
        stamp=datetime.now().astimezone().isoformat()
        with store.db:
            for name in DEFAULT_NATURES:
                if name.casefold() in names:continue
                rid='nature-'+hashlib.sha256((company+'|'+name).encode()).hexdigest()
                store.db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?)',(rid,'nature',company,json.dumps(dict(name=name),ensure_ascii=False),stamp))
            store.db.execute('INSERT INTO records VALUES(?,?,?,?,?)',(marker,'nature_config',company,'{"initialized":true}',stamp))
    return sorted([dict(p,id=rid) for rid,p in store.list('nature',company) if not p.get('_archived')],key=lambda p:p['name'].casefold())

def nature_choices(store,company,current=''):
    values=[p['name'] for p in listing(store,company)]
    if current:values.append(current)
    unique={value.casefold():value for value in values}
    return sorted(unique.values(),key=str.casefold)
def save_nature(store,company,name,rid=None):
    listing(store,company)
    name=' '.join(clean(name).strip().split())
    if not name or len(name)>60:raise ValueError('Informe a natureza com 1 a 60 caracteres.')
    if any(ord(c)<32 for c in name):raise ValueError('Remova caracteres de controle da natureza.')
    for other_id,data in store.list('nature',company):
        if not data.get('_archived') and other_id!=rid and data['name'].casefold()==name.casefold():raise ValueError('Esta natureza já está cadastrada nesta empresa.')
    return store.save('nature',{'name':name},company,rid)

def remove(store,company,rid):
    data=store.get('nature',company,rid);data['_archived']=True
    store.save('nature',data,company,rid)
    return dict(ok=True)
