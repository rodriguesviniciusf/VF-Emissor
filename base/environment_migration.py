"""Migração transacional para documentos em ambientes separados."""
from datetime import datetime
import uuid
def migrate_environments(store):
    db=store.db
    if db.execute('PRAGMA user_version').fetchone()[0]>=3:return
    backup=store.path.parent/'backups';backup.mkdir(parents=True,exist_ok=True)
    store.backup(backup/('antes-ambientes-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.sqlite3'))
    sql=db.execute("SELECT sql FROM sqlite_master WHERE name='fiscal_documents'").fetchone()[0]
    sql=sql.replace('fiscal_documents','fiscal_documents_env3',1).replace("CHECK(environment='2')","CHECK(environment IN ('1','2'))").replace('access_key TEXT NOT NULL UNIQUE','access_key TEXT NOT NULL').replace('UNIQUE(cnpj,environment,series,number)','UNIQUE(environment,access_key), UNIQUE(cnpj,environment,series,number)')
    if "CHECK(environment IN ('1','2'))" not in sql:raise ValueError('Estrutura fiscal inesperada. Migração interrompida; backup preservado.')
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute(sql)
        db.execute('INSERT INTO fiscal_documents_env3 SELECT * FROM fiscal_documents')
        db.execute('DROP TABLE fiscal_documents')
        db.execute('ALTER TABLE fiscal_documents_env3 RENAME TO fiscal_documents')
        db.execute('PRAGMA user_version=3');db.commit()
    except Exception:db.rollback();raise
