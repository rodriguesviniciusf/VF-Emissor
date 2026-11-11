import sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'base')]
from core import Store
import nature_catalog as nature

class NatureTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'vf.sqlite3');self.a=self.store.save('company',dict(xNome='A'));self.b=self.store.save('company',dict(xNome='B'))
 def tearDown(self):self.store.db.close();self.tmp.cleanup()
 def test_default_delete_is_persistent_after_restart_and_isolated(self):
  first=nature.listing(self.store,self.a)[0];nature.remove(self.store,self.a,first['id']);self.store.db.close();self.store=Store(Path(self.tmp.name)/'vf.sqlite3')
  self.assertNotIn(first['name'],nature.nature_choices(self.store,self.a));self.assertIn(first['name'],nature.nature_choices(self.store,self.b))
 def test_custom_add_duplicates_and_other_company_delete(self):
  rid=nature.save_nature(self.store,self.a,'  REMESSA   ESPECIAL  ');self.assertIn('REMESSA ESPECIAL',nature.nature_choices(self.store,self.a))
  with self.assertRaises(ValueError):nature.save_nature(self.store,self.a,'remessa especial')
  with self.assertRaises(ValueError):nature.remove(self.store,self.b,rid)
 def test_deletion_preserves_notes_defaults_and_model_descriptions(self):
  rid=nature.save_nature(self.store,self.a,'VENDA PARTICULAR');note=self.store.save('note',dict(nature='VENDA PARTICULAR'),self.a);nature.remove(self.store,self.a,rid)
  self.assertEqual(self.store.get('note',self.a,note)['nature'],'VENDA PARTICULAR');self.assertIn('VENDA PARTICULAR',nature.nature_choices(self.store,self.a,'VENDA PARTICULAR'))
 def test_can_remove_entire_default_list_without_it_returning(self):
  for row in nature.listing(self.store,self.a):nature.remove(self.store,self.a,row['id'])
  self.assertEqual(nature.listing(self.store,self.a),[])
