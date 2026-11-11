"""Prévia conserva ambiente/destinatário e nunca se apresenta como DANFE autorizado."""
import copy,re,zlib,unittest
import test_web as fixtures
import server

def streams(pdf):
    result=[]
    for raw in re.findall(rb'stream\r?\n(.*?)\r?\nendstream',pdf,re.S):
        try:result.append(zlib.decompress(raw))
        except zlib.error:result.append(raw)
    return b'\n'.join(result)

class DanfePreviewTests(unittest.TestCase):
 setUp=fixtures.WebContracts.setUp
 tearDown=fixtures.WebContracts.tearDown
 def xml(self,env='1',items=1):
    co=dict(self.co,production_enabled=True);n=copy.deepcopy(self.n);n.update(environment=env,number='1',cnf='12345678')
    n['items']=[copy.deepcopy(n['items'][0]) for _ in range(items)]
    for i,item in enumerate(n['items']):item['product']['code']=str(i+1)
    return server.build_unsigned(co,self.rec,n)[0]
 def test_production_preview_preserves_actual_recipient_and_marks_no_authorization(self):
    raw=self.xml();original=bytes(raw);pdf=server.render_danfe(raw,is_preview=True);content=streams(pdf)
    self.assertIn(b'CLIENTE SINTETICO',content);self.assertNotIn(b'NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO',content)
    self.assertIn(b'SEM VALOR FISCAL',content);self.assertIn(b'PREVIA DO DANFE - SEM AUTORIZACAO DE USO',content);self.assertEqual(raw,original)
    root=server.parse_xml(raw);self.assertEqual(root.findtext('.//{'+server.NS+'}tpAmb'),'1')
 def test_homologation_preview_keeps_required_homologation_name(self):
    pdf=server.render_danfe(self.xml('2'),is_preview=True);content=streams(pdf)
    self.assertIn(b'NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO',content);self.assertIn(b'PREVIA DO DANFE - SEM AUTORIZACAO DE USO',content)
 def test_production_without_protocol_still_cannot_generate_final_danfe(self):
    with self.assertRaisesRegex(ValueError,'protocolo'):server.render_danfe(self.xml())
 def test_preview_mark_is_printed_on_every_page(self):
    pdf=server.render_danfe(self.xml(items=90),is_preview=True);pages=len(re.findall(rb'/Type /Page\b',pdf));self.assertGreater(pages,1)
    self.assertEqual(streams(pdf).count(b'PREVIA DO DANFE - SEM AUTORIZACAO DE USO'),pages)

if __name__=='__main__':unittest.main()
