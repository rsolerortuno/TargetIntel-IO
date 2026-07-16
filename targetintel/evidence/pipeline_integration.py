"""Optional, read-only integration of stored evidence with report writers."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .reporting import EvidenceCard, EvidenceReportDecorator
from .store import EvidenceStore


def load_evidence_cards(
    evidence_store_path: str | Path,
    target_symbols: Iterable[str],
) -> dict[str, EvidenceCard]:
    """Load finalized evidence cards for requested targets without mutation.

    Supplying a store is an explicit request: missing, directory, malformed,
    and incompatible paths fail clearly rather than silently omitting evidence.
    """
    decorator = EvidenceReportDecorator()
    cards: dict[str, EvidenceCard] = {}
    with EvidenceStore(evidence_store_path, read_only=True) as store:
        for symbol in sorted(set(target_symbols)):
            card = decorator.make_card(symbol, store.list_items(target_symbol=symbol))
            if card is not None:
                cards[symbol] = card
    return cards
