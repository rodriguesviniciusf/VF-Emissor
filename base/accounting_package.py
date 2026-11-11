"""ZIP mensal da empresa/ambiente, com XML, eventos e relatórios CSV/HTML."""
import csv,hashlib,io,json,re,zipfile
from html import escape
from fiscal import FiscalStore,parse_xml,text,NS
from fiscal_events import EventStore
from core import document,money

def safe_csv(value):
    value=str(value or '')
    return "'"+value if value.startswith(('=','+','-','@','\t','\r','\n')) else value

def build(store,cid,period,env):
    if not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])',str(period)) or env not in ('1','2'):raise ValueError('Selecione mês e ambiente válidos.')
    co=store.get('company','',cid);cnpj=document(co['CNPJCPF']);files={};rows=[];seen=set();events=EventStore(store).list(cid,env)
    for d in FiscalStore(store).list(cid):
        if d['environment']!=env or d['status'] not in ('AUTORIZADA','CANCELADA') or not d['proc_xml']:continue
        inf=parse_xml(d['proc_xml']).find('n:NFe/n:infNFe',{'n':NS});stamp=text(inf,'n:ide/n:dhEmi');related=[e for e in events if e['document']==d['id'] and e['status']=='REGISTRADO' and e['proc_xml']]
        cancels=[e for e in related if e['kind']=='110111'];cancel_date=max((e['created'] for e in cancels),default='')
        if not stamp.startswith(period) and not cancel_date.startswith(period):continue
        key=d['access_key']
        if not re.fullmatch(r'\d{44}',key):raise ValueError('Chave inválida no arquivo fiscal.')
        seen.add(key);own_entry=text(inf,'n:ide/n:tpNF')=='0';group='canceladas' if d['status']=='CANCELADA' else 'entradas-emitidas' if own_entry else 'emitidas'
        files[group+'/'+key+'-procNFe.xml']=d['proc_xml']
        for e in related:files['eventos/'+key+'-'+e['kind']+'-'+str(e['sequence'])+'-procEvento.xml']=e['proc_xml']
        rows.append(['Entrada emitida' if own_entry else 'Emitida',d['number'],d['series'],stamp,cancel_date,text(inf,'n:dest/n:xNome'),key,text(inf,'n:total/n:vNFTot') or text(inf,'n:total/n:ICMSTot/n:vNF'),d['status'],'Situação registrada pelo emissor'])
    for rid,d in store.list('received',cid):
        if d.get('environment')!=env or not (d.get('issued_at','').startswith(period) or d.get('cancelled_at','').startswith(period)) or d.get('key') in seen:continue
        key=d.get('key','')
        if not re.fullmatch(r'\d{44}',key):continue
        path=store.path.parent/'xml-importados'/cid/(rid+'.xml')
        if not path.is_file() or path.is_symlink():raise ValueError('XML importado da NF-e '+str(d.get('number',''))+' não foi encontrado. Restaure o arquivo antes de gerar um pacote completo.')
        raw=path.read_bytes();root=parse_xml(raw)
        if root.tag!='{'+NS+'}nfeProc':continue
        seen.add(key);incoming=d.get('direction')=='recebida';group='entradas' if incoming else 'emitidas-importadas'
        files[group+'/'+key+'-procNFe.xml']=raw
        for e in d.get('cancellation_files',[]):
            if re.fullmatch(r'[a-f0-9]{32}-cancel-[a-f0-9]{16}\.xml',e):
                ep=path.parent/e
                if ep.is_file() and not ep.is_symlink():files['eventos/'+key+'-'+e]=ep.read_bytes()
        rows.append(['Entrada' if incoming else 'Emitida importada',d.get('number',''),d.get('series',''),d.get('issued_at',''),d.get('cancelled_at',''),d.get('issuer','') if incoming else d.get('recipient',''),key,text(root,'n:NFe/n:infNFe/n:total/n:vNFTot') or text(root,'n:NFe/n:infNFe/n:total/n:ICMSTot/n:vNF') or d.get('total','0'),'CANCELADA DECLARADA NO XML' if d.get('cancelled') else 'AUTORIZAÇÃO DECLARADA NO XML','Importação de arquivo; situação atual não consultada na SEFAZ'])
    headers=['Tipo','Número','Série','Emissão','Cancelamento','Participante','Chave de acesso','Valor NF-e','Situação','Origem da situação']
    output=io.StringIO();writer=csv.writer(output,delimiter=';');writer.writerow(headers)
    for row in rows:writer.writerow([("'"+str(v)) if i==6 else safe_csv(v) for i,v in enumerate(row)])
    files['relatorio-notas.csv']=output.getvalue().encode('utf-8-sig')
    counts=dict(emitidas=sum(r[0] in ('Emitida','Entrada emitida') and r[8]=='AUTORIZADA' for r in rows),canceladas=sum('CANCELADA' in r[8] for r in rows),entradas=sum(r[0] in ('Entrada','Entrada emitida') for r in rows),emitidas_importadas=sum(r[0]=='Emitida importada' for r in rows))
    body=''.join('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in row)+'</tr>' for row in rows)
    html=f'<!doctype html><meta charset="utf-8"><title>Pacote contábil {period}</title><style>body{{font:13px Segoe UI,Arial;color:#244b32;margin:30px}}table{{border-collapse:collapse;width:100%;font-size:11px}}td,th{{padding:9px;border-bottom:1px solid #dce6d7;text-align:left}}th{{background:#eaf2e3}}td:nth-child(7){{overflow-wrap:anywhere;max-width:220px}}</style><h1>{escape(co.get("xNome",""))}</h1><p>CNPJ {cnpj} · {period} · {"Produção" if env=="1" else "Homologação"}</p><p>Emitidas autorizadas: {counts["emitidas"]} · Emitidas importadas: {counts["emitidas_importadas"]} · Canceladas: {counts["canceladas"]} · Entradas: {counts["entradas"]}</p><p>Período pela emissão; cancelamentos também pela data de registro do evento. XML importados têm a situação declarada no arquivo. O relatório não substitui apuração fiscal nem consulta atual à SEFAZ.</p><table><thead><tr>'+''.join('<th>'+escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+body+'</tbody></table>'
    files['relatorio-notas.html']=html.encode()
    files['manifesto.json']=json.dumps(dict(cnpj=cnpj,period=period,environment=env,counts=counts,files={n:hashlib.sha256(v).hexdigest() for n,v in files.items()}),ensure_ascii=False,indent=2).encode()
    result=io.BytesIO()
    with zipfile.ZipFile(result,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in files.items():z.writestr(name,raw)
    return result.getvalue(),counts
