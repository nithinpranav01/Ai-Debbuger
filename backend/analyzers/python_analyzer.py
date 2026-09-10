"""
Python Language Analyzer.
Whole-program multi-bug analysis combining Python AST parsing, static pattern scanning,
sandboxed runtime execution, AI/ML feature suspiciousness, and automated program repair.
Does NOT terminate at the first error; discovers all independent defects across lines.
"""

import ast
import re
import sys
import time
from typing import List, Tuple, Optional, Set

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
from backend.validation.sandbox import IsolatedSandbox
from backend.validation.validator import validate_repaired_program
from .base_analyzer import BaseAnalyzer


class PythonAnalyzer(BaseAnalyzer):
    def __init__(self):
        super().__init__(SupportedLanguage.PYTHON)

    def analyze(self, code: str, test_input: str = "") -> Tuple[List[BugItem], Optional[str], ResearchMetrics]:
        start_time = time.time()
        source_hash = compute_source_hash(code)
        bugs: List[BugItem] = []
        lines = code.splitlines(keepends=True)
        total_lines = len(lines)
        funcs_count = len(re.findall(r'^\s*def\s+', code, re.MULTILINE))
        cyclo = 1 + len(re.findall(r'\b(if|for|while|and|or|elif)\b', code))

        flagged_lines: Set[int] = set()

        # =========================================================================
        # PHASE 1: Whole-Program Syntax Scanning & Error Recovery
        # =========================================================================
        ast_tree = None
        try:
            ast_tree = ast.parse(code)
        except SyntaxError:
            pass

        # 1.1 Line-by-line syntax scan for compound statements and statement formatting
        for idx, line in enumerate(lines, start=1):
            stripped = line.rstrip()
            if not stripped:
                continue

            header_match = re.search(r'^\s*(def|class|if|elif|else|for|while|try|except|finally|with)\b', stripped)
            if header_match and idx not in flagged_lines:
                header_word = header_match.group(1)

                # Check 1.1A: Extra colons at end of header (e.g., 'for i in arr::')
                if re.search(r'::+$', stripped):
                    flagged_lines.add(idx)
                    all_colons = re.search(r'(:+)$', stripped).group(1)
                    extra_colons = all_colons[1:]
                    start_col = stripped.rfind(extra_colons) + 1
                    end_col = start_col + len(extra_colons)
                    s_off = position_to_offset(code, idx, start_col)
                    e_off = s_off + len(extra_colons)
                    patch = StructuredPatch(
                        file="source.py",
                        start_line=idx,
                        start_column=start_col,
                        end_line=idx,
                        end_column=end_col,
                        original_code=extra_colons,
                        replacement_code="",
                        start_offset=s_off,
                        end_offset=e_off,
                        source_hash=source_hash,
                        reason=f"Delete extraneous colon ':' at end of {header_word} statement header."
                    )
                    cand_code = apply_patch(code, patch)
                    val_result = validate_repaired_program(SupportedLanguage.PYTHON, cand_code, test_input)
                    ml_score, ml_exp = ml_model.predict_suspiciousness(stripped, "SyntaxError", 1)
                    evidence = fusion_engine.fuse(
                        compiler_score=0.98,
                        compiler_msg=f"SyntaxError: invalid syntax at trailing colons",
                        static_score=0.98,
                        static_msg=f"Multiple colons '{all_colons}' at end of {header_word} header",
                        runtime_score=0.0,
                        runtime_msg="Parsing stage failure",
                        ast_score=0.95,
                        ast_msg="Invalid terminal colon token count",
                        ml_score=ml_score,
                        ml_msg=ml_exp
                    )
                    bug = BugItem(
                        bug_id=len(bugs) + 1,
                        category=BugCategory.SYNTAX_ERROR,
                        severity=BugSeverity.CRITICAL,
                        status="DETECTED",
                        file="source.py",
                        line=idx,
                        column=start_col,
                        end_line=idx,
                        end_column=end_col,
                        code_statement=stripped,
                        ast_node_type="SyntaxError",
                        root_cause_line=idx,
                        root_cause_column=start_col,
                        root_cause_code=stripped,
                        failure_line=idx,
                        failure_column=start_col,
                        failure_code=stripped,
                        message=f"Syntax Error: Extraneous colon ':' after {header_word} statement at line {idx}.",
                        what_is_wrong=f"The {header_word} statement header contains extra colons ('{all_colons}').",
                        why_it_is_wrong="In Python grammar, a compound statement header must terminate with exactly one colon before an indented suite block.",
                        what_happens="Python parser aborts with SyntaxError: invalid syntax.",
                        what_should_be_changed="Delete the extra colon ':'.",
                        patch=patch,
                        candidate_fixes=[
                            CandidateFix(
                                fix_id=1,
                                title="Delete extra colon",
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

                # Check 1.1B: Semicolon on header (e.g. 'def test_entry(arr);' or 'for i in arr;')
                elif re.search(r'[;]+:?$', stripped):
                    flagged_lines.add(idx)
                    bad_chars = re.search(r'([;]+:?)$', stripped).group(1)
                    start_col = stripped.rfind(bad_chars) + 1
                    end_col = start_col + len(bad_chars)
                    s_off = position_to_offset(code, idx, start_col)
                    e_off = s_off + len(bad_chars)
                    patch = StructuredPatch(
                        file="source.py",
                        start_line=idx,
                        start_column=start_col,
                        end_line=idx,
                        end_column=end_col,
                        original_code=bad_chars,
                        replacement_code=":",
                        start_offset=s_off,
                        end_offset=e_off,
                        source_hash=source_hash,
                        reason=f"Replace '{bad_chars}' with ':' at end of {header_word} statement header."
                    )
                    cand_code = apply_patch(code, patch)
                    val_result = validate_repaired_program(SupportedLanguage.PYTHON, cand_code, test_input)
                    ml_score, ml_exp = ml_model.predict_suspiciousness(stripped, "SyntaxError", 1)
                    evidence = fusion_engine.fuse(
                        compiler_score=0.99,
                        compiler_msg=f"SyntaxError: expected ':' (found '{bad_chars}')",
                        static_score=0.98,
                        static_msg=f"Semicolon '{bad_chars}' used instead of colon ':'",
                        runtime_score=0.0,
                        runtime_msg="Parsing stage failure",
                        ast_score=0.95,
                        ast_msg="Unexpected semicolon token at header terminator",
                        ml_score=ml_score,
                        ml_msg=ml_exp
                    )
                    bug = BugItem(
                        bug_id=len(bugs) + 1,
                        category=BugCategory.SYNTAX_ERROR,
                        severity=BugSeverity.CRITICAL,
                        status="DETECTED",
                        file="source.py",
                        line=idx,
                        column=start_col,
                        end_line=idx,
                        end_column=end_col,
                        code_statement=stripped,
                        ast_node_type="SyntaxError",
                        root_cause_line=idx,
                        root_cause_column=start_col,
                        root_cause_code=stripped,
                        failure_line=idx,
                        failure_column=start_col,
                        failure_code=stripped,
                        message=f"Syntax Error: Semicolon '{bad_chars}' used instead of colon ':' at line {idx}.",
                        what_is_wrong=f"The {header_word} statement terminates with '{bad_chars}' instead of ':'.",
                        why_it_is_wrong="In Python grammar, compound statement headers must terminate with a colon ':' before the block. Semicolons are statement separators, not header terminators.",
                        what_happens="Python compiler aborts with SyntaxError: expected ':'.",
                        what_should_be_changed="Replace ';' with ':'.",
                        patch=patch,
                        candidate_fixes=[
                            CandidateFix(
                                fix_id=1,
                                title="Replace ; with :",
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

                # Check 1.1C: Missing colon completely
                elif not stripped.endswith(":") and not stripped.endswith("\\"):
                    flagged_lines.add(idx)
                    start_col = len(stripped) + 1
                    end_col = start_col
                    s_off = position_to_offset(code, idx, start_col)
                    e_off = s_off
                    patch = StructuredPatch(
                        file="source.py",
                        start_line=idx,
                        start_column=start_col,
                        end_line=idx,
                        end_column=end_col,
                        original_code="",
                        replacement_code=":",
                        start_offset=s_off,
                        end_offset=e_off,
                        source_hash=source_hash,
                        reason=f"Add missing terminal colon ':' after {header_word} statement."
                    )
                    cand_code = apply_patch(code, patch)
                    val_result = validate_repaired_program(SupportedLanguage.PYTHON, cand_code, test_input)
                    ml_score, ml_exp = ml_model.predict_suspiciousness(stripped, "SyntaxError", 1)
                    evidence = fusion_engine.fuse(
                        compiler_score=0.98,
                        compiler_msg=f"Python syntax requires ':' at end of {header_word} header",
                        static_score=0.95,
                        static_msg="Unterminated compound statement header",
                        runtime_score=0.0,
                        runtime_msg="Parsing stage failure",
                        ast_score=0.90,
                        ast_msg="Missing terminal colon token",
                        ml_score=ml_score,
                        ml_msg=ml_exp
                    )
                    bug = BugItem(
                        bug_id=len(bugs) + 1,
                        category=BugCategory.SYNTAX_ERROR,
                        severity=BugSeverity.CRITICAL,
                        status="DETECTED",
                        file="source.py",
                        line=idx,
                        column=start_col,
                        end_line=idx,
                        end_column=end_col,
                        code_statement=stripped,
                        ast_node_type="SyntaxError",
                        root_cause_line=idx,
                        root_cause_column=start_col,
                        root_cause_code=stripped,
                        failure_line=idx,
                        failure_column=start_col,
                        failure_code=stripped,
                        message=f"Syntax Error: Missing colon ':' after {header_word} statement at line {idx}.",
                        what_is_wrong=f"The {header_word} statement does not end with a colon ':'.",
                        why_it_is_wrong="In Python, all compound statement headers (def, class, if, for, while) must terminate with a colon before the indented block.",
                        what_happens="Python compiler aborts with SyntaxError: expected ':' before block.",
                        what_should_be_changed="Append ':' to the statement.",
                        patch=patch,
                        candidate_fixes=[
                            CandidateFix(
                                fix_id=1,
                                title="Add missing colon",
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

            # Check 1.2: Extraneous or invalid semicolons in simple statements (e.g. 'total += i;;')
            elif idx not in flagged_lines:
                semi_match = re.search(r'(;{2,})\s*$', line)
                if semi_match:
                    flagged_lines.add(idx)
                    bad_semis = semi_match.group(1)
                    start_col = line.rfind(bad_semis) + 1
                    end_col = start_col + len(bad_semis)
                    s_off = position_to_offset(code, idx, start_col)
                    e_off = s_off + len(bad_semis)
                    patch = StructuredPatch(
                        file="source.py",
                        start_line=idx,
                        start_column=start_col,
                        end_line=idx,
                        end_column=end_col,
                        original_code=bad_semis,
                        replacement_code="",
                        start_offset=s_off,
                        end_offset=e_off,
                        source_hash=source_hash,
                        reason=f"Remove extraneous statement terminators '{bad_semis}'."
                    )
                    cand_code = apply_patch(code, patch)
                    val_result = validate_repaired_program(SupportedLanguage.PYTHON, cand_code, test_input)
                    ml_score, ml_exp = ml_model.predict_suspiciousness(stripped, "SyntaxError", 1)
                    evidence = fusion_engine.fuse(
                        compiler_score=0.95,
                        compiler_msg=f"SyntaxError: invalid syntax at '{bad_semis}'",
                        static_score=0.95,
                        static_msg=f"Consecutive semicolon tokens '{bad_semis}'",
                        runtime_score=0.0,
                        runtime_msg="Parsing stage failure",
                        ast_score=0.90,
                        ast_msg="Extraneous empty statement separator",
                        ml_score=ml_score,
                        ml_msg=ml_exp
                    )
                    bug = BugItem(
                        bug_id=len(bugs) + 1,
                        category=BugCategory.SYNTAX_ERROR,
                        severity=BugSeverity.CRITICAL,
                        status="DETECTED",
                        file="source.py",
                        line=idx,
                        column=start_col,
                        end_line=idx,
                        end_column=end_col,
                        code_statement=stripped,
                        ast_node_type="SyntaxError",
                        root_cause_line=idx,
                        root_cause_column=start_col,
                        root_cause_code=stripped,
                        failure_line=idx,
                        failure_column=start_col,
                        failure_code=stripped,
                        message=f"Syntax Error: Extraneous empty statement terminator '{bad_semis}' at line {idx}.",
                        what_is_wrong=f"The statement contains consecutive semicolons '{bad_semis}'.",
                        why_it_is_wrong="Consecutive semicolons introduce an empty statement that violates Python syntax rules.",
                        what_happens="Python parser aborts with SyntaxError: invalid syntax.",
                        what_should_be_changed="Delete the extra semicolons.",
                        patch=patch,
                        candidate_fixes=[
                            CandidateFix(
                                fix_id=1,
                                title="Delete extra semicolons",
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

        # Check 1.3: Iterative AST Parse Error Recovery
        # Discovers any remaining arbitrary syntax errors across the whole file
        temp_lines = list(lines)
        for iteration in range(15):
            curr_code = "".join(temp_lines)
            try:
                ast.parse(curr_code)
                break  # Parse succeeded across entire temporary source
            except SyntaxError as syn_err:
                err_line = syn_err.lineno or 1
                err_col = syn_err.offset or 1
                err_line_text = lines[err_line - 1].rstrip() if err_line <= total_lines else ""

                if err_line not in flagged_lines:
                    flagged_lines.add(err_line)
                    s_off = position_to_offset(code, err_line, err_col)
                    e_off = s_off + 1
                    patch = StructuredPatch(
                        file="source.py",
                        start_line=err_line,
                        start_column=err_col,
                        end_line=err_line,
                        end_column=err_col + 1,
                        original_code=code[s_off:e_off] if s_off < len(code) else err_line_text,
                        replacement_code="",
                        start_offset=s_off,
                        end_offset=e_off,
                        source_hash=source_hash,
                        reason=f"Syntax error: {syn_err.msg}"
                    )
                    evidence = fusion_engine.fuse(
                        compiler_score=0.99,
                        compiler_msg=f"Python parser error: {syn_err.msg}",
                        static_score=0.90,
                        static_msg="Invalid Python token stream",
                        runtime_score=0.0,
                        runtime_msg="Blocked at parse stage",
                        ast_score=0.85,
                        ast_msg="Malformed token",
                        ml_score=0.90,
                        ml_msg="Syntax defect"
                    )
                    bug = BugItem(
                        bug_id=len(bugs) + 1,
                        category=BugCategory.SYNTAX_ERROR,
                        severity=BugSeverity.CRITICAL,
                        status="DETECTED",
                        file="source.py",
                        line=err_line,
                        column=err_col,
                        code_statement=err_line_text,
                        ast_node_type="SyntaxError",
                        root_cause_line=err_line,
                        root_cause_column=err_col,
                        root_cause_code=err_line_text,
                        failure_line=err_line,
                        failure_column=err_col,
                        failure_code=err_line_text,
                        message=f"Syntax Error on line {err_line}: {syn_err.msg}",
                        what_is_wrong=f"Syntax error: {syn_err.msg}",
                        why_it_is_wrong="Source code violates Python grammar specifications.",
                        what_happens="Execution cannot begin until syntax errors are resolved.",
                        what_should_be_changed="Correct the syntax error.",
                        patch=patch,
                        confidence=0.95,
                        evidence=evidence
                    )
                    bugs.append(bug)

                # Recover temporary copy to uncover further syntax errors on subsequent lines
                if 1 <= err_line <= len(temp_lines):
                    indent_match = re.match(r'^(\s*)', temp_lines[err_line - 1])
                    indent = indent_match.group(1) if indent_match else ""
                    temp_lines[err_line - 1] = f"{indent}pass\n"

        # =========================================================================
        # PHASE 2: Static Boundary & Logic Checks Across Entire Source
        # =========================================================================
        # Check 2.1: Array Index Out of Bounds via range(len(arr) + 1)
        for idx, line in enumerate(lines, start=1):
            if idx in flagged_lines:
                continue
            loop_match = re.search(r'for\s+([a-zA-Z_]\w*)\s+in\s+range\s*\(\s*len\s*\(([^)]+)\)\s*\+\s*1\s*\)', line)
            if loop_match:
                root_line = idx
                flagged_lines.add(root_line)
                root_code = line.rstrip()
                loop_var = loop_match.group(1)
                arr_expr = loop_match.group(2).strip()

                # Locate failure statement accessing array with loop_var
                fail_line = root_line
                fail_code = root_code
                for sub_idx in range(idx + 1, min(total_lines + 1, idx + 25)):
                    sub_line = lines[sub_idx - 1]
                    if re.search(rf'\[\s*{loop_var}\s*\]', sub_line):
                        fail_line = sub_idx
                        fail_code = sub_line.rstrip()
                        break

                # Replacement: remove + 1
                match_span = re.search(r'range\s*\(\s*len\s*\([^)]+\)\s*\+\s*1\s*\)', root_code)
                if match_span:
                    target_str = match_span.group(0)
                    clean_str = re.sub(r'\s*\+\s*1', '', target_str)
                    s_col = match_span.start() + 1
                    e_col = match_span.end() + 1
                else:
                    target_str = "+ 1"
                    clean_str = ""
                    s_col = root_code.find("+ 1") + 1
                    e_col = s_col + 3

                s_off = position_to_offset(code, root_line, s_col)
                e_off = s_off + len(target_str)
                patch = StructuredPatch(
                    file="source.py",
                    start_line=root_line,
                    start_column=s_col,
                    end_line=root_line,
                    end_column=e_col,
                    original_code=target_str,
                    replacement_code=clean_str,
                    start_offset=s_off,
                    end_offset=e_off,
                    source_hash=source_hash,
                    reason=f"Valid indices for '{arr_expr}' are 0 to len({arr_expr})-1. range(len({arr_expr}) + 1) allows index {loop_var} to reach len({arr_expr})."
                )
                cand_code = apply_patch(code, patch)
                val_result = validate_repaired_program(SupportedLanguage.PYTHON, cand_code, test_input)
                ml_score, ml_exp = ml_model.predict_suspiciousness(root_code, "For", depth=2, is_loop=True)
                evidence = fusion_engine.fuse(
                    compiler_score=0.0,
                    compiler_msg="Static Python parser inspected boundary condition",
                    static_score=0.96,
                    static_msg="Loop range exceeds sequence boundary (+1 off-by-one)",
                    runtime_score=0.90,
                    runtime_msg="IndexError: list index out of range hazard",
                    ast_score=0.90,
                    ast_msg="Call range(BinOp(Call(len), Add, 1))",
                    ml_score=ml_score,
                    ml_msg=ml_exp
                )
                bug = BugItem(
                    bug_id=len(bugs) + 1,
                    category=BugCategory.INDEX_OUT_OF_BOUNDS,
                    severity=BugSeverity.HIGH,
                    status="DETECTED",
                    file="source.py",
                    line=root_line,
                    column=s_col,
                    end_line=root_line,
                    end_column=e_col,
                    code_statement=root_code,
                    ast_node_type="ForLoopBoundary",
                    root_cause_line=root_line,
                    root_cause_column=s_col,
                    root_cause_code=root_code,
                    failure_line=fail_line,
                    failure_column=1,
                    failure_code=fail_code,
                    message=f"Array Index Out of Bounds: Loop range exceeds sequence boundary at line {root_line}.",
                    what_is_wrong=f"The loop iteration range includes 'len(...) + 1' ({target_str}).",
                    why_it_is_wrong=f"Python sequences are 0-indexed with valid indices from 0 to len({arr_expr})-1. Using range(len({arr_expr}) + 1) produces an index equal to len({arr_expr}), causing an out-of-bounds access.",
                    what_happens="During execution, accessing the list at index len(arr) raises IndexError: list index out of range.",
                    what_should_be_changed=f"Change '{target_str}' to '{clean_str}'.",
                    patch=patch,
                    candidate_fixes=[
                        CandidateFix(
                            fix_id=1,
                            title="Remove + 1 from range(len(...))",
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

        # Check 2.2: Division by Zero across all lines
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
                        file="source.py",
                        start_line=root_line,
                        start_column=s_col,
                        end_line=root_line,
                        end_column=e_col,
                        original_code=orig_snip,
                        replacement_code=repl_snip,
                        start_offset=s_off,
                        end_offset=e_off,
                        source_hash=source_hash,
                        reason="Division by literal zero always raises ZeroDivisionError."
                    )
                cand_code = apply_patch(code, patch)
                val_result = validate_repaired_program(SupportedLanguage.PYTHON, cand_code, test_input)
                ml_score, ml_exp = ml_model.predict_suspiciousness(root_code, "BinOp", depth=1)
                evidence = fusion_engine.fuse(
                    compiler_score=0.90,
                    compiler_msg="Static inspection identified literal zero divisor",
                    static_score=0.98,
                    static_msg="Literal divisor 0 detected",
                    runtime_score=0.95,
                    runtime_msg="ZeroDivisionError runtime crash",
                    ast_score=0.90,
                    ast_msg="BinOp(Div, Constant(0))",
                    ml_score=ml_score,
                    ml_msg=ml_exp
                )
                bug = BugItem(
                    bug_id=len(bugs) + 1,
                    category=BugCategory.DIVISION_BY_ZERO,
                    severity=BugSeverity.CRITICAL,
                    status="DETECTED",
                    file="source.py",
                    line=root_line,
                    column=s_idx + 1,
                    end_line=root_line,
                    end_column=s_idx + 4,
                    code_statement=root_code,
                    ast_node_type="DivisionByZero",
                    root_cause_line=root_line,
                    root_cause_column=s_idx + 1,
                    root_cause_code=root_code,
                    failure_line=root_line,
                    failure_column=s_idx + 1,
                    failure_code=root_code,
                    message=f"Division by Zero on line {root_line}.",
                    what_is_wrong="The divisor in the arithmetic operation is 0.",
                    why_it_is_wrong="Mathematical division by zero is undefined and illegal in Python.",
                    what_happens="Raises ZeroDivisionError: division by zero.",
                    what_should_be_changed="Replace divisor with a non-zero value or guard against zero.",
                    patch=patch,
                    candidate_fixes=[
                        CandidateFix(
                            fix_id=1,
                            title="Replace / 0 with / 1",
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

        # Check 2.3: Assignment in conditional: if x = 10:
        for idx, line in enumerate(lines, start=1):
            if idx in flagged_lines:
                continue
            assign_match = re.search(r'\b(if|elif)\s+([a-zA-Z_]\w*\s*=\s*[^=;><!:]+):', line)
            if assign_match:
                root_line = idx
                flagged_lines.add(root_line)
                root_code = line.rstrip()
                orig_snip = assign_match.group(2)
                repl_snip = re.sub(r'\s*=\s*', ' == ', orig_snip, count=1)
                s_idx = line.find(orig_snip)
                if s_idx != -1:
                    s_col = s_idx + 1
                    e_col = s_col + len(orig_snip)
                    s_off = position_to_offset(code, root_line, s_col)
                    e_off = s_off + len(orig_snip)
                    patch = StructuredPatch(
                        file="source.py",
                        start_line=root_line,
                        start_column=s_col,
                        end_line=root_line,
                        end_column=e_col,
                        original_code=orig_snip,
                        replacement_code=repl_snip,
                        start_offset=s_off,
                        end_offset=e_off,
                        source_hash=source_hash,
                        reason="Use equality comparison '==' rather than assignment '=' inside condition."
                    )
                    cand_code = apply_patch(code, patch)
                    val_result = validate_repaired_program(SupportedLanguage.PYTHON, cand_code, test_input)
                    ml_score, ml_exp = ml_model.predict_suspiciousness(root_code, "If", depth=2, is_cond=True)
                    evidence = fusion_engine.fuse(
                        compiler_score=0.95,
                        compiler_msg="Syntax error: invalid syntax (assignment in if condition)",
                        static_score=0.98,
                        static_msg="Assignment operator in condition",
                        runtime_score=0.0,
                        runtime_msg="Blocked by syntax check",
                        ast_score=0.85,
                        ast_msg="Condition assignment",
                        ml_score=ml_score,
                        ml_msg=ml_exp
                    )
                    bug = BugItem(
                        bug_id=len(bugs) + 1,
                        category=BugCategory.INCORRECT_ASSIGNMENT_IN_CONDITION,
                        severity=BugSeverity.HIGH,
                        status="DETECTED",
                        file="source.py",
                        line=root_line,
                        column=s_idx + 1,
                        code_statement=root_code,
                        ast_node_type="IfAssignment",
                        root_cause_line=root_line,
                        root_cause_column=s_idx + 1,
                        root_cause_code=root_code,
                        failure_line=root_line,
                        failure_column=s_idx + 1,
                        failure_code=root_code,
                        message=f"Incorrect Assignment in Condition at line {root_line}.",
                        what_is_wrong=f"The conditional statement uses assignment '=' ({orig_snip}) instead of comparison '=='.",
                        why_it_is_wrong="In Python, variable assignment inside an 'if' condition is a syntax error.",
                        what_happens="Raises SyntaxError: invalid syntax.",
                        what_should_be_changed=f"Replace '{orig_snip}' with '{repl_snip}'.",
                        patch=patch,
                        candidate_fixes=[
                            CandidateFix(
                                fix_id=1,
                                title="Replace = with ==",
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

        # =========================================================================
        # PHASE 3: Sandboxed Runtime Execution Check (if no syntax errors)
        # =========================================================================
        has_syntax_flaws = any(b.category == BugCategory.SYNTAX_ERROR for b in bugs)
        if not has_syntax_flaws and len(bugs) == 0:
            with IsolatedSandbox(prefix="py_run_") as sandbox:
                py_f = sandbox.write_file("test.py", code)
                py_exe = sys.executable or "python"
                ok, stdout, stderr, ret = sandbox.run_process([py_exe, py_f], input_data=test_input, timeout_sec=3.0)

                if not ok or "Traceback" in stderr:
                    tb_match = re.findall(r'File ".*test\.py", line (\d+).*?\n\s*(.*?)\n(\w+Error: .*)', stderr)
                    if tb_match:
                        line_str, stmt_text, err_msg = tb_match[-1]
                        err_line = int(line_str)
                        if err_line not in flagged_lines:
                            flagged_lines.add(err_line)
                            curr_line_text = lines[err_line - 1].rstrip() if err_line <= total_lines else stmt_text
                            cat = BugCategory.RUNTIME_ERROR
                            if "IndexError" in err_msg:
                                cat = BugCategory.INDEX_OUT_OF_BOUNDS
                            elif "ZeroDivisionError" in err_msg:
                                cat = BugCategory.DIVISION_BY_ZERO
                            elif "TypeError" in err_msg:
                                cat = BugCategory.TYPE_ERROR
                            elif "NameError" in err_msg:
                                cat = BugCategory.UNDEFINED_VARIABLE

                            evidence = fusion_engine.fuse(
                                runtime_score=0.99,
                                runtime_msg=f"Traceback: {err_msg}",
                                static_score=0.40,
                                static_msg="Uncaught runtime exception",
                                ast_score=0.50,
                                ast_msg="Runtime crash location",
                                ml_score=0.75,
                                ml_msg="High runtime failure probability"
                            )
                            bug = BugItem(
                                bug_id=len(bugs) + 1,
                                category=cat,
                                severity=BugSeverity.HIGH,
                                status="DETECTED",
                                file="source.py",
                                line=err_line,
                                column=1,
                                code_statement=curr_line_text,
                                ast_node_type="RuntimeCrash",
                                root_cause_line=err_line,
                                root_cause_column=1,
                                root_cause_code=curr_line_text,
                                failure_line=err_line,
                                failure_column=1,
                                failure_code=curr_line_text,
                                message=f"Runtime Error: {err_msg}",
                                what_is_wrong=f"Execution raised {err_msg}",
                                why_it_is_wrong="The operation executed in an invalid runtime state or with invalid inputs.",
                                what_happens=f"Program terminated abnormally with exit code {ret}.",
                                what_should_be_changed="Correct the invalid operation or add proper error handling.",
                                confidence=0.90,
                                evidence=evidence
                            )
                            bugs.append(bug)

        # =========================================================================
        # PHASE 4: Sorting, Re-Indexing & Cumulative Corrected Code Generation
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
        return bugs, corrected_program, metrics
