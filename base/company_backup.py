"""Exporta somente a empresa ativa, incluindo XML e cofre protegido próprio."""
import io,sqlite3,tempfile,zipfile,json,hashlib
from datetime import datetime,timezone
from pathlib import Path

def backup_company(store,cid,cnpj,vault_file=None):
    with tempfile.TemporaryDirectory() as d:
        dbfile=Path(d)/'vf.sqlite3';store.backup(dbfile);db=sqlite3.connect(dbfile)
        try:
            with db:
                db.execute("DELETE FROM records WHERE NOT ((kind='company' AND id=?) OR company=?)",(cid,cid))
                db.execute('DELETE FROM fiscal_history WHERE document NOT IN (SELECT id FROM fiscal_documents WHERE company=?)',(cid,))
                db.execute('DELETE FROM event_history WHERE event NOT IN (SELECT id FROM fiscal_events WHERE company=?)',(cid,))
                db.execute('DELETE FROM fiscal_documents WHERE company<>?',(cid,));db.execute('DELETE FROM fiscal_events WHERE company<>?',(cid,))
                db.execute('DELETE FROM audit WHERE record NOT IN (SELECT id FROM records UNION SELECT id FROM fiscal_documents UNION SELECT id FROM fiscal_events)')
            db.execute('VACUUM')
        finally:db.close()
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            z.write(dbfile,'dados/vf.sqlite3')
            for relative in [Path('notas-fiscais')/cnpj,Path('xml-importados')/cid]:
                folder=store.path.parent/relative
                if folder.exists():
                    for f in folder.rglob('*'):
                        if f.is_file() and not f.is_symlink() and f.suffix in ('.xml','.pdf','.json'):z.write(f,(Path('dados')/f.relative_to(store.path.parent)).as_posix())
            if vault_file and Path(vault_file).is_file():z.write(vault_file,(Path('dados/certificados-protegidos')/Path(vault_file).name).as_posix())
        # Reabra o diretório central finalizado antes de conferir o conteúdo.
        # No Windows, os nomes do escritor ainda aberto podem ter separadores locais.
        with zipfile.ZipFile(output,'a',zipfile.ZIP_DEFLATED) as z:
            hashes={name:hashlib.sha256(z.read(name)).hexdigest() for name in z.namelist()}
            z.writestr('backup-manifest.json',json.dumps(dict(format=2,version='0.17.0',company=cid,cnpj=cnpj,created=datetime.now(timezone.utc).isoformat(),files=hashes),ensure_ascii=False))
        return output.getvalue()
