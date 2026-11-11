"""Contratos de cidade offline, consultas pontuais e cópias de edição sem efeitos fiscais."""
import copy,io,json,sys,tempfile,unittest,uuid,urllib.error
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'base')]
import server,public_lookup as lookup,locality_catalog as cities,editor_recovery as recovery
from core import Store
from fiscal import FiscalStore
from fiscal_events import EventStore
from company_backup import backup_company

class LocalityTests(unittest.TestCase):
 def test_official_table_unique_codes_and_all_states(self):
  rows=cities.catalog();self.assertGreaterEqual(len(rows),5571);self.assertEqual(len(rows),len({r[0] for r in rows}));self.assertEqual(len({r[2] for r in rows}),27)
 def test_city_accepts_accents_and_requires_state(self):
  self.assertEqual(cities.match_city('sao paulo','SP')['cMun'],'3550308');self.assertIsNone(cities.match_city('São Paulo','AL'))
 def test_homonymous_cities_are_distinct(self):self.assertNotEqual(cities.match_city('Bom Jesus','PI')['cMun'],cities.match_city('Bom Jesus','RS')['cMun'])
 def test_new_municipality_and_fernando_de_noronha(self):
  self.assertEqual(cities.match_city('Boa Esperança do Norte','MT')['cMun'],'5101837');self.assertEqual(cities.match_code('2605459')['UF'],'PE')
 def test_wrong_state_code_is_not_used(self):
  self.assertIsNone(cities.match_code('3550308','AL'));self.assertEqual(cities.canonical_address(dict(xMun='ARAPIRACA',UF='AL'),'3550308')['cMun'],'2700300')

class PublicLookupTests(unittest.TestCase):
 def setUp(self):lookup.CACHE.clear();lookup.LAST.clear()
 def cep(self):return dict(cep='01001-000',logradouro='Praça da Sé',bairro='Sé',localidade='São Paulo',uf='SP',ibge='3550308',complemento='lado ímpar')
 def cnpj(self):return dict(cnpj='11222333000181',razao_social='EMPRESA TESTE',nome_fantasia='TESTE',logradouro='DE TESTE',descricao_tipo_de_logradouro='RUA',numero='10',municipio='SAO PAULO',uf='SP',cep='01001000',codigo_municipio=7107,codigo_municipio_ibge=3550308,descricao_situacao_cadastral='ATIVA',cnae_fiscal=4711302,qsa=[dict(nome_socio='NÃO COPIAR')],opcao_pelo_simples=True,inscricao_estadual='NÃO COPIAR')
 def test_invalid_queries_never_reach_provider(self):
  with patch.object(lookup,'read_json') as fn:
   for kind,key in [('cep','123'),('cep','https://example.com'),('cnpj','52998224725'),('cnpj','11111111111111'),('cnpj','11222333000181?x=1'),('url','abc')]:
    with self.assertRaises(ValueError):lookup.lookup(kind,key)
   fn.assert_not_called()
 def test_cep_whitelist_and_no_number_complement_inference(self):
  with patch.object(lookup,'read_json',return_value=self.cep()):r=lookup.lookup('cep','01001-000','a')
  self.assertEqual(r['fields']['cMun'],'3550308');self.assertNotIn('nro',r['fields']);self.assertNotIn('xCpl',r['fields']);self.assertEqual(r['fields']['CEP'],'01001000')
 def test_cnpj_does_not_set_taxes_or_copy_partners(self):
  with patch.object(lookup,'read_json',return_value=self.cnpj()):r=lookup.lookup('cnpj','11.222.333/0001-81','a')
  self.assertEqual(r['fields']['xLgr'],'RUA DE TESTE');self.assertEqual(r['fields']['cMun'],'3550308');self.assertEqual(r['fields']['xMun'],'São Paulo')
  for k in ['CRT','IE','indIEDest','password','qsa','opcao_pelo_simples']:self.assertNotIn(k,r['fields'])
  self.assertNotIn('NÃO COPIAR',json.dumps(r))
 def test_cache_scoped_and_hit_does_not_query(self):
  with patch.object(lookup,'read_json',return_value=self.cep()) as fn,patch.object(lookup.time,'monotonic',side_effect=[10,10.5,12]):
   lookup.lookup('cep','01001000','a');r=lookup.lookup('cep','01001000','a');lookup.lookup('cep','01001000','b')
  self.assertTrue(r['cached']);self.assertEqual(fn.call_count,2)
 def test_rate_limit_avoids_duplicate_external_requests(self):
  with patch.object(lookup,'read_json',return_value=self.cep()) as fn,patch.object(lookup.time,'monotonic',side_effect=[10,10.2]):
   lookup.lookup('cep','01001000','a')
   with self.assertRaisesRegex(ValueError,'Aguarde'):lookup.lookup('cep','01001001','a')
  self.assertEqual(fn.call_count,1)
 def test_missing_cep_and_mismatching_identifiers(self):
  for data in [dict(erro=True),dict(self.cep(),cep='01001001')]:
   with self.assertRaises(ValueError):lookup.mapped('cep','01001000',data)
  with self.assertRaises(ValueError):lookup.mapped('cnpj','11222333000181',dict(self.cnpj(),cnpj='99999999999999'))
 def test_network_failure_allows_manual_entry(self):
  with patch.object(lookup.urllib.request,'build_opener') as build:
   build.return_value.open.side_effect=TimeoutError()
   with self.assertRaisesRegex(ValueError,'manualmente'):lookup.read_json('https://viacep.com.br/ws/01001000/json/')
 def test_http_errors_are_explained(self):
  for code,word in [(429,'limitou'),(404,'não encontrado'),(503,'indisponível')]:
   with patch.object(lookup.urllib.request,'build_opener') as build:
    build.return_value.open.side_effect=urllib.error.HTTPError('https://viacep.com.br/',code,'',{},None)
    with self.assertRaisesRegex(ValueError,word):lookup.read_json('https://viacep.com.br/')
 def test_response_size_limit(self):
  with patch.object(lookup.urllib.request,'build_opener') as build:
   build.return_value.open.return_value=io.BytesIO(b'x'*(lookup.MAX_RESPONSE+1))
   with self.assertRaisesRegex(ValueError,'limite'):lookup.read_json('https://viacep.com.br/')

class EditingRecoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'vf.sqlite3');FiscalStore(self.store);EventStore(self.store);server.STORE=self.store
  self.co=dict(CNPJCPF='11222333000181',xNome='EMPRESA A',CRT='1',UF='AL',series='1',next_number='1',environment='2')
  self.cid=self.store.save('company',self.co);self.other=self.store.save('company',dict(self.co,CNPJCPF='12345678000195',xNome='EMPRESA B'))
  self.n=dict(environment='2',series='1',number='',issued_at='2026-11-11T12:30:00-03:00',info='edição não salva',items=[]);self.rid=uuid.uuid4().hex
 def tearDown(self):self.store.db.close();self.tmp.cleanup()
 def params(self,**values):return dict(id=self.rid,version=0,write_id=uuid.uuid4().hex,note=copy.deepcopy(self.n),source_id='',base_revision='',**values)
 def save(self,p=None,cid=None):return recovery.save(self.store,cid or self.cid,p or self.params())
 def test_autosave_does_not_create_note_or_reserve_number(self):
  self.save();self.assertEqual(self.store.list('note',self.cid),[]);self.assertEqual(self.store.db.execute('SELECT count(*) FROM fiscal_documents').fetchone()[0],0);self.assertEqual(server.next_number(self.store,self.cid,'2','1'),'1')
 def test_survives_database_reopen(self):
  self.save();self.store.db.close();self.store=Store(Path(self.tmp.name)/'vf.sqlite3');server.STORE=self.store;self.assertEqual(recovery.restore(self.store,self.cid,self.rid)['note']['info'],'edição não salva')
 def test_company_and_environment_separation(self):
  self.save();self.assertEqual(recovery.list_copies(self.store,self.other,'2'),[]);self.assertEqual(recovery.list_copies(self.store,self.cid,'1'),[])
  with self.assertRaises(ValueError):recovery.restore(self.store,self.other,self.rid)
  p=self.params();p['note']['environment']='1'
  with self.assertRaises(ValueError):self.save(p)
 def test_conflict_and_idempotent_retry(self):
  p=self.params();self.save(p);self.assertEqual(self.save(p)['version'],1);p2=self.params();p2['version']=1;p2['note']['info']='mais recente';self.save(p2)
  with self.assertRaises(ValueError):self.save(self.params())
  self.assertEqual(recovery.restore(self.store,self.cid,self.rid)['note']['info'],'mais recente')
 def test_pending_item_is_preserved_without_catalog_change(self):
  item=dict(product=dict(code='X',name='Produto incompleto'),rule={'reviewed':'1'},sync_to_catalog='1');self.save(self.params(pending_item=item,item_index=-1,tax_tab='icms'));r=recovery.restore(self.store,self.cid,self.rid)
  self.assertEqual(r['pending_item']['product']['name'],'Produto incompleto');self.assertEqual(r['pending_item']['sync_to_catalog'],'0');self.assertEqual(self.store.list('product',self.cid),[])
 def test_resume_only_when_original_unchanged(self):
  saved=server.save_note(dict(cid=self.cid,data=self.n));source=saved['id'];original=self.store.get('note',self.cid,source);p=self.params();p.update(source_id=source,base_revision=saved['revision']);p['note']['number']=original['number'];self.save(p)
  self.assertTrue(recovery.list_copies(self.store,self.cid,'2')[0]['can_resume']);self.assertEqual(recovery.restore(self.store,self.cid,self.rid)['note']['_id'],source)
  original['info']='alterada';self.store.save('note',original,self.cid,source)
  with self.assertRaisesRegex(ValueError,'original mudou'):recovery.restore(self.store,self.cid,self.rid)
  r=recovery.restore(self.store,self.cid,self.rid,True);self.assertEqual(r['note']['_id'],'');self.assertEqual(r['note']['number'],'');self.assertNotIn('cnf',r['note'])
 def test_state_revision_matches_persisted_note(self):
  r=server.save_note(dict(cid=self.cid,data=self.n));self.assertEqual(server.get_state(self.cid)['documents'][0]['_edit_revision'],r['revision'])
 def test_finalized_original_cannot_be_overwritten(self):
  r=server.save_note(dict(cid=self.cid,data=self.n));source=r['id'];p=self.params();p.update(source_id=source,base_revision=r['revision']);self.save(p)
  self.store.db.execute("INSERT INTO fiscal_documents(id,company,cnpj,environment,source,series,number,access_key,status,snapshot,signed_xml,created,updated) VALUES('f',?,?,'2',?,1,1,'key','AUTORIZADA','{}',x'00','2026-11-11','2026-11-11')",(self.cid,self.co['CNPJCPF'],source));self.store.db.commit()
  with self.assertRaises(ValueError):recovery.restore(self.store,self.cid,self.rid)
  self.assertEqual(recovery.restore(self.store,self.cid,self.rid,True)['note']['_id'],'')
 def test_new_copy_clears_review_approvals(self):
  p=self.params(pending_item=dict(rule={'reviewed':'1'},taxes={'reviewed':'1'},normal_manual_reviewed='1'),item_index=-1);p['note']['items']=[dict(product={},rule={'reviewed':'1'},taxes={'reviewed':'1'})];self.save(p);r=recovery.restore(self.store,self.cid,self.rid,True)
  self.assertEqual(r['note']['items'][0]['rule']['reviewed'],'0');self.assertEqual(r['pending_item']['normal_manual_reviewed'],'0')
 def test_foreign_source_and_invalid_item_index_rejected(self):
  source=self.store.save('note',self.n,self.other);p=self.params();p['source_id']=source
  with self.assertRaises(ValueError):self.save(p)
  with self.assertRaises(ValueError):self.save(self.params(pending_item={},item_index=0))
 def test_size_limit_and_credential_fields(self):
  p=self.params();p['note'].update(password='SENHA',pfx='PFX',_key='CHAVE');self.save(p);r=recovery.restore(self.store,self.cid,self.rid)
  for key in ('password','pfx','_key'):self.assertNotIn(key,r['note'])
  p=self.params();p['id']=uuid.uuid4().hex;p['note']['info']='x'*(recovery.MAX_SIZE+1)
  with self.assertRaises(ValueError):self.save(p)
 def test_versioned_discard_preserves_saved_note(self):
  server.save_note(dict(cid=self.cid,data=self.n));self.save()
  with self.assertRaises(ValueError):recovery.drop(self.store,self.cid,self.rid,2)
  recovery.drop(self.store,self.cid,self.rid,1);self.assertEqual(len(self.store.list('note',self.cid)),1);self.assertEqual(self.store.list(recovery.KIND,self.cid),[])
 def test_backup_filters_other_company_copy(self):
  self.save();self.save(dict(self.params(),id=uuid.uuid4().hex,note=dict(self.n,info='PRIVADO_OUTRA_EMPRESA')),self.other)
  import zipfile
  with zipfile.ZipFile(io.BytesIO(backup_company(self.store,self.cid,self.co['CNPJCPF']))) as z:self.assertNotIn(b'PRIVADO_OUTRA_EMPRESA',z.read('dados/vf.sqlite3'))

class AssistanceHttpTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  import os,socket,subprocess,time
  from urllib.request import urlopen
  cls.tmp=tempfile.TemporaryDirectory();path=Path(cls.tmp.name);db=Store(path/'vf.sqlite3');FiscalStore(db);EventStore(db)
  co=dict(CNPJCPF='11222333000181',xNome='EMPRESA HTTP A',CRT='1',UF='AL',environment='2',series='1',next_number='1')
  cls.cid=db.save('company',co);cls.other=db.save('company',dict(co,CNPJCPF='12345678000195',xNome='EMPRESA HTTP B'));db.db.close()
  with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
  cls.url='http://127.0.0.1:'+str(port)
  cls.proc=subprocess.Popen([sys.executable,str(ROOT/'server.py'),'--no-browser','--data-dir',str(path),'--port',str(port)],cwd=ROOT,env=dict(os.environ),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  for _ in range(100):
   try:
    with urlopen(cls.url+'/health',timeout=.2) as r:
     if r.status==200:return
   except OSError:time.sleep(.05)
  cls.proc.terminate();raise RuntimeError('Servidor HTTP de teste não iniciou.')
 @classmethod
 def tearDownClass(cls):cls.proc.terminate();cls.proc.wait(timeout=5);cls.tmp.cleanup()
 def setUp(self):
  from urllib.request import build_opener,HTTPCookieProcessor
  from http.cookiejar import CookieJar
  self.http=build_opener(HTTPCookieProcessor(CookieJar()));self.http.open(self.url+'/').read();self.csrf=json.loads(self.http.open(self.url+'/api/state').read())['csrf']
 def post(self,data,path='/api/action',csrf=True,context=None):
  from urllib.request import Request
  headers={'Content-Type':'application/json'}
  if csrf:headers['X-VF-CSRF']=self.csrf
  if context:headers['X-VF-Company']=context
  request=Request(self.url+path,json.dumps(data).encode(),headers)
  try:
   with self.http.open(request,timeout=4) as r:return r.status,json.loads(r.read())
  except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
 def test_lookup_available_during_first_registration_but_requires_csrf(self):
  status,r=self.post(dict(action='lookup_public',kind='cep',value='INVALIDO'));self.assertEqual(status,400);self.assertIn('oito',r['error'])
  status,r=self.post(dict(action='lookup_public',kind='cep',value='INVALIDO'),csrf=False);self.assertEqual(status,403)
 def test_editor_requires_login_and_public_catalog_does_not_expose_company(self):
  self.assertEqual(self.post(dict(action='editor_list',cid=self.cid))[0],401)
  data=json.loads(self.http.open(self.url+'/municipios.json').read());self.assertGreaterEqual(len(data['municipalities']),5571)
  self.assertNotIn('EMPRESA HTTP',json.dumps(data))
 def test_company_session_prevents_forged_scope_for_editing_copy(self):
  self.assertEqual(self.post(dict(cnpj='11222333000181',password=''),'/api/login')[0],200)
  rid=uuid.uuid4().hex;n=dict(environment='2',series='1',number='',items=[],info='somente empresa A')
  status,_=self.post(dict(action='editor_save',cid=self.other,id=rid,version=0,write_id=uuid.uuid4().hex,note=n));self.assertEqual(status,409)
  status,_=self.post(dict(action='editor_save',cid=self.cid,id=rid,version=0,write_id=uuid.uuid4().hex,note=n));self.assertEqual(status,200)
  _,data=self.post(dict(action='editor_list',cid=self.cid));self.assertIn(rid,[c['id'] for c in data['copies']])
  self.post({},'/api/logout');self.post(dict(cnpj='12345678000195',password=''),'/api/login')
  self.assertEqual(self.post(dict(action='editor_list',cid=self.cid))[0],409)
  _,data=self.post(dict(action='editor_list',cid=self.other));self.assertNotIn(rid,[c['id'] for c in data['copies']])

 def test_stale_tab_cannot_save_note_after_company_switch(self):
  self.post(dict(cnpj='11222333000181',password=''),'/api/login')
  self.post(dict(cnpj='12345678000195',password=''),'/api/login')
  n=dict(environment='2',series='1',number='',items=[],info='dados da aba antiga')
  status,r=self.post(dict(action='save_note',cid=self.cid,data=n),context=self.cid)
  self.assertEqual(status,409);self.assertIn('outro acesso',r['error'])
  state=json.loads(self.http.open(self.url+'/api/state').read());self.assertEqual(state['cid'],self.other);self.assertEqual(state['documents'],[])
