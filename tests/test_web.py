"""Contratos de segurança e persistência web. Sem chamadas externas."""
import base64, copy, io, json, os, subprocess, sys, tempfile, time, unittest, zipfile
from pathlib import Path
from urllib.request import Request, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError
from http.cookiejar import CookieJar
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'base'))
import server
from core import Store
from fiscal import FiscalStore
import test_fiscal as fiscal_tests

class WebContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();server.STORE=Store(Path(self.tmp.name)/'web.sqlite3');FiscalStore(server.STORE)
        self.co=dict(CNPJCPF='11222333000181',xNome='EMPRESA SINTETICA DE TESTE',IE='240000001',xLgr='RUA DE TESTE',nro='1',xBairro='CENTRO',cMun='2700300',xMun='ARAPIRACA',UF='AL',CEP='57300000',CRT='1',series='1',next_number='1',environment='2')
        self.cid=server.save_catalog(dict(kind='company',data=self.co))['id']
        self.rec=dict(self.co,CNPJCPF='52998224725',xNome='CLIENTE SINTETICO',indIEDest='9')
        self.rid=server.save_catalog(dict(kind='recipient',cid=self.cid,data=self.rec))['id']
        rule=dict(name='Simples teste',CFOP='5102',origin='0',icms_code='102',pis_code='99',pis_rate='0',cofins_code='99',cofins_rate='0',reviewed='1',exclude_icms='0',rtc_status='nao_aplicavel_revisado')
        self.n=server.action(dict(action='new_note',cid=self.cid))['note'];self.n['recipient_id']=self.rid
        self.n['items']=[dict(product=dict(code='001',name='PRODUTO TESTE',NCM='03061710',unit='UN'),rule=rule,quantity='2',price='100',discount='10')]
    def tearDown(self):server.CERTS.clear();server.STORE.db.close();self.tmp.cleanup()
    def save(self,n=None,rid=None):return server.save_note(dict(cid=self.cid,data=n or self.n,id=rid))['id']
    def test_draft_roundtrip_and_number_allocation(self):
        a=self.save();b=self.save();s=server.get_state(self.cid)
        self.assertEqual({d['number'] for d in s['documents']},{'1','2'})
        self.assertTrue(all(d['_total']=='190.00' and d['_status']=='RASCUNHO' for d in s['documents']))
        self.assertNotEqual(a,b)
    def test_company_and_get_state_include_id(self):
        co = server.company(self.cid)
        self.assertEqual(co['_id'], self.cid)
        s = server.get_state(self.cid)
        self.assertTrue(s['authenticated'])
        self.assertEqual(s['cid'], self.cid)
        self.assertEqual(s['company']['_id'], self.cid)
        self.assertEqual(s['companies'][0]['_id'], self.cid)
    def test_danfe_preview_generates_pdf_for_draft(self):
        rid = self.save()
        co = server.company(self.cid)
        n = server.note(self.cid, rid)
        rec = server.STORE.get('recipient', self.cid, n.get('recipient_id', ''))
        unsigned, key, _ = server.build_unsigned(co, rec, n)
        pdf = server.render_danfe(unsigned, is_preview=True)
        self.assertTrue(pdf.startswith(b'%PDF'))
    def test_delete_draft_note_removes_record_and_frees_number(self):
        rid = self.save()
        self.assertEqual(len(server.rows('note', self.cid)), 1)
        res = server.action(dict(action='delete_note', cid=self.cid, id=rid))
        self.assertTrue(res.get('ok'))
        self.assertEqual(server.rows('note', self.cid), [])
        # Ensure next note allocates number '1' again rather than jumping
        n2 = server.action(dict(action='new_note', cid=self.cid))['note']
        n2['recipient_id'] = self.rid
        n2['items'] = self.n['items']
        rid2 = server.save_note(dict(cid=self.cid, data=n2))['id']
        self.assertEqual(server.note(self.cid, rid2)['number'], '1')
    def test_delete_note_blocks_authorized(self):
        rid = self.save()
        with server.STORE.db:
            server.STORE.db.execute("INSERT INTO fiscal_documents(id,company,cnpj,environment,source,series,number,access_key,status,snapshot,signed_xml,created,updated) VALUES('f1',?,?,'2',?,1,1,'key','AUTORIZADA','{}',x'00','2026-11-10T00:00:00','2026-11-10T00:00:00')", (self.cid, self.co['CNPJCPF'], rid))
        with self.assertRaisesRegex(ValueError, 'validade fiscal'):
            server.action(dict(action='delete_note', cid=self.cid, id=rid))
    def test_unsaved_draft_validation_uses_auto_number_without_reserving(self):
        result=server.action(dict(action='validate',cid=self.cid,note=self.n))
        self.assertEqual(result['issues'],[])
        self.assertEqual(server.rows('note',self.cid),[])
        self.assertEqual(FiscalStore(server.STORE).list(self.cid),[])
    def test_certificate_can_be_loaded_without_writing_a_pfx_file(self):
        fiscal_tests.FiscalTests.setUpClass()
        try:
            raw=fiscal_tests.FiscalTests.pfx.read_bytes()
            cert=server.A1Certificate.from_bytes(raw,'senha-teste',self.co['CNPJCPF'])
            self.assertEqual(cert.cnpj,self.co['CNPJCPF'])
        finally:fiscal_tests.FiscalTests.tearDownClass()
    def test_same_number_is_rejected_and_company_scope_is_enforced(self):
        self.save();self.n['number']='1'
        with self.assertRaises(ValueError):self.save()
        second=dict(self.co,CNPJCPF='12345678000195');cid2=server.save_catalog(dict(kind='company',data=second))['id']
        with self.assertRaises(ValueError):server.note(cid2,server.get_state(self.cid)['documents'][0]['_id'])
    def test_missing_certificate_never_prepares_a_fiscal_document(self):
        rid=self.save()
        with self.assertRaisesRegex(ValueError,'certificado'):server.action(dict(action='prepare',cid=self.cid,id=rid))
        self.assertEqual(FiscalStore(server.STORE).list(self.cid),[])
    def test_production_requires_explicit_enable_and_existing_draft_keeps_environment(self):
        self.n['environment']='1'
        with self.assertRaises(ValueError):self.save()
        self.n['environment']='2';rid=self.save()
        self.co.update(production_series='1',production_next_number='15')
        server.save_catalog(dict(kind='company',id=self.cid,data=self.co,enable_production=True,ack='PRODUÇÃO'))
        self.n['environment']='1'
        with self.assertRaises(ValueError):self.save(self.n,rid)
    def test_preview_blocks_certificate_and_sefaz(self):
        server.PREVIEW=True
        try:
            with self.assertRaisesRegex(ValueError,'Windows'):server.action(dict(action='load_certificate',cid=self.cid,data='',password=''))
            with self.assertRaisesRegex(ValueError,'Windows'):server.action(dict(action='sefaz_status',cid=self.cid))
        finally:server.PREVIEW=False
    def test_nonfinite_number_and_negative_values_rejected(self):
        for price in ('NaN','Infinity','-5'):
            self.n['items'][0]['price']=price
            totals,errors=server.totals(self.co,self.n)
            self.assertTrue(errors)
    def test_expired_a1_session_is_discarded(self):
        server.CERTS[self.cid]=(object(),time.time()-1)
        with self.assertRaises(ValueError):server.certificate(self.cid)
        self.assertNotIn(self.cid,server.CERTS)
    def test_invalid_or_unrelated_import_does_not_create_records(self):
        with self.assertRaises(ValueError):server.import_xml(dict(cid=self.cid,data=base64.b64encode(b'<!DOCTYPE foo><foo/>').decode()))
        self.assertEqual(server.rows('received',self.cid),[])
    def test_signed_preparation_is_separate_from_transmission_and_locks_final_documents(self):
        fiscal_tests.FiscalTests.setUpClass()
        try:
            server.CERTS[self.cid]=(fiscal_tests.FiscalTests.certificate,time.time()+3600)
            rid=self.save();prepared=server.action(dict(action='prepare',cid=self.cid,id=rid))
            doc=FiscalStore(server.STORE).get(self.cid,prepared['fiscal_id'])
            self.assertEqual(doc['status'],'PREPARADA');self.assertIsNone(doc['response_xml'])
            with server.STORE.db:server.STORE.db.execute("UPDATE fiscal_documents SET status='AUTORIZADA' WHERE id=?",(doc['id'],))
            with self.assertRaises(ValueError):self.save(self.n,rid)
        finally:fiscal_tests.FiscalTests.tearDownClass()

class HttpSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import socket
        with socket.socket() as s:s.bind(('127.0.0.1',0));cls.port=s.getsockname()[1]
        cls.tmp=tempfile.TemporaryDirectory();cls.url='http://127.0.0.1:'+str(cls.port)
        env=dict(os.environ);env['VF_DATA_DIR']=cls.tmp.name
        cls.proc=subprocess.Popen([sys.executable,str(ROOT/'server.py'),'--no-browser','--port',str(cls.port)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        cls.opener=build_opener(HTTPCookieProcessor(CookieJar()))
        for _ in range(80):
            try:
                cls.opener.open(cls.url+'/').read();break
            except OSError:time.sleep(.05)
        else:raise RuntimeError('Servidor não iniciou.')
        cls.state=json.load(cls.opener.open(cls.url+'/api/state'))
    @classmethod
    def tearDownClass(cls):cls.proc.terminate();cls.proc.communicate(timeout=10);cls.tmp.cleanup()
    def request(self,p,headers=None):
        h={'Content-Type':'application/json'};h.update(headers or {})
        return self.opener.open(Request(self.url+'/api/action',data=json.dumps(p).encode(),headers=h))
    def test_no_cookie_cannot_read_database(self):
        with self.assertRaises(HTTPError) as e:build_opener().open(self.url+'/api/state')
        self.assertEqual(e.exception.code,401)
    def test_cross_origin_and_missing_csrf_block_writes(self):
        for h in ({},{'X-VF-CSRF':self.state['csrf'],'Origin':'https://example.com'},{'X-VF-CSRF':self.state['csrf'],'Sec-Fetch-Site':'cross-site'}):
            with self.assertRaises(HTTPError) as e:self.request(dict(action='new_note',cid='invalid'),h)
            self.assertEqual(e.exception.code,403)
    def test_host_header_protects_local_service(self):
        with self.assertRaises(HTTPError) as e:self.opener.open(Request(self.url+'/api/state',headers={'Host':'attacker.example'}))
        self.assertEqual(e.exception.code,403)
    def test_backup_contains_readable_database_and_no_certificate(self):
        co=dict(CNPJCPF='11222333000181',xNome='EMPRESA BACKUP TESTE',CRT='1',UF='AL')
        self.request(dict(action='save_catalog',kind='company',data=co),{'X-VF-CSRF':self.state['csrf']}).read()
        self.opener.open(Request(self.url+'/api/login',data=json.dumps(dict(cnpj=co['CNPJCPF'],password='')).encode(),headers={'Content-Type':'application/json'})).read()
        raw=self.opener.open(self.url+'/api/download?kind=backup').read()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertIn('dados/vf.sqlite3',z.namelist());self.assertTrue(z.read('dados/vf.sqlite3').startswith(b'SQLite format 3'))
            self.assertFalse(any(n.endswith(('.pfx','.p12','.pem')) for n in z.namelist()))
    def test_editor_assets_and_official_rtc_catalog_available(self):
        for route in ('/product-ui.js','/settings-ui.js'):
            self.assertEqual(self.opener.open(self.url+route).status,200)
        table=json.loads((ROOT/'base/rtc_catalog.json').read_text(encoding='utf-8'))
        self.assertEqual(table['source'],'https://dfe-portal.svrs.rs.gov.br/Cff/ClassificacaoTributaria')
        rows={r['Cst']:r for r in table['csts']}
        self.assertEqual(rows['410']['NomeCst'],'Imunidade e não incidência')
        for code,row in rows.items():
            self.assertTrue(all(c['CodClassTrib'].startswith(code) and c['IndNfe'] for c in row['classes']))

if __name__=='__main__':unittest.main()
