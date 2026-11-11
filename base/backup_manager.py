"""Backup consistente, verificação de integridade e restauração com rollback no reinício."""
import datetime, hashlib, json, os, re, shutil, sqlite3, tempfile, uuid, zipfile
from pathlib import Path, PurePosixPath
FOLDERS=('xml','notas-fiscais')
LIMIT=1024*1024*1024

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def manifest(folder):
    return {p.relative_to(folder).as_posix():dict(size=p.stat().st_size,sha256=digest(p)) for p in Path(folder).rglob('*') if p.is_file() and p.name!='manifest.json'}
def check_db(path):
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Banco do backup está corrompido.')
        if db.execute('PRAGMA user_version').fetchone()[0]>4:raise ValueError('Backup exige versão mais nova do VF Emissor.')
        db.execute('SELECT id,kind,company,data,updated FROM records LIMIT 1').fetchone()
    finally:db.close()
def create_backup(store,target):
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    temp_target=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with tempfile.TemporaryDirectory() as d:
            stage=Path(d);store.backup(stage/'decisao.sqlite3');check_db(stage/'decisao.sqlite3')
            for name in FOLDERS:
                source=store.path.parent/name
                if source.exists():
                    for p in source.rglob('*'):
                        if p.is_symlink():raise ValueError('Backup não aceita links simbólicos.')
                        if p.is_file() and p.suffix.lower() in ('.xml','.pdf','.json','.csv','.txt'):
                            dest=stage/p.relative_to(store.path.parent);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
            (stage/'manifest.json').write_text(json.dumps(dict(format=1,created=datetime.datetime.now().astimezone().isoformat(),files=manifest(stage)),ensure_ascii=False),encoding='utf8')
            with zipfile.ZipFile(temp_target,'w',zipfile.ZIP_DEFLATED) as z:
                for p in stage.rglob('*'):
                    if p.is_file():z.write(p,p.relative_to(stage))
            os.replace(temp_target,target)
    finally:temp_target.unlink(missing_ok=True)
    return str(target)
def safe_name(name):
    if '\\' in name or ':' in name or name.startswith('/') or any(p in ('..','.') or p.rstrip(' .')!=p or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?',p) for p in name.split('/')):raise ValueError('Caminho inválido no backup.')
    parts=PurePosixPath(name).parts
    if not parts or parts[0] not in (*FOLDERS,'decisao.sqlite3','manifest.json'):raise ValueError('Conteúdo não permitido no backup.')
    if parts[0] in ('decisao.sqlite3','manifest.json') and len(parts)!=1:raise ValueError('Estrutura inválida.')
    return parts

def stage_restore(archive,data_dir):
    parent=Path(data_dir)/'restauracoes';parent.mkdir(exist_ok=True);stage=parent/uuid.uuid4().hex;stage.mkdir()
    try:
        with zipfile.ZipFile(archive) as z:
            if sum(i.file_size for i in z.infolist())>LIMIT or len(z.infolist())>50000:raise ValueError('Backup excede o limite de restauração.')
            seen=set()
            for i in z.infolist():
                name=i.filename.rstrip('/');safe_name(name)
                if name.casefold() in seen or (i.external_attr>>16)&0o170000==0o120000:raise ValueError('Entrada duplicada ou link no backup.')
                seen.add(name.casefold())
                if i.is_dir():continue
                p=stage.joinpath(*PurePosixPath(name).parts);p.parent.mkdir(parents=True,exist_ok=True)
                with z.open(i) as f,p.open('wb') as out:shutil.copyfileobj(f,out)
        check_db(stage/'decisao.sqlite3')
        mf=stage/'manifest.json';actual=manifest(stage)
        if mf.exists() and json.loads(mf.read_text('utf8')).get('files')!=actual:raise ValueError('Integridade do backup inválida.')
        return dict(stage=stage.name,files=actual,legacy=not mf.exists())
    except Exception:
        shutil.rmtree(stage);raise

def verify_stage(data_dir,plan):
    token=plan.get('stage','')
    if not re.fullmatch('[0-9a-f]{32}',token):raise ValueError('Restauração inválida.')
    stage=Path(data_dir)/'restauracoes'/token
    if stage.is_symlink() or any(p.is_symlink() for p in stage.rglob('*')) or manifest(stage)!=plan.get('files'):raise ValueError('Arquivos preparados foram alterados. Selecione o backup novamente.')
    check_db(stage/'decisao.sqlite3');return stage

def schedule_restore(store,plan):
    verify_stage(store.path.parent,plan)
    target=store.path.parent/'backups'/('antes-restauracao-'+uuid.uuid4().hex+'.zip')
    create_backup(store,target)
    marker=store.path.parent/'restauracao-pendente.json';tmp=marker.with_suffix('.tmp')
    tmp.write_text(json.dumps(plan),encoding='utf8');os.replace(tmp,marker)
    return str(target)

def apply_pending(data_dir):
    data_dir=Path(data_dir);marker=data_dir/'restauracao-pendente.json'
    if not marker.exists():return False
    plan=json.loads(marker.read_text('utf8'));stage=verify_stage(data_dir,plan)
    rollback=data_dir/'restauracoes'/('anterior-'+uuid.uuid4().hex);rollback.mkdir();moved=[];installed=[]
    try:
        for name in ('decisao.sqlite3','decisao.sqlite3-wal','decisao.sqlite3-shm',*FOLDERS):
            p=data_dir/name
            if p.exists():os.replace(p,rollback/name);moved.append(name)
        for name in ('decisao.sqlite3',*FOLDERS):
            p=stage/name
            if p.exists():os.replace(p,data_dir/name);installed.append(name)
        marker.unlink()
    except Exception:
        for name in reversed(installed):os.replace(data_dir/name,stage/name)
        for name in reversed(moved):os.replace(rollback/name,data_dir/name)
        raise
    return True

def daily_backup(store):
    folder=store.path.parent/'backups';target=folder/('automatico-'+datetime.date.today().isoformat()+'.zip')
    if not target.exists():create_backup(store,target)
    return str(target)
