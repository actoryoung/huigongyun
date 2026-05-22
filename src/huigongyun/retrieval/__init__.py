"""Retrieval and similarity contracts.

This package re-exports the project-level historical retrieval and material
similarity interfaces so future implementations can plug in keyword search,
vector search, or hybrid retrieval without changing the public API.
"""

from ..interfaces import CaseHit, HistoricalCaseRetriever, SimilarMaterialMatcher

__all__ = ["CaseHit", "HistoricalCaseRetriever", "SimilarMaterialMatcher"]