class AccountError(Exception):
    pass


class AccountingEquationViolationError(AccountError):
    pass


class CategoryOnChildAccountError(AccountError):
    pass


class TransactionOnParentAcError(AccountError):
    pass


class InvalidAccountError(AccountError):
    pass


class AccountWithTransactionCannotBeParentError(AccountError):
    pass


class ChildAccountCannotBeParentError(AccountError):
    pass


class MemberRequiredOnPersonalAcError(AccountError):
    pass


class MemberOnImpersonalAcError(AccountError):
    pass
