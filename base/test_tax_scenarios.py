import copy,unittest
from decimal import Decimal
from core import calculate,money
from fiscal import build_unsigned,unsigned_schema_issues,validate_schema,parse_xml,text
from note_validation import validate_note
from tax_scenarios import simulate_difal
import test_fiscal as fixture
class AdvancedTaxes(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixture.FiscalTests.setUpClass();cls.cert=fixture.FiscalTests.certificate
 @classmethod
 def tearDownClass(cls):fixture.FiscalTests.tearDownClass()
 def setUp(self):
  f=fixture.FiscalTests();f.cnpj='11222333000181';f.setUp();self.co=f.company;self.rec=dict(f.recipient,indIEDest='1',IE='240000001');self.n=copy.deepcopy(f.note);self.item=self.n['items'][0];self.item['product']['CEST']='0300100';self.n.update(nature='VENDA',operation='1',destination='1',purpose='1',environment='2')
  self.item['rule'].update(icms_code='202',CFOP='5403');self.item['taxes']=dict(reviewed='1',legal_reference='Enquadramento sintetico revisado para testes',st_mode='4',st_base='266',st_mva='40',st_rate='18',st_deduction='22.80')
 def amounts(self):return calculate(self.item,self.item['rule'],'1')
 def xml(self):
  data,_,totals=build_unsigned(self.co,self.rec,self.n);self.assertEqual(unsigned_schema_issues(data),[]);validate_schema(self.cert.sign(data));return parse_xml(data),totals
 def test_st_and_fcpst_arithmetic_and_totals(self):
  self.item['taxes'].update(fcpst_enabled='1',fcpst_base='266',fcpst_rate='2');a=self.amounts();self.assertEqual(a['st'],money('25.08'));self.assertEqual(a['fcpst'],money('5.32'));self.assertEqual(a['net'],money('220.40'));xml,total=self.xml();self.assertEqual(text(xml,'n:infNFe/n:total/n:ICMSTot/n:vST'),'25.08');self.assertEqual(text(xml,'n:infNFe/n:total/n:ICMSTot/n:vFCPST'),'5.32');self.assertEqual(total['net'],money('220.40'))
 def test_st_csosn_201_202_203_schema(self):
  for code in ('201','202','203'):
   self.item['rule'].update(icms_code=code,credit_rate='3');xml,_=self.xml();self.assertIn(code.encode(),self.cert.sign(build_unsigned(self.co,self.rec,self.n)[0]))
 def test_missing_cest_base_rate_deduction_mva_review_rejected(self):
  for key in ('st_base','st_rate','st_deduction','st_mva','reviewed','legal_reference'):
   old=self.item['taxes'].pop(key)
   with self.subTest(key=key):
    with self.assertRaises(ValueError):self.amounts()
   self.item['taxes'][key]=old
  self.item['product'].pop('CEST')
  with self.assertRaises(ValueError):self.amounts()
 def test_negative_st_not_silently_clamped(self):
  self.item['taxes']['st_deduction']='100'
  with self.assertRaises(ValueError):self.amounts()
 def test_st_new_context_blocks_noncontributor_returns_and_production(self):
  with self.assertRaises(ValueError):build_unsigned(self.co,dict(self.rec,indIEDest='9'),self.n)
  self.n['environment']='1';self.co['production_enabled']=True
  with self.assertRaisesRegex(ValueError,'homologação'):build_unsigned(self.co,self.rec,self.n)
 def test_manual_additional_amounts_must_match(self):
  self.item.update(auto_calc='0',manual=dict(icms_base='0',icms='0',pis_base='190',pis='0',cofins_base='190',cofins='0'));self.item['taxes']['manual_st']='25.08';self.assertEqual(self.amounts()['st'],money('25.08'));self.item['taxes']['manual_st']='20'
  with self.assertRaisesRegex(ValueError,'diverge'):self.amounts()
 def test_additional_errors_point_to_exact_field(self):
  self.item['taxes'].pop('st_rate');issues=validate_note(self.co,self.rec,self.n);self.assertTrue(any(i.field=='item.0.taxes.st_rate' for i in issues),issues)
 def test_ipi_return_percent_schema_total_and_reason(self):
  self.item['rule'].update(icms_code='900',icms_rate='12',CFOP='5102');self.item['taxes']={};origin=build_unsigned(self.co,self.rec,dict(self.n,purpose='1'))[1];self.item['rule']['CFOP']='5202'
  self.n.update(purpose='4',payment='90',has_reference='1',references=origin,number='2');self.item['taxes']=dict(reviewed='1',legal_reference='Devolucao sintetica conferida no documento original',ipi_return_enabled='1',ipi_original_value='20',ipi_return_percent='50',ipi_origin_key=origin,ipi_reason='Devolucao parcial de mercadoria de teste')
  a=self.amounts();self.assertEqual(a['ipi_return'],money('10'));xml,tot=self.xml();self.assertEqual(text(xml,'n:infNFe/n:det/n:impostoDevol/n:IPI/n:vIPIDevol'),'10.00');self.assertEqual(text(xml,'n:infNFe/n:total/n:ICMSTot/n:vIPIDevol'),'10.00');self.assertEqual(tot['net'],money('200'))
  self.n['purpose']='1'
  with self.assertRaises(ValueError):build_unsigned(self.co,self.rec,self.n)
 def test_difal_never_silently_enters_xml(self):
  self.item['taxes']['difal_enabled']='1'
  with self.assertRaisesRegex(ValueError,'DIFAL'):self.amounts()
  self.assertEqual(simulate_difal('100','20','12','2'),dict(difal=money('8'),fcp=money('2')))
 def test_ipi_normal_is_blocked_for_current_regime(self):
  self.item['taxes']['ipi_code']='50'
  with self.assertRaisesRegex(ValueError,'IPI tributado'):self.amounts()
 def test_rounding_is_per_item_and_totals_sum(self):
  self.item['taxes'].update(st_base='100.03',st_rate='17',st_deduction='0');self.n['items'].append(copy.deepcopy(self.item));xml,tot=self.xml();self.assertEqual(tot['st'],money('34.02'))
