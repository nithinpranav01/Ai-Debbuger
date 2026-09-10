"""
Code unit representation and AST node mapping for fault localization.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class CodeUnit(BaseModel):
    unit_id: str
    node_type: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    text: str
    nesting_depth: int = 0
    is_loop: bool = False
    is_condition: bool = False
    is_boundary_expression: bool = False
    has_assignment_in_condition: bool = False
    is_subscript_access: bool = False
    is_division: bool = False


def extract_tree_sitter_units(root_node, source_bytes: bytes, max_depth: int = 15) -> List[CodeUnit]:
    """
    Traverse a tree-sitter AST and extract significant statement/expression code units.
    """
    units: List[CodeUnit] = []
    unit_counter = 0

    def walk(node, depth: int):
        nonlocal unit_counter
        if depth > max_depth:
            return

        ntype = node.type
        # Filter for interesting statement/expression nodes
        interesting = (
            "statement" in ntype
            or "declaration" in ntype
            or "for" in ntype
            or "while" in ntype
            or "if" in ntype
            or "subscript" in ntype
            or "binary_expression" in ntype
            or "call_expression" in ntype
            or "assignment" in ntype
            or "ERROR" in ntype
        )

        if interesting:
            unit_counter += 1
            node_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            
            # Identify flags
            is_loop = any(k in ntype for k in ["for", "while", "do"])
            is_cond = any(k in ntype for k in ["if", "condition", "binary_expression"])
            is_boundary = ("<=" in node_text or ">=" in node_text or "==" in node_text or "!=" in node_text)
            has_assign = ("=" in node_text and "==" not in node_text and "<=" not in node_text and ">=" not in node_text and is_cond)
            is_subscript = ("subscript" in ntype or "[" in node_text)
            is_div = ("/" in node_text or "%" in node_text)

            units.append(
                CodeUnit(
                    unit_id=f"ts_{unit_counter}_{ntype}",
                    node_type=ntype,
                    start_line=node.start_point.row + 1,
                    start_col=node.start_point.column + 1,
                    end_line=node.end_point.row + 1,
                    end_col=node.end_point.column + 1,
                    text=node_text[:120],
                    nesting_depth=depth,
                    is_loop=is_loop,
                    is_condition=is_cond,
                    is_boundary_expression=is_boundary,
                    has_assignment_in_condition=has_assign,
                    is_subscript_access=is_subscript,
                    is_division=is_div
                )
            )

        for child in node.children:
            walk(child, depth + 1)

    walk(root_node, 0)
    return units
