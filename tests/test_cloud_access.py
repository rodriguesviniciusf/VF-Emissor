import base64,copy,json,sys,tempfile,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'base')]
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from cloud_access import Access,Offline,normalize_config
import requests,server
from core import Store
from fiscal import FiscalStore
from fiscal_events import EventStore

class Transport:
 def __init__(self,access,private):self.access=access;self.private=private;self.calls=[];self.offline=False;self.denied=False;self.status='approved';self.emit=True;self.until=None;self.companies=[]
 def request(self,method,url,**kw):
  self.calls.append((method,url,kw))
  if self.offline:raise requests.ConnectionError('synthetic')
  if '/token?' in url:return self.response(200,dict(user={'id':USER},access_token='private-access-token',refresh_token='private-refresh-token',expires_in=3600))
  if 'vf_client_state' in url:return self.response(200,dict(id=USER,email='teste@example.invalid',name='Teste',status=self.status,is_admin=False,companies=self.companies))
  if 'vf_request_company' in url:
   self.companies=[dict(id=LICENSE,cnpj=kw['json']['cnpj_value'],status='pending')];return self.response(200,{'id':LICENSE})
  if 'vf-license' in url:
   if self.denied:return self.response(403,{'error':'Computador desativado.'})
   issued=int(time.time());until=self.until if self.until is not None else issued+3600
   p=dict(version=1,sub=USER,installation_id=self.access.installation,license_id=LICENSE,cnpj=CNPJ,read=True,emit=self.emit,
          issued_at=issued,emit_until=until,name='Empresa sintética',valid_until='2026-12-12',status=self.status)
   return self.response(200,self.sign(p))
  return self.response(200,{'ok':True})
 def sign(self,p):
  raw=json.dumps(p).encode();return dict(payload=base64.b64encode(raw).decode(),signature=base64.b64encode(self.private.sign(raw)).decode())
 @staticmethod
 def response(status,data):
  class Response:
   status_code=status
   def json(self):return copy.deepcopy(data)
  return Response()
USER='11111111-1111-4111-8111-111111111111';LICENSE='22222222-2222-4222-8222-222222222222';CNPJ='11222333000181'

class AccessTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.private=Ed25519PrivateKey.generate()
  self.config=dict(url='https://abcdefghijklmnopqrst.supabase.co',publishable_key='sb_publishable_'+'x'*35,
    verification_key=base64.b64encode(self.private.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode())
  self.access=Access(self.root,self.root/'data');self.access.configure(self.config)
  self.transport=Transport(self.access,self.private);self.access.transport=self.transport
  self.session=self.access.login({'email':'teste@example.invalid','password':'segredo-teste'})
  self.session.update(cid='co1',license_id=LICENSE)
 def tearDown(self):self.tmp.cleanup()
 def test_no_password_or_auth_tokens_persisted(self):
  raw=''.join(p.read_text() for p in self.root.rglob('*') if p.is_file())
  for value in ('segredo-teste','private-access-token','private-refresh-token'):self.assertNotIn(value,raw)
 def test_only_public_config_is_accepted(self):
  for url in ('http://localhost:9000','https://evil.example','https://abcdefghijklmnopqrst.supabase.co@evil.example','https://abcdefghijklmnopqrst.supabase.co/redirect'):
   with self.subTest(url=url),self.assertRaises(ValueError):normalize_config(dict(self.config,url=url))
  role=base64.urlsafe_b64encode(b'{"role":"service_role"}').decode().rstrip('=')
  with self.assertRaisesRegex(ValueError,'secreta'):normalize_config(dict(self.config,publishable_key='eyJinvalid.'+role+'.xxxxxxxxxxxxxx'))
 def test_active_signed_license_and_tls_not_bypassed(self):
  data=self.access.require(self.session,CNPJ,True);self.assertTrue(data['can_emit'])
  call=self.transport.calls[-1];self.assertFalse(call[2]['allow_redirects']);self.assertNotIn('verify',call[2]);self.assertEqual(call[2]['timeout'],10)
 def test_signed_data_cannot_be_changed_or_reused_for_other_identity(self):
  self.access.lease(self.session,LICENSE);env=self.access.leases[(USER,LICENSE)];data=json.loads(base64.b64decode(env['payload']))
  bad=dict(env,payload=base64.b64encode(json.dumps(dict(data,emit_until=data['emit_until']+1000)).encode()).decode())
  with self.assertRaises(ValueError):self.access.verify(bad,self.session,LICENSE)
  for key,value in [('sub',str(uuid.uuid4())),('installation_id',str(uuid.uuid4())),('license_id',str(uuid.uuid4()))]:
   with self.subTest(key=key),self.assertRaises(ValueError):self.access.verify(self.transport.sign(dict(data,**{key:value})),self.session,LICENSE)
 def test_wrong_signing_key_and_unbounded_lease_rejected(self):
  env=self.access.lease(self.session,LICENSE);env['emit_until']=env['issued_at']+73*3600
  with self.assertRaises(ValueError):self.access.verify(self.transport.sign(env),self.session,LICENSE)
  self.access.config['verification_key']=base64.b64encode(Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
  with self.assertRaises(ValueError):self.access.lease(self.session,LICENSE,force=True)
 def test_company_mismatch_cannot_open_another_local_company(self):
  with self.assertRaisesRegex(ValueError,'não pertence'):self.access.require(self.session,'12345678000195')
 def test_outage_uses_only_previous_signed_license(self):
  self.access.require(self.session,CNPJ,True);self.transport.offline=True
  self.assertTrue(self.access.require(self.session,CNPJ,True)['offline'])
  self.access.leases.clear()
  with self.assertRaises(Offline):self.access.require(self.session,CNPJ,True)
 def test_definitive_revocation_does_not_fallback_to_cached_license(self):
  self.access.require(self.session,CNPJ,True);self.transport.denied=True
  with self.assertRaisesRegex(ValueError,'desativado'):self.access.require(self.session,CNPJ,True)
  self.assertFalse(self.access.leases)
 def test_expired_and_suspended_can_read_but_cannot_issue(self):
  self.transport.until=int(time.time())
  self.assertTrue(self.access.require(self.session,CNPJ)['read'])
  with self.assertRaisesRegex(ValueError,'bloqueadas'):self.access.require(self.session,CNPJ,True)
  self.transport.until=None;self.transport.emit=False
  with self.assertRaisesRegex(ValueError,'bloqueadas'):self.access.require(self.session,CNPJ,True)
 def test_clock_rollback_and_session_expiry(self):
  self.access.require(self.session,CNPJ,True);self.transport.offline=True
  with patch('cloud_access.time.time',return_value=time.time()-400):
   with self.assertRaises(ValueError):self.access.require(self.session,CNPJ,True)
  self.session['expires']=time.time()-1
  with self.assertRaisesRegex(ValueError,'encerrada'):self.access.token(self.session)
 def test_removing_config_does_not_reenable_legacy_login(self):
  self.access.config_file.unlink()
  with self.assertRaisesRegex(ValueError,'ausente'):Access(self.root,self.root/'data')
 def test_installation_identity_survives_restart(self):self.assertEqual(Access(self.root,self.root/'data').installation,self.access.installation)
 def test_first_company_appears_immediately_after_signup(self):
  session=self.access.signup({'email':'teste@example.invalid','password':'synthetic-password','name':'Pessoa teste','cnpj':CNPJ,'company_name':'Empresa teste'})
  self.assertEqual(self.access.profile(session)['companies'][0]['cnpj'],CNPJ)
 def test_recovery_uses_one_time_code_and_does_not_save_password(self):
  self.transport.request=lambda method,url,**kw:Transport.response(200,{'access_token':'temporary-recovery'} if '/verify' in url else {'ok':True})
  self.assertTrue(self.access.recover({'code':'x'*60,'password':'nova-senha-sintetica'})['ok'])
 def test_guard_checks_license_before_prepare_and_only_inutil_event_is_new_operation(self):
  old=server.STORE;old_access=server.ACCESS;old_access_store=server.ACCESS_STORE
  store=Store(self.root/'guard.sqlite3');FiscalStore(store);EventStore(store)
  cid=store.save('company',{'CNPJCPF':CNPJ,'xNome':'Teste'})
  try:
   server.STORE=store;server.ACCESS=self.access;server.ACCESS_STORE=store;self.session['cid']=cid;self.transport.emit=False
   with self.assertRaisesRegex(ValueError,'bloqueadas'):server.guard_access({'action':'prepare','id':'fake'},self.session)
   server.guard_access({'action':'query','id':'fake'},self.session)
   with self.assertRaisesRegex(ValueError,'mudou'):server.guard_access({'action':'query','cid':'outra'},self.session)
   with self.assertRaisesRegex(ValueError,'outro CNPJ'):server.guard_access({'action':'save_catalog','kind':'company','id':cid,'data':{'CNPJCPF':'12345678000195'}},self.session)
  finally:store.db.close();server.STORE=old;server.ACCESS=old_access;server.ACCESS_STORE=old_access_store

if __name__=='__main__':unittest.main()
