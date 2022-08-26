from decimal import Decimal

from django.db import models
from django.db.models import Sum

from django.dispatch import receiver
from django.db.models import signals

from coasc import exceptions


class ImpersonalAc(models.Model):
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
    p_ac = models.ForeignKey(
            'self', null=True, blank=True, default=None,
            on_delete=models.PROTECT)
    t_ac = models.CharField(max_length=2, blank=True, choices=TYPE_AC_CHOICES)
    code = models.CharField(
            max_length=255, blank=True, null=True, default=None, unique=True)

    def __str__(self):
        string = f'{self.name}->({self.code})'
        return string

    def who_am_i(self):
        ac_is = dict.fromkeys(['parent', 'child', 'single'], None)
        if not self.t_ac:
            ac_is['child'] = True
            return ac_is
        elif self.impersonalac_set.exists():
            ac_is['parent'] = True
            return ac_is
        elif self.t_ac and not self.impersonalac_set.exists():
            ac_is['single'] = True
            return ac_is
        else:
            return 'Something went wrong! Maybe this account should not exist'

    def bal(self):
        if self.who_am_i()['parent']:
            sps = Split.objects.filter(ac__p_ac=self)
        else:
            sps = self.split_set.all()

        dr_sps = sps.filter(t_sp='dr')
        cr_sps = sps.filter(t_sp='cr')

        dr_sum = dr_sps.aggregate(dr_sum=Sum('am'))['dr_sum'] or 0
        cr_sum = cr_sps.aggregate(cr_sum=Sum('am'))['cr_sum'] or 0
        diff = dr_sum - cr_sum

        return {'dr_sum': dr_sum, 'cr_sum': cr_sum, 'diff': diff}

    @classmethod
    def total_bal(cls, t_ac=None):
        if t_ac is None:
            acs = cls.objects.filter(p_ac=None)
        else:
            acs = cls.objects.filter(t_ac=t_ac)

        tds = Decimal(0)
        tcs = Decimal(0)
        for ac in acs:
            bals = ac.bal()
            tds += bals['dr_sum']
            tcs += bals['cr_sum']
        diff = tds - tcs

        return {'total_dr_sum': tds, 'total_cr_sum': tcs, 'diff': diff}

    @classmethod
    def validate_accounting_equation(cls):
        total_bals = cls.total_bal()
        if total_bals['diff'] != 0:
            raise exceptions.AccountingEquationViolationError(
                    'Dr, Cr side not balanced; equation, "AS=LI+CA" not true;')


@receiver(signals.pre_save, sender=ImpersonalAc)
def raise_exceptions_impersonalac(sender, **kwargs):
    ac_instance = kwargs['instance']
    if not ac_instance.p_ac and not ac_instance.t_ac:
        raise exceptions.OrphanAccountCreationError(
                'must have a parent or type')

    elif ac_instance.p_ac:
        if ac_instance.t_ac:
            raise exceptions.AccountTypeOnChildAccountError(
                    'type on a child not allowed')

        elif ac_instance.p_ac.split_set.exists():
            raise exceptions.SingleAccountIsNotParentError(
                    'single account cannot be a parent')


class Transaction(models.Model):
    desc = models.TextField(blank=True, default='')

    def __str__(self):
        string = f'{self.pk}->{self.split_set.count()}'
        return string


class Split(models.Model):
    DEBIT = 'dr'
    CREDIT = 'cr'
    TYPE_SPLIT_CHOICES = [
        (DEBIT, 'Debit'),
        (CREDIT, 'Credit'),
    ]
    tx = models.ForeignKey(Transaction, on_delete=models.PROTECT)
    ac = models.ForeignKey(ImpersonalAc, on_delete=models.PROTECT)
    t_sp = models.CharField(max_length=2, choices=TYPE_SPLIT_CHOICES)
    am = models.DecimalField(decimal_places=2, max_digits=11)

    def __str__(self):
        string = (f'{self.tx.pk}->{self.t_sp}={self.am}')
        return string


@receiver(signals.pre_save, sender=Split)
def raise_exceptions_split(sender, **kwargs):
    sp_instance = kwargs['instance']
    if (sp_instance.ac.who_am_i())['parent']:
        raise exceptions.TransactionOnParentAcError(
                'transaction on parent not allowed')
    if sp_instance.am <= 0:
        raise exceptions.ZeroAmountError('amount must be greater than 0')
