"""
Symmetrical cross-language mismatch validation for C, C++, Python, and Java.
Utilizes AST parsers (tree-sitter for C/C++/Java, ast for Python) combined with
syntactic structure and language-specific grammar markers.
"""

import ast
import re
from typing import Optional, Tuple, Dict, Any
from tree_sitter import Language, Parser
import tree_sitter_c
import tree_sitter_cpp
import tree_sitter_java

from .state import SupportedLanguage, AnalysisState


# Initialize Tree-sitter parsers
c_parser = Parser(Language(tree_sitter_c.language()))
cpp_parser = Parser(Language(tree_sitter_cpp.language()))
java_parser = Parser(Language(tree_sitter_java.language()))


def count_tree_errors(node) -> int:
    """Recursively count ERROR or MISSING nodes in a tree-sitter AST."""
    count = 1 if (node.type == "ERROR" or node.is_missing) else 0
    for child in node.children:
        count += count_tree_errors(child)
    return count


def check_python_validity(code: str) -> Tuple[bool, int, list]:
    """Check Python syntax and extract Python-specific structures."""
    try:
        tree = ast.parse(code)
        # Check node types
        has_py_defs = any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Import, ast.ImportFrom)) for n in ast.walk(tree))
        return True, 0, [type(n).__name__ for n in ast.walk(tree)]
    except SyntaxError as e:
        return False, 1, []


def score_language_match(code: str) -> Dict[SupportedLanguage, float]:
    """
    Score the likelihood of each language based on parsers and structural signatures.
    Returns a dictionary of language -> score (0.0 to 100.0+).
    """
    scores = {
        SupportedLanguage.PYTHON: 0.0,
        SupportedLanguage.JAVA: 0.0,
        SupportedLanguage.CPP: 0.0,
        SupportedLanguage.C: 0.0,
    }

    code_bytes = code.encode("utf-8")
    lines = code.splitlines()
    stripped_lines = [l.strip() for l in lines if l.strip()]

    # ==================== PYTHON ANALYSIS ====================
    py_valid, py_errs, py_nodes = check_python_validity(code)
    if py_valid:
        scores[SupportedLanguage.PYTHON] += 30.0

    # Python keyword / syntax checks
    if re.search(r'^\s*def\s+[a-zA-Z_]\w*\s*\(', code, re.MULTILINE):
        scores[SupportedLanguage.PYTHON] += 25.0
    if re.search(r'^\s*elif\s+.*:', code, re.MULTILINE):
        scores[SupportedLanguage.PYTHON] += 25.0
    if re.search(r'^\s*import\s+[a-zA-Z_]\w*|^\s*from\s+[a-zA-Z_]\w*\s+import', code, re.MULTILINE):
        scores[SupportedLanguage.PYTHON] += 20.0
    if re.search(r'print\s*\([^)]*\)', code) and not re.search(r';\s*$', code, re.MULTILINE):
        scores[SupportedLanguage.PYTHON] += 15.0
    if re.search(r'if\s+__name__\s*==\s*[\'"]__main__[\'"]:', code):
        scores[SupportedLanguage.PYTHON] += 30.0
    if re.search(r'^\s*#\s+.*', code, re.MULTILINE) and not re.search(r'^\s*#include', code, re.MULTILINE):
        scores[SupportedLanguage.PYTHON] += 10.0

    # Negative signals for Python
    if "#include" in code or "public class" in code or "System.out" in code or "int main(" in code:
        scores[SupportedLanguage.PYTHON] -= 60.0
    if any(l.endswith(";") for l in stripped_lines) and len(stripped_lines) > 1:
        scores[SupportedLanguage.PYTHON] -= 25.0

    # ==================== JAVA ANALYSIS ====================
    java_tree = java_parser.parse(code_bytes)
    java_errors = count_tree_errors(java_tree.root_node)
    if java_errors == 0 and len(code_bytes) > 0:
        scores[SupportedLanguage.JAVA] += 35.0
    elif java_errors <= 2:
        scores[SupportedLanguage.JAVA] += 15.0

    if re.search(r'public\s+(final\s+)?class\s+\w+', code):
        scores[SupportedLanguage.JAVA] += 40.0
    if re.search(r'public\s+static\s+void\s+main\s*\(\s*String\s*(\[\s*\]|\.\.\.)\s*\w+\s*\)', code):
        scores[SupportedLanguage.JAVA] += 50.0
    if "System.out.println" in code or "System.out.print" in code:
        scores[SupportedLanguage.JAVA] += 35.0
    if re.search(r'import\s+java\.', code) or re.search(r'package\s+[\w\.]+;', code):
        scores[SupportedLanguage.JAVA] += 35.0
    if "@Override" in code:
        scores[SupportedLanguage.JAVA] += 20.0

    # Negative signals for Java
    if "#include" in code or "std::" in code or "cout <<" in code or "def " in code:
        scores[SupportedLanguage.JAVA] -= 60.0

    # ==================== C++ ANALYSIS ====================
    cpp_tree = cpp_parser.parse(code_bytes)
    cpp_errors = count_tree_errors(cpp_tree.root_node)
    if cpp_errors == 0 and len(code_bytes) > 0:
        scores[SupportedLanguage.CPP] += 25.0
    elif cpp_errors <= 2:
        scores[SupportedLanguage.CPP] += 10.0

    # Distinct C++ signatures (that don't exist in standard C)
    if re.search(r'#include\s*<iostream>|#include\s*<vector>|#include\s*<string>|#include\s*<algorithm>', code):
        scores[SupportedLanguage.CPP] += 50.0
    if re.search(r'using\s+namespace\s+std\s*;', code):
        scores[SupportedLanguage.CPP] += 45.0
    if "std::cout" in code or "std::cin" in code or "std::endl" in code:
        scores[SupportedLanguage.CPP] += 45.0
    if re.search(r'\bcout\s*<<|\bcin\s*>>', code):
        scores[SupportedLanguage.CPP] += 40.0
    if re.search(r'\btemplate\s*<', code):
        scores[SupportedLanguage.CPP] += 35.0
    if re.search(r'\bnullptr\b', code):
        scores[SupportedLanguage.CPP] += 25.0
    if re.search(r'class\s+\w+\s*\{.*public\s*:', code, re.DOTALL):
        scores[SupportedLanguage.CPP] += 35.0

    # Negative signals for C++
    if "public class" in code or "System.out" in code or "def " in code:
        scores[SupportedLanguage.CPP] -= 60.0

    # ==================== C ANALYSIS ====================
    c_tree = c_parser.parse(code_bytes)
    c_errors = count_tree_errors(c_tree.root_node)
    if c_errors == 0 and len(code_bytes) > 0:
        scores[SupportedLanguage.C] += 25.0
    elif c_errors <= 2:
        scores[SupportedLanguage.C] += 10.0

    # Distinct C signatures
    if re.search(r'#include\s*<stdio\.h>|#include\s*<stdlib\.h>|#include\s*<string\.h>', code):
        scores[SupportedLanguage.C] += 40.0
    if re.search(r'\bprintf\s*\(', code) and not ("System.out" in code):
        scores[SupportedLanguage.C] += 25.0
    if re.search(r'\bscanf\s*\(', code):
        scores[SupportedLanguage.C] += 25.0
    if re.search(r'\bmalloc\s*\(|\bfree\s*\(', code):
        scores[SupportedLanguage.C] += 20.0
    if re.search(r'int\s+main\s*\(\s*(void)?\s*\)', code):
        scores[SupportedLanguage.C] += 20.0

    # Crucial distinction between C and C++:
    # If code has C++ features, penalize C
    if scores[SupportedLanguage.CPP] > 40.0 or any(kw in code for kw in ["<iostream>", "using namespace std", "std::", "cout <<", "cin >>", "nullptr", "class "]):
        scores[SupportedLanguage.C] -= 60.0

    # If code has C headers and printf, but NO C++ features at all, boost C and penalize C++
    has_c_header = bool(re.search(r'#include\s*<stdio\.h>|#include\s*<stdlib\.h>', code))
    has_cpp_marker = bool(re.search(r'<iostream>|<vector>|using namespace std|cout|cin|std::|class |template|nullptr', code))
    if has_c_header and not has_cpp_marker:
        scores[SupportedLanguage.C] += 35.0
        scores[SupportedLanguage.CPP] -= 30.0

    # Negative signals for C
    if "public class" in code or "System.out" in code or "def " in code or "elif " in code:
        scores[SupportedLanguage.C] -= 60.0

    return scores


