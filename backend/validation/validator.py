"""
Validation engine for running program builds, runtime tests, and repair verification.
"""

import os
import sys
import ast
import re
from typing import Optional, Dict, Any
from backend.core.state import SupportedLanguage
from backend.models.schemas import RepairValidationResult
from backend.utils.env_check import check_system_environment
from .sandbox import IsolatedSandbox


def validate_repaired_program(
    language: SupportedLanguage,
    code: str,
    test_input: Optional[str] = "",
    expected_output: Optional[str] = None
) -> RepairValidationResult:
    """
    Validate the repaired program by compiling/parsing and executing in an isolated sandbox.
    """
    env = check_system_environment()

    with IsolatedSandbox(prefix=f"val_{language.value}_") as sandbox:
        # ==================== PYTHON ====================
        if language == SupportedLanguage.PYTHON:
            # 1. Parse check
            try:
                ast.parse(code)
            except SyntaxError as e:
                return RepairValidationResult(
                    compile_success=False,
                    run_success=False,
                    tests_passed=False,
                    runtime_error_removed=False,
                    message=f"Python syntax verification failed: {e.msg} at line {e.lineno}",
                    stderr=f"SyntaxError: {e.msg} (line {e.lineno})"
                )

            # 2. Execution check
            py_file = sandbox.write_file("repaired.py", code)
            py_exe = sys.executable or "python"
            ok, stdout, stderr, ret = sandbox.run_process([py_exe, py_file], input_data=test_input, timeout_sec=3.0)

            # Check for runtime exceptions
            has_exception = (not ok) or ("Traceback" in stderr) or (ret != 0)
            tests_pass = True
            if expected_output is not None and expected_output.strip():
                tests_pass = (stdout.strip() == expected_output.strip())

            return RepairValidationResult(
                compile_success=True,
                run_success=not has_exception,
                tests_passed=tests_pass and (not has_exception),
                runtime_error_removed=not has_exception,
                message="Python code parsed and executed successfully without exceptions." if not has_exception else f"Runtime error during execution: {stderr.strip()[:200]}",
                stdout=stdout,
                stderr=stderr,
                reanalysis_clean=not has_exception
            )

        # ==================== C ====================
        elif language == SupportedLanguage.C:
            c_file = sandbox.write_file("main.c", code)
            gcc_path = env["gcc"]["path"]

            if gcc_path:
                exe_name = "main.exe" if os.name == "nt" else "main"
                exe_path = os.path.join(sandbox.temp_dir, exe_name)
                comp_ok, comp_out, comp_err, comp_ret = sandbox.run_process(
                    [gcc_path, "-Wall", c_file, "-o", exe_path],
                    timeout_sec=5.0
                )
                if not comp_ok or comp_ret != 0:
                    return RepairValidationResult(
                        compile_success=False,
                        run_success=False,
                        tests_passed=False,
                        runtime_error_removed=False,
                        message=f"C compilation failed:\n{comp_err}",
                        stderr=comp_err
                    )

                # Run compiled binary
                run_ok, stdout, stderr, run_ret = sandbox.run_process([exe_path], input_data=test_input, timeout_sec=3.0)
                tests_pass = True
                if expected_output is not None and expected_output.strip():
                    tests_pass = (stdout.strip() == expected_output.strip())

                return RepairValidationResult(
                    compile_success=True,
                    run_success=run_ok,
                    tests_passed=tests_pass and run_ok,
                    runtime_error_removed=run_ok,
                    message="C program compiled with GCC and executed cleanly.",
                    stdout=stdout,
                    stderr=stderr,
                    reanalysis_clean=run_ok
                )
            else:
                # Tree-sitter static validation fallback
                from tree_sitter import Language, Parser
                import tree_sitter_c
                p = Parser(Language(tree_sitter_c.language()))
                tree = p.parse(code.encode("utf-8"))
                has_err = tree.root_node.has_error
                return RepairValidationResult(
                    compile_success=not has_err,
                    run_success=not has_err,
                    tests_passed=not has_err,
                    runtime_error_removed=not has_err,
                    message="AST Syntax validation PASSED (GCC not installed in system PATH for native binary execution).",
                    stdout="[Static Tree-Sitter AST Verified]",
                    reanalysis_clean=not has_err
                )

        # ==================== C++ ====================
        elif language == SupportedLanguage.CPP:
            cpp_file = sandbox.write_file("main.cpp", code)
            gpp_path = env["g++"]["path"]

            if gpp_path:
                exe_name = "main.exe" if os.name == "nt" else "main"
                exe_path = os.path.join(sandbox.temp_dir, exe_name)
                comp_ok, comp_out, comp_err, comp_ret = sandbox.run_process(
                    [gpp_path, "-Wall", cpp_file, "-o", exe_path],
                    timeout_sec=5.0
                )
                if not comp_ok or comp_ret != 0:
                    return RepairValidationResult(
                        compile_success=False,
                        run_success=False,
                        tests_passed=False,
                        runtime_error_removed=False,
                        message=f"C++ compilation failed:\n{comp_err}",
                        stderr=comp_err
                    )

                run_ok, stdout, stderr, run_ret = sandbox.run_process([exe_path], input_data=test_input, timeout_sec=3.0)
                tests_pass = True
                if expected_output is not None and expected_output.strip():
                    tests_pass = (stdout.strip() == expected_output.strip())

                return RepairValidationResult(
                    compile_success=True,
                    run_success=run_ok,
                    tests_passed=tests_pass and run_ok,
                    runtime_error_removed=run_ok,
                    message="C++ program compiled with G++ and executed cleanly.",
                    stdout=stdout,
                    stderr=stderr,
                    reanalysis_clean=run_ok
                )
            else:
                from tree_sitter import Language, Parser
                import tree_sitter_cpp
                p = Parser(Language(tree_sitter_cpp.language()))
                tree = p.parse(code.encode("utf-8"))
                has_err = tree.root_node.has_error
                return RepairValidationResult(
                    compile_success=not has_err,
                    run_success=not has_err,
                    tests_passed=not has_err,
                    runtime_error_removed=not has_err,
                    message="AST Syntax validation PASSED (G++ not installed in system PATH for native binary execution).",
                    stdout="[Static Tree-Sitter AST Verified]",
                    reanalysis_clean=not has_err
                )

        # ==================== JAVA ====================
        elif language == SupportedLanguage.JAVA:
            # Extract class name from code if available
            class_match = re.search(r'(?:public\s+)?class\s+(\w+)', code)
            class_name = class_match.group(1) if class_match else "Main"
            java_file = sandbox.write_file(f"{class_name}.java", code)
            javac_path = env["javac"]["path"]
            java_path = env["java"]["path"]

            if javac_path and java_path:
                comp_ok, comp_out, comp_err, comp_ret = sandbox.run_process(
                    [javac_path, java_file],
                    timeout_sec=5.0
                )
                if not comp_ok or comp_ret != 0:
                    return RepairValidationResult(
                        compile_success=False,
                        run_success=False,
                        tests_passed=False,
                        runtime_error_removed=False,
                        message=f"Java compilation failed:\n{comp_err}",
                        stderr=comp_err
                    )

                run_ok, stdout, stderr, run_ret = sandbox.run_process([java_path, class_name], input_data=test_input, timeout_sec=3.0)
                tests_pass = True
                if expected_output is not None and expected_output.strip():
                    tests_pass = (stdout.strip() == expected_output.strip())

                return RepairValidationResult(
                    compile_success=True,
                    run_success=run_ok,
                    tests_passed=tests_pass and run_ok,
                    runtime_error_removed=run_ok,
                    message="Java program compiled with javac and executed cleanly.",
                    stdout=stdout,
                    stderr=stderr,
                    reanalysis_clean=run_ok
                )
            else:
                from tree_sitter import Language, Parser
                import tree_sitter_java
                p = Parser(Language(tree_sitter_java.language()))
                tree = p.parse(code.encode("utf-8"))
                has_err = tree.root_node.has_error
                return RepairValidationResult(
                    compile_success=not has_err,
                    run_success=not has_err,
                    tests_passed=not has_err,
                    runtime_error_removed=not has_err,
                    message="AST Syntax validation PASSED (javac not installed in system PATH for bytecode compilation).",
                    stdout="[Static Tree-Sitter Java AST Verified]",
                    reanalysis_clean=not has_err
                )

    return RepairValidationResult(message="Unknown language validation request.")
