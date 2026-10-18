from pydantic import BaseModel


class CheckoCompanyRequest(BaseModel):
    inn: int


class CheckoFinancesRequest(CheckoCompanyRequest):
    extended: str = "true"
