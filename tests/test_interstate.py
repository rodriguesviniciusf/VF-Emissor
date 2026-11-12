"""Matriz estrutural AL -> 27 UFs, sem transmissão nem dados fiscais reais."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'base')]
import server,interstate as inter,simple_mode
import test_fiscal as fixture
from core import Store
from fiscal import build_unsigned,validate_schema,parse_xml,text,FiscalStore
from fiscal_events import EventStore
from note_validation import validate_note

CITIES={}
for code,name,uf in json.loads((ROOT/'base/assets/municipios.json').read_text())['municipalities']:CITIES.setdefault(uf,(code,name))

class InterstateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixture.FiscalTests.setUpClass();cls.cert=fixture.FiscalTests.certificate
 @classmethod
 def tearDownClass(cls):fixture.FiscalTests.tearDownClass()
 def make(self,uf='SP',crt='3',ie='9',env='2',origin='0'):
  f=fixture.FiscalTests();f.cnpj='11222333000181';f.setUp();co=copy.deepcopy(f.company);rec=copy.deepcopy(f.recipient);n=copy.deepcopy(f.note)
  co.update(CRT=crt,production_enabled=True,rtc_policy='sem_informacao_revisada',rtc_reason='Cenario sintetico estrutural revisado, sem uso fiscal')
  rec.update(UF=uf,cMun=CITIES[uf][0],xMun=CITIES[uf][1],CNPJCPF='12345678000195' if ie=='1' else '52998224725',indIEDest=ie)
  outgoing=uf!='AL';item=n['items'][0];item.update(quantity='1',price='1000',discount='0');item['rule'].update(CFOP='6102' if outgoing else '5102',origin=origin,reviewed='1')
  n.update(nature='VENDA SINTETICA',issued_at='2026-11-12T12:00:00-03:00',environment=env,operation='1',purpose='1',destination='2' if outgoing else '1',final='1' if ie=='9' else '0')
  if crt=='3':
   item['rule'].update(icms_code='00',icms_rate=inter.rate(origin) if outgoing else '18')
   from normal_fiscal import default_groups
   item['normal_groups']=default_groups('00',origin,item['rule']['icms_rate']);item.update(normal_auto='1',normal_auto_base='1')
   if outgoing and ie=='9':item['normal_groups']['ICMSUFDest']=dict(pICMSUFDest='20',pFCPUFDest='2',pICMSInter=inter.rate(origin),pICMSInterPart='100')
  return co,rec,n,item
 def test_all_27_ufs_both_regimes_customer_types_and_environments(self):
  self.assertEqual(set(CITIES),set(inter.UFS))
  for uf in inter.UFS:
   for crt in ('1','3'):
    for ie in ('1','9'):
     for env in ('1','2'):
      with self.subTest(uf=uf,crt=crt,ie=ie,env=env):
       co,rec,n,item=self.make(uf,crt,ie,env);self.assertEqual(validate_note(co,rec,n),[])
       raw,key,totals=build_unsigned(co,rec,n);validate_schema(self.cert.sign(raw));root=parse_xml(raw)
       self.assertEqual(text(root,'n:infNFe/n:ide/n:cUF'),'27');self.assertTrue(key.startswith('27'))
       self.assertEqual(text(root,'n:infNFe/n:dest/n:enderDest/n:UF'),uf)
       self.assertEqual(text(root,'n:infNFe/n:ide/n:idDest'),'1' if uf=='AL' else '2')
       has_difal=bool(root.xpath('//*[local-name()="ICMSUFDest"]'));self.assertEqual(has_difal,uf!='AL' and crt=='3' and ie=='9')
       if has_difal:self.assertEqual(str(totals['difal']),'80.00');self.assertEqual(str(totals['fcp_dest']),'20.00')
 def test_import_origins_four_percent_for_every_destination(self):
  for uf in set(inter.UFS)-{'AL'}:
   for origin in ('1','2','3','8'):
    with self.subTest(uf=uf,origin=origin):
     co,rec,n,item=self.make(uf,origin=origin);self.assertEqual(validate_note(co,rec,n),[]);raw,_,totals=build_unsigned(co,rec,n);self.assertEqual(str(totals['difal']),'160.00')
 def test_national_and_import_exception_origins_have_twelve_percent(self):
  for origin in ('0','4','5','6','7'):self.assertEqual(inter.rate(origin),'12.00')
 def test_missing_difal_clickable_and_direct_build_cannot_bypass(self):
  co,rec,n,item=self.make();item['normal_groups'].pop('ICMSUFDest');issues=validate_note(co,rec,n)
  self.assertTrue(any(i.field=='item.0.normal_groups.ICMSUFDest.pICMSUFDest' for i in issues),issues)
  with self.assertRaisesRegex(ValueError,'694'):build_unsigned(co,rec,n)
 def test_difal_exceptions_do_not_force_tax_group(self):
  co,rec,n,item=self.make()
  for cfop in ('6910','6912','6915','6916','6552','6922','6929'):
   item['rule']['CFOP']=cfop;item['normal_groups'].pop('ICMSUFDest',None);self.assertFalse(any('694' in i['message'] for i in inter.issues(co,rec,n)),cfop)
  for purpose in ('2','3'):
   n['purpose']=purpose;item['rule']['CFOP']='6102';self.assertFalse(any('694' in i['message'] for i in inter.issues(co,rec,n)))
  n.update(purpose='1',operation='0');self.assertFalse(any('694' in i['message'] for i in inter.issues(co,rec,n)))
 def test_exempt_cst_and_special_partilha_do_not_force_difal(self):
  from normal_fiscal import default_groups
  co,rec,n,item=self.make()
  for code in ('40','41'):
   item['normal_groups']=default_groups(code);self.assertFalse(any('694' in i['message'] for i in inter.issues(co,rec,n)))
  item['normal_groups']['ICMS']={'ICMSPart':dict(CST='10',orig='0')};self.assertFalse(any('694' in i['message'] for i in inter.issues(co,rec,n)))
 def test_difal_rejects_wrong_rate_and_partilha(self):
  co,rec,n,item=self.make();d=item['normal_groups']['ICMSUFDest'];d.update(pICMSInter='7.00',pICMSInterPart='60')
  found=inter.issues(co,rec,n);self.assertTrue(any('698' in i['message'] for i in found));self.assertTrue(any('699' in i['message'] for i in found))
 def test_own_icms_limit_preserves_lower_rates_and_returns(self):
  co,rec,n,item=self.make(ie='1');icms=item['normal_groups']['ICMS']['ICMS00'];icms['pICMS']='18';self.assertTrue(any('693' in i['message'] for i in inter.issues(co,rec,n)))
  icms['pICMS']='7';self.assertFalse(inter.issues(co,rec,n));n['purpose']='4';icms['pICMS']='18';self.assertFalse(inter.issues(co,rec,n))
 def test_ie_exempt_current_nt_list_includes_new_states_and_al(self):
  self.assertIn('DF',inter.NO_EXEMPT_IE);self.assertIn('RS',inter.NO_EXEMPT_IE);self.assertNotIn('PA',inter.NO_EXEMPT_IE)
  for uf in inter.UFS:
   co,rec,n,item=self.make(uf,ie='2');found=inter.issues(co,rec,n);self.assertEqual(any('805' in i['message'] for i in found),uf in inter.NO_EXEMPT_IE,uf)
 def test_ie_exempt_exceptions_for_st_retained_and_exempt_cst(self):
  co,rec,n,item=self.make('SP',ie='2');item['normal_groups']['ICMS']={'ICMS60':dict(orig='0',CST='60',vICMSSTRet='10')};self.assertFalse(inter.issues(co,rec,n))
  item['normal_groups']['ICMS']={'ICMS40':dict(orig='0',CST='40')};self.assertFalse(inter.issues(co,rec,n))
 def test_manual_difal_and_fcp_arithmetic_is_checked(self):
  co,rec,n,item=self.make();from normal_fiscal import normalized
  item['normal_groups']=normalized(item,item['rule'])[0];item.update(normal_auto='0',normal_manual_reviewed='1');d=item['normal_groups']['ICMSUFDest'];d.update(vICMSUFDest='1',vFCPUFDest='1')
  found=inter.issues(co,rec,n);self.assertTrue(any(i['field'].endswith('vICMSUFDest') for i in found));self.assertTrue(any('793' in i['message'] for i in found))
 def test_wrong_uf_municipality_cfop_and_destination_still_block(self):
  co,rec,n,item=self.make('DF');rec['cMun']='2700300';n['destination']='1';item['rule']['CFOP']='5102';found=validate_note(co,rec,n)
  self.assertTrue(any(i.field=='recipient.cMun' for i in found));self.assertTrue(any(i.field=='destination' for i in found))
 def test_assistant_does_not_mutate_catalog_or_note_or_guess_missing_rates(self):
  co,rec,n,item=self.make();item['normal_groups'].pop('ICMSUFDest');before=copy.deepcopy(item)
  with self.assertRaises(ValueError):inter.prepare_item(co,rec,n,item,dict(cfop='6102'))
  r=inter.prepare_item(co,rec,n,item,dict(cfop='6102',rates_reviewed=True,internal='20',fcp='2'))
  self.assertEqual(item,before);self.assertEqual(r['item']['rule']['reviewed'],'0');self.assertEqual(r['item']['normal_groups']['ICMSUFDest']['pICMSInterPart'],'100.00')
 def test_simples_helper_does_not_add_own_icms_or_difal(self):
  co,rec,n,item=self.make(crt='1');r=inter.prepare_item(co,rec,n,item,dict(cfop='6108'))['item'];self.assertNotIn('normal_groups',r);self.assertEqual(r['rule']['icms_code'],'102')
 def test_simple_mode_profiles_for_all_ufs_and_both_regimes(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Store(Path(tmp)/'vf.sqlite3')
   try:
    for crt in ('1','3'):
     co,_,_,_=self.make('AL',crt);cid=db.save('company',co)
     for uf in inter.UFS:
      co,rec,n,item=self.make(uf,crt);rule=copy.deepcopy(item['rule']);rule['normal_groups']=item.get('normal_groups') if crt=='3' else None
      if crt=='1':rule.pop('normal_groups')
      rid=db.save('rule',rule,cid);pid=db.save('product',dict(item['product'],rule_id=rid,price='1000'),cid)
      m=dict(target_uf=uf,recipient_ie='9',final='1',rule_source='product',rule_id='',product_ids=[],allow_price='1',allow_discount='1',transport_mode='9')
      actual=simple_mode.make_item(db,cid,m,pid);self.assertEqual(actual['rule']['CFOP'],'5102' if uf=='AL' else '6102')
      if crt=='3' and uf!='AL':self.assertIn('ICMSUFDest',actual['normal_groups'])
   finally:db.db.close()
 def test_simple_mode_does_not_offer_normal_profile_missing_required_difal(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Store(Path(tmp)/'vf.sqlite3')
   try:
    co,_,_,item=self.make();cid=db.save('company',co);item['normal_groups'].pop('ICMSUFDest');rule=dict(item['rule'],normal_groups=item['normal_groups']);rid=db.save('rule',rule,cid);pid=db.save('product',dict(item['product'],rule_id=rid,price='1000'),cid)
    m=dict(target_uf='SP',recipient_ie='9',final='1',rule_source='product',rule_id='',product_ids=[],allow_price='1',allow_discount='1',transport_mode='9')
    with self.assertRaisesRegex(ValueError,'694'):simple_mode.make_item(db,cid,m,pid)
   finally:db.db.close()

class InterstateSettingsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Store(Path(self.tmp.name)/'vf.sqlite3');server.STORE=self.db;FiscalStore(self.db);EventStore(self.db)
  self.co=dict(CNPJCPF='11222333000181',UF='AL',CRT='1');self.a=self.db.save('company',self.co);self.b=self.db.save('company',dict(self.co,CNPJCPF='12345678000195'))
 def tearDown(self):self.db.db.close();self.tmp.cleanup()
 def fields(self):return dict(uf='SP',internal='18',fcp='0',start='2026-01-01',end='',reference='Referencia ficticia para teste, produto especifico',reviewed=True)
 def test_rates_company_isolation_persistence_and_deletion(self):
  inter.save(self.db,self.a,self.fields());self.assertFalse(inter.load(self.db,self.b)['rates']);self.db.db.close();self.db=Store(Path(self.tmp.name)/'vf.sqlite3');self.assertEqual(inter.load(self.db,self.a)['rates']['SP']['fcp'],'0')
  inter.save(self.db,self.a,dict(uf='SP',remove=True));self.assertFalse(inter.load(self.db,self.a)['rates'])
 def test_rates_require_review_basis_and_dates(self):
  for changes in (dict(reviewed=False),dict(reference=''),dict(fcp=''),dict(start='invalido'),dict(end='2025-01-01'),dict(internal='-1'),dict(uf='EX')):
   with self.subTest(changes=changes),self.assertRaises(ValueError):inter.save(self.db,self.a,dict(self.fields(),**changes))
 def test_helper_cannot_read_recipient_from_another_company(self):
  rid=self.db.save('recipient',dict(UF='SP'),self.b)
  with self.assertRaises(ValueError):server.action(dict(action='interstate_prepare_item',cid=self.a,note=dict(recipient_id=rid),item={},cfop='6102'))
 def test_backup_restore_on_other_installation_preserves_per_company_rates(self):
  import company_recovery
  inter.save(self.db,self.a,self.fields());backup=company_recovery.create(self.db,self.a);raw=Path(backup['path']).read_bytes();target=Store(Path(self.tmp.name)/'outro/vf.sqlite3');FiscalStore(target);EventStore(target)
  try:
   cid=target.save('company',self.co);token=company_recovery.upload_start(target,cid,len(raw));company_recovery.upload_chunk(target,cid,token,0,raw);company_recovery.inspect(target,cid,token);company_recovery.restore(target,cid,token,'RESTAURAR '+self.co['CNPJCPF']);self.assertEqual(inter.load(target,cid)['rates'],inter.load(self.db,self.a)['rates'])
  finally:target.db.close()
