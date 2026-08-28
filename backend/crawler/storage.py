import time
from typing import List, Any

from playwright.async_api import Page

from backend.schemas.core import Observation


class StorageCollector:
    """
    Collects browser storage data.

    Responsible only for observing:
    - localStorage
    - sessionStorage
    - IndexedDB

    Does not perform compliance analysis.
    """

    def __init__(self, page: Page, source_url: str):
        self.page = page
        self.source_url = source_url

    async def collect_local_storage(self) -> List[Observation]:
        """Collect all localStorage key-value pairs."""
        storage = await self.page.evaluate(
            """
            () => {
                const result = {};

                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    result[key] = localStorage.getItem(key);
                }

                return result;
            }
            """
        )

        observations: List[Observation] = []

        for key, value in storage.items():
            observations.append(
                Observation(
                    category="local_storage",
                    source_url=self.source_url,
                    timestamp=time.time(),
                    data={
                        "storage_type": "localStorage",
                        "key": key,
                        "value": value,
                    },
                )
            )

        return observations

    async def collect_session_storage(self) -> List[Observation]:
        """Collect all sessionStorage key-value pairs."""
        storage = await self.page.evaluate(
            """
            () => {
                const result = {};

                for (let i = 0; i < sessionStorage.length; i++) {
                    const key = sessionStorage.key(i);
                    result[key] = sessionStorage.getItem(key);
                }

                return result;
            }
            """
        )

        observations: List[Observation] = []

        for key, value in storage.items():
            observations.append(
                Observation(
                    category="session_storage",
                    source_url=self.source_url,
                    timestamp=time.time(),
                    data={
                        "storage_type": "sessionStorage",
                        "key": key,
                        "value": value,
                    },
                )
            )

        return observations

    async def collect_indexed_db(self) -> List[Observation]:
        """Collect IndexedDB databases, object stores, keys, and values."""

        databases = await self.page.evaluate(
            """
            async () => {
                if (!indexedDB.databases) {
                    return [];
                }

                const databases = await indexedDB.databases();
                const result = [];

                for (const database of databases) {
                    if (!database.name) {
                        continue;
                    }

                    try {
                        const db = await new Promise((resolve, reject) => {
                            const request = indexedDB.open(
                                database.name,
                                database.version
                            );

                            request.onsuccess = () => resolve(request.result);
                            request.onerror = () => reject(request.error);
                        });

                        const objectStores = Array.from(db.objectStoreNames);

                        for (const storeName of objectStores) {
                            const storeData = await new Promise(
                                (resolve, reject) => {
                                    const transaction = db.transaction(
                                        storeName,
                                        "readonly"
                                    );

                                    const store =
                                        transaction.objectStore(storeName);

                                    const keysRequest =
                                        store.getAllKeys();

                                    const valuesRequest =
                                        store.getAll();

                                    transaction.oncomplete = () => {
                                        resolve({
                                            keys: keysRequest.result,
                                            values: valuesRequest.result
                                        });
                                    };

                                    transaction.onerror = () => {
                                        reject(transaction.error);
                                    };
                                }
                            );

                            result.push({
                                database: database.name,
                                object_store: storeName,
                                keys: storeData.keys,
                                values: storeData.values
                            });
                        }

                        db.close();

                    } catch {
                        // Skip databases that cannot be opened.
                    }
                }

                return result;
            }
            """
        )

        observations: List[Observation] = []

        for store in databases:
            keys = store["keys"]
            values = store["values"]

            for key, value in zip(keys, values):
                observations.append(
                    Observation(
                        category="indexed_db",
                        source_url=self.source_url,
                        timestamp=time.time(),
                        data={
                            "storage_type": "IndexedDB",
                            "database": store["database"],
                            "object_store": store["object_store"],
                            "key": key,
                            "value": value,
                        },
                    )
                )

        return observations

    async def collect_all(self) -> List[Observation]:
        """Collect all supported browser storage observations."""

        local_storage = await self.collect_local_storage()
        session_storage = await self.collect_session_storage()
        indexed_db = await self.collect_indexed_db()

        return local_storage + session_storage + indexed_db