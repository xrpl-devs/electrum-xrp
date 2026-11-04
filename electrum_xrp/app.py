"""Qt desktop interface. All RPC calls run outside the UI thread."""

import sys
import webbrowser
from decimal import Decimal

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)
from xrpl.wallet import Wallet

from electrum_xrp import __version__
from electrum_xrp.core import Ledger, NETWORKS, import_wallet, validate_address


class JobSignals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Job(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.signals = JobSignals()

    def run(self):
        try:
            self.signals.done.emit(self.operation())
        except (ValueError, RuntimeError) as error:
            self.signals.failed.emit(str(error))
        except Exception:
            # Unexpected SDK/network exceptions must never expose secret inputs.
            self.signals.failed.emit("The request failed. Check your connection and try again.")
        finally:
            self.operation = None


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.wallet = None
        self.account = ""
        self.busy = False
        self.pool = QThreadPool(self)
        self.setWindowTitle(f"Electrum XRP · {__version__}")
        self.resize(940, 680)
        self.body = QWidget()
        self.setCentralWidget(self.body)
        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(28, 24, 28, 24)
        title = QLabel("Electrum XRP")
        title.setObjectName("title")
        layout.addWidget(title)
        layout.addWidget(QLabel("Your XRP Ledger desktop wallet"))
        toolbar = QHBoxLayout()
        self.network = QComboBox()
        self.network.addItems(NETWORKS)
        self.network.currentTextChanged.connect(self.network_changed)
        toolbar.addWidget(QLabel("Network"))
        toolbar.addWidget(self.network)
        toolbar.addStretch()
        for text, handler in [("New wallet", self.create_wallet),
                              ("Import seed", self.open_seed),
                              ("Watch address", self.watch), ("Lock", self.lock)]:
            button = QPushButton(text)
            button.clicked.connect(handler)
            toolbar.addWidget(button)
        layout.addLayout(toolbar)
        self.network_note = QLabel("Testnet · Test XRP has no monetary value.")
        layout.addWidget(self.network_note)
        self.address = QLineEdit()
        self.address.setReadOnly(True)
        self.address.setPlaceholderText("Create, import, or watch a wallet to get started")
        layout.addWidget(self.address)
        self.mode = QLabel("No wallet open")
        layout.addWidget(self.mode)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        overview = QWidget()
        box = QVBoxLayout(overview)
        self.balance = QLabel("— XRP")
        self.balance.setObjectName("balance")
        box.addWidget(self.balance)
        self.reserve = QLabel("Reserve: —  ·  Available before fees: —")
        box.addWidget(self.reserve)
        self.account_note = QLabel("Balances are read from validated ledgers.")
        self.account_note.setWordWrap(True)
        box.addWidget(self.account_note)
        self.refresh = QPushButton("Refresh balance and history")
        self.refresh.clicked.connect(self.load_account)
        box.addWidget(self.refresh)
        box.addStretch()
        self.tabs.addTab(overview, "Overview")
        send = QWidget()
        form = QFormLayout(send)
        self.destination = QLineEdit()
        self.destination.setPlaceholderText("r… classic XRP address")
        self.amount = QLineEdit()
        self.amount.setPlaceholderText("0.000001")
        self.tag = QLineEdit()
        self.tag.setPlaceholderText("Optional — check the recipient's instructions")
        form.addRow("Destination", self.destination)
        form.addRow("Amount (XRP)", self.amount)
        form.addRow("Destination tag", self.tag)
        self.send_button = QPushButton("Review payment")
        self.send_button.clicked.connect(self.prepare_payment)
        form.addRow(self.send_button)
        hint = QLabel("Only native XRP payments are supported. Confirm the network, address "
                      "and destination tag with the recipient before sending.")
        hint.setWordWrap(True)
        form.addRow(hint)
        self.tabs.addTab(send, "Send XRP")
        self.history = QTableWidget(0, 4)
        self.history.setHorizontalHeaderLabels(["Type", "Result", "Ledger", "Transaction hash"])
        self.history.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabs.addTab(self.history, "Recent activity")
        receive = QWidget()
        receive_layout = QVBoxLayout(receive)
        receive_layout.addWidget(QLabel("Your receiving address"))
        self.receive_address = QLineEdit()
        self.receive_address.setReadOnly(True)
        receive_layout.addWidget(self.receive_address)
        copy = QPushButton("Copy public address")
        copy.clicked.connect(self.copy_address)
        receive_layout.addWidget(copy)
        faucet = QPushButton("Open official Testnet faucet")
        faucet.clicked.connect(lambda: webbrowser.open("https://xrpl.org/resources/dev-tools/xrp-faucets"))
        receive_layout.addWidget(faucet)
        receive_layout.addWidget(QLabel("The faucet provides test XRP only. Never enter a seed on a website."))
        receive_layout.addStretch()
        self.tabs.addTab(receive, "Receive")
        footer = QLabel("Local signing · Seeds remain in this session · No automatic wallet storage")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        self.statusBar().showMessage("Ready · Testnet")
        self.update_controls()

    def ledger(self):
        return Ledger(self.network.currentText())

    def update_controls(self):
        self.refresh.setEnabled(bool(self.account))
        self.send_button.setEnabled(self.wallet is not None)

    def run_job(self, operation, completed, message):
        self.busy = True
        self.body.setEnabled(False)
        self.statusBar().showMessage(message)
        job = Job(operation)

        self._completed = completed
        job.signals.done.connect(self.job_done)
        job.signals.failed.connect(self.job_failed)
        self._job = job
        self.pool.start(job)

    def finish_job(self):
        self.busy = False
        self._job = None
        self.body.setEnabled(True)
        self.update_controls()
        self.statusBar().showMessage("Ready")

    @Slot(object)
    def job_done(self, result):
        completed = self._completed
        self._completed = None
        self.finish_job()
        completed(result)

    @Slot(str)
    def job_failed(self, message):
        self._completed = None
        self.finish_job()
        QMessageBox.warning(self, "Request failed", message)

    def replace_allowed(self):
        return self.wallet is None or QMessageBox.question(
            self, "Close current wallet?",
            "This will discard the current signing keys from this session. "
            "Make sure you have saved its seed before continuing.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def activate(self, address, wallet=None):
        self.wallet = wallet
        self.account = address
        self.address.setText(address)
        self.receive_address.setText(address)
        self.mode.setText("Signing wallet · session only" if wallet else "Watch-only · sending disabled")
        self.clear_balance()
        self.update_controls()
        self.load_account()

    def create_wallet(self):
        if not self.replace_allowed():
            return
        wallet = Wallet.create()
        dialog = QDialog(self)
        dialog.setWindowTitle("Back up your new wallet")
        dialog.setMinimumWidth(540)
        layout = QVBoxLayout(dialog)
        notice = QLabel("Write down this family seed and store it privately. It is the only way "
                        "to reopen this wallet. The application does not save it to disk.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        seed = QLineEdit(wallet.seed)
        seed.setReadOnly(True)
        seed.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(seed)
        reveal = QCheckBox("Show seed")
        reveal.toggled.connect(lambda shown: seed.setEchoMode(
            QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password))
        layout.addWidget(reveal)
        saved = QCheckBox("I saved my seed in a private place")
        layout.addWidget(saved)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        saved.toggled.connect(buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.activate(wallet.classic_address, wallet)
        seed.clear()
        dialog.deleteLater()

    def open_seed(self):
        if not self.replace_allowed():
            return
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Import wallet")
        dialog.setLabelText("XRPL family seed (not a BIP39 phrase):")
        dialog.setTextEchoMode(QLineEdit.EchoMode.Password)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                wallet = import_wallet(dialog.textValue())
                dialog.setTextValue("")
                self.activate(wallet.classic_address, wallet)
            except ValueError as error:
                QMessageBox.warning(self, "Invalid seed", str(error))
        dialog.setTextValue("")
        dialog.deleteLater()

    def watch(self):
        if not self.replace_allowed():
            return
        value, accepted = QInputDialog.getText(self, "Watch address", "Classic XRP address:")
        if accepted:
            try:
                self.activate(validate_address(value))
            except ValueError as error:
                QMessageBox.warning(self, "Invalid address", str(error))

    def lock(self):
        self.wallet = None
        self.mode.setText("Watch-only · signing keys discarded from the session" if self.account else "No wallet open")
        self.update_controls()

    def network_changed(self, network):
        self.network_note.setText("Testnet · Test XRP has no monetary value." if network == "Testnet"
                                  else "Mainnet · Payments use real XRP.")
        self.clear_balance()
        if self.account:
            self.load_account()

    def clear_balance(self):
        self.balance.setText("— XRP")
        self.reserve.setText("Reserve: —  ·  Available before fees: —")
        self.history.setRowCount(0)

    def load_account(self):
        if not self.account:
            return
        ledger, address = self.ledger(), self.account
        self.run_job(lambda: ledger.snapshot(address), self.show_account, "Loading validated account data…")

    def show_account(self, snapshot):
        self.balance.setText(f"{snapshot.balance:,.6f} XRP")
        self.reserve.setText(f"Reserve: {snapshot.reserve:f} XRP  ·  Available before fees: {snapshot.available:f} XRP")
        self.account_note.setText("Account active · last 20 transactions from the selected server."
                                  if snapshot.activated else "Account not activated on this network. "
                                  "Receive enough XRP to meet the network's current account reserve.")
        self.history.setRowCount(len(snapshot.transactions))
        for row, entry in enumerate(snapshot.transactions):
            tx = entry.get("tx_json", entry.get("tx", {}))
            meta = entry.get("meta", {})
            result = meta.get("TransactionResult", "—") if isinstance(meta, dict) else "—"
            values = [tx.get("TransactionType", "—"), result,
                      str(entry.get("ledger_index", tx.get("ledger_index", "—"))),
                      entry.get("hash", tx.get("hash", "—"))]
            for col, value in enumerate(values):
                self.history.setItem(row, col, QTableWidgetItem(str(value)))

    def copy_address(self):
        if self.account:
            QApplication.clipboard().setText(self.account)
            self.statusBar().showMessage("Public address copied", 4000)

    def prepare_payment(self):
        if self.wallet is None:
            return
        ledger = self.ledger()
        source, target, amount, tag = (self.account, self.destination.text(),
                                       self.amount.text(), self.tag.text())
        self.run_job(lambda: ledger.prepare(source, target, amount, tag),
                     lambda tx: self.confirm_payment(ledger, tx), "Preparing payment and checking reserve…")

    def confirm_payment(self, ledger, tx):
        message = (f"Network: {ledger.network}\nFrom: {tx.account}\nTo: {tx.destination}\n"
                   f"Amount: {Decimal(tx.amount) / 1_000_000:f} XRP\n"
                   f"Destination tag: {tx.destination_tag if tx.destination_tag is not None else 'Not set'}\n"
                   f"Fee: {Decimal(tx.fee) / 1_000_000:f} XRP\n"
                   f"Expires after ledger: {tx.last_ledger_sequence}\n\nSign and submit this payment?")
        if QMessageBox.question(self, "Confirm XRP payment", message,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        wallet = self.wallet
        self.run_job(lambda: ledger.send(tx, wallet), self.payment_sent,
                     "Submitting payment and waiting for validation. Keep the application open…")

    def payment_sent(self, tx_hash):
        self.amount.clear()
        QMessageBox.information(self, "Payment validated", f"Payment confirmed by the ledger.\n\n{tx_hash}")
        self.load_account()

    def closeEvent(self, event):
        if self.busy:
            QMessageBox.information(self, "Request in progress", "Wait for the current request to finish before closing.")
            event.ignore()
        elif self.replace_allowed():
            self.wallet = None
            event.accept()
        else:
            event.ignore()


STYLE = """
QWidget { background: #101827; color: #e7edf7; font-size: 14px; }
QLabel#title { font-size: 30px; font-weight: 700; color: #ffffff; }
QLabel#balance { font-size: 38px; font-weight: 600; padding: 24px 0; }
QLineEdit, QComboBox, QTableWidget { background: #172339; border: 1px solid #33445e;
    border-radius: 5px; padding: 9px; selection-background-color: #245ab5; }
QPushButton { background: #245ab5; border: 0; border-radius: 5px; padding: 10px 14px; }
QPushButton:hover { background: #3070d0; }
QPushButton:disabled { background: #28354a; color: #8694aa; }
QTabWidget::pane { border: 1px solid #33445e; padding: 14px; }
QTabBar::tab { background: #172339; padding: 12px 20px; }
QTabBar::tab:selected { background: #245ab5; }
QHeaderView::section { background: #172339; padding: 8px; border: 0; }
"""


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Electrum XRP")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    smoke_test = "--smoke-test" in sys.argv
    if smoke_test:
        # Exercise bundled crypto modules as well as the Qt startup path.
        from xrpl.models.transactions import Payment
        from xrpl.transaction import sign
        wallet = Wallet.create()
        assert import_wallet(wallet.seed).classic_address == wallet.classic_address
        tx = Payment(account=wallet.classic_address, destination=Wallet.create().classic_address,
                     amount="1000000", fee="12", sequence=1, last_ledger_sequence=100)
        assert len(sign(tx, wallet).get_hash()) == 64
    window = Window()
    window.show()
    if smoke_test:
        QTimer.singleShot(250, app.quit)
    sys.exit(app.exec())
