import asyncio
import hashlib
from copy import deepcopy
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.main import create_app
from src.modules.documents.application.dto import GetCompanyDocumentDTO, UploadCompanyDocumentDTO
from src.modules.documents.application.use_cases.get_company_document_use_case import GetCompanyDocumentUseCase
from src.modules.documents.application.use_cases.upload_company_document_use_case import UploadCompanyDocumentUseCase
from src.modules.documents.domain.enums import DocumentType
from src.modules.documents.domain.exceptions import DocumentStorageError, DocumentTooLargeError, DocumentValidationError
from src.modules.documents.domain.validation import validate_pdf, validate_reporting_year
from src.modules.documents.infrastructure.deps import get_document_repository, get_document_storage, get_document_uow
from src.modules.users.domain.auth import CurrentUser
from src.modules.users.infrastructure.deps import get_current_user
from src.shared.config import ServiceSettings

PDF = b"%PDF-1.4\n1 0 obj <</Type /Catalog>> endobj\n%%EOF\n"
PDF2 = PDF.replace(b"1.4", b"1.7")


class MemoryDocuments:
    def __init__(self, owner, company):
        self.owner, self.company = owner, company
        self.rows = {}
        self.saved = {}
        self.fail_commit = False
        self.ambiguous_commit = False

    async def lock_owned_company(self, user_id, company_id, *, write):
        return user_id == self.owner and company_id == self.company

    async def get(self, user_id, company_id, document_type, year):
        if user_id != self.owner or company_id != self.company:
            return None
        return self.rows.get((document_type, year))

    async def list(self, user_id, company_id):
        return list(self.rows.values())

    async def save(self, document):
        self.rows[document.document_type, document.year] = document

    async def commit(self):
        if self.fail_commit:
            raise DocumentStorageError()
        self.saved = deepcopy(self.rows)
        if self.ambiguous_commit:
            raise DocumentStorageError()

    async def rollback(self):
        self.rows = deepcopy(self.saved)


class MemoryStorage:
    def __init__(self):
        self.objects = {}
        self.fail_put = self.fail_delete = self.fail_get = False
        self.calls = []

    async def put(self, key, source, size):
        self.calls.append("put")
        self.objects[key] = source.read()
        if self.fail_put:
            raise DocumentStorageError()
        assert len(self.objects[key]) == size

    async def get(self, key, size, sha256):
        self.calls.append("get")
        if self.fail_get or key not in self.objects:
            raise DocumentStorageError()
        value = self.objects[key]
        assert len(value) == size and hashlib.sha256(value).hexdigest() == sha256
        return BytesIO(value)

    async def delete(self, key):
        self.calls.append("delete")
        if self.fail_delete:
            raise DocumentStorageError()
        self.objects.pop(key, None)


@pytest.fixture
def document_api():
    owner, company = uuid4(), uuid4()
    repository, storage = MemoryDocuments(owner, company), MemoryStorage()
    app = create_app(ServiceSettings(
        _env_file=None, db_url="postgresql+asyncpg://test:test@localhost/unused_test",
        keycloak_client_secret="test", keycloak_registration_client_secret="test", document_max_bytes=1024,
    ))
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=str(owner))
    app.dependency_overrides[get_document_repository] = lambda: repository
    app.dependency_overrides[get_document_uow] = lambda: repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    with TestClient(app) as client:
        yield client, app, owner, company, repository, storage


def upload(client, company, content=PDF, document_type="balance_sheet", year=2025, filename="баланс.pdf", mime="application/pdf"):
    return client.put(f"/companies/{company}/documents/{document_type}/{year}", files={"file": (filename, content, mime)})


def test_all_types_years_replace_and_download_through_api(document_api):
    client, app, owner, company, repo, storage = document_api
    for kind in DocumentType:
        result = upload(client, company, document_type=kind.value)
        assert result.status_code == 200, result.text
        value = result.json()
        assert value["user_id"] == str(owner) and value["company_id"] == str(company)
        assert value["sha256"] == hashlib.sha256(PDF).hexdigest()
        assert "object_key" not in value
    original = repo.rows[DocumentType.BALANCE_SHEET, 2025]
    result = upload(client, company, PDF2, filename="новый баланс.pdf")
    assert result.status_code == 200
    replaced = repo.rows[DocumentType.BALANCE_SHEET, 2025]
    assert replaced.id == original.id and replaced.created_at == original.created_at
    assert replaced.object_key != original.object_key and original.object_key not in storage.objects
    assert upload(client, company, year=2024).status_code == 200
    listed = client.get(f"/companies/{company}/documents")
    assert listed.status_code == 200 and len(listed.json()) == 6
    response = client.get(f"/companies/{company}/documents/balance_sheet/2025")
    assert response.status_code == 200 and response.content == PDF2
    assert response.headers["content-type"] == "application/pdf"
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert response.headers["content-length"] == str(len(PDF2))
    assert response.headers["cache-control"] == "private, no-store"
    assert client.get(f"/companies/{company}/documents/cash_flows/2020").status_code == 404
    schemas = client.get("/openapi.json").json()
    body = schemas["paths"]["/companies/{company_id}/documents/{document_type}/{year}"]["put"]["requestBody"]
    assert "multipart/form-data" in body["content"]


@pytest.mark.parametrize("method", ["PUT", "GET", "LIST"])
def test_other_users_cannot_access_company_documents(document_api, method):
    client, app, owner, company, repo, storage = document_api
    assert upload(client, company).status_code == 200
    storage.calls.clear()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=str(uuid4()))
    if method == "PUT":
        response = upload(client, company)
    else:
        response = client.get(f"/companies/{company}/documents" + ("/balance_sheet/2025" if method == "GET" else ""))
    assert response.status_code == 404 and storage.calls == []


