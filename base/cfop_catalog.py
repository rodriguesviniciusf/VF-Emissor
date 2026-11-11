"""Catálogo oficial CFOP de 04/09/2026."""
from functools import lru_cache
from pathlib import Path
import datetime,json,sys
@lru_cache(maxsize=1)
def catalog():
    file=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'assets'/'cfop.json'
    return json.loads(file.read_text(encoding='utf-8'))['codes']
def cfop_errors(code,note):
    record=catalog().get(code)
    if record is None:return ['CFOP não consta da tabela oficial instalada.']
    errors=[]
    if record['indNFe']!='1':errors.append('CFOP não habilitado para NF-e na tabela oficial.')
    date=str(note.get('issued_at') or datetime.date.today().isoformat())[:10]
    if date<record['start'] or (record['end'] and date>record['end']):errors.append('CFOP fora da vigência para a emissão.')
    if note.get('purpose','1')=='4' and record['indDevol']!='1':errors.append('Finalidade devolução exige CFOP com indicador de devolução.')
    if note.get('purpose','1')=='1' and record['indDevol']=='1':errors.append('CFOP de devolução: confira a finalidade da NF-e.')
    if record['indComb']=='1':errors.append('Este CFOP exige análise dos grupos de combustíveis, ainda não implementados.')
    return errors
