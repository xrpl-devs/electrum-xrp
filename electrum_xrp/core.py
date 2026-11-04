"""Ledger access and local signing. No secrets are persisted or logged."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from xrpl.clients import JsonRpcClient
from xrpl.core.addresscodec import is_valid_classic_address
from xrpl.models.requests import AccountInfo, AccountTx, ServerInfo
from xrpl.models.transactions import Payment
from xrpl.transaction import autofill, sign, submit_and_wait
from xrpl.wallet import Wallet

NETWORKS = {
    "Testnet": "https://s.altnet.rippletest.net:51234/",
    "Mainnet": "https://xrplcluster.com/",
}
MAX_FEE_DROPS = 100_000


def amount_to_drops(value: str) -> str:
    try:
        if len(value) > 64:
            raise ValueError
        amount = Decimal(value.strip())
        if not amount.is_finite() or amount < Decimal('0.000001') or amount > 100_000_000_000:
            raise ValueError
        if amount != amount.quantize(Decimal('0.000001')):
            raise ValueError
        drops = amount * 1_000_000
        if drops != drops.to_integral_value():
            raise ValueError
        return str(int(drops))
    except (InvalidOperation, ValueError, OverflowError):
        raise ValueError("Enter a positive XRP amount with at most 6 decimal places.") from None


def destination_tag(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    if not value.isascii() or not value.isdigit() or len(value) > 10:
        raise ValueError("Destination tag must be an integer from 0 to 4294967295.")
    tag = int(value)
    if tag > 4_294_967_295:
        raise ValueError("Destination tag must be an integer from 0 to 4294967295.")
    return tag


def validate_address(value: str) -> str:
    address = value.strip()
    if not is_valid_classic_address(address):
        raise ValueError("Enter a valid classic XRP address starting with r. X-addresses are not supported.")
    return address


def import_wallet(seed: str) -> Wallet:
    try:
        return Wallet.from_seed(seed.strip())
    except Exception:
        raise ValueError("Invalid XRPL family seed. BIP39 recovery phrases are not supported.") from None


@dataclass(frozen=True)
class AccountSnapshot:
    balance: Decimal
    reserve: Decimal
    available: Decimal
    activated: bool
    transactions: list[dict]


class Ledger:
    def __init__(self, network: str):
        self.network = network
        self.client = JsonRpcClient(NETWORKS[network])

    def _request(self, request):
        response = self.client.request(request)
        if not response.is_successful():
            code = response.result.get("error", "unknown")
            raise RuntimeError(f"Ledger request failed: {code}")
        return response.result

    def snapshot(self, address: str) -> AccountSnapshot:
        response = self.client.request(AccountInfo(account=address, ledger_index="validated"))
        if response.result.get("error") == "actNotFound":
            return AccountSnapshot(Decimal(0), Decimal(0), Decimal(0), False, [])
        if not response.is_successful():
            raise RuntimeError("Could not load the account from the selected network.")
        account = response.result["account_data"]
        info = self._request(ServerInfo())["info"]["validated_ledger"]
        reserve = Decimal(str(info["reserve_base_xrp"])) + (
            Decimal(str(info["reserve_inc_xrp"])) * int(account.get("OwnerCount", 0))
        )
        balance = Decimal(account["Balance"]) / 1_000_000
        history = self._request(AccountTx(account=address, ledger_index_min=-1,
                                          ledger_index_max=-1, limit=20, forward=False))
        return AccountSnapshot(balance, reserve, max(Decimal(0), balance - reserve),
                               True, history.get("transactions", []))

    def prepare(self, source: str, target: str, amount: str, tag: str) -> Payment:
        target = validate_address(target)
        if source == target:
            raise ValueError("Choose a destination different from this wallet.")
        drops = amount_to_drops(amount)
        tx = autofill(Payment(account=source, destination=target, amount=drops,
                              destination_tag=destination_tag(tag)), self.client)
        if tx.fee is None or int(tx.fee) <= 0 or int(tx.fee) > MAX_FEE_DROPS:
            raise ValueError("Network fee exceeds the application limit of 0.1 XRP.")
        if tx.last_ledger_sequence is None:
            raise ValueError("The server did not provide a transaction expiry ledger.")
        snapshot = self.snapshot(source)
        total = (Decimal(drops) + Decimal(tx.fee)) / 1_000_000
        if not snapshot.activated or total > snapshot.available:
            raise ValueError("Insufficient XRP after the account reserve and network fee.")
        return tx

    def send(self, tx: Payment, wallet: Wallet) -> str:
        if tx.account != wallet.classic_address:
            raise ValueError("The signing wallet does not match this payment.")
        signed = sign(tx, wallet)
        tx_hash = signed.get_hash()
        try:
            response = submit_and_wait(signed, self.client, autofill=False)
        except Exception:
            raise RuntimeError(
                f"Submission status is unknown. Check transaction {tx_hash} on {self.network} "
                "before trying again; the payment may have been submitted."
            ) from None
        result = response.result
        meta = result.get("meta", {})
        code = meta.get("TransactionResult") if isinstance(meta, dict) else None
        if not result.get("validated") or code != "tesSUCCESS":
            raise RuntimeError(f"Payment was not confirmed successful ({code or 'unknown'}). "
                               f"Transaction: {tx_hash}. Check its status before retrying.")
        return tx_hash
