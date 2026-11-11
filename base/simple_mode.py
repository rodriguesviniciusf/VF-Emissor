"""Modelos locais de emissão simplificada. Usa os cálculos e a validação fiscal existentes."""
import copy, hashlib, json, re, uuid
from datetime import datetime, timezone, timedelta
from core import number, calculate, validate_party
from normal_fiscal import default_groups

UF=set('AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PE PI PR RJ RN RO RR RS SC SE SP TO'.split())
PAYMENTS={'01','02','15','16','17','18'}
FIELDS='name nature target_uf recipient_ie final presence payment transport_mode info info_fisco rule_source rule_id allow_price allow_discount allow_payment product_ids state'.split()
CO_FIELDS='CNPJCPF CRT UF IE xNome xLgr nro xCpl xBairro cMun xMun CEP IM CNAE rtc_policy rtc_reason'.split()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def record(store,kind,cid,rid):
    d=store.get(kind,cid,rid)
    if d.get('_archived'):raise ValueError('Cadastro arquivado. Revise o modelo e os produtos.')
    return {k:copy.deepcopy(v) for k,v in d.items() if not k.startswith('_')}
def load(store,cid):
    store.get('company','',cid)
    try:return store.get('simple_config',cid,'simple-'+cid)
    except ValueError:return dict(version=0,default_mode='complete',default_model_id='',models=[])
def model_stamp(store,cid,m):
    co=store.get('company','',cid)
    data=dict(model={k:m.get(k) for k in FIELDS},company={k:co.get(k,'') for k in CO_FIELDS})
    if m.get('rule_source')=='fixed':data['rule']=record(store,'rule',cid,m['rule_id'])
    return digest(data)
def rule_for(store,cid,m,p):
    rid=m.get('rule_id') if m['rule_source']=='fixed' else p.get('rule_id')
    if not rid:raise ValueError('Produto sem tributação vinculada. Configure o perfil no produto ou no modelo.')
    r=record(store,'rule',cid,rid);co=store.get('company','',cid)
    if r.get('reviewed')!='1':raise ValueError('O perfil tributário precisa estar revisado.')
    code=str(r.get('icms_code',''))
    if len(code)!=(2 if co.get('CRT')=='3' else 3):raise ValueError('Perfil incompatível com o regime da empresa.')
    prefix='5' if m['target_uf']==co.get('UF') else '6'
    if not re.fullmatch(prefix+'[0-9]{3}',str(r.get('CFOP',''))):raise ValueError('CFOP do perfil incompatível com a UF de destino do modelo.')
    criteria=dict(profile_operation='1',profile_destination='1' if prefix=='5' else '2',profile_purpose='1',profile_recipient=m['recipient_ie'])
    if any(str(r.get(k,'')).strip() and str(r[k])!=v for k,v in criteria.items()):raise ValueError('Os critérios do perfil tributário não correspondem ao modelo.')
    return r
