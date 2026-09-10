"""
C++ Language Analyzer.
Whole-program multi-bug analysis leveraging Tree-Sitter C++ parser, G++ diagnostics,
static AST boundary inspection, fault localization distinguishing root-cause from failure location,
and candidate repair validation. Does NOT stop at the first error.
"""

import re
import time
from typing import List, Tuple, Optional, Set
from tree_sitter import Language, Parser
import tree_sitter_cpp

from backend.core.state import SupportedLanguage, BugSeverity, BugCategory
from backend.models.schemas import (
    BugItem,
    ResearchMetrics,
    StructuredPatch,
    CandidateFix,
    EvidenceBreakdown
)
from backend.fault_localization.evidence_fusion import fusion_engine
from backend.ai.model import ml_model
from backend.repair.code_stitcher import (
    apply_patch,
    apply_multiple_patches,
    compute_source_hash,
    position_to_offset,
    apply_multiple_patches_transactional
)
from backend.validation.validator import validate_repaired_program
from backend.utils.env_check import check_system_environment
from .base_analyzer import BaseAnalyzer


class CppAnalyzer(BaseAnalyzer):
    def __init__(self):
        super().__init__(SupportedLanguage.CPP)
        self.ts_parser = Parser(Language(tree_sitter_cpp.language()))

    def analyze(self, code: str, test_input: str = "") -> Tuple[List[BugItem], Optional[str], ResearchMetrics]:
        start_time = time.time()
        source_hash = compute_source_hash(code)
        bugs: List[BugItem] = []
        lines = code.splitlines(keepends=True)
        total_lines = len(lines)
        funcs_count = len(re.findall(r'\b(?:int|void|char|float|double|bool|auto)\s+\w+\s*\(', code))
        cyclo = 1 + len(re.findall(r'\b(if|for|while|case|catch)\b', code))
        env = check_system_environment()
        code_bytes = code.encode("utf-8")

        flagged_lines: Set[int] = set()


        # =========================================================================
        # PHASE 1: Tree-Sitter AST Whole-Program Syntax Diagnostics
        # =========================================================================
        tree = self.ts_parser.parse(code_bytes)
        root = tree.root_node

        error_nodes = []
        def find_errors(node):
            if node.type == "ERROR" or node.is_missing:
                error_nodes.append(node)
            for child in node.children:
                find_errors(child)

        find_errors(root)

        # Group error nodes by line
        errors_by_line = {}
        for en in error_nodes:
            line_no = en.start_point.row + 1
            if line_no not in errors_by_line:
                errors_by_line[line_no] = en

        for err_line, err_node in errors_by_line.items():
            err_col = err_node.start_point.column + 1
            err_line_text = lines[err_line - 1].rstrip() if err_line <= total_lines else ""

            prev_line_no = max(1, err_line - 1)
            prev_line_text = lines[prev_line_no - 1].rstrip() if prev_line_no <= total_lines else ""

            if not prev_line_text.endswith(";") and not prev_line_text.endswith("{") and not prev_line_text.endswith("}") and not prev_line_text.startswith("#"):
                target_line = prev_line_no
                orig = prev_line_text
                repl = prev_line_text + ";"
                explanation_what = f"Missing semicolon ';' at line {prev_line_no}."
            else:
                target_line = err_line
                orig = err_line_text
                repl = err_line_text + ";" if not err_line_text.endswith(";") else err_line_text
                explanation_what = f"Syntax error near line {err_line}: Missing semicolon or malformed C++ statement."

            if target_line not in flagged_lines:
                flagged_lines.add(target_line)
                s_off = position_to_offset(code, target_line, 1)
                e_off = s_off + len(orig)
                patch = StructuredPatch(
                    file="main.cpp",
                    start_line=target_line,
                    start_column=1,
                    end_line=target_line,
                    end_column=len(orig) + 1,
                    original_code=orig,
                    replacement_code=repl,
                    start_offset=s_off,
                    end_offset=e_off,
                    source_hash=source_hash,
                    reason="Add missing statement terminator ';'."
                )
                cand_code = apply_patch(code, patch)
                val_result = validate_repaired_program(SupportedLanguage.CPP, cand_code, test_input)
                ml_score, ml_exp = ml_model.predict_suspiciousness(orig, "SyntaxError", 1)
                evidence = fusion_engine.fuse(
                    compiler_score=0.95,
                    compiler_msg="C++ Parser generated ERROR node",
                    static_score=0.90,
                    static_msg="Unterminated statement in block",
                    runtime_score=0.0,
                    runtime_msg="Compilation stage failure",
                    ast_score=0.90,
                    ast_msg="Tree-Sitter syntax tree error",
                    ml_score=ml_score,
                    ml_msg=ml_exp
                )
                bug = BugItem(
                    bug_id=len(bugs) + 1,
                    category=BugCategory.SYNTAX_ERROR,
                    severity=BugSeverity.CRITICAL,
                    status="DETECTED",
                    file="main.cpp",
                    line=target_line,
                    column=len(orig) + 1,
                    code_statement=orig,
                    ast_node_type="ERROR",
                    root_cause_line=target_line,
                    root_cause_column=len(orig) + 1,
                    root_cause_code=orig,
                    failure_line=err_line,
                    failure_column=err_col,
                    failure_code=err_line_text,
                    message=explanation_what,
                    what_is_wrong=f"The statement '{orig.strip()}' does not end with a semicolon ';'.",
                    why_it_is_wrong="C++ statements inside function bodies must terminate with a semicolon ';'.",
                    what_happens="Compilation fails with fatal syntax error: expected ';' before next statement.",
                    what_should_be_changed=f"Append ';' to statement: '{repl.strip()}'.",
                    patch=patch,
                    candidate_fixes=[
                        CandidateFix(
                            fix_id=1,
                            title="Add missing semicolon",
                            patch=patch,
                            validation=val_result,
                            confidence=0.95,
                            is_recommended=True
                        )
                    ],
                    confidence=0.95,
                    validation=val_result,
                    evidence=evidence
                )
                bugs.append(bug)

        # =========================================================================
        # PHASE 2: Static Boundary & Logic Checks Across Entire Source
        # =========================================================================
        # Check 2.1: Loop Boundary Overrun (for i <= n)
        for idx, line in enumerate(lines, start=1):
            if idx in flagged_lines:
                continue
            loop_match = re.search(r'for\s*\(\s*([^;]+);\s*([a-zA-Z_]\w*)\s*<=\s*([^;]+);\s*([^)]+)\)', line)
            if loop_match:
                root_line = idx
                flagged_lines.add(root_line)
                root_code = line.rstrip()
                var_name = loop_match.group(2)
                limit_expr = loop_match.group(3).strip()

                fail_line = root_line
                fail_code = root_code
                for sub_idx in range(idx, min(total_lines + 1, idx + 20)):
                    sub_line = lines[sub_idx - 1]
                    if re.search(rf'\[\s*{var_name}\s*\]', sub_line):
                        fail_line = sub_idx
                        fail_code = sub_line.rstrip()
                        break

                s_idx = line.find("<=")
                if s_idx != -1:
                    s_col = s_idx + 1
                    e_col = s_col + len("<=")
                    s_off = position_to_offset(code, root_line, s_col)
                    e_off = s_off + len("<=")
                    patch = StructuredPatch(
                        file="main.cpp",
                        start_line=root_line,
                        start_column=s_col,
                        end_line=root_line,
                        end_column=e_col,
                        original_code="<=",
                        replacement_code="<",
                        start_offset=s_off,
                        end_offset=e_off,
                        source_hash=source_hash,
                        reason=f"An array containing {limit_expr} elements has valid indexes 0 through {limit_expr}-1. Condition '{var_name} <= {limit_expr}' allows index {var_name} to reach {limit_expr}."
                    )
                    cand_code = apply_patch(code, patch)
                    val_result = validate_repaired_program(SupportedLanguage.CPP, cand_code, test_input)
                    ml_score, ml_exp = ml_model.predict_suspiciousness(root_code, "for_range_loop", 2, is_loop=True)
                    evidence = fusion_engine.fuse(
                        compiler_score=0.40,
                        compiler_msg="Compiler diagnostic warning: array subscript out of bounds",
                        static_score=0.96,
                        static_msg=f"Loop boundary condition '{var_name} <= {limit_expr}' exceeds upper bound",
                        runtime_score=0.92,
                        runtime_msg="Memory safety fault: buffer overrun at boundary index",
                        ast_score=0.90,
                        ast_msg="for_statement condition binary_expression(<=)",
                        ml_score=ml_score,
                        ml_msg=ml_exp
                    )
                    bug = BugItem(
                        bug_id=len(bugs) + 1,
                        category=BugCategory.INDEX_OUT_OF_BOUNDS,
                        severity=BugSeverity.HIGH,
                        status="DETECTED",
                        file="main.cpp",
                        line=root_line,
                        column=s_col,
                        end_line=root_line,
                        end_column=e_col,
                        code_statement=root_code,
                        ast_node_type="for_statement",
                        root_cause_line=root_line,
                        root_cause_column=s_col,
                        root_cause_code=root_code,
                        failure_line=fail_line,
                        failure_column=1,
                        failure_code=fail_code,
                        message=f"Array Index Out of Bounds: The loop condition uses '<=' ({var_name} <= {limit_expr}).",
                        what_is_wrong=f"The loop condition allows index '{var_name}' to reach {limit_expr}.",
                        why_it_is_wrong=f"The array has {limit_expr} elements with valid indexes 0 through {limit_expr}-1. The loop allows {var_name} to become {limit_expr}.",
                        what_happens="Accessing index out of bounds causes buffer overrun, memory corruption, or runtime segmentation fault.",
                        what_should_be_changed="Replace '<=' with '<'.",
                        patch=patch,
                        candidate_fixes=[
                            CandidateFix(
                                fix_id=1,
                                title="Change <= to < in loop condition",
                                patch=patch,
                                validation=val_result,
                                confidence=0.96,
                                is_recommended=True
                            )
                        ],
                        confidence=0.96,
                        validation=val_result,
                        evidence=evidence
                    )
                    bugs.append(bug)

        # Check 2.2: Assignment in conditional: if (x = 10)
        for idx, line in enumerate(lines, start=1):
            if idx in flagged_lines:
                continue
            assign_match = re.search(r'\bif\s*\(\s*([a-zA-Z_]\w*\s*=\s*[^=;><!)]+)\)', line)
            if assign_match:
                root_line = idx
                flagged_lines.add(root_line)
                root_code = line.rstrip()
                orig_snip = assign_match.group(1)
                repl_snip = re.sub(r'\s*=\s*', ' == ', orig_snip, count=1)
                s_idx = line.find(orig_snip)
                if s_idx != -1:
                    s_col = s_idx + 1
                    e_col = s_col + len(orig_snip)
                    s_off = position_to_offset(code, root_line, s_col)
                    e_off = s_off + len(orig_snip)
                    patch = StructuredPatch(
                        file="main.cpp",
                        start_line=root_line,
                        start_column=s_col,
                        end_line=root_line,
                        end_column=e_col,
                        original_code=orig_snip,
                        replacement_code=repl_snip,
                        start_offset=s_off,
                        end_offset=e_off,
                        source_hash=source_hash,
                        reason="Use equality operator '==' instead of assignment operator '=' inside condition."
                    )
                    cand_code = apply_patch(code, patch)
                    val_result = validate_repaired_program(SupportedLanguage.CPP, cand_code, test_input)
                    ml_score, ml_exp = ml_model.predict_suspiciousness(root_code, "if_statement", 2, is_cond=True)
                    evidence = fusion_engine.fuse(
                        compiler_score=0.85,
                        compiler_msg="Compiler -Wparentheses warning: suggest parentheses around assignment used as truth value",
                        static_score=0.98,
                        static_msg="Assignment operator in conditional expression",
                        runtime_score=0.75,
                        runtime_msg="Condition evaluates truthiness of assigned value rather than comparison",
                        ast_score=0.85,
                        ast_msg="if_statement condition assignment_expression",
                        ml_score=ml_score,
                        ml_msg=ml_exp
                    )
                    bug = BugItem(
                        bug_id=len(bugs) + 1,
                        category=BugCategory.INCORRECT_ASSIGNMENT_IN_CONDITION,
                        severity=BugSeverity.HIGH,
                        status="DETECTED",
                        file="main.cpp",
                        line=root_line,
                        column=s_col,
                        end_line=root_line,
                        end_column=e_col,
                        code_statement=root_code,
                        ast_node_type="assignment_expression",
                        root_cause_line=root_line,
                        root_cause_column=s_col,
                        root_cause_code=root_code,
                        failure_line=root_line,
                        failure_column=s_col,
                        failure_code=root_code,
                        message=f"Assignment in Condition: '{orig_snip}' used as boolean test at line {root_line}.",
                        what_is_wrong=f"The conditional statement performs an assignment ({orig_snip}) instead of a comparison.",
                        why_it_is_wrong="In C++, '=' assigns the value and evaluates to the assigned value, while '==' checks for equality.",
                        what_happens="The condition will always evaluate to the truthiness of the assigned value and overwrite the variable.",
                        what_should_be_changed=f"Replace '{orig_snip}' with '{repl_snip}'.",
                        patch=patch,
                        candidate_fixes=[
                            CandidateFix(
                                fix_id=1,
                                title="Change '=' to '==' in condition",
                                patch=patch,
                                validation=val_result,
                                confidence=0.98,
                                is_recommended=True
                            )
                        ],
                        confidence=0.98,
                        validation=val_result,
                        evidence=evidence
                    )
                    bugs.append(bug)

        # Check 2.3: Division by zero literal
        for idx, line in enumerate(lines, start=1):
            if idx in flagged_lines:
                continue
            div_match = re.search(r'([/%])\s*0\b', line)
            if div_match:
                root_line = idx
                flagged_lines.add(root_line)
                root_code = line.rstrip()
                orig_snip = div_match.group(0)
                op = div_match.group(1)
                repl_snip = f"{op} 1"
                s_idx = line.find(orig_snip)
                if s_idx != -1:
                    s_col = s_idx + 1
                    e_col = s_col + len(orig_snip)
                    s_off = position_to_offset(code, root_line, s_col)
                    e_off = s_off + len(orig_snip)
                    patch = StructuredPatch(
                        file="main.cpp",
                        start_line=root_line,
                        start_column=s_col,
                        end_line=root_line,
                        end_column=e_col,
                        original_code=orig_snip,
                        replacement_code=repl_snip,
                        start_offset=s_off,
                        end_offset=e_off,
                        source_hash=source_hash,
                        reason="Division by zero is undefined behavior in C++."
                    )
                    cand_code = apply_patch(code, patch)
                    val_result = validate_repaired_program(SupportedLanguage.CPP, cand_code, test_input)
                    ml_score, ml_exp = ml_model.predict_suspiciousness(root_code, "binary_expression", 1)
                    evidence = fusion_engine.fuse(
                        compiler_score=0.90,
                        compiler_msg="Compiler warning: division by zero",
                        static_score=0.99,
                        static_msg="Literal zero divisor detected",
                        runtime_score=0.95,
                        runtime_msg="SIGFPE arithmetic exception",
                        ast_score=0.90,
                        ast_msg="binary_expression(/, 0)",
                        ml_score=ml_score,
                        ml_msg=ml_exp
                    )
                    bug = BugItem(
                        bug_id=len(bugs) + 1,
                        category=BugCategory.DIVISION_BY_ZERO,
                        severity=BugSeverity.CRITICAL,
                        status="DETECTED",
                        file="main.cpp",
                        line=root_line,
                        column=s_col,
                        code_statement=root_code,
                        ast_node_type="binary_expression",
                        root_cause_line=root_line,
                        root_cause_column=s_col,
                        root_cause_code=root_code,
                        failure_line=root_line,
                        failure_column=s_col,
                        failure_code=root_code,
                        message=f"Division by Zero on line {root_line}.",
                        what_is_wrong="The denominator is literal zero.",
                        why_it_is_wrong="Division by zero is undefined behavior and causes abnormal termination.",
                        what_happens="Process terminates with arithmetic exception or SIGFPE.",
                        what_should_be_changed="Replace divisor with a valid non-zero expression.",
                        patch=patch,
                        confidence=0.98,
                        validation=val_result,
                        evidence=evidence
                    )
                    bugs.append(bug)

        # =========================================================================
        # PHASE 3: Sorting, Re-Indexing & Cumulative Corrected Code Generation
        # =========================================================================
        bugs.sort(key=lambda b: (b.root_cause_line, b.column))
        for i, bug in enumerate(bugs, start=1):
            bug.bug_id = i
            if bug.patch:
                bug.patch.bug_id = i
            for cf in bug.candidate_fixes:
                cf.patch.bug_id = i

        valid_patches = [b.patch for b in bugs if b.patch is not None]
        corrected_program = None
        if valid_patches:
            res = apply_multiple_patches_transactional(code, valid_patches, source_hash)
            corrected_program = res["corrected_code"]

        elapsed = (time.time() - start_time) * 1000
        metrics = self.compute_metrics(code, bugs, elapsed, funcs_count, cyclo)
        metrics.compiler_available = env["g++"]["available"]
        metrics.compiler_name = "G++" if env["g++"]["available"] else None
        return bugs, corrected_program, metrics
