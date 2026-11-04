# Electrum XRP

A desktop XRP Ledger wallet for **Windows and Linux**, built with Python, PySide6 (Qt), and the official `xrpl-py` SDK.

This is a new implementation. It does not contain the source or commit history of the unavailable earlier Electrum XRP projects, and is not affiliated with the Bitcoin Electrum project or Ripple.

## Features

- Create a wallet or import an XRPL family seed.
- Watch a public address without loading signing keys.
- View the validated XRP balance, account reserve, and available balance before fees.
- Read the latest 20 transactions returned by the selected server.
- Receive XRP using a classic address and copy the public address.
- Send native XRP with an optional destination tag, local signing, and a confirmation showing the amount, network, recipient, fee, and expiry ledger.
- Switch between Testnet (default) and Mainnet.
- Lock the wallet to discard the application's reference to its signing keys and continue in watch-only mode.

**Version 0.1.0 is an initial development version, not an audited production wallet. Start with Testnet.** Tokens, NFTs, multisignature, hardware wallets, BIP39 phrases, and X-addresses are not supported.

## Run from source

Use **Python 3.12 or newer**. Python 3.12 is used for Windows and Linux CI builds.

### Windows (PowerShell)

```powershell
git clone https://github.com/xrpl-devs/electrum-xrp.git
cd electrum-xrp
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_wallet.py
```

### Linux (Ubuntu 22.04 or newer)

Install Python 3.12+ with its `venv` module using your distribution's packages, and the Qt runtime libraries:

```bash
sudo apt-get install libegl1 libopengl0 libxkbcommon0 libxcb-cursor0
git clone https://github.com/xrpl-devs/electrum-xrp.git
cd electrum-xrp
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run_wallet.py
```

Use a graphical desktop session to open the application. Other distributions need equivalent Qt/X11 runtime packages.

## First use

1. Leave the network set to **Testnet**.
2. Select **New wallet**, reveal the seed, and store a private backup before confirming. To reopen it later, choose **Import seed**.
3. In **Receive**, copy your public address and open the official Testnet faucet to request test XRP.
4. Refresh the balance. An account is not active until it has received enough XRP to meet the network's reserve.
5. In **Send XRP**, enter the recipient, XRP amount, and destination tag if required. Review every field before confirming.

Mainnet and Testnet have separate balances. Test XRP has no monetary value. Mainnet transactions use real XRP and cannot be undone by this application.

## Key handling and payments

Seeds and signing keys are held only in process memory; the application does not write a wallet file, log secrets, or send the seed to a server. **Keep your seed backup: closing or locking a signing wallet requires importing it again.** Python does not guarantee secure erasure of memory, and this version has no encrypted vault or automatic lock timer.

Account data is requested over HTTPS from public XRPL servers configured in `electrum_xrp/core.py`. These servers can see your address and IP. Signing happens locally. The application reads reserve values from the server, checks the amount plus fee against the available balance, and rejects a prepared fee greater than 0.1 XRP. Ledger rules remain authoritative at submission time.

A successful payment requires a validated ledger result of `tesSUCCESS`. If submission times out, the application shows the transaction hash: check its status on the selected network before retrying. A failed validated transaction may still consume a network fee.

## Build a standalone application

Install the build dependencies in the same virtual environment:

```bash
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean ElectrumXRP.spec
```

Use the virtual environment's Python (`.venv/bin/python` on Linux or `.\.venv\Scripts\python.exe` on Windows).

| Build host | Output |
| --- | --- |
| Windows x64 | `dist/ElectrumXRP/ElectrumXRP.exe` |
| Linux x64 | `dist/ElectrumXRP/ElectrumXRP` |

Distribute the **entire `dist/ElectrumXRP` folder**, including `_internal`. Python does not need to be installed on the destination machine. Qt/system runtime requirements still apply. Build Windows on Windows and Linux on Linux; PyInstaller is not a cross-compiler. Linux bundles should be built on the oldest distribution you intend to support.

The [Build desktop wallet workflow](https://github.com/xrpl-devs/electrum-xrp/actions/workflows/build.yml) runs tests, builds both platforms, smoke-tests the executables, and uploads ZIP/tar.gz artifacts. Download them from a successful Actions run. This workflow does not publish Releases, sign binaries, or create an installer.

## Development and tests

```bash
python -m unittest discover -s tests -v
python run_wallet.py --smoke-test
```

For a headless Linux smoke test, prefix the command with `QT_QPA_PLATFORM=offscreen`. Unit tests use mocked ledger responses and do not spend funds. They cover input validation, seed import, reserve and fee checks, local signing, validated results, and ambiguous submission failures. They are not an end-to-end Mainnet payment test.

```text
electrum_xrp/app.py    Qt interface and background jobs
electrum_xrp/core.py   XRPL queries, payment validation, and local signing
tests/                Automated tests
ElectrumXRP.spec       PyInstaller build configuration
.github/workflows/    Windows and Linux CI builds
```

## Feedback

Use [GitHub Issues](https://github.com/xrpl-devs/electrum-xrp/issues) for bugs and feature requests. Include the application version, operating system, selected network, and reproduction steps. Never attach a seed, private key, or wallet backup.

## References

- [XRPL public servers](https://xrpl.org/docs/tutorials/public-servers)
- [xrpl-py documentation](https://xrpl-py.readthedocs.io/)
- [PySide6 documentation](https://doc.qt.io/qtforpython-6/)
- [PyInstaller build model](https://pyinstaller.org/en/stable/operating-mode.html)
