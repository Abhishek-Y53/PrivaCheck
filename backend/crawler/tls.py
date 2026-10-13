import socket
import ssl
import time
from typing import Any
from urllib.parse import urlparse

from backend.schemas.core import Observation


class TLSCollector:
    """
    Collects TLS certificate verification evidence for an HTTPS URL.

    This class is responsible only for observing TLS properties.
    It does not make any compliance decision.
    """

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def verify(
        self,
        url: str,
        source_url: str | None = None,
    ) -> Observation:
        """
        Verify the TLS certificate of the host serving the supplied URL.

        The Python SSL stack performs normal certificate-chain and hostname
        verification using the system trust store.
        """

        timestamp = time.time()
        source = source_url or url

        data: dict[str, Any] = {
            "url": url,
            "hostname": None,
            "port": None,
            "protocol": None,
            "verified": False,
            "tls_version": None,
            "subject": None,
            "issuer": None,
            "not_before": None,
            "not_after": None,
            "error": None,
        }

        try:
            parsed_url = urlparse(url)

            hostname = parsed_url.hostname
            port = parsed_url.port or 443

            data["hostname"] = hostname
            data["port"] = port

            if parsed_url.scheme.lower() != "https":
                data["error"] = "URL is not HTTPS."

                return Observation(
                    category="tls_certificate",
                    source_url=source,
                    timestamp=timestamp,
                    data=data,
                )

            if not hostname:
                data["error"] = "HTTPS URL does not contain a hostname."

                return Observation(
                    category="tls_certificate",
                    source_url=source,
                    timestamp=timestamp,
                    data=data,
                )

            context = ssl.create_default_context()

            with socket.create_connection(
                (hostname, port),
                timeout=self.timeout,
            ) as raw_socket:

                with context.wrap_socket(
                    raw_socket,
                    server_hostname=hostname,
                ) as tls_socket:

                    certificate = tls_socket.getpeercert()

                    data["verified"] = True
                    data["protocol"] = "https"
                    data["tls_version"] = tls_socket.version()

                    data["subject"] = self._format_certificate_name(
                        certificate.get("subject", ())
                    )

                    data["issuer"] = self._format_certificate_name(
                        certificate.get("issuer", ())
                    )

                    data["not_before"] = certificate.get("notBefore")
                    data["not_after"] = certificate.get("notAfter")

        except ssl.SSLCertVerificationError as exc:
            data["protocol"] = "https"
            data["error"] = (
                getattr(exc, "verify_message", None)
                or str(exc)
            )

        except ssl.SSLError as exc:
            data["protocol"] = "https"
            data["error"] = str(exc)

        except (OSError, ValueError) as exc:
            data["error"] = str(exc)

        return Observation(
            category="tls_certificate",
            source_url=source,
            timestamp=timestamp,
            data=data,
        )

    @staticmethod
    def _format_certificate_name(
        name: tuple[Any, ...],
    ) -> list[dict[str, str]]:
        """
        Convert the certificate subject/issuer structure returned by ssl
        into a simple serializable representation.
        """

        formatted: list[dict[str, str]] = []

        for relative_distinguished_name in name:
            for attribute in relative_distinguished_name:
                if len(attribute) != 2:
                    continue

                key, value = attribute

                formatted.append(
                    {
                        "key": str(key),
                        "value": str(value),
                    }
                )

        return formatted