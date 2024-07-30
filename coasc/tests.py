from django.test import TestCase

from coasc import exceptions
from coasc.models import Ac, Member, Split, Transaction


class MemberModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        Member(name="fn ln", code=1).save()
        Member(name="fn1 ln1", code=2).save()

    def test_create_and_retreive(self):
        saved_mems = Member.objects.all()

        self.assertEqual(saved_mems[0].code, "1")
        self.assertEqual(saved_mems[1].code, "2")


class AccountModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.single = Ac.objects.create(name="single", cat="LI", t_ac="I", code="1")
        cls.parent = Ac.objects.create(name="parent", cat="EX", t_ac="I", code="2")
        cls.child = Ac.objects.create(
            name="child", p_ac=cls.parent, t_ac="I", code="2.1"
        )
        cls.child1 = Ac.objects.create(
            name="child1", p_ac=cls.parent, t_ac="I", code="2.2"
        )

        cls.tx = Transaction.objects.create(desc="tx")

        Split.objects.create(tx=cls.tx, ac=cls.single, t_sp="dr", am=6)
        Split.objects.create(tx=cls.tx, ac=cls.single, t_sp="dr", am=9)
        Split.objects.create(tx=cls.tx, ac=cls.single, t_sp="cr", am=6)
        Split.objects.create(tx=cls.tx, ac=cls.single, t_sp="cr", am=9)

        Split.objects.create(tx=cls.tx, ac=cls.child, t_sp="dr", am=6)
        Split.objects.create(tx=cls.tx, ac=cls.child, t_sp="cr", am=9)

        Split.objects.create(tx=cls.tx, ac=cls.child1, t_sp="dr", am=9)
        Split.objects.create(tx=cls.tx, ac=cls.child1, t_sp="cr", am=6)

    def test_create_and_retreive(self):
        saved_accounts = Ac.objects.all()

        self.assertEqual(saved_accounts.count(), 4)
        self.assertEqual(saved_accounts[0].code, "1")
        self.assertEqual(saved_accounts[1].code, "2")
        self.assertEqual(saved_accounts[2].code, "2.1")

    def test_raises_exception_if_cat_set_on_child(self):
        with self.assertRaises(exceptions.CategoryOnChildAccountError):
            Ac.objects.create(
                name="child ac2", p_ac=self.parent, cat="LI", t_ac="I", code="2.3"
            )

    def test_raises_exception_if_p_ac_selected_as_a_splicat(self):
        Split.objects.create(tx=self.tx, ac=self.single, t_sp="dr", am=100)
        with self.assertRaises(exceptions.TransactionOnParentAcError):
            Split.objects.create(tx=self.tx, ac=self.parent, t_sp="cr", am=100)

    def test_who_am_i(self):
        ac_is = self.single.who_am_i()
        ac1_is = self.parent.who_am_i()
        ac2_is = self.child.who_am_i()

        self.assertTrue(ac_is["single"])
        self.assertTrue(ac1_is["parent"])
        self.assertTrue(ac2_is["child"])

    def test_bal(self):
        single_bal = self.single.bal()
        child_bal = self.child.bal()
        child1_bal = self.child1.bal()
        parent_bal = self.parent.bal()

        expected_single_bal = {"dr_sum": 15, "cr_sum": 15, "diff": 0}
        expected_child_bal = {"dr_sum": 6, "cr_sum": 9, "diff": -3}
        expected_child1_bal = {"dr_sum": 9, "cr_sum": 6, "diff": 3}
        expected_parent_bal = {"dr_sum": 15, "cr_sum": 15, "diff": 0}

        self.assertEqual(single_bal, expected_single_bal)
        self.assertEqual(child_bal, expected_child_bal)
        self.assertEqual(child1_bal, expected_child1_bal)
        self.assertEqual(parent_bal, expected_parent_bal)

    def test_total_bal_with_no_args(self):
        total_bal = Ac.total_bal()

        expected_total_bal = {"total_dr_sum": 30, "total_cr_sum": 30, "diff": 0}

        self.assertEqual(total_bal, expected_total_bal)

    def test_total_bal_with_args(self):
        li_total_bal = Ac.total_bal(cat="LI")
        ex_total_bal = Ac.total_bal(cat="EX")

        li_expected_total_bal = {"total_dr_sum": 15, "total_cr_sum": 15, "diff": 0}
        ex_expected_total_bal = {"total_dr_sum": 15, "total_cr_sum": 15, "diff": 0}

        self.assertEqual(li_total_bal, li_expected_total_bal)
        self.assertEqual(ex_total_bal, ex_expected_total_bal)

    def test_validate_accounting_equation(self):
        with self.assertRaises(exceptions.AccountingEquationViolationError):
            Split.objects.create(tx=self.tx, ac=self.single, t_sp="dr", am=100)
            Split.objects.create(tx=self.tx, ac=self.child, t_sp="cr", am=50)
            Ac.validate_accounting_equation()

    def test_raises_exception_if_ac_has_no_parent_and_category(self):
        with self.assertRaises(exceptions.InvalidAccountError):
            Ac.objects.create(name="orphan", code="0")

    def test_raises_exception_if_single_ac_selected_as_parent(self):
        single = Ac.objects.create(name="single", code="3", cat="AS")
        tx = Transaction.objects.create(desc="demo")
        Split.objects.create(tx=tx, ac=single, t_sp="dr", am=1)

        with self.assertRaises(exceptions.AccountWithTransactionCannotBeParentError()):
            Ac.objects.create(name="child", code="3.1", p_ac=single)

    def test_raises_exception_if_personal_ac_has_no_member(self):
        with self.assertRaises(exceptions.MemberRequiredOnPersonalAcError):
            Ac.objects.create(name="single", code=4, cat="LI", t_ac="P")

        with self.assertRaises(exceptions.MemberRequiredOnPersonalAcError):
            Ac.objects.create(name="child", code=2.3, t_ac="P", p_ac=self.parent)

    def test_raises_exception_if_impersonal_ac_has_member(self):
        mem = Member.objects.create(name="ln fn", code=1)
        with self.assertRaises(exceptions.MemberOnImpersonalAcError):
            Ac.objects.create(name="single", code=5, cat="LI", t_ac="I", mem=mem)

        with self.assertRaises(exceptions.MemberOnImpersonalAcError):
            Ac.objects.create(
                name="child", code=2.3, t_ac="I", p_ac=self.parent, mem=mem
            )


class TransactionAndSplitModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.single = Ac.objects.create(name="single", cat="AS", t_ac="I", code="1")
        cls.parent = Ac.objects.create(name="parent", cat="LI", t_ac="I", code="2")
        cls.child = Ac.objects.create(
            name="child", p_ac=cls.parent, t_ac="I", code="2.1"
        )

        cls.tx = Transaction.objects.create(desc="tx")

        Split.objects.create(tx=cls.tx, ac=cls.single, t_sp="dr", am=6)
        Split.objects.create(tx=cls.tx, ac=cls.child, t_sp="cr", am=9)

    def test_create_and_retreive_txs(self):
        saved_tx = Transaction.objects.first()
        self.assertEqual(self.tx, saved_tx)

    def test_create_and_retreive_splits(self):
        saved_splits = Split.objects.all()

        self.assertEqual(saved_splits.count(), 2)
        self.assertEqual(saved_splits[0].ac, self.single)
        self.assertEqual(saved_splits[0].t_sp, "dr")
        self.assertEqual(saved_splits[0].am, 6)

        self.assertEqual(saved_splits[1].ac, self.child)
        self.assertEqual(saved_splits[1].t_sp, "cr")
        self.assertEqual(saved_splits[1].am, 9)
