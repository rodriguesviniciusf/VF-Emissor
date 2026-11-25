"""Duplicate review and justification, with synthetic local documents only."""
import copy,json,sys,unittest,uuid
from pathlib import Path
from unittest.mock import patch,MagicMock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'base'),str(ROOT/'tests')]
import server,editor_recovery,simple_mode
from core import Store
from fiscal import FiscalStore,FiscalService
from vf_workflow import check_duplicates
import test_simple_mode as fixture
import test_fiscal as fiscal_fixture

class DuplicateReviewTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  fiscal_fixture.FiscalTests.setUpClass();cls.cert=fiscal_fixture.FiscalTests.certificate
 @classmethod
 def tearDownClass(cls):fiscal_fixture.FiscalTests.tearDownClass()
 def setUp(self):
  self.old_store=server.STORE;self.fx=fixture.SimpleModeTests();self.fx.setUp();self.cid=self.fx.cid;self.db=self.fx.db
  self.n=self.fx.note();self.source=server.save_note(dict(cid=self.cid,data=self.n))['id'];original=server.note(self.cid,self.source)
  self.fid=uuid.uuid4().hex;self.insert(self.fid,self.source,original)
  self.n=self.fx.note();self.rid=server.save_note(dict(cid=self.cid,data=self.n))['id']
 def tearDown(self):self.fx.tearDown();server.STORE=self.old_store
 def insert(self,fid,source,n,status='AUTORIZADA',cid=None):
  cid=cid or self.cid;snap=server.snapshot(cid,n)
  with self.db.db:self.db.db.execute('INSERT INTO fiscal_documents(id,company,source,cnpj,environment,series,number,access_key,status,snapshot,signed_xml,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(fid,cid,source,snap['company']['CNPJCPF'],n['environment'],int(n['series']),int(n['number']),str(n['number']).zfill(44),status,json.dumps(snap),b'synthetic-signed-document','2026-11-01','2026-11-01'))
 def review(self):return server.action(dict(action='duplicate_review',cid=self.cid,id=self.rid))
 def params(self,**extra):
  r=self.review();p=dict(action='prepare',cid=self.cid,id=self.rid,duplicate_ack=True,duplicate_reason='Nova venda, pedido 123, com os mesmos produtos e valores.',duplicate_approval=r['token'],duplicate_revision=r['revision'],simple_review_hash=simple_mode.review_hash(server.note(self.cid,self.rid)));p.update(extra);return p
 def prepare(self,p):
  self.captured=[]
  cert=MagicMock();cert.sign.return_value=('<NFe xmlns="http://www.portalfiscal.inf.br/nfe"><infNFe Id="NFe'+('3'*44)+'"><ide><tpAmb>2</tpAmb></ide><emit><CNPJ>'+self.fx.co['CNPJCPF']+'</CNPJ></emit></infNFe></NFe>').encode()
  with patch.object(server,'checked_snapshot',side_effect=server.snapshot),patch.object(server,'certificate',return_value=cert) as loader,patch.object(server,'build_unsigned',return_value=(b'unsigned','3'*44,{})),patch.object(FiscalStore,'_archive_best_effort'):
   result=server.action(p)
  self.captured.append(json.loads(FiscalStore(self.db).get(self.cid,result['fiscal_id'])['snapshot']))
  return result,loader
 def rejected(self,p,message):
  with patch.object(server,'checked_snapshot',side_effect=server.snapshot),patch.object(server,'certificate',side_effect=AssertionError('must not access A1')) as cert:
   with self.assertRaisesRegex(ValueError,message):server.action(p)
   cert.assert_not_called()
 def test_read_only_review_lists_authorized_note_and_preserves_draft(self):
  before=server.note(self.cid,self.rid);r=self.review();self.assertEqual(len(r['matches']),1);self.assertFalse(r['blocked']);self.assertFalse(r['approved']);self.assertEqual(r['matches'][0]['source'],self.source);self.assertEqual(r['revision'],editor_recovery.revision(before));self.assertEqual(server.note(self.cid,self.rid),before)
 def test_missing_confirmation_still_blocks_before_a1(self):self.rejected(self.params(duplicate_ack=False),'justificativa')
 def test_empty_short_and_oversized_reason_are_rejected(self):
  for reason in ['','Nova venda','x'*1001]:self.rejected(self.params(duplicate_reason=reason),'15 a 1.000')
 def test_valid_reason_continues_simple_mode_with_original_review_hash(self):
  p=self.params();before=server.note(self.cid,self.rid);result,cert=self.prepare(p);self.assertTrue(result['fiscal_id']);cert.assert_called_once();saved=self.captured[0]['note'];self.assertEqual(saved['duplicate_reason'],p['duplicate_reason']);self.assertIn('duplicate_reviewed_at',saved);self.assertEqual(server.note(self.cid,self.rid),before);self.assertEqual(next(n for n in server.get_state(self.cid)['documents'] if n['_id']==self.rid)['_duplicate_reason'],p['duplicate_reason'])
 def test_valid_reason_in_complete_mode_uses_same_guard(self):
  n=server.note(self.cid,self.rid);n['simple_mode']['active']=False;self.db.save('note',n,self.cid,self.rid);result,_=self.prepare(self.params());self.assertEqual(result['status'],'PREPARADA')
 def test_changed_draft_invalidates_confirmation(self):
  p=self.params();n=server.note(self.cid,self.rid);n['info']='Changed after review';self.db.save('note',n,self.cid,self.rid);p['simple_review_hash']=simple_mode.review_hash(n);self.rejected(p,'mudaram')
 def test_changed_set_of_documents_invalidates_confirmation(self):
  p=self.params();n=server.note(self.cid,self.source);n['number']='8';self.insert(uuid.uuid4().hex,'another-source',n);self.rejected(p,'mudaram')
 def test_unresolved_note_cannot_be_overridden(self):
  for status in ['PREPARADA','ENVIANDO','INCERTA','NAO_LOCALIZADA']:
   with self.db.db:self.db.db.execute('UPDATE fiscal_documents SET status=? WHERE id=?',(status,self.fid))
   self.assertTrue(self.review()['blocked']);self.rejected(self.params(),'processamento|incerta')
 def test_other_company_cannot_review_draft(self):
  with self.assertRaises(ValueError):server.action(dict(action='duplicate_review',cid=self.fx.other,id=self.rid))
 def test_other_environment_and_cancelled_note_are_not_duplicates(self):
  for field,value in [('environment','1'),('status','CANCELADA')]:
   with self.db.db:self.db.db.execute('UPDATE fiscal_documents SET environment=?,status=? WHERE id=?',('1' if field=='environment' else '2','AUTORIZADA' if field=='environment' else value,self.fid))
   self.assertEqual(self.review()['matches'],[])
 def prepare_signed(self):
  """Real validation, XML construction and synthetic A1 signature; no network."""
  with patch.object(server,'certificate',return_value=self.cert),patch.object(server.ncm_catalog,'check_note',return_value={'issues':[]}),patch.object(FiscalStore,'_archive_best_effort'):
   return server.action(self.params())
 def send_synthetic(self,prepared):
  fs=FiscalStore(self.db);doc=fs.get(self.cid,prepared['fiscal_id'])
  response=fiscal_fixture.FiscalTests().fixture(doc['access_key'],doc['signed_xml'])
  transport=MagicMock();transport.request.return_value=response
  with patch.object(FiscalStore,'_archive_best_effort'):
   result=FiscalService(fs,self.cert,transport).send(self.cid,prepared['fiscal_id'])
  self.assertEqual(result,'AUTORIZADA');transport.request.assert_called_once()
  self.assertEqual(transport.request.call_args.args[0],'send')
  self.assertEqual(fs.get(self.cid,prepared['fiscal_id'])['status'],'AUTORIZADA')
 def test_justified_simple_sale_sends_after_reopening_saved_0201_document(self):
  before=server.note(self.cid,self.rid);prepared=self.prepare_signed()
  doc=FiscalStore(self.db).get(self.cid,prepared['fiscal_id']);signed=doc['signed_xml']
  self.assertNotIn('duplicate_reason',before)
  self.assertIn('duplicate_reason',json.loads(doc['snapshot'])['note'])
  self.assertEqual(server.note(self.cid,self.rid),before)
  self.db.db.close();server.STORE=self.db=self.fx.db=Store(self.fx.path)
  self.send_synthetic(prepared)
  self.assertEqual(FiscalStore(self.db).get(self.cid,prepared['fiscal_id'])['signed_xml'],signed)
  self.assertEqual(server.note(self.cid,self.rid),before)
 def test_justified_complete_sale_sends_without_saving_review_into_draft(self):
  n=server.note(self.cid,self.rid);n['simple_mode']['active']=False;self.db.save('note',n,self.cid,self.rid)
  prepared=self.prepare_signed();self.send_synthetic(prepared)
  self.assertNotIn('duplicate_reason',server.note(self.cid,self.rid))
 def test_actual_edits_after_justified_signature_still_block_before_transport(self):
  prepared=self.prepare_signed();original=server.note(self.cid,self.rid);fs=FiscalStore(self.db)
  edits=[('quantity','3'),('price','101'),('discount','0'),('NCM','03061790'),('icms_code','900'),('recipient_id','another-client'),('freight','20'),('payment','01'),('nature','OUTRA OPERACAO'),('info','Informacao alterada')]
  for field,value in edits:
   with self.subTest(field=field):
    n=copy.deepcopy(original)
    if field in ('quantity','price','discount'):n['items'][0][field]=value
    elif field=='NCM':n['items'][0]['product'][field]=value
    elif field=='icms_code':n['items'][0]['rule'][field]=value
    else:n[field]=value
    self.db.save('note',n,self.cid,self.rid);transport=MagicMock()
    with self.assertRaisesRegex(ValueError,'rascunho foi alterado'):FiscalService(fs,self.cert,transport).send(self.cid,prepared['fiscal_id'])
    transport.request.assert_not_called();self.assertEqual(fs.get(self.cid,prepared['fiscal_id'])['status'],'PREPARADA')
 def test_existing_justification_cannot_bypass_new_matches_or_uncertain_status(self):
  prepared=self.prepare_signed();fs=FiscalStore(self.db);transport=MagicMock()
  n=server.note(self.cid,self.source);n['number']='8';other=uuid.uuid4().hex;self.insert(other,'another-source',n)
  with self.assertRaisesRegex(ValueError,'justificativa'):FiscalService(fs,self.cert,transport).send(self.cid,prepared['fiscal_id'])
  with self.db.db:
   self.db.db.execute('DELETE FROM fiscal_documents WHERE id=?',(other,))
   self.db.db.execute('UPDATE fiscal_documents SET status=? WHERE id=?',('INCERTA',self.fid))
  with self.assertRaisesRegex(ValueError,'processamento|incerta'):FiscalService(fs,self.cert,transport).send(self.cid,prepared['fiscal_id'])
  transport.request.assert_not_called();self.assertEqual(fs.get(self.cid,prepared['fiscal_id'])['status'],'PREPARADA')

if __name__=='__main__':unittest.main()
