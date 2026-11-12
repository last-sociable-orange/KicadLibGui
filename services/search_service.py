"""UI-free DigiKey search orchestration.

Responsibilities:

* validate the query before spending an API call;
* refresh the token once and retry once after HTTP 401;
* parse the payload with the defensive shared parser;
* turn unexpected payloads into a user-facing :class:`ParseError`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import digikey_auth
import digikey_search
from kicad_core.errors import AuthRequired, ParseError, SearchError
from kicad_core.models import ProductInfo
from kicad_core.parser import parse_products
from services.auth_service import AuthService

logger = logging.getLogger(__name__)

SearchFunction = Callable[..., dict[str, Any]]


class SearchService:
    def __init__(
        self,
        auth_service: AuthService,
        *,
        limit: int = 25,
        timeout: int = 30,
        search_fn: SearchFunction | None = None,
    ):
        self.auth = auth_service
        self.limit = limit
        self.timeout = timeout
        self._search_fn = search_fn or digikey_search.digikey_search

    def _call(self, keywords: str, limit: int, offset: int) -> dict[str, Any]:
        return self._search_fn(
            keywords,
            token_file=str(self.auth.token_path),
            limit=limit,
            offset=offset,
            timeout=self.timeout,
        )

    def search(self, keywords: str, limit: int | None = None, offset: int = 0) -> list[ProductInfo]:
        """Search DigiKey and return parsed products (possibly empty)."""
        keywords = (keywords or "").strip()
        if not keywords:
            raise SearchError("Enter a part number or keyword to search for.")
        requested = self.limit if limit is None else limit
        requested = max(1, min(100, int(requested)))
        offset = max(0, int(offset))

        try:
            payload = self._call(keywords, requested, offset)
        except AuthRequired:
            logger.info("Search returned 401; refreshing the token and retrying once")
            try:
                self.auth.ensure_token(force_refresh=True, timeout=self.timeout)
            except (AuthRequired, digikey_auth.AuthError) as exc:
                raise AuthRequired(
                    "DigiKey session expired. Sign in again.", details=str(exc)
                ) from exc
            payload = self._call(keywords, requested, offset)

        try:
            products = parse_products(payload)
        except ValueError as exc:
            raise ParseError(
                "DigiKey returned an unexpected response.",
                details=str(exc),
            ) from exc
        logger.info("Search for %r returned %s products", keywords, len(products))
        return products
