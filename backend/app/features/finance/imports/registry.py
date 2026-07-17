from __future__ import annotations

from app.integrations.activobank.card_statement_parser import ActivoBankCardStatementParser
from app.integrations.activobank.statement_parser import ActivoBankStatementParser
from app.shared.statement import StatementParser

_PARSERS: dict[str, StatementParser] = {
    parser.provider: parser
    for parser in (ActivoBankStatementParser(), ActivoBankCardStatementParser())
}


def get_parser(provider: str) -> StatementParser | None:
    return _PARSERS.get(provider)


def all_parsers() -> dict[str, StatementParser]:
    return dict(_PARSERS)


def detect_parser(filename: str, content: bytes) -> StatementParser | None:
    for parser in _PARSERS.values():
        if parser.can_parse(filename, content):
            return parser
    return None


def available_providers() -> list[str]:
    return sorted(_PARSERS.keys())