def make_item(store,cid,m,pid,values=None):
    p=record(store,'product',cid,pid);v=values or {}
    if m.get('product_ids') and pid not in m['product_ids']:raise ValueError('Produto não liberado neste modelo.')
    r=rule_for(store,cid,m,p)
    if not re.fullmatch('[0-9]{8}',str(p.get('NCM',''))) or not p.get('unit'):raise ValueError('Confira NCM e unidade do produto.')
    qty=number(v.get('quantity','1'));price=number(v.get('price',p.get('price','0')));discount=number(v.get('discount','0'));freight=number(v.get('freight','0'))
    if qty<=0 or price<0 or discount<0 or freight<0 or discount>qty*price:raise ValueError('Confira quantidade, preço, desconto e frete do produto.')
    if m.get('allow_price')!='1' and price!=number(p.get('price','0')):raise ValueError('O modelo mantém o preço do cadastro. Revise a configuração para alterá-lo.')
    if m.get('allow_discount')!='1' and discount:raise ValueError('Desconto não liberado neste modelo.')
    if m['transport_mode']=='9' and freight:raise ValueError('Modelo sem transporte não permite valor de frete.')
    i=dict(product=p,rule=r,quantity=str(qty),price=str(price),discount=str(discount),freight=str(freight),insurance='0',other='0',auto_calc='1',manual={},taxes={},simple_product_id=pid)
    co=store.get('company','',cid)
    if co.get('CRT')=='3':
        i.pop('taxes');i.update(normal_groups=copy.deepcopy(r.get('normal_groups') or default_groups(code=r['icms_code'],origin=r.get('origin','0'),icms_rate=r.get('icms_rate','0'),pis_code=r.get('pis_code','99'),pis_rate=r.get('pis_rate','0'),cofins_code=r.get('cofins_code','99'),cofins_rate=r.get('cofins_rate','0'))),normal_auto='1',normal_auto_base='1',normal_st_deduction='')
        groups=i['normal_groups'];icms=next(iter(groups.get('ICMS',{}).values()),{})
        # Bases de ST e valores específicos de outra operação não podem virar padrões fixos.
        if icms.get('pICMSST') is not None or any(k in icms for k in ('vBCSTRet','vICMSSTRet','vICMSSubstituto','vBCFCPSTRet','vFCPSTRet')):raise ValueError('ST ou valores retidos específicos exigem conferência no modo completo nesta entrega.')
        if set(groups)-{'ICMS','PIS','COFINS','IPI','ICMSUFDest','IBSCBS'}:raise ValueError('O perfil possui grupos especiais que exigem o modo completo.')
        def special(value):
            if isinstance(value,dict):return any(k in ('qBCProd','qUnid','gDevTrib','gCredPres','gIBSCredPres','gCBSCredPres','vCredPres','vCredPresCondSus') or special(v) for k,v in value.items())
            if isinstance(value,list):return any(special(v) for v in value)
            return False
        if special(groups):raise ValueError('Quantidades tributáveis ou créditos/ajustes específicos exigem o modo completo.')
    # O mesmo calculate utilizado pelo editor completo também valida os grupos suportados.
    calculate(i,r,co.get('CRT','1'))
    i['simple_source_stamp']=digest(dict(product=p,rule=r))
    return i
def release_issues(store,cid,m):
    errors=[];co=store.get('company','',cid)
    if co.get('CRT') not in ('1','3') or co.get('UF')!='AL':errors.append('Conector atual: AL, CRT 1 ou 3. Confira o cadastro fiscal.')
    if m.get('rule_source')=='fixed':
        try:rule_for(store,cid,m,{})
        except ValueError as e:errors.append(str(e))
    try:
        validate_party(co,True)
        from vf_workflow import next_number
        env=co.get('environment','2');next_number(store,cid,env,co.get('production_series' if env=='1' else 'series','1'))
    except (ValueError,TypeError) as e:errors.append(str(e))
    candidates=[(rid,p) for rid,p in store.list('product',cid) if not p.get('_archived') and (not m.get('product_ids') or rid in m['product_ids'])]
    valid=0;first_error=''
    for pid,_ in candidates:
        try:
            make_item(store,cid,m,pid);valid+=1;break
        except (ValueError,KeyError) as e:
            if not first_error:first_error=str(e)
    if not valid:errors.append('Vincule ao menos um produto com NCM, unidade e tributação revisada/calculável para este contexto. '+first_error)
    return errors
