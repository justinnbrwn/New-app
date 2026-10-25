import unittest
from unittest.mock import patch,MagicMock
import bridge
class ASICReadOnlyTests(unittest.TestCase):
 def test_json_ghs(self):self.assertAlmostEqual(bridge.parse_cgminer_summary('{"SUMMARY":[{"GHS 5s":95000}]}'),95)
 def test_legacy_mhs(self):self.assertAlmostEqual(bridge.parse_cgminer_summary('SUMMARY,MHS 5s=95000000,Accepted=12|STATUS,S=Alive'),95)
 def test_reject_public_ip(self):
  with self.assertRaises(ValueError):bridge.validated_lan_ip('8.8.8.8')
 def test_reject_hostname(self):
  with self.assertRaises(ValueError):bridge.validated_lan_ip('example.com')
 def test_reject_bad_data(self):
  with self.assertRaises(ValueError):bridge.parse_cgminer_summary('{"SUMMARY":[{"GHS 5s":"NaN"}]}')
 def test_poll_sends_summary_only(self):
  sock=MagicMock();sock.recv.side_effect=[b'{"SUMMARY":[{"GHS 5s":90000}]}\x00'];sock.__enter__.return_value=sock
  with patch('bridge.socket.create_connection',return_value=sock),patch('bridge.ingest') as ingest:
   out=bridge.poll_asic('test','192.168.1.10')
   self.assertEqual(out['hashrate_ths'],90)
   sock.sendall.assert_called_once_with(b'{"command":"summary"}')
   self.assertEqual(ingest.call_args.kwargs['source'],'cgminer-summary-power-unknown')
if __name__=='__main__':unittest.main()
