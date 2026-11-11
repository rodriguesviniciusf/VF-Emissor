"""Atualiza o catálogo empacotado, somente com dados oficiais (sem dados fiscais)."""
import argparse,sys
from pathlib import Path
from urllib.request import Request,urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'base'))
import ncm_catalog as ncm
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source-file',type=Path);args=parser.parse_args()
    if args.source_file:raw=args.source_file.read_bytes()
    else:
        with urlopen(Request(ncm.SOURCE,headers={'Accept':'application/json'}),timeout=15) as response:raw=response.read(ncm.LIMIT+1)
    data=ncm.parse_official(raw);catalog=ncm.Catalog(data);ncm.BUNDLE.parent.mkdir(parents=True,exist_ok=True);ncm.BUNDLE.write_bytes(ncm.packed(data))
    print(f'Tabela oficial: {data["reference_date"]} · {len(catalog.leaves)} NCM · SHA256 fonte: {data["source_sha256"]}')
if __name__=='__main__':main()