def save(store,cid,p):
    old=load(store,cid)
    if int(p.get('version',-1))!=old['version']:raise ValueError('As configurações mudaram em outro acesso. Reabra o Modo Simples antes de salvar.')
    data=p.get('data',{});models=data.get('models',[])
    if not isinstance(models,list) or len(models)>30:raise ValueError('Use até 30 modelos por empresa.')
    out=[];seen=set();previous={m['id']:m for m in old['models']}
    for raw in models:
        mid=str(raw.get('id') or uuid.uuid4().hex)
        if not re.fullmatch('[a-f0-9]{32}',mid) or mid in seen:raise ValueError('Identificador de modelo inválido ou repetido.')
        seen.add(mid);m={k:str(raw.get(k,'')).strip() for k in FIELDS if k!='product_ids'}
        ids=raw.get('product_ids',[])
        if not isinstance(ids,list) or len(ids)>10000:raise ValueError('Lista de produtos inválida.')
        m['product_ids']=list(dict.fromkeys(str(v) for v in ids))
        for pid in m['product_ids']:record(store,'product',cid,pid)
        for k,limit in [('name',80),('nature',60),('info',5000),('info_fisco',2000)]:
            if len(m[k])>limit or (k in ('name','nature') and not m[k]):raise ValueError('Confira o campo '+k+' e seu tamanho máximo.')
        choices=dict(target_uf=UF,recipient_ie={'1','2','9'},final={'0','1'},presence={'0','1','2','3','5','9'},payment=PAYMENTS,transport_mode={'0','1','2','3','4','9'},rule_source={'product','fixed'},state={'draft','released'},allow_price={'0','1'},allow_discount={'0','1'},allow_payment={'0','1'})
        for k,values in choices.items():
            if m[k] not in values:raise ValueError('Opção inválida no modelo: '+k)
        if m['recipient_ie']=='9' and m['final']!='1':raise ValueError('Modelo para não contribuinte deve indicar consumidor final. Confira o cadastro e a operação.')
        if m['rule_source']=='fixed':record(store,'rule',cid,m['rule_id'])
        else:m['rule_id']=''
        errors=release_issues(store,cid,m)
        if m['state']=='released' and errors:raise ValueError(m['name']+': '+' '.join(errors))
        stamp=model_stamp(store,cid,m);before=previous.get(mid)
        changed=not before or any(before.get(k)!=m.get(k) for k in FIELDS) or before.get('release_stamp')!=(stamp if m['state']=='released' else '')
        if changed and m['state']=='released' and p.get('confirm_release')!=mid:raise ValueError('Confirme a revisão do modelo antes de liberá-lo.')
        m.update(id=mid,version=(before['version'] if before else 0)+(1 if changed else 0),release_stamp=stamp if m['state']=='released' else '',updated=datetime.now(timezone.utc).isoformat())
        out.append(m)
    mode=str(data.get('default_mode','complete'));default=str(data.get('default_model_id',''))
    if mode not in ('simple','complete'):raise ValueError('Modo padrão inválido.')
    if default and default not in seen:raise ValueError('Selecione um modelo existente como padrão.')
    if mode=='simple' and not any(m['state']=='released' for m in out):raise ValueError('Libere ao menos um modelo antes de ativar o Modo Simples como padrão.')
    value=dict(version=old['version']+1,default_mode=mode,default_model_id=default,models=out)
    store.save('simple_config',value,cid,'simple-'+cid);return value
def public_state(store,cid):
    result=copy.deepcopy(load(store,cid))
    for m in result['models']:
        try:stale=m.get('release_stamp')!=model_stamp(store,cid,m)
        except ValueError:stale=True
        m['needs_review']=m['state']=='released' and stale
        m['issues']=release_issues(store,cid,m)
    return result
def choose(store,cid,mid):
    m=next((m for m in load(store,cid)['models'] if m['id']==mid),None)
    if not m or m['state']!='released':raise ValueError('Selecione um modelo liberado para esta empresa.')
    if m.get('release_stamp')!=model_stamp(store,cid,m):raise ValueError('Modelo ou configuração fiscal alterados. Revise e libere novamente em Configurações → Geral → Modo Simples.')
    return m
def recipient(store,cid,m,rid):
    r=record(store,'recipient',cid,rid)
    if r.get('UF')!=m['target_uf'] or r.get('indIEDest','9')!=m['recipient_ie']:raise ValueError('Cliente incompatível com a UF ou indicador de IE deste modelo. Escolha outro modelo ou use o modo completo.')
    return r
