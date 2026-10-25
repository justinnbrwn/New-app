import tempfile,unittest
from pathlib import Path
import tenant_store as t
class TenantTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.db=Path(self.temp.name)/'t.db';t.initialize(self.db)
  self.a=t.provision(self.db,'Alpha','a@example.com','long-alpha-password');self.b=t.provision(self.db,'Beta','b@example.com','long-beta-password')
 def tearDown(self):self.temp.cleanup()
 def test_login_and_isolation(self):
  x=t.login(self.db,'a@example.com','long-alpha-password');y=t.login(self.db,'b@example.com','long-beta-password')
  self.assertEqual(t.identity(self.db,x)['tenant_id'],self.a)
  self.assertEqual(t.identity(self.db,y)['tenant_id'],self.b)
  t.upsert_device(self.db,self.a,{'device_id':'miner1','name':'Alpha','hashrate_ths':100})
  self.assertEqual(len(t.list_devices(self.db,self.a)),1);self.assertEqual(t.list_devices(self.db,self.b),[])
  t.upsert_device(self.db,self.b,{'device_id':'miner1','name':'Beta','hashrate_ths':90})
  self.assertEqual(t.list_devices(self.db,self.a)[0]['name'],'Alpha')
 def test_wrong_password(self):self.assertIsNone(t.login(self.db,'a@example.com','wrong'))
 def test_invalid_device(self):
  with self.assertRaises(ValueError):t.upsert_device(self.db,self.a,{'device_id':'bad/id','name':'Bad','hashrate_ths':1})
 def test_expired_session(self):
  token=t.login(self.db,'a@example.com','long-alpha-password')
  with t.dbconn(self.db) as db:db.execute('UPDATE tenant_sessions SET expires=0')
  self.assertIsNone(t.identity(self.db,token))
 def test_weak_password(self):
  with self.assertRaises(ValueError):t.provision(self.db,'Gamma','g@example.com','short')
if __name__=='__main__':unittest.main()
