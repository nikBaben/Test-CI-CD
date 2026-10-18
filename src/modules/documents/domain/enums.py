from enum import StrEnum


class DocumentType(StrEnum):
    """balance_sheet — бухгалтерский баланс; financial_results — финансовые результаты;
    changes_in_equity — изменения капитала; cash_flows — движение денежных средств;
    targeted_funds — целевое использование полученных средств.
    """
    BALANCE_SHEET = "balance_sheet"
    FINANCIAL_RESULTS = "financial_results"
    CHANGES_IN_EQUITY = "changes_in_equity"
    CASH_FLOWS = "cash_flows"
    TARGETED_FUNDS = "targeted_funds"
