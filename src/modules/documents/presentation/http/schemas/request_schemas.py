from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict


class UploadCompanyDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: UploadFile