@pytest.mark.parametrize("method", ["PUT", "GET", "LIST"])
def test_documents_require_bearer_authentication(document_api, method):
    client, app, owner, company, repo, storage = document_api
    del app.dependency_overrides[get_current_user]
    if method == "PUT":
        response = upload(client, company)
    else:
        response = client.get(f"/companies/{company}/documents" + ("/balance_sheet/2025" if method == "GET" else ""))
    assert response.status_code == 401 and storage.calls == []


@pytest.mark.parametrize("content,filename,mime,year,kind,status", [
    (b"", "x.pdf", "application/pdf", 2025, "balance_sheet", 422),
    (b"fake %%EOF", "x.pdf", "application/pdf", 2025, "balance_sheet", 422),
    (b"%PDF-1.4\ntruncated", "x.pdf", "application/pdf", 2025, "balance_sheet", 422),
    (PDF, "x.exe", "application/pdf", 2025, "balance_sheet", 422),
    (PDF, "x.pdf", "text/plain", 2025, "balance_sheet", 422),
    (PDF, "x.pdf", "application/pdf", 1899, "balance_sheet", 422),
    (PDF, "x.pdf", "application/pdf", 10000, "balance_sheet", 422),
    (PDF, "x.pdf", "application/pdf", "wrong", "balance_sheet", 422),
    (PDF, "x.pdf", "application/pdf", 2025, "wrong", 422),
    (b"%PDF-1.4\n" + b"a" * 2048 + b"%%EOF", "x.pdf", "application/pdf", 2025, "balance_sheet", 413),
    (b"a" * 70000, "x.pdf", "application/pdf", 2025, "balance_sheet", 413),
])
def test_invalid_uploads_do_not_reach_storage(document_api, content, filename, mime, year, kind, status):
    client, app, owner, company, repo, storage = document_api
    response = upload(client, company, content, kind, year, filename, mime)
    assert response.status_code == status, response.text
    assert repo.rows == {} and storage.calls == []


def test_chunked_upload_has_a_total_body_limit(document_api):
    client, app, owner, company, repo, storage = document_api
    response = client.put(f"/companies/{company}/documents/balance_sheet/2025",
                          headers={"Content-Type": "multipart/form-data; boundary=test"},
                          content=iter([b"--test\r\nContent-Disposition: form-data; name=\"file\"; filename=\"x.pdf\"\r\n"
                                        b"Content-Type: application/pdf\r\n\r\n", b"a" * 70000, b"\r\n--test--\r\n"]))
    assert response.status_code == 413 and storage.calls == []


def test_upload_cannot_override_owner_or_metadata(document_api):
    client, app, owner, company, repo, storage = document_api
    response = client.put(f"/companies/{company}/documents/balance_sheet/2025",
                          files={"file": ("x.pdf", PDF, "application/pdf")}, data={"user_id": str(uuid4())})
    assert response.status_code == 422 and storage.calls == []


@pytest.mark.parametrize("failure", ["minio_put", "commit", "ambiguous_commit", "delete_old"])
def test_replacement_failure_never_loses_current_file(document_api, failure):
    client, app, owner, company, repo, storage = document_api
    assert upload(client, company).status_code == 200
    old = repo.rows[DocumentType.BALANCE_SHEET, 2025]
    if failure == "minio_put":
        storage.fail_put = True
    elif failure == "commit":
        repo.fail_commit = True
    elif failure == "ambiguous_commit":
        repo.ambiguous_commit = True
    else:
        storage.fail_delete = True
    response = upload(client, company, PDF2)
    assert response.status_code == (200 if failure == "delete_old" else 503)
    current = repo.rows[DocumentType.BALANCE_SHEET, 2025]
    assert storage.objects[current.object_key] == (PDF if failure in ("minio_put", "commit") else PDF2)
    assert old.object_key in storage.objects
    assert len(repo.rows) == 1


def test_path_is_not_used_as_minio_object_key(document_api):
    client, app, owner, company, repo, storage = document_api
    response = upload(client, company, filename="../../report.pdf")
    assert response.status_code == 200 and response.json()["filename"] == "report.pdf"
    assert "report.pdf" not in next(iter(storage.objects))


@pytest.mark.parametrize("year", [True, "2025", 2025.0, -1])
def test_reporting_year_rule_is_defined_in_domain(year):
    with pytest.raises(DocumentValidationError):
        validate_reporting_year(year)


def test_domain_pdf_validation_resets_stream_after_success_and_failure():
    stream = BytesIO(PDF)
    assert validate_pdf(stream, "test.pdf", "application/pdf", 1024).size_bytes == len(PDF)
    assert stream.tell() == 0
    with pytest.raises(DocumentTooLargeError):
        validate_pdf(stream, "test.pdf", "application/pdf", 5)
    assert stream.tell() == 0


def test_download_closes_file_if_commit_fails():
    async def scenario():
        owner, company = uuid4(), uuid4()
        repo, storage = MemoryDocuments(owner, company), MemoryStorage()
        await UploadCompanyDocumentUseCase(repo, repo, storage, 1024).execute(UploadCompanyDocumentDTO(
            user_id=owner, company_id=company, document_type=DocumentType.BALANCE_SHEET,
            year=2025, filename="x.pdf", content_type="application/pdf", content=BytesIO(PDF),
        ))
        content = BytesIO(PDF)
        async def get(*args):
            return content
        storage.get = get
        repo.fail_commit = True
        with pytest.raises(DocumentStorageError):
            await GetCompanyDocumentUseCase(repo, repo, storage).execute(GetCompanyDocumentDTO(
                user_id=owner, company_id=company, document_type=DocumentType.BALANCE_SHEET, year=2025,
            ))
        assert content.closed
    asyncio.run(scenario())
