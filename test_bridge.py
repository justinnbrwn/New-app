import os
import tempfile
import unittest
from pathlib import Path
import bridge

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();bridge.DB=Path(self.tmp.name)/'test.sqlite';bridge.init_db()
    def tearDown(self):self.tmp.cleanup()
    def test_ingest_and_alerts(self):
        bridge.ingest({'device_id':'s19-1','name':'Garage','hashrate_ths':0,'watts':3000,'temperature_c':70})
        s=bridge.snapshot();self.assertEqual(s['miners'][0]['status'],'Low hashrate');self.assertEqual(s['alerts'][0]['kind'],'hashrate')
        bridge.ingest({'device_id':'s19-1','name':'Garage','hashrate_ths':100,'watts':3000,'temperature_c':70})
        self.assertEqual(bridge.snapshot()['alerts'],[])
    def test_invalid_values(self):
        for value in [-1,float('nan'),float('inf')]:
            with self.assertRaises(ValueError):bridge.ingest({'device_id':'m1','hashrate_ths':value,'watts':3000})
    def test_temperature(self):
        bridge.ingest({'device_id':'m2','hashrate_ths':100,'watts':3000,'temperature_c':90})
        self.assertEqual(bridge.snapshot()['alerts'][0]['kind'],'temperature')
    def test_offline(self):
        bridge.ingest({'device_id':'m3','hashrate_ths':100,'watts':3000})
        with bridge.connect() as db:db.execute('UPDATE miners SET last_seen=last_seen-1000')
        self.assertEqual(bridge.snapshot()['miners'][0]['status'],'Offline')

if __name__=='__main__':unittest.main()
