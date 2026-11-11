import copy,tempfile,unittest
from pathlib import Path
import test_fiscal as fixtures
from core import calculate,Store,money
from fiscal import build_unsigned,unsigned_schema_issues,validate_schema
from note_validation import validate_note
from note_finance import allocate_expenses

class WorkflowTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
    fixtures.FiscalTests.setUpClass();cls.certificate=fixtures.FiscalTests.certificate
 @classmethod
 def tearDownClass(cls):fixtures.FiscalTests.tearDownClass()
 def setUp(self):
    base=fixtures.FiscalTests();base.cnpj='11222333000181';base.setUp()
    self.company=base.company;self.recipient=base.recipient;self.note=base.note;self.rule=base.rule
    self.note.update(nature='VENDA',operation='1',destination='1',purpose='1',has_reference='0',references='',transport_mode='9')
 def check_schema(self):
    xml,key,total=build_unsigned(self.company,self.recipient,self.note)
    self.assertEqual(unsigned_schema_issues(xml),[])
    validate_schema(self.certificate.sign(xml))
    return xml,key,total
 def test_multiple_issues(self):
    self.note.update(number='0',nature='',items=[])
    issues=validate_note(self.company,None,self.note)
    self.assertTrue({'recipient','number','nature','items'}<={i.field for i in issues})
 def test_interstate_simples_schema(self):
    self.recipient.update(UF='PE',cMun='2611606',xMun='RECIFE',CEP='50000000')
    self.note['destination']='2';self.rule['CFOP']='6102'
    xml,_,_=self.check_schema();self.assertIn(b'<idDest>2</idDest>',xml)
 def test_inbound_and_reference(self):
    _,key,_=self.check_schema()
    self.note.update(number='2',operation='0',purpose='4',has_reference='1',references=key,payment='90')
    self.rule['CFOP']='1202';xml,_,_=self.check_schema()
    self.assertIn(b'<tpNF>0</tpNF>',xml);self.assertIn(key.encode(),xml)
 def test_reference_required_and_wrong_digit(self):
    self.note.update(purpose='4',payment='90');self.rule['CFOP']='5202'
    self.assertIn('references',[i.field for i in validate_note(self.company,self.recipient,self.note)])
    self.note.update(has_reference='1',references='1'*44)
    self.assertIn('references',[i.field for i in validate_note(self.company,self.recipient,self.note)])
 def test_manual_tax_and_separate_pc_bases(self):
    self.rule.update(icms_code='900',icms_rate='12',pis_code='01',pis_rate='1.65',cofins_code='01',cofins_rate='7.6')
    self.note['items'][0].update(auto_calc='0',manual=dict(icms_base='100',icms='12',pis_base='80',pis='1.32',cofins_base='90',cofins='6.84'))
    xml,_,_=self.check_schema()
    self.assertIn(b'<ICMSSN900>',xml);self.assertIn(b'<vPIS>1.32</vPIS>',xml);self.assertIn(b'<vCOFINS>6.84</vCOFINS>',xml)
 def test_manual_incoherence_blocked(self):
    self.rule.update(icms_code='900',icms_rate='12')
    item=self.note['items'][0];item.update(auto_calc='0',manual=dict(icms_base='100',icms='40',pis_base='0',pis='0',cofins_base='0',cofins='0'))
    with self.assertRaisesRegex(ValueError,'ICMS manual'):calculate(item,self.rule,'1')
 def test_expense_allocation_exact_and_persistent(self):
    items=[copy.deepcopy(self.note['items'][0]) for _ in range(3)]
    allocated=allocate_expenses(items,dict(freight='.01',insurance='.02',other='1'))
    self.assertEqual(sum(money(i['freight']) for i in allocated),money('.01'))
    with tempfile.TemporaryDirectory() as temp:
        s=Store(Path(temp)/'db');rid=s.save('note',dict(items=allocated),'company');self.assertEqual(len(s.get('note','company',rid)['items']),3);s.db.close()
 def test_transport_billing_schema(self):
    self.note.update(freight='10',insurance='2',other='3',transport_mode='0',carrier_doc=self.company['CNPJCPF'],carrier_name='TRANSPORTADORA TESTE',carrier_uf='AL',vehicle_plate='ABC1D23',vehicle_uf='AL',volume_qty='2',volume_type='CAIXA',net_weight='5',gross_weight='6',invoice_number='F1',invoice_original='205',invoice_discount='0',invoice_net='205',duplicates='001|2026-12-01|205')
    self.note['items']=allocate_expenses(self.note['items'],self.note)
    xml,_,total=self.check_schema();self.assertEqual(total['net'],money('205'));self.assertIn(b'<cobr>',xml);self.assertIn(b'<vFrete>10.00</vFrete>',xml)
 def test_no_cross_company_get(self):
    with tempfile.TemporaryDirectory() as temp:
        s=Store(Path(temp)/'db');rid=s.save('product',{'name':'A'},'A')
        with self.assertRaises(ValueError):s.get('product','B',rid)
        self.assertEqual(s.list('product','B'),[]);s.db.close()

 def test_official_catalog_and_unknown_cfop(self):
    from cfop_catalog import catalog,cfop_errors
    self.assertEqual(len(catalog()),619);self.assertEqual(catalog()['1202']['indDevol'],'1')
    self.assertTrue(cfop_errors('5999',self.note))
 def test_xml_error_has_location(self):
    self.note['nature']='A'*70
    issues=validate_note(self.company,self.recipient,self.note)
    self.assertTrue(any(i.field=='nature' for i in issues),issues)

 def test_valid_local_note_without_certificate(self):
    self.assertEqual(validate_note(self.company,self.recipient,self.note),[])
