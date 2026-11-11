"""Prepara o Python embarcado no runner Windows sem versionar binários no GitHub."""
import hashlib,json,os,shutil,subprocess,sys,tempfile,urllib.request,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
VERSION='3.12.10'
def main():
    if sys.platform!='win32':raise SystemExit('Execute a preparação no Windows com Python 3.12 de 64 bits.')
    target=ROOT/'portable';target.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive=Path(tmp)/'python-embed.zip'
        url=f'https://www.python.org/ftp/python/{VERSION}/python-{VERSION}-embed-amd64.zip'
        with urllib.request.urlopen(url,timeout=60) as response,archive.open('wb') as out:shutil.copyfileobj(response,out)
        with zipfile.ZipFile(archive) as z:z.extractall(target)
    libs=target/'libs';libs.mkdir(exist_ok=True)
    subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--only-binary=:all:','--target',str(libs),'-r',str(ROOT/'requirements.txt')],check=True)
    (target/'python312._pth').write_text('python312.zip\n.\nlibs\n..\n',encoding='utf-8')
    from importlib.metadata import distributions
    versions={d.metadata['Name']:d.version for d in distributions(path=[str(libs)])}
    (ROOT/'DEPENDENCIAS-WINDOWS.json').write_text(json.dumps(versions,indent=2,sort_keys=True),encoding='utf-8')
    subprocess.run([str(target/'python.exe'),'-c','import lxml,cryptography,openpyxl,brazilfiscalreport;print("Runtime Windows pronto")'],check=True)
if __name__=='__main__':main()
