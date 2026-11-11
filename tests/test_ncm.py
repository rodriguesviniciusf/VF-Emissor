import copy,gzip,json,sys,tempfile,unittest
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch,MagicMock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'base')]
import server,ncm_catalog as ncm
from core import Store
from fiscal import FiscalStore

class NcmTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.data=json.loads(gzip.decompress(ncm.BUNDLE.read_bytes()));cls.catalog=ncm.Catalog(cls.data);cls.day=date.fromisoformat(cls.data['reference_date'])
 def test_bundle_complete_leading_zeros_and_full_hierarchy(self):
  with patch.object(ncm,'today',return_value=self.day):r=self.catalog.lookup('0306.17.10')
  self.assertEqual(r['code'],'03061710');self.assertEqual(r['status'],'valid');self.assertEqual(r['description'],'Inteiros')
  descriptions=' '.join(h['description'] for h in r['hierarchy']);self.assertIn('Outros camarões',descriptions);self.assertIn('Congelados',descriptions)
  self.assertEqual(len(self.catalog.leaves),10516);self.assertEqual(len(self.catalog.rows),15157)
 def test_search_uses_parent_descriptions_and_accents(self):
  hits=self.catalog.search('camaroes inteiros');self.assertIn('03061710',[r['code'] for r in hits]);self.assertLessEqual(len(hits),30)
  self.assertEqual(self.catalog.search('0306.17.1')[0]['code'],'03061710')
 def test_not_found_does_not_claim_exact_expiry_or_never_existed(self):
  with patch.object(ncm,'today',return_value=self.day):r=self.catalog.lookup('99999999')
  self.assertEqual(r['status'],'not_found');self.assertNotIn('end',r)
 def test_old_and_future_absent_codes_are_unverified(self):
  for offset in (-1,1):
   with patch.object(ncm,'today',return_value=self.day):r=self.catalog.lookup('99999999',(self.day+timedelta(days=offset)).isoformat())
   self.assertEqual(r['status'],'unverified')
 def test_stale_copy_never_claims_current_validity(self):
  with patch.object(ncm,'today',return_value=self.day+timedelta(days=1)):
   r=self.catalog.lookup('03061710');self.assertEqual(r['status'],'unverified');self.assertTrue(r['table']['stale'])
 def test_date_boundaries_and_actual_start_end(self):
  d=copy.deepcopy(self.data);row=next(r for r in d['rows'] if r[0]=='03061710');row[3]=self.day.isoformat();row[4]=self.day.isoformat();catalog=ncm.Catalog(d)
  with patch.object(ncm,'today',return_value=self.day):self.assertEqual(catalog.lookup('03061710')['status'],'valid')
  row[3]=(self.day+timedelta(days=1)).isoformat();row[4]='9999-12-31';catalog=ncm.Catalog(d)
  with patch.object(ncm,'today',return_value=self.day):self.assertEqual(catalog.lookup('03061710')['status'],'not_started')
  row[3]='2022-04-01';row[4]=(self.day-timedelta(days=1)).isoformat();catalog=ncm.Catalog(d)
  with patch.object(ncm,'today',return_value=self.day):self.assertEqual(catalog.lookup('03061710')['status'],'expired')
 def test_input_rejects_partial_letters_and_arbitrary_urls(self):
  for value in ('0306','0306171a','https://site/03061710','0306-17-10'):
   with self.assertRaises(ValueError):self.catalog.lookup(value)
 def test_corrupt_cache_falls_back_to_bundle(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'ncm-catalog/ncm.json.gz';p.parent.mkdir();p.write_bytes(b'corrompido')
   self.assertEqual(ncm.local(tmp).meta['source_sha256'],self.data['source_sha256'])
 def test_failed_download_keeps_previous_bytes_and_sends_no_company_data(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'ncm-catalog/ncm.json.gz';p.parent.mkdir();p.write_bytes(ncm.BUNDLE.read_bytes());before=p.read_bytes()
   with patch.object(ncm,'urlopen',side_effect=OSError('offline')) as fetch:
    r=ncm.refresh(tmp,force=True)
   self.assertIn('error',r);self.assertEqual(p.read_bytes(),before);request=fetch.call_args.args[0];self.assertEqual(request.full_url,ncm.SOURCE);self.assertIsNone(request.data)
 def test_invalid_download_never_replaces_good_table(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'ncm-catalog/ncm.json.gz';p.parent.mkdir();p.write_bytes(ncm.BUNDLE.read_bytes());before=p.read_bytes()
   response=MagicMock();response.__enter__.return_value=response;response.geturl.return_value=ncm.SOURCE;response.read.return_value=b'{"Nomenclaturas":[]}'
   with patch.object(ncm,'urlopen',return_value=response):r=ncm.refresh(tmp,force=True)
   self.assertIn('error',r);self.assertEqual(p.read_bytes(),before)
 def test_official_html_is_text_and_source_limits_enforced(self):
  self.assertEqual(ncm.plain('<i>Camarões</i> &amp; outros'),'Camarões & outros')
  with self.assertRaises(ValueError):ncm.parse_official(b'x'*(ncm.LIMIT+1))

class NcmServerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'vf.sqlite3');server.STORE=self.store;FiscalStore(self.store)
  self.cid=self.store.save('company',dict(CNPJCPF='11222333000181',CRT='1'))
  self.recipient=self.store.save('recipient',dict(xNome='Teste'),self.cid)
  self.note=dict(number='1',series='1',recipient_id=self.recipient,issued_at=ncm.local(self.tmp.name).meta['reference_date']+'T12:00:00-03:00',items=[dict(product=dict(NCM='99999999'),rule={})])
 def tearDown(self):self.store.db.close();self.tmp.cleanup()
 def test_local_validation_returns_clickable_item_path_in_both_modes(self):
  with patch.object(server,'validate_note',return_value=[]):
   result=server.action(dict(action='validate',cid=self.cid,note=self.note));simple=server.action(dict(action='simple_review',cid=self.cid,note=self.note))
  self.assertEqual(result['issues'][0]['field'],'item.0.product.NCM');self.assertEqual(simple['issues'][0]['field'],'item.0.product.NCM');self.assertFalse(simple['review_hash'])
 def test_prepare_blocks_invalid_ncm_before_certificate_or_signature(self):
  rid=self.store.save('note',self.note,self.cid)
  with patch.object(server,'validate_note',return_value=[]),patch.object(server,'certificate') as certificate:
   with self.assertRaisesRegex(ValueError,'NCM'):server.action(dict(action='prepare',cid=self.cid,id=rid))
   certificate.assert_not_called()
 def test_note_warning_for_date_not_covered(self):
  self.note['issued_at']='2099-01-01T12:00:00-03:00'
  result=ncm.check_note(self.tmp.name,self.note);self.assertFalse(result['issues']);self.assertEqual(result['warnings'][0]['field'],'item.0.product.NCM')
 def test_lookup_uses_company_auth_scope(self):
  with self.assertRaises(ValueError):server.action(dict(action='ncm_lookup',cid='outra',code='03061710'))
  self.assertEqual(server.action(dict(action='ncm_lookup',cid=self.cid,code='03061710'))['code'],'03061710')
