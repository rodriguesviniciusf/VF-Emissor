"""Municípios oficiais incluídos no instalador para pesquisa sem internet."""
import json,unicodedata
from pathlib import Path
from functools import lru_cache
PATH=Path(__file__).parent/'assets/municipios.json'
def normalize(value):return ''.join(c for c in unicodedata.normalize('NFKD',str(value).casefold()) if not unicodedata.combining(c)).strip()
@lru_cache(maxsize=1)
def catalog():return json.loads(PATH.read_text(encoding='utf-8'))['municipalities']
def match_city(name,uf):return next((dict(cMun=c,xMun=n,UF=u) for c,n,u in catalog() if u==str(uf).upper() and normalize(n)==normalize(name)),None)
def match_code(code,uf=''):return next((dict(cMun=c,xMun=n,UF=u) for c,n,u in catalog() if c==str(code) and (not uf or u==str(uf).upper())),None)
def canonical_address(fields,code=''):
    found=match_code(code,fields.get('UF','')) if code else None
    found=found or match_city(fields.get('xMun',''),fields.get('UF',''))
    if found:fields.update(found)
    return fields
