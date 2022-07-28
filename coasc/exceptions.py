class AccountError(Exception):
    pass


class AccountingEquationViolationError(AccountError):
    pass


class AccountTypeOnChildAccountError(AccountError):
    pass


class TransactionOnParentAcError(AccountError):
    pass


class OrphanAccountCreationError(AccountError):
    pass


class SelfReferencingError(AccountError):
    pass


class JournalError(Exception):
    pass


class ZeroAmountError(JournalError):
    pass
