from decimal import Decimal
from django.test import TestCase

from coasc.models import ImpersonalAccount
from coasc import exceptions
from coasc.models import Transaction, Split


class AccountModelTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.single_ac1 = ImpersonalAccount.objects.create(
                name='single ac1', type_ac='AS', code='1')
        cls.parent_ac1 = ImpersonalAccount.objects.create(
                name='parent ac1', type_ac='LI', code='2')
        cls.child_ac1 = ImpersonalAccount.objects.create(
                name='child ac1', parent_ac=cls.parent_ac1, code='2.1')
        cls.child_ac2 = ImpersonalAccount.objects.create(
                name='child ac2', parent_ac=cls.parent_ac1, code='2.2')

        cls.transaction1 = Transaction.objects.create(
                description='transaction1')

    def test_create_and_retreive_accounts(self):
        saved_accounts = ImpersonalAccount.objects.all()

        self.assertEqual(saved_accounts.count(), 4)
        self.assertEqual(saved_accounts[0].name, 'single ac1')
        self.assertEqual(saved_accounts[0].parent_ac, None)
        self.assertEqual(saved_accounts[0].type_ac, 'AS')
        self.assertEqual(saved_accounts[0].code, '1')

        self.assertEqual(saved_accounts[1].name, 'parent ac1')
        self.assertEqual(saved_accounts[1].parent_ac, None)
        self.assertEqual(saved_accounts[1].type_ac, 'LI')
        self.assertEqual(saved_accounts[1].code, '2')

        self.assertEqual(saved_accounts[2].name, 'child ac1')
        self.assertEqual(saved_accounts[2].parent_ac, self.parent_ac1)
        self.assertEqual(saved_accounts[2].type_ac, 'LI')
        self.assertEqual(saved_accounts[2].code, '2.1')

    def test_raises_exception_if_type_ac_set_manually_on_child_ac(self):
        with self.assertRaises(exceptions.AccountTypeOnChildAccountError):
            ImpersonalAccount.objects.create(
                    name='child ac2', parent_ac=self.parent_ac1, type_ac='LI',
                    code='2.2')

    def test_raises_exception_if_parent_ac_selected_as_a_split_ac(self):
        Split.objects.create(
                transaction=self.transaction1, account=self.single_ac1,
                type_split='dr', amount=100)

        with self.assertRaises(exceptions.TransactionOnParentAcError):
            Split.objects.create(
                    transaction=self.transaction1, account=self.parent_ac1,
                    type_split='cr', amount=100)

    def test_who_am_i(self):
        ac1 = self.single_ac1.who_am_i()
        ac2 = self.parent_ac1.who_am_i()
        ac3 = self.child_ac1.who_am_i()

        self.assertTrue(ac1['single'] is True)
        self.assertTrue(ac2['parent'] is True)
        self.assertTrue(ac3['child'] is True)

    def test_current_balance(self):
        Split.objects.create(
                transaction=self.transaction1, account=self.single_ac1,
                type_split='dr', amount=100)
        Split.objects.create(
                transaction=self.transaction1, account=self.single_ac1,
                type_split='cr', amount=50)
        Split.objects.create(
                transaction=self.transaction1, account=self.child_ac1,
                type_split='dr', amount=200)
        Split.objects.create(
                transaction=self.transaction1, account=self.child_ac1,
                type_split='cr', amount=150)
        Split.objects.create(
                transaction=self.transaction1, account=self.child_ac2,
                type_split='dr', amount=300)
        Split.objects.create(
                transaction=self.transaction1, account=self.child_ac2,
                type_split='cr', amount=250)

        single_ac1_balance = self.single_ac1.current_balance()
        child_ac1_balance = self.child_ac1.current_balance()
        child_ac2_balance = self.child_ac2.current_balance()
        parent_ac1_balance = self.parent_ac1.current_balance()

        self.assertEqual(single_ac1_balance['dr_sum'], 100)
        self.assertEqual(single_ac1_balance['cr_sum'], 50)
        self.assertEqual(child_ac1_balance['dr_sum'], 200)
        self.assertEqual(child_ac1_balance['cr_sum'], 150)
        self.assertEqual(child_ac2_balance['dr_sum'], 300)
        self.assertEqual(child_ac2_balance['cr_sum'], 250)
        self.assertEqual(parent_ac1_balance['dr_sum'], 500)
        self.assertEqual(parent_ac1_balance['cr_sum'], 400)

    def test_total_current_balance_with_no_arguments(self):
        Split.objects.create(
                transaction=self.transaction1, account=self.single_ac1,
                type_split='dr', amount=100)
        Split.objects.create(
                transaction=self.transaction1, account=self.child_ac1,
                type_split='dr', amount=200)
        Split.objects.create(
                transaction=self.transaction1, account=self.child_ac2,
                type_split='dr', amount=300)
        Split.objects.create(
                transaction=self.transaction1, account=self.single_ac1,
                type_split='cr', amount=50)
        Split.objects.create(
                transaction=self.transaction1, account=self.child_ac1,
                type_split='cr', amount=150)
        Split.objects.create(
                transaction=self.transaction1, account=self.child_ac2,
                type_split='cr', amount=250)

        total_dr_sum = ImpersonalAccount.total_current_balance()[
                'total_dr_sum']
        total_cr_sum = ImpersonalAccount.total_current_balance()[
                'total_cr_sum']

        self.assertEqual(total_dr_sum, 600)
        self.assertEqual(total_cr_sum, 450)

    def test_total_current_balance_with_arguments(self):
        Split.objects.create(
                transaction=self.transaction1, account=self.single_ac1,
                type_split='dr', amount=100)
        Split.objects.create(
                transaction=self.transaction1, account=self.child_ac1,
                type_split='dr', amount=200)
        Split.objects.create(
                transaction=self.transaction1, account=self.child_ac2,
                type_split='dr', amount=300)
        Split.objects.create(
                transaction=self.transaction1, account=self.single_ac1,
                type_split='cr', amount=50)
        Split.objects.create(
                transaction=self.transaction1, account=self.child_ac1,
                type_split='cr', amount=150)
        Split.objects.create(
                transaction=self.transaction1, account=self.child_ac2,
                type_split='cr', amount=450)

        total_current_balance1 = ImpersonalAccount.total_current_balance(
                type_ac='AS')
        total_current_balance2 = ImpersonalAccount.total_current_balance(
                type_ac='LI')

        expected_total_current_balance1 = {
                'total_dr_sum': Decimal(100.00),
                'total_cr_sum': Decimal(50.00),
                'difference': Decimal(50.00)
        }
        expected_total_current_balance2 = {
                'total_dr_sum': Decimal(500.00),
                'total_cr_sum': Decimal(600.00),
                'difference': Decimal(-100.00)
        }

        self.assertEqual(
                total_current_balance1, expected_total_current_balance1)
        self.assertEqual(
                total_current_balance2, expected_total_current_balance2)

    def test_validate_accounting_equation(self):
        with self.assertRaises(
                exceptions.AccountingEquationViolationError):
            Split.objects.create(
                    transaction=self.transaction1, account=self.single_ac1,
                    type_split='dr', amount=100)
            Split.objects.create(
                    transaction=self.transaction1, account=self.child_ac1,
                    type_split='cr', amount=50)
            ImpersonalAccount.validate_accounting_equation()

    def test_raises_exception_if_ac_has_no_parent_and_type_ac(self):
        with self.assertRaises(exceptions.OrphanAccountCreationError):
            ImpersonalAccount.objects.create(
                    name='orphan_ac1', code='0')

    def test_raises_exception_if_ac_refrences_self_as_parent_ac(self):
        self_referencing_ac1 = ImpersonalAccount.objects.create(
                name='self_referencing_ac1', type_ac='AS', code='0')
        with self.assertRaises(exceptions.SelfReferencingError):
            self_referencing_ac1.parent_ac = self_referencing_ac1
            self_referencing_ac1.save()


class TransactionAndSplitModelTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.single_ac1 = ImpersonalAccount.objects.create(
                name='single_ac11', type_ac='AS', code='1')
        cls.parent_ac1 = ImpersonalAccount.objects.create(
                name='parent_ac1', type_ac='LI', code='2')
        cls.child_ac1 = ImpersonalAccount.objects.create(
                name='child_ac1', parent_ac=cls.parent_ac1, code='2.1')

        cls.transaction1 = Transaction.objects.create(
            description='transaction1')

    def test_create_and_retreive_transactions(self):
        saved_transactions = Transaction.objects.all()

        self.assertEqual(saved_transactions.count(), 1)
        self.assertEqual(
                saved_transactions[0].description, 'transaction1')

    def test_create_and_retreive_splits(self):
        Split.objects.create(
                transaction=self.transaction1, account=self.single_ac1,
                type_split='dr', amount=100)
        Split.objects.create(
                transaction=self.transaction1, account=self.child_ac1,
                type_split='cr', amount=100)

        saved_split = Split.objects.all()

        self.assertEqual(saved_split.count(), 2)
        self.assertEqual(saved_split[0].account, self.single_ac1)
        self.assertEqual(saved_split[0].type_split, 'dr')
        self.assertEqual(saved_split[0].amount, 100)

        self.assertEqual(saved_split[1].account, self.child_ac1)
        self.assertEqual(saved_split[1].type_split, 'cr')
        self.assertEqual(saved_split[1].amount, 100)

    def test_raises_exception_if_split_amount_zero(self):
        Split.objects.create(
                transaction=self.transaction1, account=self.single_ac1,
                type_split='dr', amount=100)
        with self.assertRaises(exceptions.ZeroAmountError):
            Split.objects.create(
                    transaction=self.transaction1, account=self.child_ac1,
                    type_split='cr', amount=0)
