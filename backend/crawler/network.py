import time
from typing import List
from urllib.parse import urlparse
from uuid import uuid4

from playwright.async_api import Page, Request, Response

from backend.schemas.core import Observation


class NetworkCollector:
    """
    Collector responsible for intercepting and recording network requests and responses.
    Adheres to the Single Responsibility Principle: strictly collects data, does not analyze it.
    """

    def __init__(self, page: Page, source_url: str):
        self.page = page
        self.source_url = source_url
        self.observations: List[Observation] = []
        self._request_ids: dict[Request, str] = {}

    def start_collecting(self) -> None:
        """
        Attaches event listeners to the page to collect network data.
        """
        self.page.on("request", self._on_request)
        self.page.on("response", self._on_response)

    def stop_collecting(self) -> None:
        """
        Removes event listeners from the page.
        """
        self.page.remove_listener("request", self._on_request)
        self.page.remove_listener("response", self._on_response)

    def get_observations(self) -> List[Observation]:
        """
        Returns the collected network observations.
        """
        return self.observations

    def _on_request(self, request: Request) -> None:
        request_id = str(uuid4())
        parsed_url = urlparse(request.url)

        self._request_ids[request] = request_id

        data = {
            "request_id": request_id,
            "url": request.url,
            "hostname": parsed_url.hostname,
            "protocol": parsed_url.scheme,
            "method": request.method,
            "headers": request.headers,
            "resource_type": request.resource_type,
            "is_navigation_request": request.is_navigation_request(),
        }

        self.observations.append(
            Observation(
                category="network_request",
                source_url=self.source_url,
                timestamp=time.time(),
                data=data,
            )
        )

    def _on_response(self, response: Response) -> None:
        request = response.request
        request_id = self._request_ids.get(request)
        parsed_url = urlparse(response.url)

        data = {
            "request_id": request_id,
            "url": response.url,
            "hostname": parsed_url.hostname,
            "protocol": parsed_url.scheme,
            "status": response.status,
            "headers": response.headers,
            "status_text": response.status_text,
        }

        self.observations.append(
            Observation(
                category="network_response",
                source_url=self.source_url,
                timestamp=time.time(),
                data=data,
            )
        )
