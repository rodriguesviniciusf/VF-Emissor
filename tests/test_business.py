import base64,copy,io,json,os,shutil,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'base')]
import server,core,business_config,catalog_wizard,company_recovery,stock_control,drive_copy,accounting_package,rejection_center,business_runtime
import test_fiscal as fiscal_fixture
import test_events as event_fixture
from fiscal import FiscalStore,build_unsigned
from fiscal_events import EventStore
from web_settings import save_settings,load_settings

class BusinessTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fiscal_fixture.FiscalTests.setUpClass();cls.cert=fiscal_fixture.FiscalTests.certificate
 @classmethod
 def tearDownClass(cls):fiscal_fixture.FiscalTests.tearDownClass()
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=core.Store(self.root/'vf.sqlite3');self.fiscal=FiscalStore(self.store);self.events=EventStore(self.store);server.STORE=self.store;server.PREVIEW=False
  self.f=fiscal_fixture.FiscalTests();self.f.cnpj='11222333000181';self.f.setUp()
  self.cid=self.store.save('company',self.f.company);self.other=self.store.save('company',dict(self.f.company,CNPJCPF='12345678000195',xNome='EMPRESA B PRIVADA'))
  self.product=self.store.save('product',dict(self.f.item['product'],price='100'),self.cid)
  self.rid=self.store.save('recipient',self.f.recipient,self.cid)
 def tearDown(self):
  self.store.db.close();self.tmp.cleanup();business_runtime.PLANS.clear()
 def api(self,action,cid=None,**kwargs):return server.action(dict(action=action,cid=cid or self.cid,**kwargs))
 def authorized(self,number='1',date=None):
  n=copy.deepcopy(self.f.note);n.update(environment='2',number=number,recipient_id=self.rid)
  if date:n['issued_at']=date
  source=self.store.save('note',n,self.cid);xml,key,_=build_unsigned(self.f.company,self.f.recipient,n);signed=self.cert.sign(xml)
  did=self.fiscal.prepare(self.cid,source,dict(company=self.f.company,recipient=self.f.recipient,note=n),signed,key)
  self.fiscal.apply_response(self.cid,did,self.f.fixture(key,signed));return did
 def stock_on(self,cid=None):return business_config.save(self.store,cid or self.cid,dict(stock_enabled='1'))
 def balance(self,cid=None,env='2'):
  return sum(core.number(p['balance']) for p in stock_control.state(self.store,cid or self.cid,env)['products'])
 def upload(self,data,cid=None):
  cid=cid or self.cid;token=company_recovery.upload_start(self.store,cid,len(data));company_recovery.upload_chunk(self.store,cid,token,0,data);return token
 def test_csv_import_preserves_identifiers_and_parties(self):
  raw='codigo;descricao;ncm;unidade;preco\nPX;Café;03061710;UN;12,34\n'.encode()
  preview=catalog_wizard.preview(self.store,self.cid,'product',raw,'produtos.csv');self.assertEqual(preview[0]['data']['NCM'],'03061710');self.assertEqual(preview[0]['data']['price'],'12.34')
  self.assertEqual(catalog_wizard.apply(self.store,self.cid,'product',preview)['created'],1);self.assertEqual(len(self.store.list('product',self.other)),0)
 def test_xlsx_example_roundtrip_has_text_identifiers(self):
  raw=(ROOT/'templates/modelo-cadastros.xlsx').read_bytes()
  for kind in ('product','recipient','supplier'):
   rows=catalog_wizard.preview(self.store,self.cid,kind,raw,'modelo.xlsx');self.assertTrue(rows);self.assertFalse([r['errors'] for r in rows if r['errors']])
  self.assertEqual(catalog_wizard.preview(self.store,self.cid,'product',raw,'m.xlsx')[0]['data']['NCM'],'03061710')
 def test_existing_and_duplicate_rows_are_preserved(self):
  raw=b'code;name;NCM;unit;price\n001;Alterado;03061710;UN;1\nNOVO;Novo;03061710;UN;2\nNOVO;Duplicado;03061710;UN;3\n'
  rows=catalog_wizard.preview(self.store,self.cid,'product',raw,'a.csv');self.assertTrue(rows[0]['duplicate']);self.assertTrue(rows[2]['duplicate']);result=catalog_wizard.apply(self.store,self.cid,'product',rows)
  self.assertEqual((result['created'],result['skipped']),(1,2));self.assertEqual(self.store.get('product',self.cid,self.product)['name'],'PRODUTO DE TESTE')
 def test_partial_import_is_an_explicit_choice(self):
  rows=catalog_wizard.preview(self.store,self.cid,'product',b'code;name;NCM;unit;price\nOK;Bom;03061710;UN;1\nBAD;Erro;123;UN;1\n','x.csv')
  with self.assertRaises(ValueError):catalog_wizard.apply(self.store,self.cid,'product',rows)
  self.assertEqual(len(self.store.list('product',self.cid)),1)
  self.assertEqual(catalog_wizard.apply(self.store,self.cid,'product',rows,True)['created'],1)
 def test_preview_token_is_bound_to_company_and_apply_is_idempotent(self):
  data=base64.b64encode(b'code;name;NCM;unit;price\nNOVO;Novo;03061710;UN;1\n').decode();p=self.api('import_catalog_preview',kind='product',data=data,filename='p.csv')
  with self.assertRaises(ValueError):self.api('import_catalog_apply',cid=self.other,token=p['token'])
  a=self.api('import_catalog_apply',token=p['token']);b=self.api('import_catalog_apply',token=p['token']);self.assertEqual(a,b);self.assertEqual(len(self.store.list('product',self.cid)),2)
 def test_xml_catalog_can_extract_supplier_without_creating_invoice(self):
  d=self.fiscal.get(self.cid,self.authorized());raw=d['proc_xml']
  rows=catalog_wizard.preview(self.store,self.other,'supplier',raw,'nfe.xml');self.assertEqual(rows[0]['data']['CNPJCPF'],'11222333000181');self.assertEqual(rows[0]['errors'],[])
  catalog_wizard.apply(self.store,self.other,'supplier',rows);self.assertEqual(len(self.store.list('supplier',self.other)),1);self.assertFalse(self.store.list('received',self.other))
 def test_features_and_fiscal_preferences_save_for_two_companies(self):
  self.stock_on();self.assertEqual(business_config.load(self.store,self.other)['stock_enabled'],'0')
  save_settings(self.store,self.cid,'defaults',dict(info='Empresa A'));save_settings(self.store,self.other,'defaults',dict(info='Empresa B'))
  self.assertEqual(load_settings(self.store,self.cid)['defaults']['info'],'Empresa A');self.assertEqual(load_settings(self.store,self.other)['defaults']['info'],'Empresa B')
 def test_disabled_stock_does_not_move_and_activation_does_not_backfill(self):
  self.authorized();self.assertEqual(self.balance(),0);self.stock_on();self.assertEqual(self.balance(),0)
 def test_authorization_repeated_queries_do_not_duplicate_stock(self):
  self.stock_on();self.authorized();self.assertEqual(self.balance(),-2);self.assertEqual(self.balance(),-2);self.assertEqual(len(self.store.list('stock_move',self.cid)),1)
 def test_cancellation_reverses_once_and_does_not_touch_another_company(self):
  self.stock_on();did=self.authorized();self.assertEqual(self.balance(),-2)
  with self.store.db:self.store.db.execute("UPDATE fiscal_documents SET status='CANCELADA' WHERE id=?",(did,))
  self.assertEqual(self.balance(),0);self.assertEqual(self.balance(),0);self.assertFalse(self.store.list('stock_move',self.other))
 def test_stock_adjustments_and_environment_separation(self):
  self.stock_on();stock_control.manual(self.store,self.cid,'1',self.product,'10','Saldo inicial conferido');stock_control.manual(self.store,self.cid,'2',self.product,'3','Saldo inicial teste')
  self.assertEqual(self.balance(env='1'),10);self.assertEqual(self.balance(),3)
  with self.assertRaises(ValueError):stock_control.manual(self.store,self.cid,'2',self.product,'1','curto')
 def test_unknown_product_requires_mapping_before_stock_is_moved(self):
  self.stock_on();did=self.authorized();p=self.store.get('product',self.cid,self.product);p['code']='DIFERENTE';self.store.save('product',p,self.cid,self.product)
  st=stock_control.state(self.store,self.cid,'2');self.assertEqual(len(st['pending']),1);self.assertEqual(self.balance(),0)
  stock_control.set_mapping(self.store,self.cid,'SAIDA',did,1,self.product,'12');self.assertEqual(self.balance(),-24)
  with self.assertRaises(ValueError):stock_control.set_mapping(self.store,self.cid,'SAIDA',did,1,self.product,'1')
 def test_entry_xml_can_be_kept_without_enabling_stock(self):
  d=self.fiscal.get(self.cid,self.authorized());p=self.api('entry_preview',data=base64.b64encode(d['proc_xml']).decode());r=self.api('entry_apply',token=p['token'],move_stock=False)
  self.assertTrue((self.root/'xml-importados'/self.cid/(r['id']+'.xml')).is_file());self.assertFalse(self.store.get('received',self.cid,r['id'])['stock_enabled'])
 def test_entry_from_another_company_is_rejected(self):
  d=self.fiscal.get(self.cid,self.authorized())
  with self.assertRaises(ValueError):self.api('entry_preview',cid=self.other,data=base64.b64encode(d['proc_xml']).decode())
 def test_incoming_stock_mapping_conversion_and_apply_retry(self):
  self.f.recipient.update(CNPJCPF='12345678000195');did=self.authorized();raw=self.fiscal.get(self.cid,did)['proc_xml'];self.stock_on(self.other)
  target=self.store.save('product',dict(code='EST001',name='Caixa convertida',NCM='03061710',unit='UN',price='1'),self.other)
  p=self.api('entry_preview',cid=self.other,data=base64.b64encode(raw).decode());r=self.api('entry_apply',cid=self.other,token=p['token'],move_stock=True,mappings=[dict(line=1,product_id=target,factor='12')]);r2=self.api('entry_apply',cid=self.other,token=p['token'],move_stock=True)
  self.assertEqual(r,r2);self.assertEqual(self.balance(self.other),24);self.assertEqual(len(self.store.list('received',self.other)),1)
 def test_stock_mapping_cannot_reference_another_company_product(self):
  self.stock_on(self.other)
  with self.assertRaises(ValueError):stock_control.manual(self.store,self.other,'2',self.product,'1','Ajuste de teste')
 def incoming_for_deletion(self,mapped=True):
  self.f.recipient['CNPJCPF']='12345678000195';did=self.authorized();raw=self.fiscal.get(self.cid,did)['proc_xml'];self.stock_on(self.other)
  target=self.store.save('product',dict(code='EST001',name='Caixa convertida',NCM='03061710',unit='UN',price='1'),self.other)
  p=self.api('entry_preview',cid=self.other,data=base64.b64encode(raw).decode());result=self.api('entry_apply',cid=self.other,token=p['token'],move_stock=True,mappings=[dict(line=1,product_id=target,factor='12')] if mapped else [])
  return did,result['id'],raw,target
 def test_delete_import_reverses_once_preserves_xml_and_fiscal_documents(self):
  did,rid,raw,target=self.incoming_for_deletion();self.assertEqual(self.balance(self.other),24);doc=self.store.get('received',self.other,rid)
  self.assertEqual(self.api('entry_delete',cid=self.other,id=rid,ack=doc['key'])['reversed'],1);self.assertEqual(self.balance(self.other),0)
  self.assertEqual(self.api('entry_delete',cid=self.other,id=rid,ack=doc['key'])['reversed'],0);self.assertEqual(len(self.store.list('stock_move',self.other)),2)
  self.assertEqual((self.root/'xml-importados'/self.other/(rid+'.xml')).read_bytes(),raw);self.assertEqual(self.fiscal.get(self.cid,did)['status'],'AUTORIZADA');self.assertFalse(server.rows('received',self.other))
  package,_=accounting_package.build(self.store,self.other,'2026-11','2')
  with zipfile.ZipFile(io.BytesIO(package)) as z:self.assertFalse(any(n.endswith('procNFe.xml') for n in z.namelist()))
 def test_delete_import_rejects_wrong_company_ack_and_environment(self):
  _,rid,_,_=self.incoming_for_deletion();key=self.store.get('received',self.other,rid)['key']
  for kwargs in (dict(cid=self.cid,ack=key),dict(cid=self.other,ack='ERRADO')):
   with self.assertRaises(ValueError):self.api('entry_delete',id=rid,**kwargs)
  co=self.store.get('company','',self.other);co['environment']='1';self.store.save('company',co,'',self.other)
  with self.assertRaises(ValueError):self.api('entry_delete',cid=self.other,id=rid,ack=key)
  self.assertFalse(self.store.get('received',self.other,rid).get('_archived'))
 def test_delete_pending_import_removes_stock_pending_without_inventing_movement(self):
  _,rid,_,target=self.incoming_for_deletion(False);self.assertTrue(stock_control.state(self.store,self.other,'2')['pending']);key=self.store.get('received',self.other,rid)['key']
  self.api('entry_delete',cid=self.other,id=rid,ack=key);self.assertFalse(stock_control.state(self.store,self.other,'2')['pending']);self.assertFalse(self.store.list('stock_move',self.other))
  with self.assertRaises(ValueError):stock_control.set_mapping(self.store,self.other,'ENTRADA',rid,1,target,'1')
 def test_delete_cancelled_import_does_not_reverse_twice_even_with_stock_off(self):
  _,rid,_,_=self.incoming_for_deletion();self.assertEqual(self.balance(self.other),24);doc=self.store.get('received',self.other,rid);doc['cancelled']=True;self.store.save('received',doc,self.other,rid);self.assertEqual(self.balance(self.other),0)
  business_config.save(self.store,self.other,dict(stock_enabled='0'));self.api('entry_delete',cid=self.other,id=rid,ack=doc['key']);self.assertEqual(self.balance(self.other),0);self.assertEqual(len(self.store.list('stock_move',self.other)),2)
 def test_reimport_after_delete_can_move_stock_again_without_duplicate_old_movement(self):
  _,rid,raw,target=self.incoming_for_deletion();self.assertEqual(self.balance(self.other),24);key=self.store.get('received',self.other,rid)['key'];self.api('entry_delete',cid=self.other,id=rid,ack=key)
  plan=self.api('entry_preview',cid=self.other,data=base64.b64encode(raw).decode());result=self.api('entry_apply',cid=self.other,token=plan['token'],move_stock=True,mappings=[dict(line=1,product_id=target,factor='12')])
  self.assertNotEqual(result['id'],rid);self.assertEqual(self.balance(self.other),24);self.assertEqual(len(server.rows('received',self.other)),1)
 def test_delete_import_transaction_rolls_back_reversal_if_archive_fails(self):
  _,rid,_,_=self.incoming_for_deletion();self.assertEqual(self.balance(self.other),24);doc=self.store.get('received',self.other,rid)
  self.store.db.execute("CREATE TEMP TRIGGER fail_archive BEFORE UPDATE ON records WHEN NEW.kind='received' BEGIN SELECT RAISE(ABORT,'falha simulada'); END")
  with self.assertRaises(ValueError):self.api('entry_delete',cid=self.other,id=rid,ack=doc['key'])
  self.assertEqual(self.balance(self.other),24);self.assertFalse(self.store.get('received',self.other,rid).get('_archived'));self.assertEqual(len(self.store.list('stock_move',self.other)),1)
 def test_natures_backup_to_new_company_id_keeps_deletions(self):
  import nature_catalog
  removed=nature_catalog.listing(self.store,self.cid)[0];nature_catalog.remove(self.store,self.cid,removed['id']);backup=company_recovery.create(self.store,self.cid)
  target=core.Store(self.root/'new-install/vf.sqlite3');FiscalStore(target);EventStore(target)
  try:
   cid=target.save('company',self.f.company);raw=Path(backup['path']).read_bytes();token=company_recovery.upload_start(target,cid,len(raw));company_recovery.upload_chunk(target,cid,token,0,raw);company_recovery.inspect(target,cid,token);company_recovery.restore(target,cid,token,'RESTAURAR 11222333000181')
   self.assertNotIn(removed['name'],nature_catalog.nature_choices(target,cid))
  finally:target.db.close()
 def test_backup_is_filtered_and_manifest_verified(self):
  r=company_recovery.create(self.store,self.cid);raw=Path(r['path']).read_bytes();token=self.upload(raw);p=company_recovery.inspect(self.store,self.cid,token)
  self.assertEqual(p['cnpj'],'11222333000181');self.assertEqual(p['counts']['company'],1)
  with zipfile.ZipFile(io.BytesIO(raw)) as z:self.assertNotIn(b'EMPRESA B PRIVADA',z.read('dados/vf.sqlite3'))
 def test_restore_replaces_only_active_company_and_keeps_previous_backup(self):
  did=self.authorized();before=company_recovery.create(self.store,self.cid);token=self.upload(Path(before['path']).read_bytes());company_recovery.inspect(self.store,self.cid,token)
  self.store.save('product',dict(code='DEPOIS',name='Depois',NCM='03061710',unit='UN',price='1'),self.cid)
  oldother=self.store.get('company','',self.other);result=company_recovery.restore(self.store,self.cid,token,'RESTAURAR 11222333000181')
  self.assertTrue(result['ok']);self.assertEqual(len(self.store.list('product',self.cid)),1);self.assertEqual(self.store.get('company','',self.other),oldother);self.assertEqual(self.fiscal.get(self.cid,did)['status'],'AUTORIZADA');self.assertFalse(self.store.get('company','',self.cid)['production_enabled']);self.assertTrue((company_recovery.backup_root(self.store,self.cid)/result['backup_before']).exists())
 def test_restore_rejects_wrong_company_and_wrong_confirmation(self):
  r=company_recovery.create(self.store,self.cid);raw=Path(r['path']).read_bytes()
  with self.assertRaises(ValueError):company_recovery.inspect(self.store,self.other,self.upload(raw,self.other))
  token=self.upload(raw);company_recovery.inspect(self.store,self.cid,token)
  with self.assertRaises(ValueError):company_recovery.restore(self.store,self.cid,token,'RESTAURAR')
  with self.assertRaises(ValueError):company_recovery.upload_chunk(self.store,self.other,token,len(raw),b'')
 def test_tampered_backup_or_zip_slip_is_rejected(self):
  r=company_recovery.create(self.store,self.cid);out=io.BytesIO()
  with zipfile.ZipFile(r['path']) as source,zipfile.ZipFile(out,'w') as target:
   for i in source.infolist():target.writestr(i.filename,source.read(i.filename))
   target.writestr('dados/notas-fiscais/11222333000181/extra.xml',b'alterado')
  with self.assertRaises(ValueError):company_recovery.inspect(self.store,self.cid,self.upload(out.getvalue()))
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:z.writestr('../vf.sqlite3',b'ruim')
  with self.assertRaises(ValueError):company_recovery.inspect(self.store,self.cid,self.upload(out.getvalue()))
 def test_automatic_backup_respects_interval_and_retention(self):
  business_config.save(self.store,self.cid,dict(backup_keep='2'));first=company_recovery.automatic(self.store,self.cid);self.assertTrue(first);self.assertIsNone(company_recovery.automatic(self.store,self.cid))
  manual=company_recovery.create(self.store,self.cid)
  for _ in range(4):company_recovery.create(self.store,self.cid,True)
  files=company_recovery.list_backups(self.store,self.cid);self.assertEqual(len([f for f in files if f['name'].startswith('automatico-')]),2);self.assertTrue(Path(manual['path']).exists())
 def test_monthly_package_contains_xml_csv_and_no_other_company(self):
  self.authorized();raw,counts=accounting_package.build(self.store,self.cid,'2026-11','2');self.assertEqual(counts['emitidas'],1)
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   self.assertIn('relatorio-notas.csv',z.namelist());self.assertIn('relatorio-notas.html',z.namelist());self.assertEqual(len([n for n in z.namelist() if n.startswith('emitidas/')]),1);self.assertNotIn(b'EMPRESA B PRIVADA',z.read('relatorio-notas.html'))
  raw,counts=accounting_package.build(self.store,self.cid,'2026-11','1');self.assertEqual(counts['emitidas'],0)
 def test_monthly_package_includes_registered_cancellation_from_later_month(self):
  self.did=self.authorized(date='2026-10-04T09:00:00-03:00');rid=self.events.prepare(self.cid,self.did,'110111','Cancelamento ficticio sem circulacao',self.cert,acknowledged=True,allow_late=True)
  self.events.begin(self.cid,rid,self.cert);self.events.apply(self.cid,rid,event_fixture.EventTests.response(self,rid))
  raw,counts=accounting_package.build(self.store,self.cid,'2026-11','2');self.assertEqual(counts['canceladas'],1)
  with zipfile.ZipFile(io.BytesIO(raw)) as z:self.assertTrue(any(n.startswith('eventos/') for n in z.namelist()));self.assertTrue(any(n.startswith('canceladas/') for n in z.namelist()))
 def test_drive_is_additional_copy_and_offline_preserves_original(self):
  did=self.authorized();doc=self.fiscal.get(self.cid,did);original=self.root/'notas-fiscais';local=list(original.rglob('*-procNFe.xml'))[0];before=local.read_bytes();drive=self.root/'MeuDrive';drive.mkdir()
  business_config.save(self.store,self.cid,dict(drive_enabled='1',drive_directory=str(drive)));result=drive_copy.copy_xml(self.store,self.cid);self.assertEqual(result['copied'],1);self.assertEqual(local.read_bytes(),before)
  copied=list(drive.rglob('*-procNFe.xml'));self.assertEqual(len(copied),1);self.assertEqual(copied[0].read_bytes(),before);drive_copy.copy_xml(self.store,self.cid);self.assertEqual(len(list(drive.rglob('*.xml'))),1)
  shutil.rmtree(drive);result=drive_copy.copy_xml(self.store,self.cid);self.assertTrue(result['pending']);self.assertEqual(local.read_bytes(),before)
 def test_rejection_hyperlink_and_correction_keep_same_fiscal_identity(self):
  did=self.authorized();d=self.fiscal.get(self.cid,did)
  with self.store.db:self.store.db.execute("UPDATE fiscal_documents SET status='REJEITADA',proc_xml=NULL,reason='778 — NCM inexistente [nItem: 1]' WHERE id=?",(did,))
  r=rejection_center.entries(self.store,self.cid,'2')[0];self.assertEqual(r['issues'][0]['field'],'item.0.product.NCM');self.assertTrue(r['editable'])
  correction=self.api('correction_draft',id=did);self.assertEqual(correction['note']['number'],str(d['number']));self.assertEqual(correction['note']['cnf'],json.loads(d['snapshot'])['note']['cnf']);self.assertEqual(correction['id'],d['source'])
 def test_uncertain_or_authorized_document_cannot_be_corrected(self):
  did=self.authorized()
  with self.assertRaises(ValueError):self.api('correction_draft',id=did)
  with self.store.db:self.store.db.execute("UPDATE fiscal_documents SET status='INCERTA' WHERE id=?",(did,))
  self.assertFalse(rejection_center.entries(self.store,self.cid,'2')[0]['editable'])
  with self.assertRaises(ValueError):self.api('correction_draft',id=did)
 def test_clone_latest_has_new_number_and_requires_tax_review(self):
  did=self.authorized();r=self.api('clone_latest');self.assertEqual(r['source_number'],'1');self.assertEqual(r['note']['number'],'2');self.assertNotIn('_fiscal_id',r['note']);self.assertEqual(r['note']['items'][0]['rule']['reviewed'],'0');self.assertIn('issued_at',r['note']);self.assertEqual(len(self.store.list('note',self.cid)),1)
 def test_accounting_csv_neutralizes_formula_injection(self):
  self.f.company['xNome']='=HYPERLINK("x")';self.f.recipient['CNPJCPF']='12345678000195';did=self.authorized();d=self.fiscal.get(self.cid,did);p=self.api('entry_preview',cid=self.other,data=base64.b64encode(d['proc_xml']).decode());self.api('entry_apply',cid=self.other,token=p['token']);raw,_=accounting_package.build(self.store,self.other,'2026-11','2')
  with zipfile.ZipFile(io.BytesIO(raw)) as z:self.assertIn("'=HYPERLINK",z.read('relatorio-notas.csv').decode('utf-8-sig'))
 def test_local_status_failure_does_not_make_a_successful_invoice_fail(self):
  did=self.authorized()
  with patch.object(drive_copy,'copy_xml',side_effect=OSError('drive fora do ar')) as external:
   business_runtime.after_change(self.store,self.cid);external.assert_not_called()
  self.assertEqual(self.fiscal.get(self.cid,did)['status'],'AUTORIZADA');self.assertTrue(business_runtime.MAINTENANCE_WAKE.is_set())
 def test_stock_survives_disable_and_cancel_then_reenable(self):
  self.stock_on();did=self.authorized();self.assertEqual(self.balance(),-2);business_config.save(self.store,self.cid,dict(stock_enabled='0'))
  with self.store.db:self.store.db.execute("UPDATE fiscal_documents SET status='CANCELADA' WHERE id=?",(did,))
  self.assertEqual(self.balance(),-2);self.stock_on();self.assertEqual(self.balance(),0)
 def test_restore_in_new_company_identity_does_not_duplicate_stock(self):
  self.stock_on();self.authorized();self.assertEqual(self.balance(),-2);backup=company_recovery.create(self.store,self.cid);raw=Path(backup['path']).read_bytes()
  target=core.Store(self.root/'newpc'/'vf.sqlite3');FiscalStore(target);EventStore(target);cid=target.save('company',self.f.company)
  try:
   token=company_recovery.upload_start(target,cid,len(raw));company_recovery.upload_chunk(target,cid,token,0,raw);company_recovery.inspect(target,cid,token);company_recovery.restore(target,cid,token,'RESTAURAR 11222333000181')
   st=stock_control.state(target,cid,'2');self.assertEqual(sum(core.number(p['balance']) for p in st['products']),-2);self.assertEqual(len(target.list('stock_move',cid)),1)
  finally:target.db.close()
 def test_imported_cancellation_stores_event_and_reverses_incoming_stock(self):
  self.f.recipient['CNPJCPF']='12345678000195';self.did=self.authorized();d=self.fiscal.get(self.cid,self.did);self.stock_on(self.other)
  product=self.store.save('product',dict(code='IN',name='Entrada',NCM='03061710',unit='UN',price='1'),self.other)
  p=self.api('entry_preview',cid=self.other,data=base64.b64encode(d['proc_xml']).decode());self.api('entry_apply',cid=self.other,token=p['token'],move_stock=True,mappings=[dict(line=1,product_id=product,factor='1')]);self.assertEqual(self.balance(self.other),2)
  event=self.events.prepare(self.cid,self.did,'110111','Cancelamento ficticio sem circulacao',self.cert,acknowledged=True,allow_late=True);self.events.begin(self.cid,event,self.cert);self.events.apply(self.cid,event,event_fixture.EventTests.response(self,event));raw=self.events.get(self.cid,event)['proc_xml']
  p=self.api('entry_preview',cid=self.other,data=base64.b64encode(raw).decode());self.api('entry_apply',cid=self.other,token=p['token']);self.assertEqual(self.balance(self.other),0);self.assertEqual(self.balance(self.other),0)
  package,counts=accounting_package.build(self.store,self.other,'2026-11','2')
  with zipfile.ZipFile(io.BytesIO(package)) as z:self.assertTrue(any(n.startswith('eventos/') for n in z.namelist()))
 def test_backup_restore_failure_rolls_back_files_and_database(self):
  self.authorized();backup=company_recovery.create(self.store,self.cid);raw=Path(backup['path']).read_bytes();token=self.upload(raw);company_recovery.inspect(self.store,self.cid,token)
  marker=self.root/'notas-fiscais'/'11222333000181'/'local.txt';marker.write_text('preservar')
  # Força erro depois de substituir a primeira pasta, sem tocar arquivos do usuário.
  original=shutil.copytree
  with patch.object(company_recovery.shutil,'copytree',side_effect=OSError('falha simulada')):
   with self.assertRaises(OSError):company_recovery.restore(self.store,self.cid,token,'RESTAURAR 11222333000181')
  self.assertEqual(marker.read_text(),'preservar');self.assertEqual(len(self.store.list('product',self.cid)),1)
 def test_preview_old_backup_without_manifest_can_be_restored(self):
  backup=company_recovery.create(self.store,self.cid);out=io.BytesIO()
  with zipfile.ZipFile(backup['path']) as src,zipfile.ZipFile(out,'w') as dst:
   for n in src.namelist():
    if n!='backup-manifest.json':dst.writestr(n,src.read(n))
  token=self.upload(out.getvalue());self.assertTrue(company_recovery.inspect(self.store,self.cid,token)['legacy']);self.assertTrue(company_recovery.restore(self.store,self.cid,token,'RESTAURAR 11222333000181')['ok'])
 def test_supplier_and_product_manual_duplicates_are_scoped(self):
  p=dict(code='001',name='Duplicado',NCM='03061710',unit='UN',price='10')
  with self.assertRaises(ValueError):self.api('save_catalog',kind='product',data=p)
  self.assertTrue(self.api('save_catalog',cid=self.other,kind='product',data=p)['id'])
  party=dict(xNome='Fornecedor',CNPJCPF='52998224725');self.api('save_catalog',kind='supplier',data=party)
  with self.assertRaises(ValueError):self.api('save_catalog',kind='supplier',data=party)
 def test_restore_saved_preview_is_not_an_arbitrary_file_reader(self):
  backup=company_recovery.create(self.store,self.cid);self.assertEqual(self.api('restore_saved_preview',name=backup['name'])['cnpj'],'11222333000181')
  for name in ('../../vf.sqlite3','..\\vf.sqlite3','vf.sqlite3'):
   with self.assertRaises(ValueError):self.api('restore_saved_preview',name=name)
 def test_legacy_settings_migrate_without_duplicate_restore_ids(self):
  self.store.save('settings',dict(defaults=dict(info='Antigo')),self.cid,'preferences');save_settings(self.store,self.cid,'defaults',dict(info='Atual'))
  self.assertEqual(len(self.store.list('settings',self.cid)),1)
  self.store.save('settings',dict(defaults=dict(info='Antigo')),self.cid,'preferences')
  backup=company_recovery.create(self.store,self.cid);token=self.upload(Path(backup['path']).read_bytes());company_recovery.inspect(self.store,self.cid,token);company_recovery.restore(self.store,self.cid,token,'RESTAURAR 11222333000181')
  self.assertEqual(load_settings(self.store,self.cid)['defaults']['info'],'Atual');self.assertEqual(len(self.store.list('settings',self.cid)),1)
 def test_malformed_upload_is_reported_as_validation_error(self):
  token=self.upload(b'nao e um zip')
  with self.assertRaises(ValueError):self.api('restore_preview',token=token)
  with self.assertRaises(ValueError):self.api('import_catalog_preview',kind='product',filename='falso.xlsx',data=base64.b64encode(b'nao e xlsx').decode())
 def test_missing_incoming_xml_is_repaired_without_moving_stock_again(self):
  self.f.recipient['CNPJCPF']='12345678000195';did=self.authorized();raw=self.fiscal.get(self.cid,did)['proc_xml'];self.stock_on(self.other)
  pid=self.store.save('product',dict(code='ENT',name='Entrada',NCM='03061710',unit='UN',price='1'),self.other)
  p=self.api('entry_preview',cid=self.other,data=base64.b64encode(raw).decode());r=self.api('entry_apply',cid=self.other,token=p['token'],move_stock=True,mappings=[dict(line=1,product_id=pid,factor='2')]);self.assertEqual(self.balance(self.other),4)
  path=self.root/'xml-importados'/self.other/(r['id']+'.xml');path.unlink()
  with self.assertRaises(ValueError):accounting_package.build(self.store,self.other,'2026-11','2')
  p=self.api('entry_preview',cid=self.other,data=base64.b64encode(raw).decode());self.assertTrue(p['repair']);r2=self.api('entry_apply',cid=self.other,token=p['token'],move_stock=False)
  self.assertTrue(r2['repaired']);self.assertEqual(r2['id'],r['id']);self.assertEqual(path.read_bytes(),raw);self.assertEqual(self.balance(self.other),4)
 def test_chunk_upload_rejects_duplicate_offset_without_corrupting_file(self):
  data=b'x'*(1500*1024);token=company_recovery.upload_start(self.store,self.cid,len(data));first=data[:768*1024]
  self.assertEqual(company_recovery.upload_chunk(self.store,self.cid,token,0,first),len(first))
  with self.assertRaises(ValueError):company_recovery.upload_chunk(self.store,self.cid,token,0,first)
  company_recovery.upload_chunk(self.store,self.cid,token,len(first),data[len(first):]);folder,_=company_recovery.upload_folder(self.store,self.cid,token);self.assertEqual((folder/'upload.zip').read_bytes(),data)
 def test_clone_preserves_detailed_payments_but_clears_approvals(self):
  from vf_workflow import duplicate
  n=copy.deepcopy(self.f.note);n.update(normal_payment=dict(detPag=[dict(tPag='01',vPag='190')]),normal_payment_reviewed='1',normal_totals=dict(IBSCBSTot=dict(vBCIBSCBS='190')),normal_totals_reviewed='1',normal_vnftot='190');n['items'][0]['normal_manual_reviewed']='1'
  cloned=duplicate(self.store,self.cid,n);self.assertEqual(cloned['normal_payment'],n['normal_payment']);self.assertEqual(cloned['normal_totals'],n['normal_totals']);self.assertEqual(cloned['normal_payment_reviewed'],'0');self.assertEqual(cloned['normal_totals_reviewed'],'0');self.assertEqual(cloned['items'][0]['normal_manual_reviewed'],'0');self.assertEqual(n['normal_payment_reviewed'],'1')
 def test_xml_of_third_party_entry_reverses_inventory_direction(self):
  self.f.recipient['CNPJCPF']='12345678000195';did=self.authorized()
  # XML externo sintético de entrada: assina novamente após mudar tpNF/CFOP.
  from fiscal import parse_xml,serialize,NS,DS
  root=parse_xml(self.fiscal.get(self.cid,did)['proc_xml']);nfe=root.find('n:NFe',{'n':NS});nfe.remove(nfe.find('{'+DS+'}Signature'));nfe.find('n:infNFe/n:ide/n:tpNF',{'n':NS}).text='0';nfe.find('n:infNFe/n:det/n:prod/n:CFOP',{'n':NS}).text='1102'
  signed=parse_xml(self.cert.sign(serialize(nfe)));root.replace(nfe,signed);digest=signed.findtext('ds:Signature/ds:SignedInfo/ds:Reference/ds:DigestValue',namespaces={'ds':DS});root.find('n:protNFe/n:infProt/n:digVal',{'n':NS}).text=digest;raw=serialize(root);self.stock_on(self.other)
  pid=self.store.save('product',dict(code='P',name='Operação inversa',NCM='03061710',unit='UN',price='1'),self.other)
  p=self.api('entry_preview',cid=self.other,data=base64.b64encode(raw).decode());self.assertEqual(p['stock_sign'],-1);self.api('entry_apply',cid=self.other,token=p['token'],move_stock=True,mappings=[dict(line=1,product_id=pid,factor='1')]);self.assertEqual(self.balance(self.other),-2)

if __name__=='__main__':unittest.main()
