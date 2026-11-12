"""Shared, GUI-free core for KiCad LibGen.

The modules in this package are extracted from the upstream
``kicad_lib_gen`` CLI (pinned at commit ``64ca2a9``).  They contain no
``print``/``input`` calls and no ANSI colour handling, so the CLI, the
services and the Tk GUI can all share one implementation.
"""

from .database import (
    ProductDb,
    UpsertOutcome,
    ensure_schema,
    product_from_row,
    product_to_row,
    validate_schema,
)
from .errors import (
    AppError,
    AuthError,
    AuthRequired,
    BatchError,
    DatabaseError,
    DatabaseLockedError,
    NetworkError,
    ParseError,
    RateLimitError,
    SchemaError,
    SearchError,
    ServerError,
)
from .models import (
    ALL_COLUMNS,
    DEFAULT_PARAM,
    METADATA_COLUMNS,
    PARAM_COLUMNS,
    PARAM_COUNT,
    ProductInfo,
    ProductInfoBase,
    resolve_mapping,
    validate_mapping,
)
from .parser import parse_categories, parse_digikey_response

__all__ = [
    "ALL_COLUMNS",
    "DEFAULT_PARAM",
    "METADATA_COLUMNS",
    "PARAM_COLUMNS",
    "PARAM_COUNT",
    "AppError",
    "AuthError",
    "AuthRequired",
    "BatchError",
    "DatabaseError",
    "DatabaseLockedError",
    "NetworkError",
    "ParseError",
    "ProductDb",
    "ProductInfo",
    "ProductInfoBase",
    "RateLimitError",
    "SchemaError",
    "SearchError",
    "ServerError",
    "UpsertOutcome",
    "ensure_schema",
    "parse_categories",
    "parse_digikey_response",
    "product_from_row",
    "product_to_row",
    "resolve_mapping",
    "validate_mapping",
    "validate_schema",
]
