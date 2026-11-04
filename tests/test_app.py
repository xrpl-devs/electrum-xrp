import os
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication
from electrum_xrp.app import Window


class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = Window()

    def tearDown(self):
        self.window.wallet = None
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def wait_for_job(self):
        deadline = time.monotonic() + 5
        while self.window.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertFalse(self.window.busy)

    def test_starts_on_testnet_without_signing_keys(self):
        self.assertEqual(self.window.network.currentText(), 'Testnet')
        self.assertFalse(self.window.send_button.isEnabled())
        self.assertEqual(self.window.tabs.count(), 4)

    def test_worker_completes_on_gui_thread(self):
        results = []
        self.window.run_job(lambda: 42,
            lambda value: results.append((value, QThread.currentThread())), 'Working')
        self.assertFalse(self.window.body.isEnabled())
        self.wait_for_job()
        self.assertEqual(results, [(42, self.app.thread())])
        self.assertTrue(self.window.body.isEnabled())

    def test_unexpected_errors_do_not_expose_inputs(self):
        def fail():
            raise Exception('sensitive-seed-value')
        with patch('electrum_xrp.app.QMessageBox.warning') as warning:
            self.window.run_job(fail, lambda _: None, 'Working')
            self.wait_for_job()
            warning.assert_called_once()
            self.assertNotIn('sensitive-seed-value', warning.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
