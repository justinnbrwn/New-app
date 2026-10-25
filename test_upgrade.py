import unittest
import tempfile
from pathlib import Path
import bridge

class UpgradeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();bridge.DB=Path(self.tmp.name)/'test.db';bridge.init_db()
 def tearDown(self):self.tmp.cleanup()
 def test_profit(self):
  x=bridge.profitability(dict(hashrate_ths=100,watts=3000,btc_per_th_day='0.00000045',btc_price_usd=80000,electricity_usd_kwh='0.1',pool_fee_percent=2,uptime_percent=100,other_usd_day=0))
  self.assertEqual(x['net_usd_day'],'-3.67200000')
 def test_zero_yield(self):
  x=bridge.profitability(dict(hashrate_ths=0,watts=3000,btc_per_th_day=0,btc_price_usd=80000,electricity_usd_kwh='0.1',pool_fee_percent=2,uptime_percent=100,other_usd_day=0))
  self.assertIsNone(x['break_even_btc_usd'])
 def test_braiins_normalize(self):
  x=bridge.normalize_braiins_workers({'btc':{'workers':{'a.worker':{'hash_rate_unit':'Gh/s','hash_rate_5m':95000,'state':'ok'}}}})
  self.assertEqual(x[0]['hashrate_ths'],95.0)
  self.assertEqual(x[0]['watts'],0)
 def test_history(self):
  bridge.ingest(dict(device_id='test',hashrate_ths=80,watts=2800))
  with bridge.connect() as db:self.assertEqual(db.execute('select count(*) from samples').fetchone()[0],1)
 def test_negative(self):
  with self.assertRaises(ValueError):bridge.profitability(dict(hashrate_ths=-1,watts=1,btc_per_th_day=0,btc_price_usd=1,electricity_usd_kwh=1,pool_fee_percent=0,uptime_percent=100,other_usd_day=0))
if __name__=='__main__':unittest.main()
