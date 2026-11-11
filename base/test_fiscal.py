import copy, tempfile, unittest, json
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cryptography import x509
from cryptography.x509.oid import NameOID,ObjectIdentifier
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from fiscal import *

class FiscalTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
    cls.tmp=tempfile.TemporaryDirectory();cls.cnpj='11222333000181'
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'CERTIFICADO DE TESTE:'+cls.cnpj)])
    now=datetime.now(timezone.utc)
    cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=2)).add_extension(x509.SubjectAlternativeName([x509.OtherName(ObjectIdentifier('2.16.76.1.3.3'),b'\x0c\x0e'+cls.cnpj.encode())]),False).sign(key,hashes.SHA256())
    cls.pfx=Path(cls.tmp.name)/'sintetico.pfx';cls.pfx.write_bytes(pkcs12.serialize_key_and_certificates(b'teste',key,cert,None,serialization.BestAvailableEncryption(b'senha-teste')))
    cls.certificate=A1Certificate.load(cls.pfx,'senha-teste',cls.cnpj)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def setUp(self):
    self.company=dict(CNPJCPF=self.cnpj,xNome='EMPRESA DE TESTE LTDA',IE='240000001',xLgr='RUA DE TESTE',nro='1',xBairro='CENTRO',cMun='2700300',xMun='ARAPIRACA',UF='AL',CEP='57300000',CRT='1',series='1',next_number='1')
    self.recipient=dict(self.company,CNPJCPF='52998224725',xNome='DESTINATARIO TESTE',indIEDest='9')
    self.rule=dict(name='Simples teste',CFOP='5102',origin='0',icms_code='102',pis_code='99',pis_rate='0',cofins_code='99',cofins_rate='0',reviewed='1',exclude_icms='0')
    self.item=dict(product=dict(code='001',name='PRODUTO DE TESTE',NCM='03061710',unit='UN'),rule=self.rule,quantity='2',price='100',discount='10')
    self.note=dict(final='1',number='1',series='1',cnf='12345678',issued_at='2026-11-04T09:00:00-03:00',items=[self.item],payment='01')
 def signed(self):
    xml,key,total=build_unsigned(self.company,self.recipient,self.note)
    return self.certificate.sign(xml),key
 def fixture(self,key,signed,code='100'):
    digest=parse_xml(signed).findtext('ds:Signature/ds:SignedInfo/ds:Reference/ds:DigestValue',namespaces={'ds':DS})
    return f'<retEnviNFe xmlns="{NS}" versao="4.00"><tpAmb>2</tpAmb><cStat>104</cStat><xMotivo>Lote processado</xMotivo><protNFe versao="4.00"><infProt><tpAmb>2</tpAmb><verAplic>TESTE</verAplic><chNFe>{key}</chNFe><dhRecbto>2026-11-04T09:00:01-03:00</dhRecbto><nProt>127260000000001</nProt><digVal>{digest}</digVal><cStat>{code}</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo></infProt></protNFe></retEnviNFe>'.encode()
 def test_key_check_digit(self):
    key=access_key(self.cnpj,1,1,'12345678',datetime.fromisoformat(self.note['issued_at']))
    self.assertEqual(len(key),44); self.assertTrue(key.startswith('272611')); self.assertEqual(key[6:20],self.cnpj)
 def test_a1_wrong_password(self):
    with self.assertRaises(ValueError):A1Certificate.load(self.pfx,'errada')
 def test_a1_other_company(self):
    with self.assertRaises(ValueError):A1Certificate.load(self.pfx,'senha-teste','99999999000191')
 def test_a1_metadata_has_no_password(self):self.assertNotIn('password',self.certificate.metadata())
 def test_signed_schema(self):
    signed,key=self.signed();validate_schema(signed);self.assertIn(key.encode(),signed)
 def test_simples_101_credit(self):
    self.rule.update(icms_code='101',credit_rate='3.25')
    signed,key=self.signed(); self.assertEqual(text(parse_xml(signed),'n:infNFe/n:det/n:imposto/n:ICMS/n:ICMSSN101/n:vCredICMSSN'),'6.18')
 def test_codes_103_300_400(self):
    for code in ['103','300','400']:
        self.rule['icms_code']=code;signed,_=self.signed();validate_schema(signed)
 def test_sn_without_false_rtc_checkbox(self):
    self.assertNotIn('rtc_status',self.rule);self.signed()
 def test_production_rejected(self):
    self.note['environment']='1'
    with self.assertRaises(ValueError):self.signed()
 def test_2027_rejected(self):
    self.note['issued_at']='2027-01-01T09:00:00-03:00'
    with self.assertRaises(ValueError):self.signed()
 def test_other_state_rejected(self):
    self.recipient['UF']='PE'
    with self.assertRaises(ValueError):self.signed()
 def test_party_location_errors_identify_record(self):
    for attr,role in [('company','Emitente'),('recipient','Destinatário')]:
        party=getattr(self,attr); original=party.copy()
        party['UF']='PE'
        with self.assertRaisesRegex(ValueError,role+': UF cadastrada PE'): self.signed()
        party.update(original); party['cMun']='2611606'
        with self.assertRaisesRegex(ValueError,role+': código IBGE 2611606'): self.signed()
        party.update(original)
 def test_location_normalization_preserves_inputs(self):
    self.company['UF']=' al '; self.recipient['cMun']=' 2700300 '
    signed,_=self.signed(); validate_schema(signed)
    self.assertEqual(self.company['UF'],' al ')
    self.assertEqual(self.recipient['cMun'],' 2700300 ')
 def test_additional_fields_signed_schema_and_roundtrip(self):
    self.note.update(info='Observacao de teste',info_fisco='Informacao fiscal de teste',purchase_order='PED-123',purchase_contract='CT-456',purchase_commitment='EMP-789')
    signed,_=self.signed();validate_schema(signed);node=parse_xml(signed)
    for xpath,value in [('n:infNFe/n:infAdic/n:infCpl','Observacao de teste'),('n:infNFe/n:infAdic/n:infAdFisco','Informacao fiscal de teste'),('n:infNFe/n:compra/n:xPed','PED-123'),('n:infNFe/n:compra/n:xCont','CT-456'),('n:infNFe/n:compra/n:xNEmp','EMP-789')]:
        self.assertEqual(text(node,xpath),value)
    from core import Store
    with tempfile.TemporaryDirectory() as temp:
        store=Store(Path(temp)/'test.sqlite3');cid=store.save('company',self.company)
        rid=store.save('note',self.note,cid);restored=store.get('note',cid,rid);store.db.close()
        self.assertEqual(restored['purchase_order'],'PED-123');self.assertEqual(restored['info_fisco'],'Informacao fiscal de teste')
 def test_additional_fields_limits_and_control_characters(self):
    for field,limit in [('info',5000),('info_fisco',2000),('purchase_order',60),('purchase_contract',60),('purchase_commitment',22)]:
        self.note[field]='A'*(limit+1)
        with self.assertRaisesRegex(ValueError,'limite'):self.signed()
        self.note[field]='A\x01B'
        with self.assertRaisesRegex(ValueError,'controle'):self.signed()
        del self.note[field]
 def test_fraction_not_truncated(self):
    self.item['quantity']='1.00001'
    with self.assertRaises(ValueError):self.signed()
 def test_process_matches_digest(self):
    signed,key=self.signed();result=unpack_response(self.fixture(key,signed),key);proc=assemble_process(signed,result)
    self.assertIn(b'nfeProc',proc);validate_schema(proc,'procNFe_v4.00.xsd')
 def test_wrong_key_not_authorized(self):
    signed,key=self.signed()
    with self.assertRaises(ValueError):unpack_response(self.fixture('0'*44,signed),key)
 def test_wrong_digest_not_authorized(self):
    signed,key=self.signed();result=unpack_response(self.fixture(key,signed),key);result['digest']='A'*28
    with self.assertRaises(ValueError):assemble_process(signed,result)
 def test_cancelled_query_not_authorized(self):
    signed,key=self.signed();data=self.fixture(key,signed).replace(b'<retEnviNFe',b'<retConsSitNFe').replace(b'</retEnviNFe>',b'</retConsSitNFe>').replace(b'<cStat>104</cStat>',b'<cStat>101</cStat>')
    self.assertEqual(unpack_response(data,key)['code'],'101')
 def test_migration_and_authorization(self):
    with tempfile.TemporaryDirectory() as tmp:
        store=Store(Path(tmp)/'decisao.sqlite3');cid=store.save('company',self.company);store.save('product',{'name':'PRESERVADO'},cid)
        fiscal=FiscalStore(store);self.assertTrue(list((Path(tmp)/'backups').glob('*.sqlite3')));self.assertEqual(store.list('product',cid)[0][1]['name'],'PRESERVADO')
        signed,key=self.signed();snap=dict(company=self.company,recipient=self.recipient,note=self.note)
        rid=fiscal.prepare(cid,'rascunho-1',snap,signed,key)
        with self.assertRaises(ValueError):fiscal.prepare(cid,'rascunho-2',snap,signed,key)
        fiscal.begin_send(cid,rid);self.assertEqual(fiscal.get(cid,rid)['status'],'ENVIANDO')
        fiscal.apply_response(cid,rid,self.fixture(key,signed));self.assertEqual(fiscal.get(cid,rid)['status'],'AUTORIZADA');self.assertEqual(store.get('company','',cid)['next_number'],'2')
        with self.assertRaises(ValueError):fiscal.begin_send(cid,rid)
        with self.assertRaises(ValueError):fiscal.get('outra-empresa',rid)
        store.db.close()
 def test_timeout_persisted_no_retry(self):
    with tempfile.TemporaryDirectory() as tmp:
        store=Store(Path(tmp)/'db.sqlite3');cid=store.save('company',self.company);fiscal=FiscalStore(store);signed,key=self.signed();rid=fiscal.prepare(cid,'nota',dict(company=self.company,recipient=self.recipient,note=self.note),signed,key)
        class Fail:
            count=0
            def request(self_,operation,data):self_.count+=1;raise TimeoutError('simulado')
        transport=Fail();service=FiscalService(fiscal,self.certificate,transport)
        with self.assertRaises(TimeoutError):service.send(cid,rid)
        self.assertEqual(transport.count,1);self.assertEqual(fiscal.get(cid,rid)['status'],'INCERTA')
        with self.assertRaises(ValueError):service.send(cid,rid)
        self.assertEqual(transport.count,1);store.db.close()
 def test_danfe_local(self):
    signed,key=self.signed();pdf=render_danfe(assemble_process(signed,unpack_response(self.fixture(key,signed),key)))
    self.assertTrue(pdf.startswith(b'%PDF'));self.assertGreater(len(pdf),3000)
 def test_service_failure_does_not_allow_new_xml(self):
    with tempfile.TemporaryDirectory() as tmp:
        store=Store(Path(tmp)/'db.sqlite3');self.addCleanup(store.db.close);cid=store.save('company',self.company);fiscal=FiscalStore(store);signed,key=self.signed();snap=dict(company=self.company,recipient=self.recipient,note=self.note);rid=fiscal.prepare(cid,'nota',snap,signed,key)
        fiscal.begin_send(cid,rid)
        fiscal.apply_response(cid,rid,f'<retConsSitNFe xmlns="{NS}"><tpAmb>2</tpAmb><cStat>108</cStat><xMotivo>Servico paralisado</xMotivo></retConsSitNFe>'.encode())
        self.assertEqual(fiscal.get(cid,rid)['status'],'INCERTA')
        with self.assertRaises(ValueError):fiscal.prepare(cid,'nota',snap,signed,key)
        store.db.close()
 def test_rejected_snapshot_can_be_corrected(self):
    with tempfile.TemporaryDirectory() as tmp:
        store=Store(Path(tmp)/'db.sqlite3');self.addCleanup(store.db.close);cid=store.save('company',self.company);fiscal=FiscalStore(store);signed,key=self.signed();snap=dict(company=self.company,recipient=self.recipient,note=self.note);rid=fiscal.prepare(cid,'nota',snap,signed,key)
        fiscal.begin_send(cid,rid);fiscal.apply_response(cid,rid,self.fixture(key,signed,code='539'))
        self.assertEqual(fiscal.get(cid,rid)['status'],'INCERTA')
        # Rejeição específica do documento, com chave correspondente.
        fiscal.apply_response(cid,rid,self.fixture(key,signed,code='778'))
        self.assertEqual(fiscal.get(cid,rid)['status'],'REJEITADA');self.assertEqual(fiscal.prepare(cid,'nota',snap,signed,key),rid)
        self.assertEqual(fiscal.get(cid,rid)['status'],'PREPARADA');store.db.close()
 def test_duplicate_batch_status_is_not_authorization(self):
    signed,key=self.signed();response=f'<retEnviNFe xmlns="{NS}"><tpAmb>2</tpAmb><cStat>104</cStat><xMotivo>Lote processado</xMotivo></retEnviNFe>'.encode()
    result=unpack_response(response,key)
    with self.assertRaises(ValueError):assemble_process(signed,result)
 def test_official_trust_chain_fingerprints(self):
    chain=svrs_trust_chain();certs=x509.load_pem_x509_certificates(chain.encode())
    self.assertEqual(tuple(c.fingerprint(hashes.SHA256()).hex() for c in certs),SVRS_CA_FINGERPRINTS)
 def test_tls_adapter_keeps_verification(self):
    import ssl
    adapter=create_tls_adapter(self.certificate)
    try:
        self.assertEqual(adapter.ssl_context.verify_mode,ssl.CERT_REQUIRED);self.assertTrue(adapter.ssl_context.check_hostname)
        trusted={__import__('hashlib').sha256(c).hexdigest() for c in adapter.ssl_context.get_ca_certs(binary_form=True)}
        self.assertIn(SVRS_CA_FINGERPRINTS[0],trusted)
    finally:adapter.close()
 def test_trust_resource_tampering_rejected(self):
    with patch('pathlib.Path.read_bytes',return_value=self.certificate.cert.public_bytes(serialization.Encoding.PEM)):
        with self.assertRaises(RuntimeError):svrs_trust_chain()
 def _local_tls(self,trust,hostname):
    import ssl,socket,threading
    now=datetime.now(timezone.utc);ca_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    ca_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'CA SINTETICA LOCAL')])
    ca=x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=0),True).sign(ca_key,hashes.SHA256())
    server_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    server_cert=x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])).issuer_name(ca_name).public_key(server_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]),False).add_extension(x509.BasicConstraints(ca=False,path_length=None),True).sign(ca_key,hashes.SHA256())
    with tempfile.TemporaryDirectory() as tmp:
        certpath=Path(tmp)/'server.pem';keypath=Path(tmp)/'server.key'
        certpath.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM));keypath.write_bytes(server_key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        server_context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);server_context.load_cert_chain(certpath,keypath)
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(5)
        def serve():
            try:
                raw,_=listener.accept();raw.settimeout(5)
                with raw:
                    try:
                        with server_context.wrap_socket(raw,server_side=True) as tls:tls.recv(1)
                    except (ssl.SSLError,OSError):pass
            finally:listener.close()
        thread=threading.Thread(target=serve,daemon=True);thread.start();adapter=create_tls_adapter(self.certificate)
        try:
            if trust:adapter.ssl_context.load_verify_locations(cadata=ca.public_bytes(serialization.Encoding.PEM).decode())
            try:
                with socket.create_connection(listener.getsockname(),timeout=5) as raw:
                    with adapter.ssl_context.wrap_socket(raw,server_hostname=hostname) as tls:tls.send(b'x');return True
            except ssl.SSLCertVerificationError:return False
        finally:adapter.close();thread.join(5)
 def test_local_tls_trusted_ca_accepted(self):self.assertTrue(self._local_tls(True,'localhost'))
 def test_local_tls_unknown_ca_rejected(self):self.assertFalse(self._local_tls(False,'localhost'))
 def test_local_tls_wrong_hostname_rejected(self):self.assertFalse(self._local_tls(True,'outro.invalid'))
 def test_soap_context_signature_and_no_production(self):
    signed,key=self.signed();envi=ET.Element('{'+NS+'}enviNFe',nsmap={None:NS},versao='4.00');tag(envi,'idLote','1');tag(envi,'indSinc','1');envi.append(parse_xml(signed))
    captured={}
    class Response:
        status_code=200
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def iter_content(self,*a):yield self.fixture(key,signed)
    response=Response();response.fixture=self.fixture
    class Session:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def mount(self,*a):pass
        def post(self,url,**kwargs):captured.update(url=url,**kwargs);return response
    with patch('requests.Session',Session):SefazTransport(self.certificate).request('send',serialize(envi))
    self.assertIn('nfe-homologacao.svrs.rs.gov.br',captured['url']);self.assertTrue(captured['verify']);self.assertFalse(captured['allow_redirects'])

if __name__=='__main__':unittest.main()
