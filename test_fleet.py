import os,tempfile,unittest
from pathlib import Path
import bridge
class FleetTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();bridge.DB=Path(self.tmp.name)/'test.sqlite3';bridge.init_db()
 def tearDown(self):self.tmp.cleanup()
 def test_unknown_power_not_fabricated(self):
  bridge.ingest({'device_id':'pool1','name':'pool1','hashrate_ths':100,'watts':0},source='braiins-pool-worker')
  bridge.configure_device({'device_id':'pool1','electricity_usd_kwh':.12,'btc_per_th_day':.000001,'btc_price_usd':80000,'pool_fee_percent':2,'other_usd_day':0})
  v=bridge.fleet_economics();self.assertIsNone(v['miners'][0]['net_usd_day']);self.assertEqual(v['coverage']['modeled'],0)
 def test_modeled_device(self):
  bridge.ingest({'device_id':'asic1','name':'asic1','hashrate_ths':100,'watts':3000})
  bridge.configure_device({'device_id':'asic1','electricity_usd_kwh':.12,'btc_per_th_day':.000001,'btc_price_usd':80000,'pool_fee_percent':2,'other_usd_day':0})
  v=bridge.fleet_economics();self.assertEqual(v['coverage']['modeled'],1);self.assertLess(float(v['known_estimated_net_usd_day']),0)
 def test_invalid_settings(self):
  bridge.ingest({'device_id':'asic1','hashrate_ths':1,'watts':100})
  with self.assertRaises(ValueError):bridge.configure_device({'device_id':'asic1','electricity_usd_kwh':-1,'btc_per_th_day':0,'btc_price_usd':0,'pool_fee_percent':0,'other_usd_day':0})
if __name__=='__main__':unittest.main()
