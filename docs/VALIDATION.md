# Validation of the initial implementation

- 13 automated tests cover input validation, family-seed round trips, live-reserve calculations with mocked responses, fee limits, local signing, validated results, timeout handling, and Qt background-job completion on the GUI thread.
- The source application starts with the Qt offscreen platform.
- A PyInstaller Linux bundle was built locally and started with the offscreen platform.
- Live Testnet account queries were exercised through `xrpl-py`.
- An ephemeral wallet was funded with free Testnet XRP, then sent 2 test XRP to a new account with destination tag 0. The result was validated successfully; the recipient's activation and balance were checked afterward.

Testnet payment hash:

```text
E9334DF807CAB657D2E860EBA7A7AEF5F5693077BF6C63483F02F13C5543D6D7
```

The test used no Mainnet funds. Testnet resets can remove this transaction later.

The GitHub Actions workflow builds and smoke-tests Windows and Linux separately. Local Linux checks do not establish Windows compatibility or constitute a security audit. The application has not been tested with Mainnet payments.
