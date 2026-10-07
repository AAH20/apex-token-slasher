"""Deterministic AST Call-Graph Slicer.

Analyzes Python source trees using standard library `ast`, builds symbol dependency graphs,
and slices out unreached functions, dead helper routines, and unused classes.
Zero external dependencies.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from apex_token_slasher.core.models import ChunkKind, TokenChunk


@dataclass
class SymbolNode:
    """Represents a discrete symbol extracted from the AST."""
    name: str
    kind: str  # "function", "class", "async_function", "assign", "import"
    parent_class: Optional[str] = None
    line_start: int = 1
    line_end: int = 1
    source_segment: str = ""
    dependencies: Set[str] = field(default_factory=set)
    docstring: Optional[str] = None


class DependencyVisitor(ast.NodeVisitor):
    """Walks an AST subtree to collect referenced symbol names and function calls."""

    def __init__(self) -> None:
        self.references: Set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.references.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.references.add(node.attr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            self.references.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self.references.add(node.func.attr)
        self.generic_visit(node)


class AstCallGraphSlicer:
    """Extracts, maps, and prunes AST symbol graphs to keep only reachable code paths."""

    def __init__(self, strip_docstrings: bool = False, preserve_class_skeletons: bool = True) -> None:
        self.strip_docstrings = strip_docstrings
        self.preserve_class_skeletons = preserve_class_skeletons

    def parse_and_index(self, code: str, file_path: Optional[str] = None) -> Dict[str, SymbolNode]:
        """Parses Python source code and returns a map of symbol qualified names to SymbolNodes."""
        lines = code.splitlines(keepends=True)
        try:
            tree = ast.parse(code)
        except SyntaxError:
            # Non-python or invalid python: treat as single monolithic chunk
            return {}

        symbols: Dict[str, SymbolNode] = {}

        # 1. Collect top-level imports
        import_lines: List[str] = []
        import_start = None
        import_end = None
        import_deps: Set[str] = set()

        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if import_start is None:
                    import_start = node.lineno
                import_end = node.end_lineno or node.lineno
                for alias in node.names:
                    import_deps.add(alias.asname or alias.name)
                import_lines.append(ast.get_source_segment(code, node) or "")

        if import_lines and import_start is not None and import_end is not None:
            symbols["__imports__"] = SymbolNode(
                name="__imports__",
                kind="import",
                line_start=import_start,
                line_end=import_end,
                source_segment="\n".join(import_lines),
                dependencies=import_deps,
            )

        # 2. Extract classes and functions
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sym = self._extract_function(node, code)
                symbols[sym.name] = sym

            elif isinstance(node, ast.ClassDef):
                class_sym, method_syms = self._extract_class(node, code)
                symbols[class_sym.name] = class_sym
                for m in method_syms:
                    symbols[f"{class_sym.name}.{m.name}"] = m

        return symbols

    def _extract_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, full_code: str, parent: Optional[str] = None) -> SymbolNode:
        visitor = DependencyVisitor()
        visitor.visit(node)
        # Remove function's own name and parameter names from dependencies
        param_names = {arg.arg for arg in node.args.args}
        deps = visitor.references - param_names - {node.name}

        doc = ast.get_docstring(node)
        source = ast.get_source_segment(full_code, node) or ""

        return SymbolNode(
            name=node.name,
            kind="async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
            parent_class=parent,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            source_segment=source,
            dependencies=deps,
            docstring=doc,
        )

    def _extract_class(self, node: ast.ClassDef, full_code: str) -> Tuple[SymbolNode, List[SymbolNode]]:
        visitor = DependencyVisitor()
        for base in node.bases:
            visitor.visit(base)

        doc = ast.get_docstring(node)
        class_deps = set(visitor.references)

        methods: List[SymbolNode] = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(self._extract_function(item, full_code, parent=node.name))

        class_source = ast.get_source_segment(full_code, node) or ""

        class_sym = SymbolNode(
            name=node.name,
            kind="class",
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            source_segment=class_source,
            dependencies=class_deps,
            docstring=doc,
        )
        return class_sym, methods

    def slice_reachable(
        self,
        symbols: Dict[str, SymbolNode],
        entry_points: Set[str],
        max_hops: int = 10,
    ) -> Set[str]:
        """Performs BFS reachability traversal to find all symbols directly or indirectly needed."""
        if not symbols:
            return set()

        reachable: Set[str] = set()
        queue: List[str] = []

        # Initialize queue with matching entry points
        for ep in entry_points:
            for sym_key, node in symbols.items():
                if sym_key == ep or ep in sym_key or node.name == ep:
                    reachable.add(sym_key)
                    queue.append(sym_key)

        # If no entry points matched, retain top-level public functions and classes
        if not reachable:
            for sym_key, node in symbols.items():
                if not node.name.startswith("_") or node.name == "__imports__":
                    reachable.add(sym_key)
                    queue.append(sym_key)

        # BFS expansion
        visited_hops = 0
        while queue and visited_hops < max_hops:
            current_level = queue
            queue = []
            visited_hops += 1

            for curr in current_level:
                node = symbols.get(curr)
                if not node:
                    continue

                for dep in node.dependencies:
                    # Look for dep in symbol table
                    for cand_key, cand_node in symbols.items():
                        if cand_key == dep or cand_node.name == dep or cand_key.endswith(f".{dep}"):
                            if cand_key not in reachable:
                                reachable.add(cand_key)
                                queue.append(cand_key)

                            # If a method is reached, also reach its parent class definition
                            if cand_node.parent_class and cand_node.parent_class in symbols:
                                if cand_node.parent_class not in reachable:
                                    reachable.add(cand_node.parent_class)
                                    queue.append(cand_node.parent_class)

        # Always retain imports if any code was reached
        if reachable and "__imports__" in symbols:
            reachable.add("__imports__")

        return reachable

    def generate_sliced_code(
        self,
        code: str,
        symbols: Dict[str, SymbolNode],
        reachable_keys: Set[str],
    ) -> str:
        """Emits sliced source code preserving required definitions and stubbing out unreached methods."""
        if not symbols or not reachable_keys:
            return code

        output_parts: List[str] = []

        # 1. Add imports first if reachable
        if "__imports__" in reachable_keys and "__imports__" in symbols:
            output_parts.append(symbols["__imports__"].source_segment)

        # 2. Group by class and top-level
        top_level_fns: List[SymbolNode] = []
        classes: Dict[str, List[SymbolNode]] = {}

        for key in reachable_keys:
            if key == "__imports__":
                continue
            node = symbols.get(key)
            if not node:
                continue

            if node.parent_class:
                classes.setdefault(node.parent_class, []).append(node)
            elif node.kind == "class":
                classes.setdefault(node.name, [])
            else:
                top_level_fns.append(node)

        # Render classes
        for class_name, active_methods in classes.items():
            class_node = symbols.get(class_name)
            if not class_node:
                continue

            # Class header
            header_lines: List[str] = []
            for line in class_node.source_segment.splitlines():
                header_lines.append(line)
                if line.strip().startswith("class ") and ":" in line:
                    break

            class_rendered = "\n".join(header_lines)
            if class_node.docstring and not self.strip_docstrings:
                class_rendered += f'\n    """{class_node.docstring}"""\n'

            if not active_methods:
                class_rendered += "\n    pass\n"
            else:
                for m in active_methods:
                    method_indented = "\n".join(f"    {l}" for l in m.source_segment.splitlines())
                    class_rendered += f"\n{method_indented}\n"

            output_parts.append(class_rendered)

        # Render top-level functions
        for fn in top_level_fns:
            output_parts.append(fn.source_segment)

        return "\n\n".join(output_parts)

    def slice_to_chunks(
        self,
        code: str,
        file_path: str,
        entry_points: Set[str],
    ) -> Tuple[List[TokenChunk], List[TokenChunk]]:
        """Parses and partitions file into retained TokenChunks and dropped TokenChunks."""
        symbols = self.parse_and_index(code, file_path)
        if not symbols:
            # Fallback for non-Python or unparseable code: keep entire file
            chunk = TokenChunk(
                chunk_id=f"{file_path}:full",
                content=code,
                kind=ChunkKind.SOURCE_CODE,
                file_path=file_path,
                is_pinned=bool(entry_points),
            )
            return [chunk], []

        reachable = self.slice_reachable(symbols, entry_points)

        retained: List[TokenChunk] = []
        dropped: List[TokenChunk] = []

        for key, node in symbols.items():
            chunk = TokenChunk(
                chunk_id=f"{file_path}:{key}",
                content=node.source_segment,
                kind=ChunkKind.SOURCE_CODE if node.kind != "import" else ChunkKind.SYSTEM_INSTRUCTION,
                file_path=file_path,
                symbol_name=key,
                line_start=node.line_start,
                line_end=node.line_end,
                dependencies=node.dependencies,
                is_pinned=(key in entry_points or key == "__imports__"),
            )
            if key in reachable:
                retained.append(chunk)
            else:
                dropped.append(chunk)

        return retained, dropped
