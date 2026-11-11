import unittest, tempfile, pathlib, configparser, io, socket, threading
from decimal import Decimal
from core import *

class CoreTests(unittest.TestCase):
 def setUp(self):
    self.rule=dict(name='Teste',CFOP='5102',origin='0',icms_code='00',icms_rate='18',pis_code='01',pis_rate='1.65',cofins_code='01',cofins_rate='7.6',exclude_icms='1',reviewed='1',rtc_status='nao_aplicavel_revisado')
    self.item=dict(quantity='2',price='100,00',discount='10',product=dict(code='1',name='PRODUTO DE TESTE',NCM='00000000',unit='UN'),rule=self.rule)
    self.company=dict(CNPJCPF='11222333000181',xNome='EMITENTE TESTE',IE='123',xLgr='RUA TESTE',nro='1',xBairro='CENTRO',cMun='3550308',xMun='SAO PAULO',UF='SP',CEP='01001000',CRT='3')
    self.recipient=dict(self.company,CNPJCPF='52998224725',xNome='DESTINATARIO TESTE',indIEDest='9')
    self.note=dict(final='1',items=[self.item],number='1',series='1',cnf='12345678',date='04/11/2026 12:00:00')
 def test_decimal_br(self): self.assertEqual(number('1.234,5678'),Decimal('1234.5678'))
 def test_half_up(self): self.assertEqual(money('0.005'),Decimal('0.01'))
 def test_nan_rejected(self):
    with self.assertRaises(ValueError): number('NaN')
 def test_invalid_document(self): self.assertFalse(valid_document('00000000000000'))
 def test_cpf_cnpj(self):
    self.assertTrue(valid_document('11.222.333/0001-81')); self.assertTrue(valid_document('529.982.247-25'))
 def test_taxes_with_icms_exclusion(self):
    r=calculate(self.item,self.rule,'3')
    self.assertEqual(r['net'],Decimal('190')); self.assertEqual(r['icms'],Decimal('34.20')); self.assertEqual(r['pcbase'],Decimal('155.80')); self.assertEqual(r['pis'],Decimal('2.57')); self.assertEqual(r['cofins'],Decimal('11.84'))
 def test_simple_99_zero(self):
    rule=dict(self.rule,icms_code='102',pis_code='99',cofins_code='99',pis_rate='0',cofins_rate='0')
    r=calculate(self.item,rule,'1'); self.assertEqual(r['icms'],0); self.assertEqual(r['pis'],0)
 def test_no_silent_rate(self):
    with self.assertRaises(ValueError): calculate(self.item,dict(self.rule,pis_rate=''),'3')
 def test_discount_overflow(self):
    with self.assertRaises(ValueError): calculate(dict(self.item,discount='201'),self.rule,'3')
 def test_st_rejected(self):
    with self.assertRaises(ValueError): calculate(self.item,dict(self.rule,icms_code='10'),'3')
 def test_ini_only_homologation(self):
    result,_=build_ini(self.company,self.recipient,self.note)
    ini=configparser.ConfigParser(); ini.read_string(result)
    self.assertEqual(ini['Identificacao']['tpamb'],'2'); self.assertEqual(ini['PIS001']['vpis'],'2.57'); self.assertEqual(ini['Total']['vnf'],'190.00')
 def test_more_than_ten_items(self):
    result,total=build_ini(self.company,self.recipient,dict(self.note,items=[self.item]*15))
    self.assertIn('[Produto015]',result); self.assertEqual(total['net'],Decimal('2850'))
 def test_state_operation_block(self):
    with self.assertRaises(ValueError): build_ini(self.company,dict(self.recipient,UF='AL'),self.note)
 def test_rule_review_required(self):
    self.item['rule']=dict(self.rule,reviewed='0')
    with self.assertRaises(ValueError): build_ini(self.company,self.recipient,self.note)
 def test_rtc_not_silently_omitted(self):
    self.item['rule']=dict(self.rule,rtc_status='')
    with self.assertRaises(ValueError): build_ini(self.company,self.recipient,self.note)
 def test_ini_injection(self):
    with self.assertRaises(ValueError): clean('Produto\n[Total]\nvNF=0')
 def test_company_isolation_and_backup(self):
    with tempfile.TemporaryDirectory() as tmp:
        s=Store(pathlib.Path(tmp)/'db.sqlite'); rid=s.save('product',{'name':'A'},'empresa-a')
        self.assertEqual(s.list('product','empresa-b'),[])
        with self.assertRaises(ValueError): s.get('product','empresa-b',rid)
        with self.assertRaises(ValueError): s.save('product',{'name':'B'},'empresa-b',rid)
        s.backup(pathlib.Path(tmp)/'backup.sqlite'); s.db.close()
        restored=Store(pathlib.Path(tmp)/'backup.sqlite'); self.assertEqual(restored.get('product','empresa-a',rid)['name'],'A'); restored.db.close()
 def test_xml_entity_rejected(self):
    with tempfile.TemporaryDirectory() as tmp:
        target=pathlib.Path(tmp)/'bad.xml'; target.write_text('<!DOCTYPE x [<!ENTITY a SYSTEM "file:///test">]><x/>')
        with self.assertRaises(ValueError): parse_authorization(target)
 def test_import_wrong_issuer(self):
    with tempfile.TemporaryDirectory() as tmp:
        target=pathlib.Path(tmp)/'test.xml'; target.write_text('<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe Id="NFe'+'1'*44+'"><emit><CNPJ>11222333000181</CNPJ></emit></infNFe></NFe></nfeProc>')
        with self.assertRaises(ValueError): parse_authorization(target,'00000000000000')
 def test_monitor_greeting_not_response(self):
    server=socket.socket(); server.bind(('127.0.0.1',0)); server.listen(1); port=server.getsockname()[1]
    def serve():
        conn,_=server.accept()
        with conn:
            conn.sendall(b'ACBrMonitor pronto\r\n\x03'); conn.recv(8192); conn.sendall(b'OK: Resposta real\r\n\x03')
        server.close()
    thread=threading.Thread(target=serve); thread.start()
    result=Monitor(port).command('ACBr.Versao'); thread.join(); self.assertEqual(result,'OK: Resposta real')

if __name__=='__main__': unittest.main()
