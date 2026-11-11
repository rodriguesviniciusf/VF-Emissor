import copy,json,sys,tempfile,unittest
from pathlib import Path
from decimal import Decimal
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'base'))
import server
from core import Store
from fiscal import FiscalStore,build_unsigned,unsigned_schema_issues,parse_xml,NS
from normal_fiscal import default_groups,calculate_normal
from web_settings import load_settings,save_settings

class PreferencesTests(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory();server.STORE=Store(Path(self.tmp.name)/'test.sqlite3');FiscalStore(server.STORE)
    self.co=dict(CNPJCPF='11222333000181',xNome='EMPRESA TESTE',IE='240000001',xLgr='RUA',nro='1',xBairro='CENTRO',cMun='2700300',xMun='ARAPIRACA',UF='AL',CEP='57300000',CRT='3',rtc_policy='sem_informacao_revisada',rtc_reason='Cenario ficticio revisado para testes',environment='2',series='1')
    self.cid=server.save_catalog(dict(kind='company',data=self.co))['id']
    self.rule=dict(CFOP='5102',icms_code='00',origin='0',icms_rate='18',pis_code='01',pis_rate='1.65',cofins_code='01',cofins_rate='7.6',reviewed='1')
    self.i=dict(product=dict(code='P1',name='TESTE',unit='UN',NCM='03061710'),quantity='1',price='1000',discount='0',rule=self.rule)
 def tearDown(self):server.STORE.db.close();self.tmp.cleanup()
 def save(self,section,data,cid=None):return server.action(dict(action='save_settings',cid=cid or self.cid,section=section,data=data))
 def test_defaults_apply_only_to_new_notes(self):
    before=server.action(dict(action='new_note',cid=self.cid))['note']
    self.save('defaults',dict(nature='VENDA TESTE',payment='17',info='Texto padrão',transport_mode='1'))
    after=server.action(dict(action='new_note',cid=self.cid))['note']
    self.assertEqual((after['nature'],after['payment'],after['info'],after['transport_mode']),('VENDA TESTE','17','Texto padrão','1'))
    self.assertEqual(before['nature'],'VENDA DE MERCADORIA');self.assertEqual(before['items'],[])
 def test_preferences_are_company_scoped(self):
    other=server.save_catalog(dict(kind='company',data=dict(self.co,CNPJCPF='12345678000195')))['id']
    self.save('defaults',dict(info='Somente empresa um'))
    self.assertEqual(load_settings(server.STORE,other)['defaults']['info'],'')
 def test_accountant_roundtrip_and_validation(self):
    self.save('accountant',dict(name='CONTADOR TESTE',cpf='52998224725',crc='AL000001',email='teste@example.com'))
    self.assertEqual(load_settings(server.STORE,self.cid)['accountant']['crc'],'AL000001')
    with self.assertRaises(ValueError):self.save('accountant',dict(cpf='123'))
    self.assertEqual(load_settings(server.STORE,self.cid)['accountant']['name'],'CONTADOR TESTE')
 def test_reject_invalid_defaults_and_foreign_rule(self):
    for data in [dict(CFOP='123'),dict(payment='abc'),dict(final='2'),dict(cMunFG='1'),dict(authorized_xml='123'),dict(authorized_xml=','.join(['52998224725']*11)),dict(rule_id='missing')]:
        with self.subTest(data=data),self.assertRaises(ValueError):self.save('defaults',data)
 def test_settings_survive_reopen(self):
    self.save('defaults',dict(info='Persistido'))
    server.STORE.db.close();server.STORE=Store(Path(self.tmp.name)/'test.sqlite3')
    self.assertEqual(load_settings(server.STORE,self.cid)['defaults']['info'],'Persistido')
 def test_public_state_omits_password_hash(self):
    server.save_catalog(dict(kind='company',id=self.cid,data=dict(self.co,password='senha-sintetica')))
    state=server.get_state(self.cid)
    self.assertNotIn('password_hash',state['company']);self.assertNotIn('password_hash',state['companies'][0])
 def test_authorized_xml_and_generator_municipality_in_xml(self):
    self.co.update(fantasia='EMPRESA FICTICIA',IM='123456',CNAE='4712100')
    self.save('defaults',dict(authorized_xml='52998224725,12345678000195',cMunFG='2704302'))
    note=server.action(dict(action='new_note',cid=self.cid))['note'];note.update(number='1',cnf='12345678',items=[self.i])
    rec=dict(self.co,CNPJCPF='52998224725',xNome='CLIENTE TESTE',indIEDest='9')
    xml,_,_=build_unsigned(self.co,rec,note);self.assertEqual(unsigned_schema_issues(xml),[])
    root=parse_xml(xml);n={'n':NS}
    self.assertEqual(root.findtext('n:infNFe/n:ide/n:cMunFG',namespaces=n),'2704302')
    self.assertEqual(root.findtext('n:infNFe/n:emit/n:IM',namespaces=n),'123456')
    self.assertEqual(root.findtext('n:infNFe/n:emit/n:CNAE',namespaces=n),'4712100')
    self.assertEqual(root.xpath('//n:autXML/n:CPF/text()',namespaces=n),['52998224725'])
    self.assertEqual(root.xpath('//n:autXML/n:CNPJ/text()',namespaces=n),['12345678000195'])
 def test_invalid_authorized_xml_cannot_enter_document(self):
    note=dict(environment='2',series='1',number='1',cnf='12345678',issued_at='2026-11-10T11:00:00-03:00',items=[self.i],authorized_xml='123')
    with self.assertRaisesRegex(ValueError,'autorizado'):build_unsigned(self.co,dict(self.co,CNPJCPF='52998224725',indIEDest='9'),note)
 def st_item(self,mode='4'):
    i=copy.deepcopy(self.i);i['normal_groups']=default_groups('10','0','18','01','1.65','01','7.6')
    i['normal_groups']['ICMS']['ICMS10'].update(modBCST=mode,pMVAST='40',pRedBCST='0',pICMSST='18')
    i['normal_st_base_mode']='formula';return i
 def test_st_mva_with_ipi_and_reduction(self):
    i=self.st_item();i['normal_groups']['IPI']=dict(cEnq='999',IPITrib=dict(CST='50',pIPI='5'))
    totals=calculate_normal(i,self.rule);self.assertEqual(totals['st_base'],Decimal('1470'));self.assertEqual(totals['st'],Decimal('84.60'));self.assertEqual(totals['net'],Decimal('1134.60'))
    i['normal_groups']['ICMS']['ICMS10']['pRedBCST']='10'
    self.assertEqual(calculate_normal(i,self.rule)['st_base'],Decimal('1323'))
 def test_st_pauta_and_value_modes(self):
    i=self.st_item('5');i['quantity']='2';i['normal_st_unit_value']='1500'
    self.assertEqual(calculate_normal(i,self.rule)['st_base'],Decimal('3000'))
    i=self.st_item('6');self.assertEqual(calculate_normal(i,self.rule)['st_base'],Decimal('1000'))
 def test_st_manual_base_is_preserved_for_existing_items(self):
    i=self.st_item();i.pop('normal_st_base_mode');i['normal_groups']['ICMS']['ICMS10']['vBCST']='1600'
    self.assertEqual(calculate_normal(i,self.rule)['st_base'],Decimal('1600'))
 def test_st_rejects_unreviewed_formula_modes_and_invalid_parameters(self):
    for mode in ['0','1','2','3']:
        with self.subTest(mode=mode),self.assertRaises(ValueError):calculate_normal(self.st_item(mode),self.rule)
    i=self.st_item('5')
    with self.assertRaisesRegex(ValueError,'pauta'):calculate_normal(i,self.rule)
    i=self.st_item();i['normal_groups']['ICMS']['ICMS10']['pMVAST']='-10'
    with self.assertRaisesRegex(ValueError,'negativa'):calculate_normal(i,self.rule)
 def test_partial_calculation_does_not_authorize_invalid_structure(self):
    i=copy.deepcopy(self.i);i['normal_groups']=default_groups('20');i['normal_groups']['ICMS']['ICMS20']['pRedBC']=''
    self.assertEqual(calculate_normal(i,self.rule,validate=False)['net'],Decimal('1000'))
    with self.assertRaises(ValueError):calculate_normal(i,self.rule)
 def test_auto_rtc_and_difal_bases_recalculate_after_price_change(self):
    from normal_fiscal import normalized
    i=copy.deepcopy(self.i);i['normal_groups']=default_groups('00','0','18')
    i['normal_groups']['IBSCBS']=dict(CST='000',cClassTrib='000001',gIBSCBS=dict(vBC='1000',gIBSUF=dict(pIBSUF='0.1'),gIBSMun=dict(pIBSMun='0'),gCBS=dict(pCBS='0.9')))
    i['normal_groups']['ICMSUFDest']=dict(vBCUFDest='1000',vBCFCPUFDest='1000',pFCPUFDest='2',pICMSUFDest='18',pICMSInter='12',pICMSInterPart='100')
    g,_=normalized(i,self.rule);i['normal_groups']=g;i['price']='2000'
    g,_=normalized(i,self.rule)
    self.assertEqual(g['IBSCBS']['gIBSCBS']['vBC'],'2000.00')
    self.assertEqual(g['IBSCBS']['gIBSCBS']['gCBS']['vCBS'],'18.00')
    self.assertEqual(g['ICMSUFDest']['vBCFCPUFDest'],'2000.00')
    self.assertEqual(g['ICMSUFDest']['vFCPUFDest'],'40.00')

if __name__=='__main__':unittest.main()
