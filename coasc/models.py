"""
Coasc: Comprehensive Accounting System

This module implements a double-entry bookkeeping system with support for
hierarchical accounts, transactions, and splits. It provides functionality
for managing accounts, recording transactions, and generating balance reports.

Key components:
- Member: Represents individuals or entities associated with accounts.
- Ac (Account): The core entity representing different types of accounts.
- Transaction: Represents financial transactions.
- Split: Represents individual debit or credit entries within a transaction.

The system enforces various accounting rules and constraints to maintain
data integrity and adherence to accounting principles.
"""

from decimal import Decimal

from django.db import models, transaction
from django.db.models import Case, F, Sum, When, signals
from django.db.models.query import Q
from django.dispatch import receiver
from django.utils import timezone

from coasc import exceptions


class Member(models.Model):
    """
    Represents a member associated with personal accounts.

    Attributes:
        name (str): The name of the member.
        code (str): A unique code identifying the member.
    """

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=255, unique=True)

    def __str__(self):
        string = f"{self.name} ({self.code})"
        return string


class Ac(models.Model):
    """
    Represents an account in the accounting system.

    Accounts can be hierarchical (parent-child relationship) and are categorized
    into different types (Asset, Liability, Income, Expense).

    Attributes:
        name (str): The name of the account.
        t_ac (str): The type of account (Personal or Impersonal).
        p_ac (Ac): The parent account, if any.
        cat (str): The category of the account.
        mem (Member): Associated member for personal accounts.
        code (str): A unique code for the account.
    """

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
    cat = models.CharField(
        max_length=2, blank=True, null=True, default=None, choices=CATEGORY_CHOICES
    )
    mem = models.ForeignKey(
        Member, null=True, blank=True, default=None, on_delete=models.PROTECT
    )
    code = models.CharField(
        max_length=255, blank=True, null=True, default=None, unique=True
    )

    def __str__(self):
        string = f"{self.name} ({self.code})"
        return string

    @property
    def is_parent(self):
        """Check if the account is a parent account (has category, no parent, and has children)."""
        return self.cat is not None and self.p_ac is None and self.ac_set.exists()

    @property
    def is_standalone(self):
        """Check if the account is a standalone account (has category, no parent, and no children)."""
        return self.cat is not None and self.p_ac is None and not self.ac_set.exists()

    @property
    def is_child(self):
        """Check if the account is a child account (has parent and no category)."""
        return self.p_ac is not None and self.cat is None

    def bal(self, start_date=None, end_date=None):
        """
        Calculate the balance for this account.

        For parent accounts, it includes the balances of all child accounts.

        Args:
            start_date (date, optional): Start date for balance calculation.
            end_date (date, optional): End date for balance calculation.

        Returns:
            dict: A dictionary containing net balance, net debit, net credit,
                  total debit, and total credit.
        """

        if self.is_parent:
            sps = Split.objects.filter(ac__p_ac=self)
        else:
            sps = self.split_set.all()

        if start_date:
            sps = sps.filter(tx__tx_date__gte=start_date)
        if end_date:
            sps = sps.filter(tx__tx_date__lte=end_date)

        balances = sps.aggregate(
            total_debit=Sum(
                Case(
                    When(t_sp="dr", then=F("am")),
                )
            ),
            total_credit=Sum(
                Case(
                    When(t_sp="cr", then=F("am")),
                )
            ),
        )

        total_debit = balances["total_debit"] or Decimal(0)
        total_credit = balances["total_credit"] or Decimal(0)

        # handle child don't have category (TODO: rethink if child should have category too for consistency)
        ac_cat = self.p_ac.cat if self.is_child else self.cat

        if ac_cat in [self.ASSET, self.EXPENSES]:
            net_balance = total_debit - total_credit
            net_debit = max(net_balance, Decimal(0))
            net_credit = max(-net_balance, Decimal(0))
        elif ac_cat in [self.LIABILITY, self.INCOME]:
            net_balance = total_credit - total_debit
            net_debit = max(-net_balance, Decimal(0))
            net_credit = max(net_balance, Decimal(0))

        return {
            "net_balance": net_balance,
            "net_debit": net_debit,
            "net_credit": net_credit,
            "total_debit": total_debit,
            "total_credit": total_credit,
        }

    @classmethod
    def get_flat_balances(cls, cat=None, start_date=None, end_date=None):
        """
        Get balances for all top-level accounts.

        Args:
            cat (str, optional): Category to filter accounts.
            start_date (date, optional): Start date for balance calculation.
            end_date (date, optional): End date for balance calculation.

        Returns:
            list: List of dictionaries containing account and balance information.
        """

        top_level_accounts = cls.objects.filter(p_ac__isnull=True, cat__isnull=False)
        if cat:
            top_level_accounts = top_level_accounts.filter(cat=cat)

        return [
            {"account": account, "balance": account.bal(start_date, end_date)}
            for account in top_level_accounts
        ]

    @classmethod
    def get_hierarchical_balances(cls, cat=None, start_date=None, end_date=None):
        """
        Get hierarchical balances for all top-level accounts and their children.

        Args:
            cat (str, optional): Category to filter accounts.
            start_date (date, optional): Start date for balance calculation.
            end_date (date, optional): End date for balance calculation.

        Returns:
            list: Nested list of dictionaries containing account, balance,
                  and children information.
        """

        top_level_accounts = cls.objects.filter(p_ac__isnull=True, cat__isnull=False)
        if cat:
            top_level_accounts = top_level_accounts.filter(cat=cat)

        result = [
            {
                "account": account,
                "balance": account.bal(start_date, end_date),
                "children": [
                    {"account": child, "balance": child.bal(start_date, end_date)}
                    for child in account.ac_set.all()
                ],
            }
            for account in top_level_accounts
        ]

        return result

    @classmethod
    def validate_accounting_equation(cls):
        """
        Validate that the accounting equation (Assets = Liabilities + Equity) holds.

        Raises:
            AccountingEquationViolationError: If the equation doesn't balance.

        Returns:
            bool: True if the equation balances.
        """

        total_balance = Split.objects.aggregate(
            total_debit=Sum("am", filter=models.Q(t_sp="dr")),
            total_credit=Sum("am", filter=models.Q(t_sp="cr")),
        )

        total_debit = total_balance["total_debit"] or Decimal("0")
        total_credit = total_balance["total_credit"] or Decimal("0")
        difference = total_debit - total_credit

        if difference != Decimal("0"):
            raise exceptions.AccountingEquationViolationError(
                f"Accounting equation violation. Difference between debits and credits: {difference}"
            )

        return True


