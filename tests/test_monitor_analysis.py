import unittest
from integrations.monitor_analysis import detect_changes, profitability

class AnalysisTests(unittest.TestCase):
    def test_new_offline(self):
        old = [{"name": "rig1", "state": "ok"}]
        new = [{"name": "rig1", "state": "off"}]
        self.assertEqual(len(detect_changes(old, new)), 1)
        self.assertEqual(detect_changes(new, new), [])
    def test_low_state(self):
        self.assertEqual(detect_changes([], [{"name":"rig2","state":"low"}])[0]["state"], "low")
    def test_daily_profit(self):
        result = profitability(3, 0.10, 12)
        self.assertAlmostEqual(result["electricity_usd_per_day"], 7.2)
        self.assertAlmostEqual(result["net_usd_per_day"], 4.8)
    def test_downtime(self):
        result = profitability(3, 0.10, 12, 0.5)
        self.assertAlmostEqual(result["net_usd_per_day"], 2.4)
    def test_invalid(self):
        for value in (-1, "NaN", "Infinity"):
            with self.assertRaises(ValueError):
                profitability(value, 0.1, 10)

if __name__ == "__main__":
    unittest.main()