def resolve(store,cid,p):
    m=choose(store,cid,p['model_id']);co=store.get('company','',cid);env=co.get('environment','2')
    incoming=p.get('note') or {};old_meta=incoming.get('simple_mode',{})
    if old_meta.get('active') and not p.get('revalidate'):
        issues=verify(store,cid,incoming,partial=True)
        if issues:raise ValueError(issues[0]['message'])
    from web_settings import new_note_defaults
    n=new_note_defaults(store,cid)
    # Campos especiais não representados pelo modo simples não são herdados de preferências.
    for key in ('authorized_xml','cMunFG'):n[key]=n.get(key,'')
    n.update(nature=m['nature'],operation='1',purpose='1',destination='1' if m['target_uf']==co['UF'] else '2',final=m['final'],presence=m['presence'],payment=m['payment'],transport_mode=m['transport_mode'],info=m['info'],info_fisco=m['info_fisco'],environment=env,series=co.get('production_series' if env=='1' else 'series','1'),number='',has_reference='0',references='',items=[],issued_at=datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-3))).isoformat(timespec='seconds'))
    for key in ('_id','number','cnf','issued_at','invoice_number','invoice_original','invoice_discount','invoice_net','duplicates','carrier_doc','carrier_name','carrier_ie','carrier_address','carrier_city','carrier_uf','vehicle_plate','vehicle_uf','volume_qty','volume_type','volume_brand','volume_number','net_weight','gross_weight'):
        if key in incoming:n[key]=copy.deepcopy(incoming[key])
    n['info']=str(incoming.get('info',m['info']))
    if m['allow_payment']=='1':n['payment']=str(incoming.get('payment',m['payment']))
    if n['payment'] not in PAYMENTS:raise ValueError('Pagamento exige o modo completo nesta versão.')
    rid=str(p.get('recipient_id',incoming.get('recipient_id','')));n['recipient_id']=rid
    r=recipient(store,cid,m,rid) if rid else None
    values=p.get('rows',incoming.get('items',[]))
    if not isinstance(values,list) or len(values)>990:raise ValueError('Máximo de 990 itens.')
    for v in values:n['items'].append(make_item(store,cid,m,str(v.get('product_id') or v.get('simple_product_id') or ''),v))
    attempt=old_meta.get('attempt_id') or uuid.uuid4().hex
    if not re.fullmatch('[a-f0-9]{32}',attempt):raise ValueError('Identificador da edição inválido.')
    n['simple_mode']=dict(active=True,attempt_id=attempt,model_id=m['id'],model_version=m['version'],model_stamp=m['release_stamp'],model_snapshot=copy.deepcopy(m),recipient_stamp=digest(r) if r else '',step=int(old_meta.get('step',1)))
    return n
def verify(store,cid,n,partial=False):
    meta=n.get('simple_mode',{})
    if not meta.get('active'):return []
    def issue(msg,field='simple_mode'):return [dict(field=field,message=msg)]
    try:
        m=choose(store,cid,meta['model_id']);co=store.get('company','',cid)
        if meta.get('model_version')!=m['version'] or meta.get('model_stamp')!=m['release_stamp']:raise ValueError('Este rascunho usa outra versão do modelo. Clique em Revalidar modelo e itens para conferir as mudanças.')
        if n.get('environment')!=co.get('environment','2'):raise ValueError('O ambiente mudou. Reabra a nota no ambiente correspondente.')
        expected=dict(nature=m['nature'],operation='1',purpose='1',destination='1' if m['target_uf']==co['UF'] else '2',presence=m['presence'],final=m['final'],transport_mode=m['transport_mode'],info_fisco=m['info_fisco'])
        if any(str(n.get(k,''))!=str(v) for k,v in expected.items()):raise ValueError('Os parâmetros do modelo foram alterados. Revalide ou continue no modo completo.')
        if n.get('payment') not in PAYMENTS or (m['allow_payment']!='1' and n.get('payment')!=m['payment']):raise ValueError('Forma de pagamento não liberada no modelo.')
        if n.get('has_reference','0')!='0' or n.get('references') or any(n.get(k) for k in ('recipient_override','normal_payment','normal_totals','normal_vnftot','normal_schema_flags')):raise ValueError('A nota contém dados especiais. Continue no modo completo para conferir.')
        if n.get('recipient_id'):
            r=recipient(store,cid,m,n['recipient_id'])
            if meta.get('recipient_stamp')!=digest(r):raise ValueError('O cadastro do cliente mudou. Revalide o modelo e confira os dados.')
        elif not partial:return issue('Escolha o cliente.','recipient_id')
        for ix,i in enumerate(n.get('items',[])):
            expected_item=make_item(store,cid,m,i['simple_product_id'],i)
            if i!=expected_item:return issue('O produto, preço de cadastro ou perfil tributário mudou. Revalide o modelo e confira os itens.','item.'+str(ix))
        if not n.get('items') and not partial:return issue('Adicione ao menos um produto.','items')
    except (ValueError,KeyError,TypeError) as e:return issue(str(e))
    return []
def review_hash(n):
    value={k:copy.deepcopy(v) for k,v in n.items() if not k.startswith('_') and k not in ('number','cnf','status')}
    if isinstance(value.get('simple_mode'),dict):value['simple_mode'].pop('step',None)
    return digest(value)
def existing_attempt(store,cid,n):
    meta=n.get('simple_mode',{})
    if not meta.get('active'):return None
    attempt=meta.get('attempt_id','')
    if not re.fullmatch('[a-f0-9]{32}',attempt):raise ValueError('Identificador da edição inválido.')
    for rid,old in store.list('note',cid):
        if not old.get('_archived') and old.get('simple_mode',{}).get('attempt_id')==attempt:return rid
    return None