@receiver(signals.pre_save, sender=Ac)
def raise_exceptions_ac(sender, **kwargs):
    """
    Validate account constraints before saving.

    Raises various exceptions if account constraints are violated.
    """

    ac_instance = kwargs["instance"]

    if not ac_instance.is_root and not ac_instance.is_child:
        raise exceptions.InvalidAccountError(
            "Account must be either a root account or a child account"
        )

    if ac_instance.is_child:
        if ac_instance.cat:
            raise exceptions.CategoryOnChildAccountError(
                "Child account cannot have a category"
            )

        elif ac_instance.p_ac.split_set.exists():
            raise exceptions.AccountWithTransactionCannotBeParentError(
                "Account with transactions cannot be a parent"
            )

        elif ac_instance.p_ac.is_child:
            raise exceptions.ChildAccountCannotBeParentError(
                "A child account cannot be a parent"
            )
    if ac_instance.t_ac == Ac.PERSONAL and not ac_instance.mem_id:
        raise exceptions.MemberRequiredOnPersonalAcError(
            "Personal Ac must have a member"
        )

    if ac_instance.t_ac == Ac.IMPERSONAL and ac_instance.mem_id:
        raise exceptions.MemberOnImpersonalAcError("Impersonal Ac cannot have a member")


class Transaction(models.Model):
    """
    Represents a financial transaction.

    Attributes:
        created_at (datetime): Timestamp of when the transaction was created.
        tx_date (date): The date of the transaction.
        desc (str): Description of the transaction.
    """

    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    tx_date = models.DateField(default=timezone.now)
    desc = models.TextField()

    def __str__(self):
        string = f"{self.pk}->{self.split_set.count()}"
        return string

    def validate_transaction(self):
        """
        Validate that the transaction is balanced.

        Raises:
            EmptyTransactionError: If the transaction has no splits.
            UnbalancedTransactionError: If debits don't equal credits.

        Returns:
            bool: True if the transaction is valid.
        """

        # None is returned if no splits are found
        split_sums = self.split_set.aggregate(
            total_debit=Sum("am", filter=Q(t_sp="dr")),
            total_credit=Sum("am", filter=Q(t_sp="cr")),
        )

        total_debit = split_sums["total_debit"]
        total_credit = split_sums["total_credit"]

        if total_debit is None and total_credit is None:
            raise exceptions.EmptyTransactionError(
                "Transaction must have at least one split each for debit and credit"
            )

        # this also handles when only one type of split is present
        if total_debit != total_credit:
            raise exceptions.UnbalancedTransactionError(
                f"Transaction is not balanced. Debit: {total_debit}, Credit: {total_credit}"
            )

        return True

    def revert_transaction(self):
        """
        Create a new transaction that reverts this transaction.

        Returns:
            Transaction: The newly created revert transaction.

        Note:
            This method is executed within a database transaction. If any part
            of the operation fails, all changes will be rolled back.
        """

        with transaction.atomic():
            revert_tx = Transaction.objects.create(desc=f"Revert: {self.desc}")

            for sp in self.split_set.all():
                t_sp = Split.DEBIT if sp.t_sp == Split.CREDIT else Split.CREDIT
                Split.objects.create(tx=revert_tx, ac=sp.ac, t_sp=t_sp, am=sp.am)

        return revert_tx


class Split(models.Model):
    """
    Represents a single debit or credit entry in a transaction.

    Attributes:
        tx (Transaction): The associated transaction.
        ac (Ac): The account affected by this split.
        t_sp (str): The type of split (debit or credit).
        am (Decimal): The amount of the split.
    """

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
    """
    Validate split constraints before saving.

    Raises:
        TransactionOnParentAcError: If attempting to create a split for a parent account.
    """

    sp_instance = kwargs["instance"]
    if sp_instance.ac.is_parent:
        raise exceptions.TransactionOnParentAcError("Transaction on parent not allowed")