def validate_language(selected_language: SupportedLanguage, code: str) -> Dict[str, Any]:
    """
    Validate that the supplied source code corresponds to the selected language.
    Returns:
    {
        "status": AnalysisState.VALID_SOURCE | AnalysisState.LANGUAGE_MISMATCH | AnalysisState.INVALID_SOURCE,
        "is_mismatch": bool,
        "selected_language": str,
        "detected_language": Optional[str],
        "message": str
    }
    """
    if not code or not code.strip():
        return {
            "status": AnalysisState.INVALID_SOURCE,
            "is_mismatch": False,
            "selected_language": selected_language.value,
            "detected_language": None,
            "message": "Source code is empty."
        }

    scores = score_language_match(code)
    best_lang, best_score = max(scores.items(), key=lambda item: item[1])
    selected_score = scores[selected_language]

    # Check for symmetrical language mismatch
    # If best_lang is different from selected_language and has strong positive score,
    # or selected language has heavy penalty/low score while best_lang is clearly positive:
    if best_lang != selected_language:
        # Require clear disparity to avoid false positives on tiny snippets
        # If best_score is >= 20.0 and selected_score < best_score - 15.0
        if best_score >= 20.0 and (best_score - selected_score >= 15.0 or selected_score < 0):
            lang_display_names = {
                SupportedLanguage.C: "C",
                SupportedLanguage.CPP: "C++",
                SupportedLanguage.PYTHON: "Python",
                SupportedLanguage.JAVA: "Java",
            }
            sel_name = lang_display_names.get(selected_language, selected_language.value)
            det_name = lang_display_names.get(best_lang, best_lang.value)

            return {
                "status": AnalysisState.LANGUAGE_MISMATCH,
                "is_mismatch": True,
                "selected_language": selected_language.value,
                "detected_language": best_lang.value,
                "message": f"Language Mismatch: The selected language is {sel_name}, but the supplied source appears to be {det_name}. Please select {det_name} or provide valid {sel_name} code.",
                "scores": {k.value: round(v, 2) for k, v in scores.items()}
            }

    return {
        "status": AnalysisState.VALID_SOURCE,
        "is_mismatch": False,
        "selected_language": selected_language.value,
        "detected_language": selected_language.value,
        "message": "Source code matches the selected language.",
        "scores": {k.value: round(v, 2) for k, v in scores.items()}
    }
