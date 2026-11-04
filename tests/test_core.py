import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

from xrpl.models.response import Response, ResponseStatus
from xrpl.models.transactions import Payment
from xrpl.wallet import Wallet

from electrum_xrp.core import (
    AccountSnapshot, Ledger, amount_to_drops, destination_tag, import_wallet,
    validate_address,
)


class InputTests(unittest.TestCase):
    def test_exact_drops(self):
        self.assertEqual(amount_to_drops('0.000001'), '1')
        self.assertEqual(amount_to_drops('1.123456'), '1123456')
        self.assertEqual(amount_to_drops(' 10 '), '10000000')

    def test_reject_invalid_or_fractional_drops(self):
        for text in ['NaN', 'Infinity', '-1', '0', '0.0000001', '', '1,2', '1e1000000',
                     '1e-1000000', '1.0000000000000000000000000000000001']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                amount_to_drops(text)

    def test_tag_boundaries_and_zero(self):
        self.assertIsNone(destination_tag(' '))
        self.assertEqual(destination_tag('0'), 0)
        self.assertEqual(destination_tag('4294967295'), 4294967295)
        for text in ['-1', '4294967296', '1.0', 'abc', '²']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                destination_tag(text)

    def test_seed_round_trip_and_sanitized_error(self):
        wallet = Wallet.create()
        self.assertEqual(import_wallet(wallet.seed).classic_address, wallet.classic_address)
        with self.assertRaises(ValueError) as error:
            import_wallet('secret-input-that-must-not-be-displayed')
        self.assertNotIn('secret-input', str(error.exception))
        self.assertEqual(validate_address(wallet.classic_address), wallet.classic_address)
        with self.assertRaises(ValueError):
            validate_address('invalid')


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.wallet = Wallet.create()
        self.target = Wallet.create().classic_address
        self.ledger = Ledger('Testnet')
        self.tx = Payment(account=self.wallet.classic_address, destination=self.target,
                          amount='1000000', fee='12', sequence=1, last_ledger_sequence=100)

    def test_unactivated_account_is_not_a_connection_failure(self):
        self.ledger.client = Mock()
        self.ledger.client.request.return_value = Response(
            status=ResponseStatus.ERROR, result={'error': 'actNotFound'})
        self.assertFalse(self.ledger.snapshot(self.wallet.classic_address).activated)

    def test_reserve_comes_from_server(self):
        def success(result):
            return Response(status=ResponseStatus.SUCCESS, result=result)
        self.ledger.client = Mock()
        self.ledger.client.request.side_effect = [
            success({'account_data': {'Balance': '20000000', 'OwnerCount': 3}}),
            success({'info': {'validated_ledger': {'reserve_base_xrp': 1, 'reserve_inc_xrp': 0.2}}}),
            success({'transactions': []}),
        ]
        snapshot = self.ledger.snapshot(self.wallet.classic_address)
        self.assertEqual(snapshot.reserve, Decimal('1.6'))
        self.assertEqual(snapshot.available, Decimal('18.4'))

    @patch('electrum_xrp.core.autofill')
    def test_prepare_preserves_zero_tag_and_checks_fee(self, autofill):
        autofill.return_value = self.tx
        with patch.object(self.ledger, 'snapshot', return_value=AccountSnapshot(
            Decimal(10), Decimal(1), Decimal(9), True, [])):
            self.ledger.prepare(self.wallet.classic_address, self.target, '1', '0')
        self.assertEqual(autofill.call_args.args[0].destination_tag, 0)
        autofill.return_value = Payment(account=self.wallet.classic_address,
                                       destination=self.target, amount='1000000',
                                       fee='100001', sequence=1, last_ledger_sequence=100)
        with self.assertRaisesRegex(ValueError, 'fee'):
            self.ledger.prepare(self.wallet.classic_address, self.target, '1', '')

    @patch('electrum_xrp.core.autofill')
    def test_amount_plus_fee_must_fit_above_reserve(self, autofill):
        autofill.return_value = self.tx
        with patch.object(self.ledger, 'snapshot', return_value=AccountSnapshot(
            Decimal(2), Decimal(1), Decimal(1), True, [])):
            with self.assertRaisesRegex(ValueError, 'Insufficient'):
                self.ledger.prepare(self.wallet.classic_address, self.target, '1', '')

    @patch('electrum_xrp.core.submit_and_wait')
    def test_signs_locally_and_requires_validated_success(self, submit):
        submit.return_value = Response(status=ResponseStatus.SUCCESS,
            result={'validated': True, 'meta': {'TransactionResult': 'tesSUCCESS'}})
        tx_hash = self.ledger.send(self.tx, self.wallet)
        self.assertEqual(len(tx_hash), 64)
        signed = submit.call_args.args[0]
        self.assertTrue(signed.txn_signature)
        self.assertFalse(submit.call_args.kwargs['autofill'])
        submit.return_value = Response(status=ResponseStatus.SUCCESS,
            result={'validated': True, 'meta': {'TransactionResult': 'tecDST_TAG_NEEDED'}})
        with self.assertRaisesRegex(RuntimeError, 'tecDST_TAG_NEEDED'):
            self.ledger.send(self.tx, self.wallet)

    @patch('electrum_xrp.core.submit_and_wait', side_effect=TimeoutError)
    def test_timeout_includes_hash_and_does_not_retry(self, submit):
        with self.assertRaisesRegex(RuntimeError, 'status is unknown'):
            self.ledger.send(self.tx, self.wallet)
        submit.assert_called_once()


if __name__ == '__main__':
    unittest.main()
