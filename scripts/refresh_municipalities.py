"""Gera o catálogo offline a partir da Divisão Territorial Brasileira oficial."""
import hashlib,io,json,re,urllib.request,zipfile,xml.etree.ElementTree as E
from pathlib import Path
from datetime import datetime,timezone
URL='https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/divisao_territorial/2025/DTB_2025.zip'
UFS=dict(zip('11 12 13 14 15 16 17 21 22 23 24 25 26 27 28 29 31 32 33 35 41 42 43 50 51 52 53'.split(),'RO AC AM RR PA AP TO MA PI CE RN PB PE AL SE BA MG ES RJ SP PR SC RS MS MT GO DF'.split()))
def convert(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:ods=z.read('RELATORIO_DTB_BRASIL_2025_MUNICIPIOS.ods')
    with zipfile.ZipFile(io.BytesIO(ods)) as z:root=E.fromstring(z.read('content.xml'))
    ns={'t':'urn:oasis:names:tc:opendocument:xmlns:table:1.0','x':'urn:oasis:names:tc:opendocument:xmlns:text:1.0'};items=[]
    for row in root.findall('.//t:table-row',ns):
        values=[]
        for cell in row.findall('t:table-cell',ns):
            value=' '.join(''.join(p.itertext()) for p in cell.findall('x:p',ns));values.extend([value]*min(int(cell.get('{'+ns['t']+'}number-columns-repeated','1')),10))
            if len(values)>=9:break
        if len(values)>=9 and values[0] in UFS and re.fullmatch(r'\d{7}',values[7]):items.append([values[7],values[8],UFS[values[0]]])
    assert len(items)>=5570 and len({i[0] for i in items})==len(items) and len({i[2] for i in items})==27
    return dict(source=URL,reference='DTB 2025 — data base 31/12/2025',retrieved_at=datetime.now(timezone.utc).isoformat(),source_sha256=hashlib.sha256(raw).hexdigest(),municipalities=sorted(items,key=lambda i:(i[2],i[1])))
if __name__=='__main__':
    import sys
    if len(sys.argv)>1:raw=Path(sys.argv[1]).read_bytes()
    else:
        with urllib.request.urlopen(URL,timeout=30) as r:raw=r.read(5000000)
    result=convert(raw);out=Path(__file__).resolve().parents[1]/'base/assets/municipios.json';out.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8');print(len(result['municipalities']),'municípios/distrito estadual, 27 UFs')
