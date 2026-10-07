"""Cognee Knowledge Graph & Code Search Bridge.

Ingests Cognee entity graphs, extracts structural symbols, and translates Cognee
retrieval results into deterministic AST pinning constraints for token reduction.
Zero external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from apex_token_slasher.core.models import ChunkKind, TokenChunk


@dataclass
class CogneeEntity:
    """Represents a code or domain entity resolved by Cognee."""
    entity_id: str
    name: str
    entity_type: str  # "function", "class", "module", "table", "endpoint"
    source_file: str = ""
    relationships: List[str] = field(default_factory=list)


class CogneeGraphBridge:
    """Projects Cognee GraphRAG entities into high-priority AST seed points."""

    def __init__(self) -> None:
        self.indexed_entities: Dict[str, CogneeEntity] = {}

    def register_entities(self, entities: List[Dict[str, Any]]) -> int:
        """Parses and indexes Cognee entities from GraphRAG search responses."""
        count = 0
        for item in entities:
            name = item.get("name") or item.get("id") or ""
            if not name:
                continue
            entity = CogneeEntity(
                entity_id=item.get("id", name),
                name=name,
                entity_type=item.get("type", "unknown"),
                source_file=item.get("file", ""),
                relationships=item.get("relationships", []),
            )
            self.indexed_entities[name] = entity
            count += 1
        return count

    def extract_ast_entry_points(self, query: str) -> Set[str]:
        """Resolves query terms against the Cognee entity graph to find key entry symbols."""
        query_terms = set(query.lower().replace(".", " ").replace("::", " ").split())
        matched_symbols: Set[str] = set()

        for name, entity in self.indexed_entities.items():
            name_lower = name.lower()
            if name_lower in query_terms or any(term in name_lower for term in query_terms if len(term) > 3):
                matched_symbols.add(name)
                # Add directly related entities
                for rel in entity.relationships:
                    matched_symbols.add(rel)

        return matched_symbols

    def build_cognee_graph_chunk(self, matched_symbols: Set[str]) -> TokenChunk:
        """Constructs an ultra-dense, token-compressed summary of the Cognee entity subgraph."""
        lines = ["# [COGNEE_GRAPH_PROJECTION]"]
        for sym in sorted(matched_symbols):
            entity = self.indexed_entities.get(sym)
            if entity:
                rels = f" -> {', '.join(entity.relationships[:3])}" if entity.relationships else ""
                lines.append(f"- {entity.entity_type.upper()}: {entity.name}{rels}")

        content = "\n".join(lines)
        return TokenChunk(
            chunk_id="cognee:subgraph_projection",
            content=content,
            kind=ChunkKind.SYSTEM_INSTRUCTION,
            estimated_tokens=max(5, int(len(content) / 3.8)),
            is_pinned=True,
        )
