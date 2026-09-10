"""
Feature extraction module for AST code units.
Converts syntactic and structural AST properties into numeric feature vectors for ML inference.
"""

from typing import List, Dict, Any
import numpy as np


FEATURE_NAMES = [
    "nesting_depth",
    "is_loop_header",
    "is_boundary_operator",
    "is_assignment_in_condition",
    "has_subscript_access",
    "has_division_operator",
    "has_null_or_none",
    "cyclomatic_weight",
    "token_count",
]


def extract_features_from_statement(
    text: str,
    node_type: str,
    nesting_depth: int = 1,
    is_loop: bool = False,
    is_cond: bool = False
) -> np.ndarray:
    """
    Extract normalized feature vector for a statement or code unit.
    """
    clean_text = text.strip()

    # 1. nesting_depth
    f_depth = min(nesting_depth, 10) / 10.0

    # 2. is_loop_header
    f_loop = 1.0 if is_loop or any(w in clean_text for w in ["for", "while", "do "]) else 0.0

    # 3. is_boundary_operator (<=, >=)
    f_boundary = 1.0 if ("<=" in clean_text or ">=" in clean_text) else 0.0

    # 4. is_assignment_in_condition (if (x = 10))
    f_assign_cond = 1.0 if (is_cond and "=" in clean_text and "==" not in clean_text and "<=" not in clean_text and ">=" not in clean_text) else 0.0

    # 5. has_subscript_access
    f_subscript = 1.0 if ("[" in clean_text and "]" in clean_text) else 0.0

    # 6. has_division_operator
    f_div = 1.0 if ("/" in clean_text or "%" in clean_text) else 0.0

    # 7. has_null_or_none
    f_null = 1.0 if any(k in clean_text for k in ["NULL", "nullptr", "None", "null"]) else 0.0

    # 8. cyclomatic_weight
    cyclo = 1
    if any(k in clean_text for k in ["if", "for", "while", "&&", "||", "and", "or", "case"]):
        cyclo += 1
    f_cyclo = min(cyclo, 5) / 5.0

    # 9. token_count
    tokens = clean_text.split()
    f_tokens = min(len(tokens), 30) / 30.0

    return np.array([
        f_depth,
        f_loop,
        f_boundary,
        f_assign_cond,
        f_subscript,
        f_div,
        f_null,
        f_cyclo,
        f_tokens
    ], dtype=np.float32)
