from decimal import Decimal

from django.db import models
from django.db.models import Sum, signals
from django.dispatch import receiver

from coasc import exceptions


class Member(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=255, unique=True)

    def __str__(self):
        string = f"{self.name}->{self.code}"
        return string


class Ac(models.Model):
    ASSET = "AS"
    LIABILITY = "LI"
    INCOME = "IN"
    EXPENSES = "EX"

    CATEGORY_CHOICES = [
        (ASSET, "Asset"),
        (LIABILITY, "Liability"),
        (INCOME, "Income"),
        (EXPENSES, "Expense"),
    ]

    PERSONAL = "P"
    IMPERSONAL = "I"

    TYPE_AC_CHOICES = [
        (PERSONAL, "Personal"),
        (IMPERSONAL, "Impersonal"),
    ]

    name = models.CharField(max_length=255)
    t_ac = models.CharField(max_length=1, choices=TYPE_AC_CHOICES)
    p_ac = models.ForeignKey(
        "self", null=True, blank=True, default=None, on_delete=models.PROTECT
    )
    cat = models.CharField(max_length=2, blank=True, choices=CATEGORY_CHOICES)
    mem = models.ForeignKey(
        Member, null=True, blank=True, default=None, on_delete=models.PROTECT
    )
    code = models.CharField(
        max_length=255, blank=True, null=True, default=None, unique=True
    )

    def __str__(self):
        string = f"{self.name}->({self.code})"
        return string

    def who_am_i(self):
        ac_is = dict.fromkeys(["parent", "child", "single"], None)
        if not self.cat:
            ac_is["child"] = True
            return ac_is
        elif self.ac_set.exists():
            ac_is["parent"] = True
            return ac_is
        elif self.cat and not self.ac_set.exists():
            ac_is["single"] = True
            return ac_is
        else:
            return "Something went wrong! Maybe this account should not exist"

    def bal(self):
        if self.who_am_i()["parent"]:
            sps = Split.objects.filter(ac__p_ac=self)
        else:
            sps = self.split_set.all()

        dr_sps = sps.filter(t_sp="dr")
        cr_sps = sps.filter(t_sp="cr")

        dr_sum = dr_sps.aggregate(dr_sum=Sum("am"))["dr_sum"] or 0
        cr_sum = cr_sps.aggregate(cr_sum=Sum("am"))["cr_sum"] or 0
        diff = dr_sum - cr_sum

        return {"dr_sum": dr_sum, "cr_sum": cr_sum, "diff": diff}

    @classmethod
    def total_bal(cls, cat=None):
        # if no category in argument, get all parent and single accounts
        if cat is None:
            acs = cls.objects.filter(p_ac=None)
        # if category in argument, get parent and single accounts of that category
        # dont get child accounts regardless
        else:
            acs = cls.objects.filter(cat=cat)

        tds = Decimal(0)
        tcs = Decimal(0)
        for ac in acs:
            bals = ac.bal()
            tds += bals["dr_sum"]
            tcs += bals["cr_sum"]
        diff = tds - tcs

        return {"total_dr_sum": tds, "total_cr_sum": tcs, "diff": diff}

    @classmethod
    def validate_accounting_equation(cls):
        total_bals = cls.total_bal()
        if total_bals["diff"] != 0:
            raise exceptions.AccountingEquationViolationError(
                'Dr, Cr side not balanced; equation, "AS=LI+CA" not true;'
            )


@receiver(signals.pre_save, sender=Ac)
def raise_exceptions_ac(sender, **kwargs):
    ac_instance = kwargs["instance"]
    if not ac_instance.p_ac and not ac_instance.cat:
        raise exceptions.OrphanAccountCreationError("must have a parent or category")

    if ac_instance.p_ac:
        if ac_instance.cat:
            raise exceptions.AccountTypeOnChildAccountError(
                "category on a child not allowed"
            )

        elif ac_instance.p_ac.split_set.exists():
            raise exceptions.SingleAccountIsNotParentError(
                "single account cannot be a parent"
            )

    if ac_instance.t_ac == "P":
        if ac_instance.mem is None:
            raise exceptions.MemberRequiredOnPersonalAcError(
                "Personal Ac must have a member"
            )

    if ac_instance.t_ac == "I":
        if ac_instance.mem:
            raise exceptions.MemberOnImpersonalAcError(
                "Impersonal Ac cannot have a member"
            )


class Transaction(models.Model):
    date_created = models.DateTimeField(auto_now_add=True, editable=False)
    desc = models.TextField(blank=True, default="")

    def __str__(self):
        string = f"{self.pk}->{self.split_set.count()}"
        return string


class Split(models.Model):
    DEBIT = "dr"
    CREDIT = "cr"
    TYPE_SPLIT_CHOICES = [
        (DEBIT, "Debit"),
        (CREDIT, "Credit"),
    ]
    tx = models.ForeignKey(Transaction, on_delete=models.PROTECT)
    ac = models.ForeignKey(Ac, on_delete=models.PROTECT)
    t_sp = models.CharField(max_length=2, choices=TYPE_SPLIT_CHOICES)
    am = models.DecimalField(decimal_places=2, max_digits=11)

    def __str__(self):
        string = f"{self.tx.pk}->{self.t_sp}={self.am}"
        return string


@receiver(signals.pre_save, sender=Split)
def raise_exceptions_split(sender, **kwargs):
    sp_instance = kwargs["instance"]
    if (sp_instance.ac.who_am_i())["parent"]:
        raise exceptions.TransactionOnParentAcError("transaction on parent not allowed")
    if sp_instance.am <= 0:
        raise exceptions.ZeroAmountError("amount must be greater than 0")
