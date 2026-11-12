import copy, unittest, sys, tempfile
from pathlib import Path
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).parents[1]/'base'))
from normal_fiscal import *
from fiscal import build_unsigned,unsigned_schema_issues,parse_xml,NS as NAMESPACES
from note_validation import validate_note

def specimen(s):
    if s['kind']=='element':
        if 'content' in s:return specimen(s['content'])
        if 'fixed' in s:return s['fixed']
        if s.get('enum'):return next((v['value'] for v in s['enum'] if v['value']=='AL'),s['enum'][0]['value'])
        return '0'
    out={};children=s.get('children',[])
    if s['kind']=='choice':children=children[:1]
    for c in children:
        if c.get('optional'):continue
        if c['kind']=='element':out[c['name']]=specimen(c)
        else:out.update(specimen(c))
    return out

class NormalTests(unittest.TestCase):
    def setUp(self):
        self.co=dict(CNPJCPF='11222333000181',xNome='EMPRESA SINTETICA NORMAL',IE='240000001',xLgr='RUA DE TESTE',nro='1',xBairro='CENTRO',cMun='2700300',xMun='ARAPIRACA',UF='AL',CEP='57300000',CRT='3',rtc_policy='sem_informacao_revisada',rtc_reason='Cenario sintetico de teste estrutural revisado')
        self.rec=dict(self.co,CNPJCPF='52998224725',xNome='DESTINATARIO TESTE',indIEDest='9')
        self.rule=dict(reviewed='1',CFOP='5102',icms_code='00',icms_rate='18',pis_code='01',pis_rate='1.65',cofins_code='01',cofins_rate='7.6')
        self.item=dict(product=dict(code='001',name='PRODUTO SINTETICO',unit='UN',NCM='03061710'),quantity='1',price='1000',discount='0',rule=self.rule)
        self.n=dict(number='1',series='1',cnf='12345678',issued_at='2026-11-10T11:00:00-03:00',items=[self.item],final='1',nature='VENDA DE MERCADORIA',environment='2',operation='1',destination='1',payment='01')
    def groups(self):
        self.item['normal_groups']=normal_groups(self.item,self.rule);return self.item['normal_groups']
    def xml(self):
        xml,key,totals=build_unsigned(self.co,self.rec,self.n)
        self.assertEqual(unsigned_schema_issues(xml),[])
        return parse_xml(xml),totals
    def test_00_calculation_rounding_and_xml_crt3(self):
        root,t=self.xml();self.assertEqual(t['icms'],Decimal('180'));self.assertEqual(t['pis'],Decimal('16.50'));self.assertEqual(t['cofins'],Decimal('76'))
        self.assertEqual(root.findtext('n:infNFe/n:emit/n:CRT',namespaces={'n':N}),'3')
        self.assertIsNotNone(root.find('.//n:ICMS00',{'n':N}))
    def test_20_reduced_base(self):
        g=self.groups();g['ICMS']={'ICMS20':dict(orig='0',CST='20',modBC='3',pRedBC='50',pICMS='18')}
        _,t=self.xml();self.assertEqual(t['icms_base'],Decimal('500'));self.assertEqual(t['icms'],Decimal('90'))
    def test_41_non_taxed_and_zero_pis_cofins(self):
        self.item['normal_groups']=default_groups('41',pis_code='08',cofins_code='08');_,t=self.xml();self.assertEqual(t['icms'],0);self.assertEqual(t['pis'],0)
    def test_51_deferred(self):
        self.groups()['ICMS']={'ICMS51':dict(orig='0',CST='51',modBC='3',pRedBC='0',pICMS='18',pDif='50')}
        root,t=self.xml();self.assertEqual(t['icms'],Decimal('90'));self.assertEqual(root.findtext('.//n:vICMSDif',namespaces={'n':N}),'90.00')
    def test_10_st_and_fcp_total(self):
        self.groups()['ICMS']={'ICMS10':dict(orig='0',CST='10',modBC='3',pICMS='18',modBCST='4',pMVAST='40',vBCST='1400',pICMSST='18',vBCFCPST='1400',pFCPST='2')}
        _,t=self.xml();self.assertEqual(t['st'],Decimal('72'));self.assertEqual(t['fcpst'],Decimal('28'));self.assertEqual(t['net'],Decimal('1100'))
    def test_blank_st_deduction_uses_own_icms(self):
        self.item['normal_st_deduction']='';self.test_10_st_and_fcp_total()
    def test_ipi_normal_and_optional_inclusion_in_icms_base(self):
        self.groups()['IPI']=dict(cEnq='999',IPITrib=dict(CST='50',pIPI='10'))
        self.rule['icms_include_ipi']='1';_,t=self.xml();self.assertEqual(t['ipi'],Decimal('100'));self.assertEqual(t['icms_base'],Decimal('1100'));self.assertEqual(t['net'],Decimal('1100'))
    def test_pis_cofins_quantity_basis(self):
        g=self.groups();g['PIS']={'PISQtde':dict(CST='03',qBCProd='5',vAliqProd='2.1')};g['COFINS']={'COFINSQtde':dict(CST='03',qBCProd='5',vAliqProd='3')}
        _,t=self.xml();self.assertEqual(t['pis'],Decimal('10.50'));self.assertEqual(t['cofins'],Decimal('15'))
    def test_explicit_bases_are_preserved(self):
        self.item['normal_auto_base']='0';g=self.groups()
        g['ICMS']['ICMS00'].update(vBC='1000',pICMS='4');g['PIS']['PISAliq'].update(vBC='0',pPIS='0');g['COFINS']['COFINSAliq'].update(vBC='0',pCOFINS='0')
        _,t=self.xml();self.assertEqual(t['icms'],Decimal('40'));self.assertEqual(t['pis_base'],Decimal('0'));self.assertEqual(t['cofins_base'],Decimal('0'))
    def test_interstate_difal_with_explicit_rates(self):
        self.rec.update(UF='SP',cMun='3552205');self.rule.update(CFOP='6102',icms_rate='12');self.n['destination']='2'
        self.groups()['ICMSUFDest']=dict(vBCFCPUFDest='1000',pFCPUFDest='2',pICMSUFDest='18',pICMSInter='12.00',pICMSInterPart='100')
        _,t=self.xml();self.assertEqual(t['difal'],Decimal('60'));self.assertEqual(t['fcp_dest'],Decimal('20'))
    def test_wrong_difal_context_is_rejected(self):
        self.groups()['ICMSUFDest']={'vBCUFDest':'1000'}
        with self.assertRaisesRegex(ValueError,'DIFAL'):self.xml()
    def test_manual_arithmetic_mismatch_is_rejected(self):
        self.item.update(normal_auto='0',normal_manual_reviewed='1');g=self.groups();g['ICMS']['ICMS00'].update(vBC='1000',vICMS='1');g['PIS']['PISAliq'].update(vBC='1000',vPIS='16.5');g['COFINS']['COFINSAliq'].update(vBC='1000',vCOFINS='76')
        with self.assertRaisesRegex(ValueError,'diverge'):calculate_normal(self.item,self.rule)
    def test_unknown_fields_are_not_silently_omitted(self):
        self.groups()['ICMS']['ICMS00']['injected']='x'
        with self.assertRaisesRegex(ValueError,'não reconhecido'):calculate_normal(self.item,self.rule)
    def test_contradictory_choices_are_rejected(self):
        self.groups()['PIS']['PISNT']={'CST':'08'}
        with self.assertRaisesRegex(ValueError,'alternativa'):calculate_normal(self.item,self.rule)
    def test_missing_rtc_decision_blocks_emission(self):
        self.co['rtc_policy']='definir'
        with self.assertRaisesRegex(ValueError,'IBS/CBS'):self.xml()
    def test_required_rtc_group_cannot_be_omitted(self):
        self.co['rtc_policy']='informar'
        with self.assertRaisesRegex(ValueError,'IBS/CBS'):self.xml()
    def test_all_normal_icms_schema_branches(self):
        for spec in elements(catalog()['ICMS']['content']):
            if spec['name'].startswith('ICMSSN'):continue
            with self.subTest(group=spec['name']):
                self.setUp();g=self.groups();g['ICMS']={spec['name']:specimen(spec)}
                for name in ('PIS','COFINS'):
                    g[name]={name+'NT':{'CST':'08'}}
                self.item.update(normal_auto='0',normal_manual_reviewed='1');self.xml()
    def test_manual_precision_beyond_schema_is_rejected(self):
        self.groups()['ICMS']['ICMS00']['pICMS']='18.00001'
        with self.assertRaisesRegex(ValueError,'casas decimais'):self.xml()
    def test_automatic_base_does_not_guess_mva_or_pauta(self):
        self.groups()['ICMS']['ICMS00']['modBC']='0'
        with self.assertRaisesRegex(ValueError,'bases manuais'):self.xml()
    def test_retained_fcp_and_effective_icms(self):
        self.groups()['ICMS']={'ICMS60':dict(orig='0',CST='60',vBCFCPSTRet='1000',pFCPSTRet='2',pRedBCEfet='10',pICMSEfet='18')}
        root,t=self.xml();self.assertEqual(t['fcpst_ret'],Decimal('20'));self.assertEqual(root.findtext('.//n:vICMSEfet',namespaces={'n':N}),'162.00')
    def rtc(self):
        self.co['rtc_policy']='informar'
        self.groups()['IBSCBS']=dict(CST='000',cClassTrib='000001',gIBSCBS=dict(vBC='1000',gIBSUF=dict(pIBSUF='0.1'),gIBSMun=dict(pIBSMun='0.05'),gCBS=dict(pCBS='0.9')))
        self.n.update(normal_totals_reviewed='1',normal_vnftot='1010.50',normal_totals={'IBSCBSTot':dict(vBCIBSCBS='1000',gIBS=dict(gIBSUF=dict(vDif='0',vDevTrib='0',vIBSUF='1'),gIBSMun=dict(vDif='0',vDevTrib='0',vIBSMun='0.5'),vIBS='1.5',vCredPres='0',vCredPresCondSus='0'),gCBS=dict(vDif='0',vDevTrib='0',vCBS='9',vCredPres='0',vCredPresCondSus='0'))})
    def test_basic_rtc_values_totals_and_schema(self):
        self.rtc();root,t=self.xml();self.assertEqual(t['ibs'],Decimal('1.5'));self.assertEqual(t['cbs'],Decimal('9'));self.assertEqual(root.findtext('.//n:vNFTot',namespaces={'n':N}),'1010.50')
    def test_rtc_total_conservation(self):
        self.rtc();self.n['normal_totals']['IBSCBSTot']['gIBS']['vIBS']='999'
        with self.assertRaisesRegex(ValueError,'diverge'):self.xml()
    def test_rtc_totals_require_review(self):
        self.rtc();self.n['normal_totals_reviewed']='0'
        with self.assertRaisesRegex(ValueError,'totais'):self.xml()
    def test_returned_ipi_in_return_invoice(self):
        from fiscal import access_key
        from datetime import datetime
        key=access_key(self.co['CNPJCPF'],'1','10','87654321',datetime.fromisoformat(self.n['issued_at']))
        self.n.update(purpose='4',payment='90',references=key,has_reference='1');self.rule['CFOP']='5202'
        self.item.update(normal_ipi_return_enabled='1',normal_ipi_original='100',normal_ipi_return_percent='50')
        root,t=self.xml();self.assertEqual(t['ipi_return'],Decimal('50'));self.assertEqual(t['net'],Decimal('1050'));self.assertEqual(root.findtext('.//n:impostoDevol/n:IPI/n:vIPIDevol',namespaces={'n':N}),'50.00')
    def test_returned_ipi_rejects_wrong_purpose(self):
        self.item.update(normal_ipi_return_enabled='1',normal_ipi_original='100',normal_ipi_return_percent='50')
        with self.assertRaisesRegex(ValueError,'devolução'):self.xml()
    def test_detailed_split_payments(self):
        self.n.update(normal_payment_reviewed='1',normal_payment={'detPag':[dict(indPag='0',tPag='01',vPag='400'),dict(indPag='0',tPag='15',vPag='600')]})
        root,t=self.xml();self.assertEqual(len(root.findall('.//n:detPag',{'n':N})),2)
    def test_detailed_payment_total_mismatch(self):
        self.n.update(normal_payment_reviewed='1',normal_payment={'detPag':[dict(indPag='0',tPag='15',vPag='1')]})
        with self.assertRaisesRegex(ValueError,'pagamentos'):self.xml()
    def test_payment_without_review_is_rejected(self):
        self.n.update(normal_payment={'detPag':[dict(indPag='0',tPag='15',vPag='1000')]})
        with self.assertRaisesRegex(ValueError,'pagamentos'):self.xml()
    def test_crt3_signed_xml_and_simulated_authorization(self):
        import test_fiscal as test_fixture
        from core import Store
        from fiscal import FiscalStore,FiscalService
        test_fixture.FiscalTests.setUpClass()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                store=Store(Path(tmp)/'test.sqlite3');cid=store.save('company',self.co)
                source=store.save('note',self.n,cid);xml,key,_=build_unsigned(self.co,self.rec,self.n)
                cert=test_fixture.FiscalTests.certificate;signed=cert.sign(xml)
                fs=FiscalStore(store);rid=fs.prepare(cid,source,dict(company=self.co,recipient=self.rec,note=self.n),signed,key)
                response=test_fixture.FiscalTests().fixture(key,signed)
                class Transport:
                    def request(self,operation,payload):return response
                self.assertEqual(FiscalService(fs,cert,Transport()).send(cid,rid),'AUTORIZADA')
                self.assertIsNotNone(fs.get(cid,rid)['proc_xml']);store.db.close()
        finally:test_fixture.FiscalTests.tearDownClass()

if __name__=='__main__':unittest.main()
