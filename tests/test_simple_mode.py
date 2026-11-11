"""Contratos fiscais, isolamento e recuperação do Modo Simples. Sem transmissão real."""
import copy,io,json,sys,tempfile,unittest,uuid,zipfile,sqlite3
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'base'))
import server,simple_mode as simple,editor_recovery
from core import Store,calculate
from fiscal import FiscalStore,build_unsigned,unsigned_schema_issues
from fiscal_events import EventStore
from company_backup import backup_company

class SimpleModeTests(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'vf.sqlite3';server.STORE=self.db=Store(self.path);FiscalStore(self.db);EventStore(self.db)
    self.co=dict(CNPJCPF='11222333000181',xNome='EMPRESA FICTICIA',IE='240000001',xLgr='RUA TESTE',nro='1',xBairro='CENTRO',cMun='2700300',xMun='ARAPIRACA',UF='AL',CEP='57300000',CRT='1',environment='2',series='1',next_number='1')
    self.cid=server.save_catalog(dict(kind='company',data=self.co))['id'];self.other=server.save_catalog(dict(kind='company',data=dict(self.co,CNPJCPF='12345678000195')))['id']
    self.rec=dict(self.co,CNPJCPF='52998224725',xNome='CLIENTE FICTICIO',indIEDest='9');self.rid=server.save_catalog(dict(kind='recipient',cid=self.cid,data=self.rec))['id']
    self.rule=dict(name='Perfil revisado',CFOP='5102',origin='0',icms_code='102',pis_code='99',pis_rate='0',cofins_code='99',cofins_rate='0',reviewed='1',exclude_icms='0',rtc_status='nao_aplicavel_revisado')
    self.ruleid=server.save_catalog(dict(kind='rule',cid=self.cid,data=self.rule))['id'];self.product=dict(code='001',name='PRODUTO FICTICIO',unit='UN',NCM='03061710',price='100',rule_id=self.ruleid)
    self.pid=server.save_catalog(dict(kind='product',cid=self.cid,data=self.product))['id'];self.mid=uuid.uuid4().hex
    self.model=dict(id=self.mid,name='Venda habitual',nature='VENDA DE MERCADORIA',target_uf='AL',recipient_ie='9',final='1',presence='1',payment='17',transport_mode='9',info='',info_fisco='',rule_source='product',rule_id='',allow_price='1',allow_discount='1',allow_payment='1',product_ids=[],state='released')
    self.save_config([self.model])
 def tearDown(self):server.CERTS.clear();self.db.db.close();self.tmp.cleanup()
 def save_config(self,models=None,**kw):
    old=simple.load(self.db,self.cid);data=dict(old,models=models if models is not None else old['models']);data.update(kw)
    return simple.save(self.db,self.cid,dict(version=old['version'],data=data,confirm_release=self.mid))
 def resolve(self,n=None,**kw):return simple.resolve(self.db,self.cid,dict(model_id=self.mid,note=n,**kw))
 def note(self):return self.resolve(recipient_id=self.rid,rows=[dict(product_id=self.pid,quantity='2',price='100',discount='10')])
 def test_config_company_scope_and_default_mode(self):
    self.save_config(default_mode='simple',default_model_id=self.mid)
    self.assertEqual(simple.load(self.db,self.other)['models'],[]);self.assertEqual(simple.load(self.db,self.other)['default_mode'],'complete');self.assertEqual(server.get_state(self.cid)['simple_config']['default_mode'],'simple')
 def test_release_requires_explicit_confirmation_and_conflict_protection(self):
    old=simple.load(self.db,self.cid);data=copy.deepcopy(old);data['models'][0]['name']='Alterado'
    with self.assertRaisesRegex(ValueError,'Confirme'):simple.save(self.db,self.cid,dict(version=old['version'],data=data))
    self.save_config(data['models'])
    with self.assertRaisesRegex(ValueError,'outro acesso'):simple.save(self.db,self.cid,dict(version=old['version'],data=old))
 def test_no_model_no_simple_default(self):
    with self.assertRaises(ValueError):self.save_config([],default_mode='simple')
 def test_persistence_and_backup_company_filter(self):
    self.db.save('simple_config',dict(private='OUTRA_EMPRESA_PRIVADA'),self.other,'simple-'+self.other)
    raw=backup_company(self.db,self.cid,self.co['CNPJCPF'])
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        self.assertNotIn(b'OUTRA_EMPRESA_PRIVADA',z.read('dados/vf.sqlite3'));self.assertIn(b'Venda habitual',z.read('dados/vf.sqlite3'))
    self.db.db.close();server.STORE=self.db=Store(self.path);self.assertEqual(simple.load(self.db,self.cid)['models'][0]['id'],self.mid)
 def test_resolve_does_not_allocate_number_create_document_or_stock(self):
    n=self.note();self.assertEqual(n['number'],'');self.assertEqual(self.db.list('note',self.cid),[]);self.assertEqual(FiscalStore(self.db).list(self.cid),[]);self.assertEqual(self.db.list('stock_move',self.cid),[])
    self.assertEqual(server.next_number(self.db,self.cid,'2','1'),'1')
 def test_restore_into_another_installation_remaps_configuration_identity(self):
    import company_recovery
    self.save_config(default_mode='simple',default_model_id=self.mid);raw=backup_company(self.db,self.cid,self.co['CNPJCPF'])
    path=Path(self.tmp.name)/'other-pc';path.mkdir();target=Store(path/'vf.sqlite3');FiscalStore(target);EventStore(target)
    try:
        cid=target.save('company',self.co);self.assertNotEqual(cid,self.cid)
        token=company_recovery.upload_start(target,cid,len(raw));company_recovery.upload_chunk(target,cid,token,0,raw);company_recovery.inspect(target,cid,token);company_recovery.restore(target,cid,token,'RESTAURAR '+self.co['CNPJCPF'])
        cfg=simple.load(target,cid);self.assertEqual(cfg['default_mode'],'simple');self.assertEqual(cfg['models'][0]['id'],self.mid);self.assertEqual(target.list('simple_config',cid)[0][0],'simple-'+cid)
        n=simple.resolve(target,cid,dict(model_id=self.mid,recipient_id=self.rid,rows=[dict(product_id=self.pid)]));self.assertEqual(simple.verify(target,cid,n),[])
    finally:target.db.close()
 def test_sn_same_calculation_and_exact_xml_as_complete(self):
    n=self.note();self.assertEqual(simple.verify(self.db,self.cid,n),[]);self.assertEqual(server.action(dict(action='validate',cid=self.cid,note=n))['issues'],[])
    n.update(number='1',cnf='12345678');full=copy.deepcopy(n);full.pop('simple_mode');full['items'][0].pop('simple_source_stamp');full['items'][0].pop('simple_product_id')
    self.assertEqual(calculate(n['items'][0],n['items'][0]['rule'],'1')['net'],190)
    xml=build_unsigned(self.co,self.rec,n)[0];self.assertEqual(xml,build_unsigned(self.co,self.rec,full)[0]);self.assertEqual(unsigned_schema_issues(xml),[])
 def test_normal_same_calculation_and_xml_as_complete(self):
    self.co.update(CRT='3',rtc_policy='sem_informacao_revisada',rtc_reason='Cenario ficticio revisado para teste');server.save_catalog(dict(kind='company',id=self.cid,data=self.co))
    self.rule.update(icms_code='00',icms_rate='18',pis_code='01',pis_rate='1.65',cofins_code='01',cofins_rate='7.6');server.save_catalog(dict(kind='rule',cid=self.cid,id=self.ruleid,data=self.rule));self.save_config()
    n=self.note();self.assertEqual(simple.verify(self.db,self.cid,n),[]);self.assertEqual(server.action(dict(action='validate',cid=self.cid,note=n))['issues'],[])
    n.update(number='1',cnf='12345678');full=copy.deepcopy(n);full.pop('simple_mode');self.assertEqual(build_unsigned(self.co,self.rec,n)[0],build_unsigned(self.co,self.rec,full)[0]);self.assertEqual(unsigned_schema_issues(build_unsigned(self.co,self.rec,n)[0]),[])
 def test_client_uf_and_ie_are_enforced(self):
    for changes in [dict(UF='PE'),dict(indIEDest='1')]:
        rid=self.db.save('recipient',dict(self.rec,**changes),self.cid)
        with self.assertRaisesRegex(ValueError,'incompatível'):self.resolve(recipient_id=rid)
 def test_company_regime_change_requires_model_review(self):
    n=self.note();co=self.db.get('company','',self.cid);co['CRT']='3';self.db.save('company',co,'',self.cid)
    self.assertTrue(simple.public_state(self.db,self.cid)['models'][0]['needs_review']);self.assertTrue(simple.verify(self.db,self.cid,n))
 def test_product_rule_changes_do_not_silently_rewrite_note(self):
    n=self.note();before=copy.deepcopy(n);rule=self.db.get('rule',self.cid,self.ruleid);rule['pis_rate']='1';self.db.save('rule',rule,self.cid,self.ruleid)
    self.assertTrue(simple.verify(self.db,self.cid,n));self.assertEqual(n,before)
    with self.assertRaises(ValueError):self.resolve(n)
    revised=self.resolve(n,revalidate=True);self.assertEqual(simple.verify(self.db,self.cid,revised),[]);self.assertNotEqual(revised['items'][0]['simple_source_stamp'],n['items'][0]['simple_source_stamp'])
 def test_model_version_change_requires_explicit_revalidation(self):
    n=self.note();self.model['info']='Novo texto';self.save_config([self.model]);self.assertTrue(simple.verify(self.db,self.cid,n))
    with self.assertRaises(ValueError):self.resolve(n)
    revised=self.resolve(n,revalidate=True);self.assertGreater(revised['simple_mode']['model_version'],n['simple_mode']['model_version'])
 def test_recipient_change_requires_revalidation(self):
    n=self.note();self.db.save('recipient',dict(self.rec,xNome='NOME ALTERADO'),self.cid,self.rid);self.assertTrue(simple.verify(self.db,self.cid,n));self.assertEqual(simple.verify(self.db,self.cid,self.resolve(n,revalidate=True)),[])
 def test_header_or_tax_tampering_is_blocked(self):
    for change in ['operation','tax','manual','extra_group']:
        n=self.note()
        if change=='operation':n['operation']='0'
        elif change=='tax':n['items'][0]['rule']['icms_code']='900'
        elif change=='manual':n['items'][0]['auto_calc']='0'
        else:n['normal_vnftot']='1'
        self.assertTrue(simple.verify(self.db,self.cid,n),change)
 def test_locked_prices_discounts_and_payments(self):
    self.model.update(allow_price='0',allow_discount='0',allow_payment='0');self.save_config([self.model])
    for row in [dict(price='80'),dict(discount='1'),dict(quantity='0'),dict(quantity='NaN'),dict(freight='10')]:
        with self.subTest(row=row),self.assertRaises(ValueError):self.resolve(rows=[dict(product_id=self.pid,**row)])
    n=self.resolve(rows=[dict(product_id=self.pid)],recipient_id=self.rid);n['payment']='01';self.assertTrue(simple.verify(self.db,self.cid,n))
 def test_allowed_product_subset(self):
    second=self.db.save('product',dict(self.product,code='002'),self.cid);self.model['product_ids']=[self.pid];self.save_config([self.model])
    with self.assertRaisesRegex(ValueError,'não liberado'):self.resolve(rows=[dict(product_id=second)])
 def test_invalid_profile_context_and_foreign_records(self):
    self.rule['CFOP']='6102';self.db.save('rule',self.rule,self.cid,self.ruleid)
    with self.assertRaisesRegex(ValueError,'produto'):self.save_config()
    foreign=self.db.save('rule',self.rule,self.other);self.model.update(rule_source='fixed',rule_id=foreign)
    with self.assertRaises(ValueError):self.save_config([self.model])
 def test_unreviewed_or_archived_profile_prevents_release(self):
    for changes in [dict(reviewed='0'),dict(_archived=True)]:
        self.db.save('rule',dict(self.rule,**changes),self.cid,self.ruleid)
        with self.assertRaises(ValueError):self.save_config()
 def test_fixed_st_base_from_another_note_cannot_be_reused(self):
    from normal_fiscal import default_groups
    self.co.update(CRT='3',rtc_policy='sem_informacao_revisada',rtc_reason='Cenario ficticio revisado para teste');server.save_catalog(dict(kind='company',id=self.cid,data=self.co))
    rule=dict(self.rule,icms_code='10',normal_groups=default_groups('10','0','18'))
    rule['normal_groups']['ICMS']['ICMS10'].update(modBCST='4',pMVAST='40',pICMSST='18',vBCST='1400')
    self.db.save('rule',rule,self.cid,self.ruleid)
    with self.assertRaisesRegex(ValueError,'ST'):self.save_config()
 def test_review_hash_survives_number_allocation_but_not_edits(self):
    n=self.note();r=server.action(dict(action='simple_review',cid=self.cid,note=n));self.assertTrue(r['review_hash']);self.assertEqual(r['issues'],[])
    n['simple_mode']['step']=3;saved=server.save_note(dict(cid=self.cid,data=n));persisted=server.note(self.cid,saved['id']);self.assertEqual(simple.review_hash(persisted),r['review_hash'])
    persisted['items'][0]['quantity']='3';self.assertNotEqual(simple.review_hash(persisted),r['review_hash'])
 def test_prepare_requires_current_review_before_certificate(self):
    n=self.note();saved=server.save_note(dict(cid=self.cid,data=n));rid=saved['id']
    with self.assertRaisesRegex(ValueError,'resumo'):server.action(dict(action='prepare',cid=self.cid,id=rid))
    with self.assertRaisesRegex(ValueError,'certificado'):server.action(dict(action='prepare',cid=self.cid,id=rid,simple_review_hash=simple.review_hash(server.note(self.cid,rid))))
    self.assertEqual(FiscalStore(self.db).list(self.cid),[])
 def test_retry_same_attempt_reuses_saved_note_and_number(self):
    n=self.note();first=server.save_note(dict(cid=self.cid,data=n));second=server.save_note(dict(cid=self.cid,data=n));self.assertEqual(first['id'],second['id']);self.assertEqual(second['number'],'1');self.assertEqual(len(self.db.list('note',self.cid)),1)
    n['_id']=first['id'];n['number']='';self.assertEqual(server.save_note(dict(cid=self.cid,id=first['id'],data=n))['number'],'1')
 def test_review_prepare_and_send_use_existing_fiscal_pipeline(self):
    import test_fiscal,time
    fixture=test_fiscal.FiscalTests;fixture.setUpClass()
    try:
        cert=server.A1Certificate.from_bytes(fixture.pfx.read_bytes(),'senha-teste',self.co['CNPJCPF']);server.CERTS[self.cid]=(cert,time.time()+3600)
        n=self.note();review=server.action(dict(action='simple_review',cid=self.cid,note=n));saved=server.save_note(dict(cid=self.cid,data=n));args=dict(action='prepare',cid=self.cid,id=saved['id'],simple_review_hash=review['review_hash'])
        prepared=server.action(args);again=server.action(args);self.assertEqual(prepared['fiscal_id'],again['fiscal_id']);self.assertEqual(len(FiscalStore(self.db).list(self.cid)),1)
        with patch.object(server.FiscalService,'send',return_value='AUTORIZADA') as send:
            r=server.action(dict(action='send',cid=self.cid,id=prepared['fiscal_id'],ack_key=prepared['key']))
            self.assertEqual(r['status'],'AUTORIZADA');send.assert_called_once_with(self.cid,prepared['fiscal_id'])
    finally:fixture.tearDownClass()
 def test_finalized_attempt_cannot_create_another_note(self):
    n=self.note();rid=server.save_note(dict(cid=self.cid,data=n))['id']
    with self.db.db:self.db.db.execute("INSERT INTO fiscal_documents(id,company,cnpj,environment,source,series,number,access_key,status,snapshot,signed_xml,created,updated) VALUES('f',?,?,'2',?,1,1,'key','INCERTA','{}',x'00','2026-11-11','2026-11-11')",(self.cid,self.co['CNPJCPF'],rid))
    with self.assertRaisesRegex(ValueError,'transmitido'):server.save_note(dict(cid=self.cid,data=n))
    self.assertEqual(len(self.db.list('note',self.cid)),1)
 def test_recovery_keeps_model_and_step_without_reserving_number(self):
    n=self.note();n['simple_mode']['step']=2;rid=uuid.uuid4().hex;editor_recovery.save(self.db,self.cid,dict(id=rid,version=0,write_id=uuid.uuid4().hex,note=n,source_id='',base_revision=''))
    recovered=editor_recovery.restore(self.db,self.cid,rid)['note'];self.assertEqual(recovered['simple_mode']['model_id'],self.mid);self.assertEqual(recovered['simple_mode']['step'],2);self.assertEqual(self.db.list('note',self.cid),[])
 def test_switch_to_complete_keeps_items_and_uses_regular_validation(self):
    n=self.note();before=copy.deepcopy(n['items']);n['simple_mode']['active']=False;n['presence']='2';self.assertEqual(simple.verify(self.db,self.cid,n),[]);saved=server.save_note(dict(cid=self.cid,data=n));self.assertEqual(server.note(self.cid,saved['id'])['items'],before)
 def test_environment_isolation(self):
    n=self.note();co=self.db.get('company','',self.cid);co['environment']='1';self.db.save('company',co,'',self.cid);self.assertTrue(simple.verify(self.db,self.cid,n))
 def test_missing_client_and_items_return_linkable_issues(self):
    n=self.resolve();self.assertEqual(simple.verify(self.db,self.cid,n)[0]['field'],'recipient_id');n=self.resolve(recipient_id=self.rid);self.assertEqual(simple.verify(self.db,self.cid,n)[0]['field'],'items')

import test_assistance as assistance_tests
class SimpleHttpTests(unittest.TestCase):
 setUpClass=classmethod(assistance_tests.AssistanceHttpTests.setUpClass.__func__)
 tearDownClass=classmethod(assistance_tests.AssistanceHttpTests.tearDownClass.__func__)
 setUp=assistance_tests.AssistanceHttpTests.setUp
 post=assistance_tests.AssistanceHttpTests.post
 def test_configuration_requires_login_and_csrf(self):
    data=dict(action='simple_config_save',cid=self.cid,version=0,data=dict(models=[],default_mode='complete'))
    self.assertEqual(self.post(data)[0],401)
    self.post(dict(cnpj='11222333000181',password=''),'/api/login')
    self.assertEqual(self.post(data,csrf=False)[0],403)
 def test_forged_company_and_stale_tab_cannot_modify_models(self):
    self.post(dict(cnpj='11222333000181',password=''),'/api/login')
    data=dict(action='simple_config_save',cid=self.other,version=0,data=dict(models=[],default_mode='complete'))
    self.assertEqual(self.post(data)[0],409)
    self.post(dict(cnpj='12345678000195',password=''),'/api/login');data['cid']=self.cid
    self.assertEqual(self.post(data,context=self.cid)[0],409)
 def test_static_interface_is_packaged(self):
    self.assertIn(b'function renderSimple',self.http.open(self.url+'/simple-ui.js').read())
    self.assertIn(b'.simple-dialog',self.http.open(self.url+'/simple.css').read())

if __name__=='__main__':unittest.main()
