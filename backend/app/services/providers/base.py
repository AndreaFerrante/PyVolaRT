"""Market-data provider interface.

A provider acquires data from somewhere (IBKR, or a simulator) and writes
normalized models into a ``MarketSink``. Nothing downstream depends on which
provider is running — that is the whole point of the abstraction, and it is
what lets the IBKR integration stay isolated behind the M2 validation gate.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.core.models.contracts import OptionContract
from app.core.models.market import GreeksUpdate, OpenInterestRecord, UnderlyingQuote


@runtime_checkable
class MarketSink(Protocol):
    """The write surface a provider pushes into. ``MarketState`` implements it."""

    def register_contract(self, contract: OptionContract) -> None: ...
    def on_greeks(self, update: GreeksUpdate) -> None: ...
    def on_quote(self, quote: UnderlyingQuote) -> None: ...
    def on_oi(self, record: OpenInterestRecord) -> None: ...


@dataclass
class ProviderHealth:
    connected: bool
    lines_in_use: int


class MarketDataProvider(ABC):
    """Lifecycle + health. Implementations write to the sink they were given."""

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    def health(self) -> ProviderHealth: ...
