import copy,tempfile,unittest
from pathlib import Path
import test_fiscal as fixtures
from core import Store,consumer_final_error
from fiscal import FiscalStore,FiscalService,build_unsigned,parse_xml,serialize,NS
from note_validation import validate_note

class CorrectionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
    fixtures.FiscalTests.setUpClass();cls.cert=fixtures.FiscalTests.certificate
 @classmethod
 def tearDownClass(cls):fixtures.FiscalTests.tearDownClass()
 def setUp(self):
    f=fixtures.FiscalTests();f.cnpj='11222333000181';f.setUp()
    self.company=f.company;self.recipient=f.recipient;self.note=f.note
    self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'db')
    self.fiscal=FiscalStore(self.store);self.cid=self.store.save('company',self.company)
 def tearDown(self):self.store.db.close();self.temp.cleanup()
 def reserve(self,legacy=False,tamper=False):
    note=copy.deepcopy(self.note);unsigned,key,_=build_unsigned(self.company,self.recipient,note)
    if legacy:
        root=parse_xml(unsigned);root.find('n:infNFe/n:ide/n:indFinal',{'n':NS}).text='0'
        unsigned=serialize(root);note['final']='0'
    signed=self.cert.sign(unsigned)
    if tamper:
        root=parse_xml(signed);root.find('n:infNFe/n:det/n:prod/n:xProd',{'n':NS}).text='ALTERADO SEM ASSINAR';signed=serialize(root)
    source=self.store.save('note',note,self.cid);snapshot=dict(company=self.company,recipient=self.recipient,note=note)
    rid=self.fiscal.prepare(self.cid,source,snapshot,signed,key)
    return rid,source,note,signed,key
 def reject(self,rid):
    response=f'<retEnviNFe xmlns="{NS}" versao="4.00"><tpAmb>2</tpAmb><cStat>696</cStat><xMotivo>Operacao com nao contribuinte deve indicar consumidor final</xMotivo></retEnviNFe>'.encode()
    self.fiscal.begin_send(self.cid,rid);self.fiscal.apply_response(self.cid,rid,response);return response
 def spy(self):
    class Transport:
        count=0
        def request(self,*args):self.count+=1;raise AssertionError('Não deveria transmitir')
    return Transport()
 def test_696_points_to_final(self):
    note=dict(self.note,final='0')
    self.assertTrue(any(i.field=='final' and '696' in i.message for i in validate_note(self.company,self.recipient,note)))
    self.assertFalse(consumer_final_error(self.recipient,dict(note,operation='0')))
    self.assertFalse(consumer_final_error(dict(self.recipient,indIEDest='1'),note))
 def test_legacy_invalid_signed_document_never_sends(self):
    rid,_,_,_,_=self.reserve(legacy=True);spy=self.spy()
    with self.assertRaisesRegex(ValueError,'696'):FiscalService(self.fiscal,self.cert,spy).send(self.cid,rid)
    self.assertEqual(spy.count,0);self.assertEqual(self.fiscal.get(self.cid,rid)['status'],'PREPARADA')
 def test_correction_keeps_id_number_and_history(self):
    rid,source,_,old_xml,key=self.reserve(legacy=True);response=self.reject(rid)
    note=self.fiscal.draft_for_correction(self.cid,rid);note['final']='1'
    self.store.save('note',note,self.cid,source)
    unsigned,new_key,_=build_unsigned(self.company,self.recipient,note);signed=self.cert.sign(unsigned)
    self.assertEqual(self.fiscal.prepare(self.cid,source,dict(company=self.company,recipient=self.recipient,note=note),signed,new_key),rid)
    self.assertEqual(len(self.fiscal.list(self.cid)),1);self.assertEqual(new_key,key)
    doc=self.fiscal.get(self.cid,rid);self.assertEqual(doc['status'],'PREPARADA');self.assertEqual(doc['number'],1)
    data=self.store.db.execute('SELECT data FROM fiscal_history WHERE document=?',(rid,)).fetchall()
    self.assertIn((old_xml,),data);self.assertIn((response,),data);self.fiscal.assert_sendable(self.cid,rid)
 def test_correction_rejects_final_and_uncertain_states(self):
    rid,_,_,_,_=self.reserve()
    for state in ('ENVIANDO','INCERTA','PROCESSANDO','AUTORIZADA','CANCELADA','DENEGADA','NAO_LOCALIZADA'):
        with self.store.db:self.store.db.execute('UPDATE fiscal_documents SET status=? WHERE id=?',(state,rid))
        with self.assertRaises(ValueError):self.fiscal.draft_for_correction(self.cid,rid)
 def test_changed_draft_never_sends_old_xml(self):
    rid,source,note,_,_=self.reserve();note['nature']='OUTRA OPERACAO'
    self.store.save('note',note,self.cid,source);spy=self.spy()
    with self.assertRaisesRegex(ValueError,'rascunho foi alterado'):FiscalService(self.fiscal,self.cert,spy).send(self.cid,rid)
    self.assertEqual(spy.count,0);self.assertEqual(self.fiscal.get(self.cid,rid)['status'],'PREPARADA')
 def test_bad_signature_is_blocked_before_begin_send(self):
    rid,_,_,_,_=self.reserve(tamper=True);spy=self.spy()
    with self.assertRaises(Exception):FiscalService(self.fiscal,self.cert,spy).send(self.cid,rid)
    self.assertEqual(spy.count,0);self.assertEqual(self.fiscal.get(self.cid,rid)['status'],'PREPARADA')
 def test_old_revision_cannot_start_send(self):
    rid,source,note,old_xml,key=self.reserve();note['info']='REVISAO ANTES DO ENVIO'
    self.store.save('note',note,self.cid,source)
    unsigned,new_key,_=build_unsigned(self.company,self.recipient,note)
    self.fiscal.prepare(self.cid,source,dict(company=self.company,recipient=self.recipient,note=note),self.cert.sign(unsigned),new_key)
    with self.assertRaises(ValueError):self.fiscal.begin_send(self.cid,rid,old_xml)
    self.assertEqual(self.fiscal.get(self.cid,rid)['status'],'PREPARADA')
