import copy,json,sqlite3,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch,MagicMock
import test_fiscal as fixtures
from fiscal import *
from core import Store,build_ini
from invoice_archive import export_issued,issued_metadata,archive_path

class EnvironmentTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixtures.FiscalTests.setUpClass()
 @classmethod
 def tearDownClass(cls):fixtures.FiscalTests.tearDownClass()
 def setUp(self):
  self.f=fixtures.FiscalTests();self.f.setUp();self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.store=Store(Path(self.temp.name)/'db.sqlite3');self.addCleanup(self.store.db.close)
  self.cid=self.store.save('company',self.f.company);self.db=FiscalStore(self.store)
 def production(self):
  self.f.company.update(self.store.get('company','',self.cid))
  self.f.company.update(environment='1',production_enabled=True,production_series='1',production_next_number='1')
  self.store.save('company',self.f.company,'',self.cid);self.f.note['environment']='1'
 def reserve(self,source):
  signed,key=self.f.signed();rid=self.db.prepare(self.cid,source,dict(company=self.f.company,recipient=self.f.recipient,note=self.f.note),signed,key)
  return rid,signed,key
 def test_new_company_always_homologation(self):
  cid=self.store.save('company',dict(self.f.company,environment='1',production_enabled=True))
  co=self.store.get('company','',cid);self.assertEqual(co['environment'],'2');self.assertFalse(co['production_enabled'])
 def test_production_xml_schema_name_and_explicit_activation(self):
  self.production();signed,key=self.f.signed();validate_schema(signed)
  self.assertEqual(text(parse_xml(signed),'n:infNFe/n:ide/n:tpAmb'),'1')
  self.assertEqual(text(parse_xml(signed),'n:infNFe/n:dest/n:xNome'),self.f.recipient['xNome'])
  self.f.company['production_enabled']=False
  with self.assertRaises(ValueError):self.f.signed()
 def test_production_danfe_with_matching_authorization(self):
  self.production();signed,key=self.f.signed();response=self.f.fixture(key,signed).replace(b'<tpAmb>2</tpAmb>',b'<tpAmb>1</tpAmb>')
  proc=assemble_process(signed,unpack_response(response,key,'1'));self.assertTrue(render_danfe(proc).startswith(b'%PDF'))
 def test_production_danfe_rejects_unsigned_protocol_and_wrong_environment(self):
  self.production();signed,key=self.f.signed()
  with self.assertRaises(ValueError):render_danfe(signed)
  response=self.f.fixture(key,signed).replace(b'<tpAmb>2</tpAmb>',b'<tpAmb>1</tpAmb>');proc=assemble_process(signed,unpack_response(response,key,'1'))
  node=parse_xml(proc);node.find('n:protNFe/n:infProt/n:tpAmb',{'n':NS}).text='2'
  with self.assertRaises(ValueError):render_danfe(serialize(node))
 def test_responses_cannot_cross_environments(self):
  signed,key=self.f.signed();response=self.f.fixture(key,signed)
  with self.assertRaises(ValueError):unpack_response(response,key,'1')
  mixed=response.replace(b'<tpAmb>2</tpAmb>',b'<tpAmb>1</tpAmb>',1)
  with self.assertRaises(ValueError):unpack_response(mixed,key,'1')
  result=unpack_response(response,key);result['environment']='1'
  with self.assertRaises(ValueError):assemble_process(signed,result)
 def test_same_number_key_separate_counters_archives_and_exports(self):
  h,hs,key=self.reserve('homo');self.db.apply_response(self.cid,h,self.f.fixture(key,hs))
  self.production();p,ps,pk=self.reserve('prod');self.assertEqual(key,pk)
  self.db.assert_sendable(self.cid,p)
  self.db.apply_response(self.cid,p,self.f.fixture(pk,ps).replace(b'<tpAmb>2</tpAmb>',b'<tpAmb>1</tpAmb>'))
  co=self.store.get('company','',self.cid);self.assertEqual(co['production_next_number'],'2');self.assertEqual(co['next_number'],'2')
  self.assertEqual(len(issued_metadata(self.db,self.cid,environment='1')),1);self.assertEqual(len(issued_metadata(self.db,self.cid,environment='2')),1)
  target=Path(self.temp.name)/'both.zip';export_issued(self.db,self.cid,[h,p],target)
  with zipfile.ZipFile(target) as z:
   self.assertEqual(json.loads(z.read('manifesto.json'))['ambientes'],['1','2'])
   self.assertEqual(sum('/producao/' in n for n in z.namelist()),1);self.assertEqual(sum('/homologacao/' in n for n in z.namelist()),1)
  self.assertNotEqual(archive_path(Path(self.temp.name),self.db.get(self.cid,h)),archive_path(Path(self.temp.name),self.db.get(self.cid,p)))
 def test_active_environment_blocks_send(self):
  self.production();rid,signed,key=self.reserve('prod')
  co=self.store.get('company','',self.cid);co.update(environment='2',production_enabled=False);self.store.save('company',co,'',self.cid)
  with self.assertRaisesRegex(ValueError,'outro ambiente'):self.db.assert_sendable(self.cid,rid)
 def test_existing_document_cannot_change_environment(self):
  rid,signed,key=self.reserve('same');self.production()
  with self.assertRaisesRegex(ValueError,'ambiente'):self.reserve('same')
 def test_transport_official_endpoints_and_tls_no_retries(self):
  for environment,host in [('1',PRODUCTION),('2',HOMOLOG)]:
   response=MagicMock();response.status_code=200;response.iter_content.return_value=[b'<ok/>'];response.__enter__.return_value=response
   session=MagicMock();session.__enter__.return_value=session;session.post.return_value=response
   with patch('requests.Session',return_value=session),patch('fiscal.create_tls_adapter',return_value=MagicMock()):
    SefazTransport(fixtures.FiscalTests.certificate).request('status',payload('consStatServ',tpAmb=environment,cUF='27',xServ='STATUS'))
   args,kwargs=session.post.call_args;self.assertTrue(args[0].startswith(host+'/'));self.assertTrue(kwargs['verify']);self.assertFalse(kwargs['allow_redirects']);self.assertFalse(session.trust_env);self.assertEqual(session.post.call_count,1)
 def test_migration_preserves_rows_history_and_backup(self):
  rid,signed,key=self.reserve('old');before=self.db.get(self.cid,rid)
  self.store.db.execute('PRAGMA user_version=2');self.store.db.commit()
  # Recreate the exact prior table constraints, keeping all records/history.
  sql=self.store.db.execute("SELECT sql FROM sqlite_master WHERE name='fiscal_documents'").fetchone()[0]
  sql=sql.replace('fiscal_documents','fiscal_legacy',1).replace("CHECK(environment IN ('1','2'))","CHECK(environment='2')").replace('access_key TEXT NOT NULL','access_key TEXT NOT NULL UNIQUE').replace('UNIQUE(environment,access_key), ','')
  self.store.db.execute(sql);self.store.db.execute('INSERT INTO fiscal_legacy SELECT * FROM fiscal_documents');self.store.db.execute('DROP TABLE fiscal_documents');self.store.db.execute('ALTER TABLE fiscal_legacy RENAME TO fiscal_documents');self.store.db.commit()
  oldbackups=set((Path(self.temp.name)/'backups').glob('antes-ambientes-*'))
  FiscalStore(self.store);self.assertEqual(self.db.get(self.cid,rid),before);self.assertEqual(self.store.db.execute('PRAGMA user_version').fetchone()[0],4)
  self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM fiscal_history WHERE document=?',(rid,)).fetchone()[0],1)
  backups=list((Path(self.temp.name)/'backups').glob('antes-ambientes-*'));self.assertGreaterEqual(len(backups),2)
  db=sqlite3.connect(next(iter(set(backups)-oldbackups)))
  try:self.assertEqual(db.execute('SELECT COUNT(*) FROM fiscal_documents').fetchone()[0],1)
  finally:db.close()
if __name__=='__main__':unittest.main()
