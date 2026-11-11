"""Descrições de operação, sem substituir CFOP/finalidade/tributação dos itens."""
from core import clean
DEFAULT_NATURES=(
 'VENDA DE MERCADORIA','VENDA DE PRODUÇÃO DO ESTABELECIMENTO','COMPRA DE MERCADORIAS',
 'DEVOLUÇÃO DE MERCADORIA','REMESSA PARA CONSERTO','RETORNO DE CONSERTO',
 'REMESSA PARA DEMONSTRAÇÃO','RETORNO DE DEMONSTRAÇÃO','TRANSFERÊNCIA DE MERCADORIAS',
 'NF-E COMPLEMENTAR','NF-E DE AJUSTE',
)
def nature_choices(store,company,current=''):
    values=list(DEFAULT_NATURES)+[p['name'] for _,p in store.list('nature',company)]
    if current:values.append(current)
    unique={value.casefold():value for value in values}
    return sorted(unique.values(),key=str.casefold)
def save_nature(store,company,name,rid=None):
    name=' '.join(clean(name).strip().split())
    if not name or len(name)>60:raise ValueError('Informe a natureza com 1 a 60 caracteres.')
    if any(ord(c)<32 for c in name):raise ValueError('Remova caracteres de controle da natureza.')
    for other_id,data in store.list('nature',company):
        if other_id!=rid and data['name'].casefold()==name.casefold():raise ValueError('Esta natureza já está cadastrada nesta empresa.')
    return store.save('nature',{'name':name},company,rid)
