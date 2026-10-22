import pytest
from pydantic import ValidationError

from backend.schemas.scan_request import ScanRequest


def test_scan_request_normalizes_fragment_and_keeps_path():
    request = ScanRequest(url="https://example.com/privacy#cookies")
    assert request.url == "https://example.com/privacy"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1/",
        "http://169.254.169.254/",
        "https://user:pass@example.com/",
        "https://example.com:8443/",
    ],
)
def test_scan_request_rejects_unsafe_syntax(url):
    with pytest.raises(ValidationError):
        ScanRequest(url=url)


def test_scan_request_rejects_extra_fields():
    with pytest.raises(ValidationError):
        ScanRequest(url="https://example.com", admin=True)
