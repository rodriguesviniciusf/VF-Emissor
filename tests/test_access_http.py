"""Rotas HTTP reais com Auth e assinatura sintéticos; não usa A1 nem transmite NF-e."""
import json,queue,threading,time,unittest
from http.server import HTTPServer
from unittest.mock import patch
import requests
import test_cloud_access as fixture
LICENSE=fixture.LICENSE;CNPJ=fixture.CNPJ
import server
from core import Store
from fiscal import FiscalStore
from fiscal_events import EventStore

class AccessHTTPTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixture.AccessTests();self.fixture.setUp();self.manager=self.fixture.access
  self.old={k:getattr(server,k) for k in ('STORE','ACCESS','ACCESS_STORE','PREVIEW','ALLOW_REMOTE','SESSIONS')}
  self.store=Store(self.fixture.root/'http.sqlite3');FiscalStore(self.store);EventStore(self.store)
  self.cid=self.store.save('company',dict(CNPJCPF=CNPJ,xNome='Empresa preservada',UF='AL',CRT='1',environment='2'))
  self.other=self.store.save('company',dict(CNPJCPF='12345678000195',xNome='Outra empresa isolada',UF='AL',CRT='1',environment='2'))
  server.STORE=self.store;server.ACCESS=self.manager;server.ACCESS_STORE=self.store;server.PREVIEW=False;server.ALLOW_REMOTE=False;server.SESSIONS={}
  self.http=HTTPServer(('127.0.0.1',0),server.Handler);self.http.timeout=3
  self.url='http://127.0.0.1:'+str(self.http.server_port);self.cookie='vf_session='+server.RUN_TOKEN
 def tearDown(self):
  self.http.server_close();self.store.db.close()
  for key,value in self.old.items():setattr(server,key,value)
  self.fixture.tearDown()
 def call(self,path,p=None,csrf=True):
  result=queue.Queue();headers={'Cookie':self.cookie}
  if csrf:headers['X-VF-CSRF']=server.CSRF
  def client():
   try:result.put(requests.request('POST' if p is not None else 'GET',self.url+path,json=p,headers=headers,timeout=5))
   except Exception as exc:result.put(exc)
  thread=threading.Thread(target=client);thread.start();self.http.handle_request();thread.join(6);value=result.get(timeout=1)
  if isinstance(value,Exception):raise value
  if value.headers.get('Set-Cookie'):self.cookie+='; '+value.headers['Set-Cookie'].split(';')[0]
  return value
 def login(self):
  r=self.call('/api/access',dict(action='login',email='teste@example.invalid',password='synthetic-password'))
  self.assertEqual(r.status_code,200,r.text);return r
 def select(self):
  self.login();r=self.call('/api/access',dict(action='select',id=LICENSE));self.assertEqual(r.status_code,200,r.text);return r
 def test_anonymous_and_pending_do_not_see_local_fiscal_data(self):
  r=self.call('/api/state');self.assertFalse(r.json()['authenticated']);self.assertNotIn('products',r.json())
  self.fixture.transport.status='pending';self.login();r=self.call('/api/state');self.assertEqual(r.json()['access']['account']['status'],'pending');self.assertEqual(r.json()['companies'],[])
  r=self.call('/api/action',dict(action='save_catalog',kind='company',data={'CNPJCPF':CNPJ}));self.assertEqual(r.status_code,400)
 def test_login_requires_csrf_and_returns_only_opaque_http_only_session(self):
  self.assertEqual(self.call('/api/access',dict(action='login'),csrf=False).status_code,403)
  r=self.login();self.assertEqual(r.json(),{'ok':True});self.assertIn('HttpOnly',r.headers['Set-Cookie']);self.assertIn('SameSite=Strict',r.headers['Set-Cookie']);self.assertNotIn('private-access-token',r.text)
 def test_existing_company_is_reused_without_resetting_data(self):
  r=self.select();self.assertEqual(r.json()['cid'],self.cid);self.assertFalse(r.json()['created']);self.assertEqual(self.store.get('company','',self.cid)['xNome'],'Empresa preservada')
  r=self.call('/api/state?cid='+self.other);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['cid'],self.cid);self.assertEqual(len(r.json()['companies']),1)
 def test_other_company_and_cnpj_change_are_refused_before_save(self):
  self.select();r=self.call('/api/action',dict(action='search_products',cid=self.other));self.assertEqual(r.status_code,400,r.text)
  r=self.call('/api/action',dict(action='save_catalog',kind='company',id=self.cid,data={'CNPJCPF':'12345678000195'}));self.assertEqual(r.status_code,400)
  self.assertEqual(self.store.get('company','',self.cid)['CNPJCPF'],CNPJ)
 def test_expiry_blocks_prepare_before_certificate_or_fiscal_preparation(self):
  self.select();self.fixture.transport.emit=False
  with patch.object(server,'certificate',side_effect=AssertionError('A1 não deve ser aberto')) as cert:
   r=self.call('/api/action',dict(action='prepare',id='fake-note'));self.assertEqual(r.status_code,400);self.assertIn('bloqueadas',r.text);cert.assert_not_called()
 def test_expiry_keeps_backup_download_available(self):
  self.select();self.fixture.transport.emit=False;self.manager.leases.clear()
  r=self.call('/api/download?kind=backup');self.assertEqual(r.status_code,200,r.text[:100] if not r.content.startswith(b'PK') else '');self.assertTrue(r.content.startswith(b'PK'))
 def test_legacy_login_cannot_bypass_activated_commercial_access(self):
  r=self.call('/api/login',dict(cnpj=CNPJ,password=''));self.assertEqual(r.status_code,400);self.assertIn('e-mail',r.text)
 def test_signout_invalidates_local_account_session(self):
  self.select();r=self.call('/api/logout',{});self.assertEqual(r.status_code,200);r=self.call('/api/state');self.assertFalse(r.json()['authenticated']);self.assertIsNone(r.json()['access']['account'])

if __name__=='__main__':unittest.main()
