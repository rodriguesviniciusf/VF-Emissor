"""Dados fora da instalação; importação consistente sem alterar a origem."""
import json,os,shutil,sqlite3,sys,tempfile,uuid
from pathlib import Path

def data_directory(root,*,platform=None,environ=None):
    env=os.environ if environ is None else environ;platform=platform or sys.platform
    if env.get('VF_DATA_DIR'):return Path(env['VF_DATA_DIR']).expanduser().resolve()
    if platform=='win32':return Path(env.get('LOCALAPPDATA') or Path.home()/'AppData/Local')/'VFEmissor'/'Dados'
    return Path(root)/'dados'

def has_companies(db_path):
    if not Path(db_path).exists():return False
    db=sqlite3.connect(str(db_path))
    try:
        table=db.execute("SELECT 1 FROM sqlite_master WHERE name='records'").fetchone()
        return bool(table and db.execute("SELECT 1 FROM records WHERE kind='company' LIMIT 1").fetchone())
    finally:db.close()

def import_legacy(source,target):
    source=Path(source).expanduser().resolve();target=Path(target).expanduser().resolve()
    if (source/'dados'/'vf.sqlite3').exists():source=source/'dados'
    if source==target:raise ValueError('A pasta escolhida já é a pasta atual de dados.')
    src=source/'vf.sqlite3'
    if not src.is_file():raise ValueError('Não foi encontrado dados/vf.sqlite3 nessa pasta. Selecione a pasta da versão anterior.')
    if not has_companies(src):raise ValueError('A pasta anterior não contém empresas cadastradas.')
    if has_companies(target/'vf.sqlite3'):raise ValueError('Já existem empresas nesta instalação. A importação inicial não sobrescreve cadastros existentes.')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent,prefix='importacao-') as d:
        stage=Path(d);old=sqlite3.connect(src.as_uri()+'?mode=ro',uri=True);new=sqlite3.connect(stage/'vf.sqlite3')
        try:
            old.backup(new)
            if new.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Banco de origem inválido.')
            count=new.execute("SELECT count(*) FROM records WHERE kind='company'").fetchone()[0]
        finally:new.close();old.close()
        for name in ['notas-fiscais','xml','xml-importados','certificados-protegidos']:
            folder=source/name
            if folder.exists():
                if folder.is_symlink() or any(p.is_symlink() for p in folder.rglob('*')):raise ValueError('A origem contém links; escolha a pasta original de dados.')
                shutil.copytree(folder,stage/name)
        # Nenhum arquivo da origem é movido ou excluído. A pasta vazia anterior também é guardada.
        backup=None
        if target.exists():backup=target.with_name('Dados-antes-importacao-'+uuid.uuid4().hex);os.replace(target,backup)
        try:os.replace(stage,target)
        except Exception:
            if backup:os.replace(backup,target)
            raise
    (target/'importacao.json').write_text(json.dumps(dict(empresas=count,origem=str(source)),ensure_ascii=False),encoding='utf-8')
    return count

def migrate_bundled(root,target):
    src=Path(root)/'dados'
    if (src/'vf.sqlite3').exists() and not has_companies(Path(target)/'vf.sqlite3') and src.resolve()!=Path(target).resolve():return import_legacy(src,target)
    return 0


def backup_before_update(data_dir,version):
    data_dir=Path(data_dir);source=data_dir/'vf.sqlite3'
    if not source.exists():return None
    import re
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version):raise ValueError('Versão de backup inválida.')
    folder=data_dir/'backups';folder.mkdir(exist_ok=True)
    target=folder/('antes-atualizacao-'+version+'.sqlite3')
    if target.exists():return target
    temp=target.with_suffix('.tmp');src=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);dst=sqlite3.connect(temp)
    try:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Falha na verificação do backup anterior à atualização.')
    finally:src.close();dst.close()
    os.replace(temp,target);return target
