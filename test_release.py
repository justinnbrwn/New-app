import unittest
from pathlib import Path
import bridge

class ReleaseTests(unittest.TestCase):
    def test_health_endpoint_present(self):
        self.assertIn("if path=='/healthz'", Path(bridge.__file__).read_text())
    def test_android_https_required(self):
        root=Path(__file__).parent
        source=(root/'android/app/src/main/java/com/hashmargin/pro/MainActivity.kt').read_text()
        self.assertIn('target.startsWith("https://")',source)
        self.assertIn('url.port == origin.port',source)
    def test_android_cleartext_disabled(self):
        manifest=(Path(__file__).parent/'android/app/src/main/AndroidManifest.xml').read_text()
        self.assertIn('android:usesCleartextTraffic="false"',manifest)
    def test_local_only_compose(self):
        data=(Path(__file__).parent/'compose.yaml').read_text()
        self.assertIn('HASHMARGIN_HOST: 127.0.0.1',data)
        self.assertNotIn('ports:',data)

if __name__=='__main__':unittest.main()
