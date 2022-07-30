from decimal import Decimal

from django.db import models
from django.db.models import Sum

from django.dispatch import receiver
from django.db.models import signals

from coasc import exceptions


class ImpersonalAccount(models.Model):
    ASSET = 'AS'
    LIABILITY = 'LI'
    INCOME = 'IN'
    EXPENSES = 'EX'
    TYPE_AC_CHOICES = [
        (ASSET, 'Asset'),
        (LIABILITY, 'Liability'),
        (INCOME, 'Income'),
        (EXPENSES, 'Expense'),
    ]
    name = models.CharField(max_length=255)
    parent_ac = models.ForeignKey(
            'self', null=True, blank=True, default=None,
            on_delete=models.PROTECT)
    type_ac = models.CharField(
            max_length=2, blank=True, choices=TYPE_AC_CHOICES)
    code = models.CharField(
            max_length=255, blank=True, null=True, default=None, unique=True)

    def save(self, *args, **kwargs):
        if not self.parent_ac and not self.type_ac:
            raise exceptions.OrphanAccountCreationError(
                    'must have a parent or type')
        if self.parent_ac == self:
            raise exceptions.SelfReferencingError(
                    'self cannot be a parent of self')
        if self.parent_ac and self.type_ac:
            raise exceptions.AccountTypeOnChildAccountError(
                    'manually setting type on a child not allowed')
        if self.parent_ac:
            self.type_ac = self.parent_ac.type_ac
        super(ImpersonalAccount, self).save(*args, **kwargs)

    def __simple_balance(self):
        account_splits = self.split_set.all()
        dr_splits = account_splits.filter(type_split='dr')
        cr_splits = account_splits.filter(type_split='cr')
        dr_sum = dr_splits.aggregate(
                dr_sum=Sum('amount'))['dr_sum'] or Decimal(0)
        cr_sum = cr_splits.aggregate(
                cr_sum=Sum('amount'))['cr_sum'] or Decimal(0)
        difference = dr_sum - cr_sum
        return {'dr_sum': dr_sum, 'cr_sum': cr_sum, 'difference': difference}

    def __accumulated_balance(self):
        dr_sum = Decimal(0)
        cr_sum = Decimal(0)
        for account in self.impersonalaccount_set.all():
            if account.who_am_i()['parent']:
                recursion_balances = account.__accumulated_balance()
                dr_sum += recursion_balances['dr_sum']
                cr_sum += recursion_balances['cr_sum']
            account_splits = account.split_set.all()
            dr_splits = account_splits.filter(type_split='dr')
            cr_splits = account_splits.filter(type_split='cr')
            dr_sum += dr_splits.aggregate(
                    dr_sum=Sum('amount'))['dr_sum'] or Decimal(0)
            cr_sum += cr_splits.aggregate(
                    cr_sum=Sum('amount'))['cr_sum'] or Decimal(0)
        difference = dr_sum - cr_sum
        return {'dr_sum': dr_sum, 'cr_sum': cr_sum, 'difference': difference}

    def who_am_i(self):
        ac = dict.fromkeys(['parent', 'child', 'single'], None)
        if self.impersonalaccount_set.exists():
            ac['parent'] = True
            return ac
        if self.parent_ac:
            ac['child'] = True
            return ac
        if not self.impersonalaccount_set.exists() and not self.parent_ac:
            ac['single'] = True
            return ac

    def current_balance(self):
        ac = self.who_am_i()
        if ac['parent']:
            return self.__accumulated_balance()
        if ac['single'] or ac['child']:
            return self.__simple_balance()

    @staticmethod
    def total_current_balance():
        accounts = ImpersonalAccount.objects.all()
        tds = Decimal(0)
        tcs = Decimal(0)
        for account in accounts:
            ac = account.who_am_i()
            if ac['child']:
                continue
            balances = account.current_balance()
            tds += balances['dr_sum']
            tcs += balances['cr_sum']
        diff = tds - tcs
        return {'total_dr_sum': tds, 'total_cr_sum': tcs, 'difference': diff}

    @classmethod
    def validate_accounting_equation(cls):
        total_balances = cls.total_current_balance()
        if total_balances['difference'] != 0:
            raise exceptions.AccountingEquationViolationError(
                    'Dr, Cr side not balanced; equation, "AS=LI+CA" not true;')


class Transaction(models.Model):
    description = models.TextField(blank=True, default='')


class Split(models.Model):
    DEBIT = 'dr'
    CREDIT = 'cr'
    TYPE_SPLIT_CHOICES = [
        (DEBIT, 'Debit'),
        (CREDIT, 'Credit'),
    ]
    transaction = models.ForeignKey(
            Transaction, on_delete=models.PROTECT)
    account = models.ForeignKey(ImpersonalAccount, on_delete=models.PROTECT)
    type_split = models.CharField(max_length=2, choices=TYPE_SPLIT_CHOICES)
    amount = models.DecimalField(decimal_places=2, max_digits=11)


@receiver(signals.pre_save, sender=Split)
def check_for_exceptions(sender, **kwargs):
    split_instance = kwargs['instance']
    if (split_instance.account.who_am_i())['parent']:
        raise exceptions.TransactionOnParentAcError(
                'transaction on parent not allowed')
    if split_instance.amount <= 0:
        raise exceptions.ZeroAmountError(
                'amount must be greater than 0')
