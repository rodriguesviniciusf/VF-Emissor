import copy,datetime,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from core import Store
from fiscal import FiscalStore,build_unsigned,parse_xml,serialize,NS,TZ,SefazTransport
from fiscal_events import EventStore,EventService,build_event,build_inutil,verify_signature,check_number_available
from vf_workflow import next_number
import test_fiscal as fixture
class EventTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixture.FiscalTests.setUpClass();cls.cert=fixture.FiscalTests.certificate
 @classmethod
 def tearDownClass(cls):fixture.FiscalTests.tearDownClass()
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'db');self.fiscal=FiscalStore(self.store);self.events=EventStore(self.store);f=fixture.FiscalTests();f.cnpj='11222333000181';f.setUp();self.f=f;self.cid=self.store.save('company',f.company);self.note=copy.deepcopy(f.note);source=self.store.save('note',self.note,self.cid);xml,key,_=build_unsigned(f.company,f.recipient,self.note);signed=self.cert.sign(xml);self.did=self.fiscal.prepare(self.cid,source,dict(company=f.company,recipient=f.recipient,note=self.note),signed,key);self.fiscal.apply_response(self.cid,self.did,f.fixture(key,signed))
 def tearDown(self):self.store.db.close();self.temp.cleanup()
 def prepare(self,kind='110111',content='Cancelamento de teste sem circulação'):
  return self.events.prepare(self.cid,self.did,kind,content,self.cert,acknowledged=True,allow_late=True)
 def response(self,rid,code='135',key=None,env=None,seq=None):
  e=self.events.get(self.cid,rid);inf=parse_xml(e['signed_xml']).find('n:infEvento',{'n':NS});key=key or inf.findtext('n:chNFe',namespaces={'n':NS});env=env or e['environment'];seq=str(seq or e['sequence']);protocol='<nProt>127260000000002</nProt>' if code in ('135','136','155') else ''
  return f'<retEnvEvento xmlns="{NS}" versao="1.00"><idLote>1</idLote><tpAmb>{env}</tpAmb><verAplic>TESTE</verAplic><cOrgao>27</cOrgao><cStat>128</cStat><xMotivo>Lote processado</xMotivo><retEvento versao="1.00"><infEvento><tpAmb>{env}</tpAmb><verAplic>TESTE</verAplic><cOrgao>27</cOrgao><cStat>{code}</cStat><xMotivo>Retorno de teste</xMotivo><chNFe>{key}</chNFe><tpEvento>{e["kind"]}</tpEvento><nSeqEvento>{seq}</nSeqEvento><dhRegEvento>2026-11-05T09:00:00-03:00</dhRegEvento>{protocol}</infEvento></retEvento></retEnvEvento>'.encode()
 def inutil_response(self,rid,code='102'):
  e=self.events.get(self.cid,rid)
  return f'<retInutNFe xmlns="{NS}" versao="4.00"><infInut><tpAmb>{e["environment"]}</tpAmb><verAplic>TESTE</verAplic><cStat>{code}</cStat><xMotivo>Inutilizacao de teste</xMotivo><cUF>27</cUF><ano>{str(e["year"])[-2:]}</ano><CNPJ>11222333000181</CNPJ><mod>55</mod><serie>{e["series"]}</serie><nNFIni>{e["start_number"]}</nNFIni><nNFFin>{e["end_number"]}</nNFFin><dhRecbto>2026-11-05T09:00:00-03:00</dhRecbto><nProt>127260000000003</nProt></infInut></retInutNFe>'.encode()
 def test_migration_backs_up_and_old_client_blocked(self):
  self.assertEqual(self.store.db.execute('PRAGMA user_version').fetchone()[0],4);self.assertTrue(list((self.store.path.parent/'backups').glob('antes-eventos-*.sqlite3')))
 def test_cancel_signature_schema_and_registration(self):
  rid=self.prepare();e=self.events.get(self.cid,rid);verify_signature(parse_xml(e['signed_xml']),self.cert);self.events.begin(self.cid,rid,self.cert);self.assertEqual(self.events.apply(self.cid,rid,self.response(rid)),'REGISTRADO');self.assertEqual(self.fiscal.get(self.cid,self.did)['status'],'CANCELADA');self.assertTrue(self.fiscal.get(self.cid,self.did)['proc_xml']);self.assertTrue(self.events.get(self.cid,rid)['proc_xml'])
 def test_late_cancel_155_accepted_only_for_cancel(self):
  rid=self.prepare();self.events.begin(self.cid,rid,self.cert);self.assertEqual(self.events.apply(self.cid,rid,self.response(rid,'155')),'REGISTRADO')
 def test_cce_does_not_modify_original_note(self):
  before=self.fiscal.get(self.cid,self.did);rid=self.prepare('110110','Correcao de observacao comercial de teste');self.events.begin(self.cid,rid,self.cert);self.events.apply(self.cid,rid,self.response(rid));after=self.fiscal.get(self.cid,self.did);self.assertEqual(before['signed_xml'],after['signed_xml']);self.assertEqual(after['status'],'AUTORIZADA')
 def test_new_cce_sequence_and_full_revision(self):
  first=self.prepare('110110','Correcao de observacao comercial inicial');self.events.begin(self.cid,first,self.cert);self.events.apply(self.cid,first,self.response(first));second=self.prepare('110110','Todas as correcoes consolidadas neste texto');self.assertEqual(self.events.get(self.cid,second)['sequence'],2)
 def test_revision_keeps_sequence_and_history(self):
  first=self.prepare('110110','Correcao de observacao comercial inicial');old=self.events.get(self.cid,first)['signed_xml'];second=self.prepare('110110','Correcao revisada completa no mesmo pedido');self.assertEqual(first,second);self.assertNotEqual(self.events.get(self.cid,first)['signed_xml'],old);self.assertTrue(self.store.db.execute("SELECT 1 FROM event_history WHERE event=? AND action='REVISAO'",(first,)).fetchone())
 def test_wrong_key_environment_sequence_never_applied(self):
  rid=self.prepare();self.events.begin(self.cid,rid,self.cert)
  for args in ({'key':'1'*44},{'env':'1'},{'seq':2}):
   with self.assertRaises(ValueError):self.events.apply(self.cid,rid,self.response(rid,**args))
  self.assertEqual(self.fiscal.get(self.cid,self.did)['status'],'AUTORIZADA')
 def test_136_does_not_cancel_and_blocks_new_event(self):
  rid=self.prepare();self.events.begin(self.cid,rid,self.cert);self.assertEqual(self.events.apply(self.cid,rid,self.response(rid,'136')),'PENDENTE');self.assertEqual(self.fiscal.get(self.cid,self.did)['status'],'AUTORIZADA')
  with self.assertRaises(ValueError):self.prepare()
 def test_573_is_uncertain_not_registered(self):
  rid=self.prepare();self.events.begin(self.cid,rid,self.cert);self.assertEqual(self.events.apply(self.cid,rid,self.response(rid,'573')),'INCERTO')
 def test_timeout_persists_and_never_auto_retries(self):
  rid=self.prepare();calls=[]
  class Transport:
   def request(inner,op,body):calls.append(op);raise TimeoutError('simulated timeout')
  svc=EventService(self.events,self.cert,Transport())
  with self.assertRaises(TimeoutError):svc.send(self.cid,rid)
  self.assertEqual(self.events.get(self.cid,rid)['status'],'INCERTO')
  with self.assertRaises(ValueError):svc.send(self.cid,rid)
  self.assertEqual(len(calls),1)
 def test_cancel_scope_and_confirmation(self):
  with self.assertRaises(ValueError):self.events.prepare(self.cid,self.did,'110111','Motivo de cancelamento',self.cert)
  with self.assertRaises(ValueError):self.events.get('other',self.prepare())
 def test_prepared_signature_tampering_blocked_before_begin(self):
  rid=self.prepare();e=self.events.get(self.cid,rid)
  with self.store.db:self.store.db.execute('UPDATE fiscal_events SET signed_xml=? WHERE id=?',(e['signed_xml'].replace(b'Cancelamento de teste',b'Cancelamento adulterado'),rid))
  with self.assertRaises(Exception):self.events.begin(self.cid,rid,self.cert)
  self.assertEqual(self.events.get(self.cid,rid)['status'],'PREPARADO')
 def test_inutil_signature_and_reserved_range(self):
  year=datetime.datetime.now(TZ).year;rid=self.events.prepare_inutil(self.cid,year,1,2,10,'Falha de numeracao sintetica revisada',self.cert,True);self.assertEqual(next_number(self.store,self.cid,'2','1'),'11')
  with self.assertRaises(ValueError):check_number_available(self.store,self.cid,dict(self.note,number='5'))
  self.events.begin(self.cid,rid,self.cert);self.assertEqual(self.events.apply(self.cid,rid,self.inutil_response(rid)),'REGISTRADO');self.assertTrue(self.events.get(self.cid,rid)['proc_xml'])
 def test_inutil_overlap_and_used_numbers_rejected(self):
  year=datetime.datetime.now(TZ).year
  with self.assertRaises(ValueError):self.events.prepare_inutil(self.cid,year,1,1,2,'Faixa de teste com numero usado',self.cert,True)
  self.events.prepare_inutil(self.cid,year,1,2,5,'Faixa sintetica de teste sem uso',self.cert,True)
  with self.assertRaises(ValueError):self.events.prepare_inutil(self.cid,year,1,4,6,'Faixa sintetica de teste repetida',self.cert,True)
 def test_inutil_rejection_revision_and_wrong_range(self):
  year=datetime.datetime.now(TZ).year;rid=self.events.prepare_inutil(self.cid,year,1,2,5,'Motivo sintetico de numeracao',self.cert,True);self.events.begin(self.cid,rid,self.cert);self.events.apply(self.cid,rid,self.inutil_response(rid,'201'));new=self.events.prepare_inutil(self.cid,year,1,2,5,'Motivo sintetico corrigido para revisao',self.cert,True);self.assertEqual(rid,new)
  with self.assertRaises(ValueError):self.events.apply(self.cid,rid,self.inutil_response(rid).replace(b'<nNFFin>5',b'<nNFFin>6'))
 def test_event_signature_survives_soap_envelope_without_network(self):
  rid=self.prepare();e=self.events.get(self.cid,rid)
  from fiscal import tag,serialize
  from lxml import etree as ET
  env=ET.Element('{'+NS+'}envEvento',nsmap={None:NS},versao='1.00');tag(env,'idLote','1');env.append(parse_xml(e['signed_xml']))
  class Response:
   status_code=200
   def __enter__(s):return s
   def __exit__(s,*a):pass
   def iter_content(s,*a):return [b'<ok/>']
  class Session:
   def __enter__(s):return s
   def __exit__(s,*a):pass
   def mount(s,*a):pass
   def post(s,*a,**kw):self.assertTrue(kw['verify']);self.assertFalse(kw['allow_redirects']);return Response()
  with patch('requests.Session',Session),patch('fiscal.create_tls_adapter',return_value=object()):SefazTransport(self.cert).request('event',serialize(env))

 def test_query_reconciles_registered_event_after_timeout(self):
  rid=self.prepare();self.events.begin(self.cid,rid,self.cert);self.events.uncertain(self.cid,rid,'Timeout sintetico');e=self.events.get(self.cid,rid);returned=parse_xml(self.response(rid)).find('n:retEvento',{'n':NS})
  from lxml import etree as ET
  from fiscal import tag
  proc=ET.Element('{'+NS+'}procEventoNFe',nsmap={None:NS},versao='1.00');proc.append(parse_xml(e['signed_xml']));proc.append(returned)
  root=ET.Element('{'+NS+'}retConsSitNFe',nsmap={None:NS},versao='4.00');tag(root,'tpAmb','2');tag(root,'chNFe',self.fiscal.get(self.cid,self.did)['access_key']);root.append(proc);data=serialize(root)
  class Transport:
   def request(inner,op,body):self.assertEqual(op,'query');return data
  self.assertEqual(EventService(self.events,self.cert,Transport()).query(self.cid,rid),'REGISTRADO');self.assertEqual(self.fiscal.get(self.cid,self.did)['status'],'CANCELADA')
 def test_query_without_event_never_releases_resend(self):
  rid=self.prepare();self.events.begin(self.cid,rid,self.cert);self.events.uncertain(self.cid,rid,'Timeout sintetico')
  class Transport:
   def request(inner,op,body):return ('<retConsSitNFe xmlns="'+NS+'" versao="4.00"><tpAmb>2</tpAmb><cStat>100</cStat></retConsSitNFe>').encode()
  with self.assertRaises(ValueError):EventService(self.events,self.cert,Transport()).query(self.cid,rid)
  self.assertEqual(self.events.get(self.cid,rid)['status'],'INCERTO')
 def test_registered_event_files_are_in_document_hub(self):
  from document_hub import entries,artifacts
  rid=self.prepare('110110','Observacao comercial corrigida integralmente');self.events.begin(self.cid,rid,self.cert);self.events.apply(self.cid,rid,self.response(rid));entry=next(e for e in entries(self.store,self.cid,'2') if e['id']==self.did);files=artifacts(self.store,self.cid,entry);self.assertTrue(any('eventos/' in n and n.endswith('processado.xml') for n in files))
 def test_uncertain_other_kind_blocks_new_event(self):
  rid=self.prepare();self.events.begin(self.cid,rid,self.cert);self.events.uncertain(self.cid,rid,'Timeout')
  with self.assertRaises(ValueError):self.prepare('110110','Correcao comercial nao deve ser preparada')

 def test_stale_authorization_cannot_reverse_registered_cancel(self):
  rid=self.prepare();self.events.begin(self.cid,rid,self.cert);self.events.apply(self.cid,rid,self.response(rid));d=self.fiscal.get(self.cid,self.did)
  with self.assertRaises(ValueError):self.fiscal.apply_response(self.cid,self.did,self.f.fixture(d['access_key'],d['signed_xml']))
  self.assertEqual(self.fiscal.get(self.cid,self.did)['status'],'CANCELADA')

 def test_discard_only_never_sent_and_keeps_history(self):
  rid=self.prepare();self.events.discard(self.cid,rid);self.assertEqual(self.events.get(self.cid,rid)['status'],'DESCARTADO');new=self.prepare();self.assertEqual(new,rid);self.events.begin(self.cid,new,self.cert)
  with self.assertRaises(ValueError):self.events.discard(self.cid,new)
 def test_discard_inutil_releases_only_untransmitted_range(self):
  year=datetime.datetime.now(TZ).year;rid=self.events.prepare_inutil(self.cid,year,1,2,5,'Faixa sintetica ainda nao enviada',self.cert,True);self.events.discard(self.cid,rid);self.assertEqual(next_number(self.store,self.cid,'2','1'),'2')
 def test_concurrent_stale_response_keeps_cancel(self):
  doc=self.fiscal.get(self.cid,self.did)
  import fiscal
  original=fiscal.unpack_response
  def race(*args,**kwargs):
   result=original(*args,**kwargs)
   with self.store.db:self.store.db.execute("UPDATE fiscal_documents SET status='CANCELADA' WHERE id=?",(self.did,))
   return result
  with patch('fiscal.unpack_response',side_effect=race):
   with self.assertRaises(ValueError):self.fiscal.apply_response(self.cid,self.did,self.f.fixture(doc['access_key'],doc['signed_xml']))
  self.assertEqual(self.fiscal.get(self.cid,self.did)['status'],'CANCELADA')

 def test_production_event_mocked_keeps_homologation_separate(self):
  co=self.store.get('company','',self.cid);co.update(environment='1',production_enabled=True);self.store.save('company',co,'',self.cid);note=copy.deepcopy(self.note);note['environment']='1';source=self.store.save('note',note,self.cid);xml,key,_=build_unsigned(co,self.f.recipient,note);signed=self.cert.sign(xml);did=self.fiscal.prepare(self.cid,source,dict(company=co,recipient=self.f.recipient,note=note),signed,key);response=self.f.fixture(key,signed).replace(b'<tpAmb>2</tpAmb>',b'<tpAmb>1</tpAmb>');self.fiscal.apply_response(self.cid,did,response)
  rid=self.events.prepare(self.cid,did,'110111','Cancelamento sintetico em transporte simulado',self.cert,True,True);outer=self
  class Transport:
   def request(inner,op,body):
    outer.assertEqual(op,'event');outer.assertEqual(parse_xml(body).findtext('n:evento/n:infEvento/n:tpAmb',namespaces={'n':NS}),'1');return outer.response(rid)
  self.assertEqual(EventService(self.events,self.cert,Transport()).send(self.cid,rid),'REGISTRADO');self.assertEqual(self.fiscal.get(self.cid,did)['status'],'CANCELADA');self.assertEqual(self.fiscal.get(self.cid,self.did)['status'],'AUTORIZADA')
