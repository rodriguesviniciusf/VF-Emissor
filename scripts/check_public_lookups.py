"""Diagnóstico pontual da rede do runner; falha externa mantém preenchimento manual."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'base'))
from public_lookup import lookup
for kind,key in [('cep','01001000'),('cnpj','19131243000197')]:
    try:
        result=lookup(kind,key,'diagnostico-publico')
        print(json.dumps(dict(kind=kind,status='consulta_real_ok',provider=result['provider'],municipality=result['fields'].get('cMun','')),ensure_ascii=False))
    except ValueError as error:print(json.dumps(dict(kind=kind,status='preenchimento_manual_disponivel',message=str(error)),ensure_ascii=False))
