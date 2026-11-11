import base64,copy,hashlib,io,json,os,sqlite3,subprocess,sys,tempfile,time,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'base'))
import server
from core import Store
from fiscal import FiscalStore,A1Certificate
from fiscal_events import EventStore
from certificate_vault import CertificateVault,WindowsProtector
from desktop_storage import data_directory,import_legacy,has_companies
from app_updates import ReleaseUpdater,version_number,repository
from company_backup import backup_company
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class TestProtector:
    """Somente fixture: autenticação por empresa é exercitada sem DPAPI no Linux."""
    def __init__(self):self.key=AESGCM.generate_key(bit_length=256)
    def protect(self,data,entropy):
        nonce=os.urandom(12);return nonce+AESGCM(self.key).encrypt(nonce,data,entropy)
    def unprotect(self,data,entropy):
        try:return AESGCM(self.key).decrypt(data[:12],data[12:],entropy)
        except Exception as e:raise ValueError('Cofre de teste: autenticação inválida') from e

class DesktopDataTests(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.source=self.root/'anterior/dados';self.source.mkdir(parents=True)
    self.store=Store(self.source/'vf.sqlite3');FiscalStore(self.store);EventStore(self.store);server.STORE=self.store
    self.co=dict(CNPJCPF='11222333000181',xNome='EMPRESA UM',CRT='1',UF='AL')
    self.cid=server.save_catalog(dict(kind='company',data=self.co))['id']
    self.cid2=server.save_catalog(dict(kind='company',data=dict(self.co,CNPJCPF='12345678000195',xNome='OUTRA_EMPRESA_PRIVADA_MARCADOR')))['id']
    self.p1=server.save_catalog(dict(kind='product',cid=self.cid,data=dict(name='Café torrado',code='C001',NCM='09012100',unit='UN',price='10')))['id']
    server.save_catalog(dict(kind='product',cid=self.cid2,data=dict(name='PRODUTO_PRIVADO_OUTRO_MARCADOR',code='X1',NCM='09012100',unit='UN',price='50')))
 def tearDown(self):
    server.CERTS.clear();server.VAULT_ERRORS.clear()
    try:server.STORE.db.close()
    except Exception:pass
    self.tmp.cleanup()
 def test_product_search_lists_all_and_filters_accents_code_ncm(self):
    for query in ['', 'cafe','C001','09012100']:
        rows=server.action(dict(action='search_products',cid=self.cid,query=query))['products']
        self.assertEqual([r['_id'] for r in rows],[self.p1])
    self.assertEqual(server.action(dict(action='search_products',cid=self.cid,query='privado'))['products'],[])
 def test_saved_valid_a1_reloads_after_memory_expiry_and_restart(self):
    import test_fiscal
    fixture=test_fiscal.FiscalTests;fixture.setUpClass()
    v=CertificateVault(self.root/'vault',None if sys.platform=='win32' else TestProtector())
    try:
        raw=fixture.pfx.read_bytes()
        with patch.object(server,'vault',return_value=v):
            result=server.action(dict(action='load_certificate',cid=self.cid,data=base64.b64encode(raw).decode(),password='senha-teste',remember=True))
            self.assertTrue(result['saved']);disk=v.path(self.cid).read_bytes();self.assertNotIn(b'senha-teste',disk);self.assertNotIn(raw,disk)
            server.CERTS.clear();self.assertEqual(server.certificate(self.cid).cnpj,self.co['CNPJCPF'])
            server.CERTS[self.cid]=(server.CERTS[self.cid][0],time.time()-1)
            self.assertEqual(server.certificate(self.cid).cnpj,self.co['CNPJCPF'])
            with self.assertRaises(ValueError):server.certificate(self.cid2)
    finally:fixture.tearDownClass()
 def test_archived_product_is_not_returned(self):
    server.action(dict(action='archive',kind='product',cid=self.cid,id=self.p1))
    self.assertEqual(server.action(dict(action='search_products',cid=self.cid))['products'],[])
 def test_catalog_and_settings_survive_process_restart(self):
    server.action(dict(action='save_settings',cid=self.cid,section='defaults',data=dict(info='APENAS EMPRESA UM')))
    self.store.db.close();server.STORE=Store(self.source/'vf.sqlite3')
    self.assertEqual(server.get_state(self.cid)['products'][0]['code'],'C001')
    self.assertEqual(server.get_state(self.cid)['company']['settings']['defaults']['info'],'APENAS EMPRESA UM')
    self.assertEqual(server.get_state(self.cid2)['company']['settings']['defaults']['info'],'')
 def test_windows_data_directory_does_not_depend_on_program_folder(self):
    env={'LOCALAPPDATA':str(self.root/'usuario')}
    a=data_directory(self.root/'versao-1',platform='win32',environ=env);b=data_directory(self.root/'versao-2',platform='win32',environ=env)
    self.assertEqual(a,b);self.assertEqual(a,self.root/'usuario/VFEmissor/Dados')
 def test_legacy_import_preserves_source_and_all_companies_xml(self):
    f=self.source/'notas-fiscais/11222333000181/homologacao/2026-11/emitidas/nota.xml';f.parent.mkdir(parents=True);f.write_bytes(b'<xml>teste</xml>')
    target=self.root/'appdata/Dados';before=hashlib.sha256((self.source/'vf.sqlite3').read_bytes()).digest()
    count=import_legacy(self.source.parent,target)
    self.assertEqual(count,2);self.assertTrue(has_companies(target/'vf.sqlite3'))
    self.assertEqual((target/f.relative_to(self.source)).read_bytes(),f.read_bytes())
    self.assertEqual(hashlib.sha256((self.source/'vf.sqlite3').read_bytes()).digest(),before)
    db=Store(target/'vf.sqlite3')
    try:self.assertEqual(len(db.list('company')),2)
    finally:db.db.close()
 def test_legacy_import_refuses_overwriting_existing_companies(self):
    with self.assertRaisesRegex(ValueError,'já é a pasta atual'):import_legacy(self.source,self.source)
 def test_legacy_target_existing_database_is_not_overwritten(self):
    target=self.root/'existente';target.mkdir();db=Store(target/'vf.sqlite3');db.save('company',dict(CNPJCPF='99999999999999',xNome='PRESERVAR'));db.db.close()
    before=(target/'vf.sqlite3').read_bytes()
    with self.assertRaisesRegex(ValueError,'Já existem'):import_legacy(self.source,target)
    self.assertEqual((target/'vf.sqlite3').read_bytes(),before)
 def test_failed_import_does_not_remove_existing_empty_target(self):
    target=self.root/'destino';target.mkdir();(target/'marcador.txt').write_text('preservar')
    with self.assertRaises(ValueError):import_legacy(self.root/'inexistente',target)
    self.assertEqual((target/'marcador.txt').read_text(),'preservar')
 def test_company_backup_excludes_other_company_and_files(self):
    for cnpj,content in [('11222333000181',b'<xml>proprio</xml>'),('12345678000195',b'<xml>PRIVADO_OUTRO</xml>')]:
        f=self.source/'notas-fiscais'/cnpj/'producao/nota.xml';f.parent.mkdir(parents=True);f.write_bytes(content)
    raw=backup_company(self.store,self.cid,'11222333000181')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist();dbbytes=z.read('dados/vf.sqlite3')
        self.assertFalse(any('12345678000195' in n for n in names))
        self.assertNotIn(b'OUTRA_EMPRESA_PRIVADA_MARCADOR',dbbytes);self.assertNotIn(b'PRODUTO_PRIVADO_OUTRO_MARCADOR',dbbytes)
        f=self.root/'restaurado.sqlite3';f.write_bytes(dbbytes);db=sqlite3.connect(f)
        try:self.assertEqual(db.execute("SELECT count(*) FROM records WHERE kind='company'").fetchone()[0],1)
        finally:db.close()
 def test_backup_before_update_is_consistent_and_preserves_existing_copy(self):
    from desktop_storage import backup_before_update
    path=backup_before_update(self.source,'0.13.0')
    db=sqlite3.connect(path)
    try:self.assertEqual(db.execute("SELECT count(*) FROM records WHERE kind='company'").fetchone()[0],2)
    finally:db.close()
    before=path.read_bytes();backup_before_update(self.source,'0.13.0');self.assertEqual(path.read_bytes(),before)


class CertificateVaultTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.protector=TestProtector();self.v=CertificateVault(self.root,self.protector)
 def tearDown(self):self.tmp.cleanup()
 def test_save_is_encrypted_and_survives_new_vault_instance(self):
    self.v.save('empresa-1','11222333000181',b'PFX-SINTETICO','senha-sintetica')
    disk=self.v.path('empresa-1').read_bytes();self.assertNotIn(b'PFX-SINTETICO',disk);self.assertNotIn(b'senha-sintetica',disk)
    other=CertificateVault(self.root,self.protector);self.assertEqual(other.load('empresa-1','11222333000181'),(b'PFX-SINTETICO','senha-sintetica'))
 def test_other_company_or_document_cannot_decrypt(self):
    self.v.save('empresa-1','11222333000181',b'teste','senha')
    self.v.path('empresa-2').write_bytes(self.v.path('empresa-1').read_bytes())
    for cid,doc in [('empresa-2','11222333000181'),('empresa-1','12345678000195')]:
        with self.assertRaises(ValueError):self.v.load(cid,doc)
 def test_tampering_rejected_and_remove_is_company_scoped(self):
    self.v.save('a','1',b'a','p');self.v.save('b','2',b'b','p')
    data=bytearray(self.v.path('a').read_bytes());data[-1]^=1;self.v.path('a').write_bytes(data)
    with self.assertRaises(ValueError):self.v.load('a','1')
    self.v.remove('a');self.assertTrue(self.v.exists('b'));self.assertFalse(self.v.exists('a'))
 @unittest.skipUnless(sys.platform=='win32','DPAPI nativa disponível no Windows; exercitada no workflow Windows')
 def test_native_windows_dpapi_survives_process_restart(self):
    v=CertificateVault(self.root);v.save('native-test','11222333000181',b'SYNTHETIC-PFX','synthetic-pass')
    code="from certificate_vault import CertificateVault;import sys;v=CertificateVault(sys.argv[1]);assert v.load('native-test','11222333000181')==(b'SYNTHETIC-PFX','synthetic-pass');print('ok')"
    env=dict(os.environ);env['PYTHONPATH']=str(ROOT/'base')
    result=subprocess.run([sys.executable,'-c',"import sys;sys.path.insert(0,sys.argv.pop(1));"+code,str(ROOT/'base'),str(self.root)],capture_output=True,text=True,env=env,check=True)
    self.assertEqual(result.stdout.strip(),'ok')
 @unittest.skipIf(sys.platform=='win32','Aplica-se a plataformas sem DPAPI')
 def test_non_windows_never_saves_plaintext_fallback(self):
    with self.assertRaises(ValueError):CertificateVault(self.root).save('a','1',b'pfx','senha')
    self.assertFalse(any(self.root.iterdir()))

class FakeResponse(io.BytesIO):
 def __init__(self,data,url='https://release-assets.githubusercontent.com/test'):super().__init__(data);self.url=url
 def geturl(self):return self.url

class UpdatesTests(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.u=ReleaseUpdater(self.root,self.root/'Dados','0.12.0');self.u.configure('escritorio/vf-emissor')
    self.body=b'MZ'+b'INSTALADOR-SINTETICO'*10;self.sha=hashlib.sha256(self.body).hexdigest()
 def tearDown(self):self.tmp.cleanup()
 def release(self):
    prefix='https://github.com/escritorio/vf-emissor/releases/download/v0.13.0/'
    return dict(tag_name='v0.13.0',draft=False,prerelease=False,body='Melhorias',assets=[dict(name='VF-Emissor-Setup-0.13.0.exe',browser_download_url=prefix+'VF-Emissor-Setup-0.13.0.exe',size=len(self.body),digest='sha256:'+self.sha),dict(name='update-manifest.json',browser_download_url=prefix+'update-manifest.json')])
 def manifest(self):return dict(format=1,version='0.13.0',asset='VF-Emissor-Setup-0.13.0.exe',size=len(self.body),sha256=self.sha)
 def test_repository_and_versions_reject_paths_commands_and_downgrades(self):
    for value in ['https://evil.example/a','a/../b','owner/repo;cmd','owner/repo?token=secret','owner/repo/extra']:
        with self.assertRaises(ValueError):repository(value)
    self.assertEqual(repository('https://github.com/escritorio/vf-emissor/'),'escritorio/vf-emissor')
    self.assertGreater(version_number('v0.13.0'),version_number('0.12.0'))
 def test_matching_release_and_hash_download_verified(self):
    with patch.object(self.u,'_json',side_effect=[self.release(),self.manifest()]):release=self.u.check()
    with patch.object(self.u,'_open',return_value=FakeResponse(self.body)):
        path=self.u.download(release)
    self.assertEqual(path.read_bytes(),self.body)
 def test_tampered_installer_is_not_retained(self):
    with patch.object(self.u,'_json',side_effect=[self.release(),self.manifest()]):release=self.u.check()
    with patch.object(self.u,'_open',return_value=FakeResponse(self.body[:-1]+b'!')):
        with self.assertRaises(ValueError):self.u.download(release)
    self.assertFalse(list((self.root/'Cache/atualizacoes').glob('*')))
 def test_release_cannot_point_to_other_repository(self):
    r=self.release();r['assets'][0]['browser_download_url']='https://github.com/other/repo/releases/download/v0.13.0/VF-Emissor-Setup-0.13.0.exe'
    with patch.object(self.u,'_json',return_value=r),self.assertRaises(ValueError):self.u.check()
 def test_manifest_mismatch_prevents_download(self):
    m=self.manifest();m['version']='0.14.0'
    with patch.object(self.u,'_json',side_effect=[self.release(),m]),self.assertRaises(ValueError):self.u.check()
 def test_same_version_and_offline_keep_existing_data(self):
    marker=self.root/'Dados/preservar.txt';marker.parent.mkdir(exist_ok=True);marker.write_text('dados locais')
    with patch.object(self.u,'_json',return_value=dict(tag_name='v0.12.0')):self.assertFalse(self.u.check()['available'])
    with patch.object(self.u,'_json',side_effect=OSError('offline')),self.assertRaises(ValueError):self.u.check()
    self.assertEqual(marker.read_text(),'dados locais')
 def test_public_repository_configuration_survives_app_update(self):
    other=ReleaseUpdater(self.root/'outro-programa',self.root/'Dados','0.13.0')
    self.assertEqual(other.configuration()['repository'],'escritorio/vf-emissor')


class CertificateRestoreTests(unittest.TestCase):
 def test_saved_synthetic_certificate_loads_after_memory_is_cleared(self):
    import test_fiscal
    test_fiscal.FiscalTests.setUpClass()
    try:
        with tempfile.TemporaryDirectory() as d:
            s=Store(Path(d)/'vf.sqlite3');FiscalStore(s);EventStore(s);server.STORE=s
            try:
                cid=server.save_catalog(dict(kind='company',data=dict(CNPJCPF='11222333000181',xNome='TESTE CERTIFICADO',UF='AL',CRT='1')))['id']
                v=CertificateVault(Path(d)/'certificados-protegidos',TestProtector())
                with patch.object(server,'vault',return_value=v):
                    server.action(dict(action='load_certificate',cid=cid,data=base64.b64encode(test_fiscal.FiscalTests.pfx.read_bytes()).decode(),password='senha-teste',remember=True))
                    server.CERTS.clear()
                    restored=server.certificate(cid);self.assertEqual(restored.cnpj,'11222333000181')
                    server.action(dict(action='forget_certificate',cid=cid));self.assertFalse(v.exists(cid))
            finally:server.CERTS.clear();s.db.close()
    finally:test_fiscal.FiscalTests.tearDownClass()

class HttpCompanyIsolation(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
    import socket
    from http.cookiejar import CookieJar
    from urllib.request import build_opener,HTTPCookieProcessor,Request
    cls.tmp=tempfile.TemporaryDirectory();folder=Path(cls.tmp.name);store=Store(folder/'vf.sqlite3');FiscalStore(store);EventStore(store)
    cls.cids=[]
    for cnpj,name in [('11222333000181','EMPRESA UM'),('12345678000195','EMPRESA DOIS')]:
        cid=store.save('company',dict(CNPJCPF=cnpj,xNome=name,UF='AL',CRT='1',environment='2'));cls.cids.append(cid)
        store.save('product',dict(code=name,name=name,NCM='09012100',unit='UN',price='10'),cid)
    store.db.close()
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    cls.url='http://127.0.0.1:'+str(port);env=dict(os.environ,VF_DATA_DIR=cls.tmp.name)
    cls.proc=subprocess.Popen([sys.executable,str(ROOT/'server.py'),'--no-browser','--port',str(port)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    cls.client=build_opener(HTTPCookieProcessor(CookieJar()));cls.anon=build_opener(HTTPCookieProcessor(CookieJar()))
    for _ in range(80):
        try:cls.client.open(cls.url+'/').read();break
        except OSError:time.sleep(.05)
    else:raise RuntimeError('Servidor não iniciou')
    cls.anon.open(cls.url+'/').read();cls.state=json.load(cls.client.open(cls.url+'/api/state'))
    cls.client.open(Request(cls.url+'/api/login',data=json.dumps(dict(cnpj='11222333000181',password='')).encode(),headers={'Content-Type':'application/json'})).read()
 @classmethod
 def tearDownClass(cls):cls.proc.terminate();cls.proc.communicate(timeout=10);cls.tmp.cleanup()
 def post(self,p,client=None):
    from urllib.request import Request
    return (client or self.client).open(Request(self.url+'/api/action',data=json.dumps(p).encode(),headers={'Content-Type':'application/json','X-VF-CSRF':self.state['csrf']}))
 def test_cid_query_cannot_read_another_company(self):
    result=json.load(self.client.open(self.url+'/api/state?cid='+self.cids[1]))
    self.assertEqual(result['cid'],self.cids[0]);self.assertEqual(result['products'][0]['name'],'EMPRESA UM')
 def test_anonymous_query_cannot_select_company(self):
    result=json.load(self.anon.open(self.url+'/api/state?cid='+self.cids[0]))
    self.assertFalse(result['authenticated']);self.assertEqual(result['companies'],[])
 def test_action_scope_overrides_forged_company_id(self):
    result=json.load(self.post(dict(action='search_products',cid=self.cids[1])))
    self.assertEqual([p['name'] for p in result['products']],['EMPRESA UM'])
 def test_company_mutation_cannot_target_another_company(self):
    from urllib.error import HTTPError
    with self.assertRaises(HTTPError) as exc:self.post(dict(action='save_catalog',kind='company',cid=self.cids[1],id=self.cids[1],data=dict(CNPJCPF='12345678000195',xNome='ALTERAR')))
    self.assertEqual(exc.exception.code,403)
 def test_anonymous_cannot_use_data_actions_or_download_backup(self):
    from urllib.error import HTTPError
    with self.assertRaises(HTTPError) as exc:self.post(dict(action='search_products',cid=self.cids[0]),self.anon)
    self.assertEqual(exc.exception.code,401)
    with self.assertRaises(HTTPError):self.anon.open(self.url+'/api/download?kind=backup&cid='+self.cids[0])

if __name__=='__main__':unittest.main()
