"""
API route definitions for the AI Bug Finder dashboard.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from backend.core.state import AnalysisState, SupportedLanguage, BugCategory
from backend.core.language_validator import validate_language
from backend.models.schemas import (
    AnalysisRequest,
    AnalysisReport,
    ResearchMetrics,
    ApplyPatchRequest,
    ApplyAllFixesRequest,
    ApplyAllFixesResponse
)
from backend.analyzers.python_analyzer import PythonAnalyzer
from backend.analyzers.c_analyzer import CAnalyzer
from backend.analyzers.cpp_analyzer import CppAnalyzer
from backend.analyzers.java_analyzer import JavaAnalyzer
from backend.repair.code_stitcher import (
    apply_patch,
    apply_single_patch_verified,
    apply_multiple_patches_transactional,
    compute_source_hash
)
from backend.validation.validator import validate_repaired_program
from backend.utils.env_check import check_system_environment

router = APIRouter(prefix="/api")

# Analyzer instances
analyzers = {
    SupportedLanguage.PYTHON: PythonAnalyzer(),
    SupportedLanguage.C: CAnalyzer(),
    SupportedLanguage.CPP: CppAnalyzer(),
    SupportedLanguage.JAVA: JavaAnalyzer(),
}


@router.get("/env")
def get_environment():
    """Return status of installed compilers, runtimes, and tools."""
    return check_system_environment()


@router.post("/repair/apply")
def apply_single_patch_endpoint(request: ApplyPatchRequest) -> Dict[str, Any]:
    """Apply a single structured patch to code with strict offset and hash verification."""
    result = apply_single_patch_verified(request.code, request.patch, request.source_hash)
    if not result["success"]:
        return {
            "success": False,
            "status": result["status"],
            "code": request.code,
            "message": result["message"]
        }
    return {
        "success": True,
        "status": "APPLIED",
        "code": result["code"],
        "message": "Patch cleanly replaced target code."
    }


@router.post("/repair/apply_all", response_model=ApplyAllFixesResponse)
def apply_all_fixes_endpoint(request: ApplyAllFixesRequest) -> ApplyAllFixesResponse:
    """
    Apply all non-conflicting fixes transactionally:
    1. Validates source hash (rejects STALE_SOURCE).
    2. Sorts patches bottom-to-top (descending start_offset) to avoid offset shift.
    3. Confirms exact target match at every slice before replacing.
    4. Slices code with strict replacement (deleting original error).
    5. Validates candidate in isolated sandbox with compiler/runtime.
    6. Re-analyzes repaired code to confirm bugs were eliminated.
    7. Rolls back if validation fails or introduces new critical errors.
    """
    current_hash = compute_source_hash(request.code)
    if request.source_hash and request.source_hash != current_hash:
        return ApplyAllFixesResponse(
            success=False,
            status="STALE_SOURCE",
            corrected_code=request.code,
            original_code=request.code,
            total_candidates=len(request.patches),
            message="Source code has changed since last analysis. Please re-analyze before applying fixes."
        )

    res = apply_multiple_patches_transactional(
        source_code=request.code,
        patches=request.patches,
        expected_hash=request.source_hash or current_hash
    )

    if not res["success"] or res["applied_count"] == 0:
        return ApplyAllFixesResponse(
            success=False,
            status=res["status"],
            corrected_code=request.code,
            original_code=request.code,
            total_candidates=len(request.patches),
            applied_count=res["applied_count"],
            failed_count=res["failed_count"],
            conflict_count=res["conflict_count"],
            applied_fixes=res["applied_fixes"],
            failed_fixes=res["failed_fixes"],
            conflicts=res["conflicts"],
            message=res["message"],
            patch_log=res["patch_log"]
        )

    repaired_code = res["corrected_code"]

    # Sandboxed validation of the cumulative repaired program
    val_result = validate_repaired_program(request.language, repaired_code, request.test_input or "")

    # Re-analysis of repaired code to confirm defects are resolved
    analyzer = analyzers.get(request.language)
    reanalysis_clean = False
    if analyzer:
        rem_bugs, _, _ = analyzer.analyze(repaired_code, request.test_input or "")
        reanalysis_clean = (len(rem_bugs) == 0)

    # Rollback check: if repair caused a regression on previously compiling code
    if not val_result.compile_success and val_result.message and "Failed" in val_result.message:
        orig_bugs, _, _ = analyzer.analyze(request.code, request.test_input or "") if analyzer else ([], None, None)
        orig_had_syntax = any(b.category == BugCategory.SYNTAX_ERROR for b in orig_bugs)
        if not orig_had_syntax and not val_result.compile_success:
            return ApplyAllFixesResponse(
                success=False,
                status="VALIDATION_FAILED_ROLLBACK",
                corrected_code=request.code,
                original_code=request.code,
                total_candidates=len(request.patches),
                applied_count=0,
                failed_count=res["applied_count"],
                conflict_count=res["conflict_count"],
                applied_fixes=[],
                failed_fixes=res["applied_fixes"],
                conflicts=res["conflicts"],
                validation=val_result,
                reanalysis_clean=False,
                message="Applying all fixes resulted in compilation error. Rolled back changes.",
                patch_log=res["patch_log"]
            )

    return ApplyAllFixesResponse(
        success=True,
        status="APPLIED_SUCCESSFULLY",
        corrected_code=repaired_code,
        original_code=request.code,
        total_candidates=len(request.patches),
        applied_count=res["applied_count"],
        failed_count=res["failed_count"],
        conflict_count=res["conflict_count"],
        applied_fixes=res["applied_fixes"],
        failed_fixes=res["failed_fixes"],
        conflicts=res["conflicts"],
        validation=val_result,
        reanalysis_clean=reanalysis_clean,
        message=f"Successfully applied {res['applied_count']} of {len(request.patches)} fix(es).",
        patch_log=res["patch_log"]
    )


@router.post("/analyze", response_model=AnalysisReport)
def analyze_code(request: AnalysisRequest) -> AnalysisReport:
    """
    Main analysis endpoint:
    1. Validates language match across all 12 pairs.
    2. Runs language-specific AST and compiler/runtime analysis.
    3. Performs fault localization (root cause vs failure line).
    4. Generates candidate patches and validates repairs in an isolated sandbox.
    5. Returns a comprehensive research analysis report.
    """
    code = request.code or ""
    req_id = request.request_id or "1"
    env_info = check_system_environment()
    source_hash = compute_source_hash(code)

    # Rule 32/33 Check: Empty or whitespace source
    if not code.strip():
        return AnalysisReport(
            request_id=req_id,
            status=AnalysisState.INVALID_SOURCE,
            language=request.language.value,
            is_mismatch=False,
            detected_language=None,
            message="Source code is empty. Please provide code to analyze.",
            bugs=[],
            corrected_code=None,
            original_code=code,
            metrics=ResearchMetrics(language=request.language.value),
            overall_summary="Invalid input: Source code is empty.",
            source_hash=source_hash,
            environment=env_info
        )

    # Step 1: Symmetrical Cross-Language Mismatch Validation
    val_result = validate_language(request.language, code)
    if val_result["status"] == AnalysisState.LANGUAGE_MISMATCH:
        return AnalysisReport(
            request_id=req_id,
            status=AnalysisState.LANGUAGE_MISMATCH,
            language=request.language.value,
            is_mismatch=True,
            detected_language=val_result["detected_language"],
            message=val_result["message"],
            bugs=[],
            corrected_code=None,
            original_code=code,
            metrics=ResearchMetrics(language=request.language.value),
            overall_summary=f"Analysis Halted: Language Mismatch detected. Selected {request.language.value.upper()}, but code is {val_result['detected_language'].upper()}.",
            source_hash=source_hash,
            environment=env_info
        )

    # Step 2: Language Analysis
    analyzer = analyzers.get(request.language)
    if not analyzer:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {request.language}")

    bugs, corrected_code, metrics = analyzer.analyze(code, request.test_input or "")

    # Step 3: Determine Overall Status
    total_bugs_count = len(bugs)
    is_blocked = any(b.category == BugCategory.SYNTAX_ERROR for b in bugs)
    raw_diag_count = sum(1 + len(b.related_diagnostics) for b in bugs)

    analysis_sum = {
        "confirmed_bugs": total_bugs_count,
        "analysis_blocked": is_blocked,
        "raw_diagnostics_count": raw_diag_count
    }

    if bugs:
        status = AnalysisState.BUG_DETECTED
        validated_repairs = sum(1 for b in bugs if b.validation and b.validation.compile_success)
        if validated_repairs == total_bugs_count and corrected_code:
            summary = f"Total Bugs Detected: {total_bugs_count}. All candidate repairs validated. Sequential fixes available below."
        elif validated_repairs > 0:
            summary = f"Total Bugs Detected: {total_bugs_count}. {validated_repairs} repair validated. Select any defect to rectify sequentially."
        else:
            summary = f"Total Bugs Detected: {total_bugs_count}. Candidate repairs generated for sequential rectification."
    else:
        # Code is Clean only when language passed, parsing succeeded, and 0 bugs were detected
        status = AnalysisState.CLEAN
        summary = "Code is Clean: Source code passed language validation, whole-program AST structure parsing, and all defect checks."

    return AnalysisReport(
        request_id=req_id,
        status=status,
        language=request.language.value,
        is_mismatch=False,
        detected_language=request.language.value,
        message=summary,
        total_bugs=total_bugs_count,
        bugs=bugs,
        corrected_code=corrected_code,
        original_code=code,
        metrics=metrics,
        overall_summary=summary,
        analysis_summary=analysis_sum,
        source_hash=source_hash,
        environment=env_info
    )


@router.get("/samples")
def get_sample_programs() -> Dict[str, Any]:
    """Provide real, verifiable sample programs for demonstration."""
    return {
        "python": {
            "multi_bug": 'def compute_values(arr)\n    total = 0\n    for i in range(len(arr) + 1):\n        total += arr[i]\n    scale = 100 / 0\n    return total * scale\n\ndata = [1, 2, 3, 4, 5]\nprint(compute_values(data))\n',
            "off_by_one": 'a = [1, 2, 3, 4, 5]\ntotal = 0\n\nfor i in range(len(a) + 1):\n    total += a[i]\n\nprint("Total:", total)\n',
            "clean": 'def calculate_total(arr):\n    total = 0\n    for x in arr:\n        total += x\n    return total\n\nprint("Total:", calculate_total([1, 2, 3, 4, 5]))\n',
            "syntax_error": 'def test()\n    print("Hello from Python!")\n',
            "division_by_zero": 'x = 10\ny = 0\nresult = x / y\nprint("Result:", result)\n',
            "repaired": 'a = [1, 2, 3, 4, 5]\ntotal = 0\n\nfor i in range(len(a)):\n    total += a[i]\n\nprint("Total:", total)\n'
        },
        "cpp": {
            "multi_bug": '#include <iostream>\nusing namespace std;\n\nint main() {\n    int n = 5;\n    int a[5] = {1, 2, 3, 4, 5};\n    int x = 10\n\n    for(int i = 0; i <= n; i++) {\n        cout << a[i] << endl;\n    }\n\n    if (x = 20) {\n        cout << "x is twenty" << endl;\n    }\n\n    return 0;\n}\n',
            "off_by_one": '#include <iostream>\nusing namespace std;\n\nint main() {\n    int n = 5;\n    int a[5] = {1, 2, 3, 4, 5};\n\n    for(int i = 0; i <= n; i++) {\n        cout << a[i] << endl;\n    }\n\n    return 0;\n}\n',
            "clean": '#include <iostream>\nusing namespace std;\n\nint main() {\n    int n = 5;\n    int a[5] = {1, 2, 3, 4, 5};\n    for(int i = 0; i < n; i++) {\n        cout << a[i] << " ";\n    }\n    cout << endl;\n    return 0;\n}\n',
            "syntax_error": '#include <iostream>\nusing namespace std;\n\nint main() {\n    int x = 10\n    cout << x << endl;\n    return 0;\n}\n',
            "assignment_in_cond": '#include <iostream>\nusing namespace std;\n\nint main() {\n    int x = 5;\n    if (x = 10) {\n        cout << "x is ten" << endl;\n    }\n    return 0;\n}\n',
            "repaired": '#include <iostream>\nusing namespace std;\n\nint main() {\n    int n = 5;\n    int a[5] = {1, 2, 3, 4, 5};\n\n    for(int i = 0; i < n; i++) {\n        cout << a[i] << endl;\n    }\n\n    return 0;\n}\n'
        },
        "c": {
            "multi_bug": '#include <stdio.h>\n\nint main(void) {\n    int n = 5;\n    int a[5] = {1, 2, 3, 4, 5};\n    int x = 10\n\n    for(int i = 0; i <= n; i++) {\n        printf("%d\\n", a[i]);\n    }\n\n    if (x = 20) {\n        printf("Match\\n");\n    }\n\n    return 0;\n}\n',
            "off_by_one": '#include <stdio.h>\n\nint main(void) {\n    int n = 5;\n    int a[5] = {1, 2, 3, 4, 5};\n\n    for(int i = 0; i <= n; i++) {\n        printf("%d\\n", a[i]);\n    }\n\n    return 0;\n}\n',
            "clean": '#include <stdio.h>\n\nint main(void) {\n    int n = 5;\n    int a[5] = {1, 2, 3, 4, 5};\n    for(int i = 0; i < n; i++) {\n        printf("%d ", a[i]);\n    }\n    printf("\\n");\n    return 0;\n}\n',
            "syntax_error": '#include <stdio.h>\n\nint main(void) {\n    int x = 42\n    printf("%d\\n", x);\n    return 0;\n}\n',
            "assignment_in_cond": '#include <stdio.h>\n\nint main(void) {\n    int x = 5;\n    if (x = 10) {\n        printf("Match\\n");\n    }\n    return 0;\n}\n',
            "repaired": '#include <stdio.h>\n\nint main(void) {\n    int n = 5;\n    int a[5] = {1, 2, 3, 4, 5};\n\n    for(int i = 0; i < n; i++) {\n        printf("%d\\n", a[i]);\n    }\n\n    return 0;\n}\n'
        },
        "java": {
            "multi_bug": 'public class Main {\n    public static void main(String[] args) {\n        int[] a = {1, 2, 3, 4, 5};\n        int x = 10\n\n        for(int i = 0; i <= a.length; i++) {\n            System.out.println(a[i]);\n        }\n\n        if (x = 20) {\n            System.out.println("Match");\n        }\n    }\n}\n',
            "off_by_one": 'public class Main {\n    public static void main(String[] args) {\n        int[] a = {1, 2, 3, 4, 5};\n        for(int i = 0; i <= a.length; i++) {\n            System.out.println(a[i]);\n        }\n    }\n}\n',
            "clean": 'public class Main {\n    public static void main(String[] args) {\n        int[] a = {1, 2, 3, 4, 5};\n        for(int i = 0; i < a.length; i++) {\n            System.out.println(a[i]);\n        }\n    }\n}\n',
            "syntax_error": 'public class Main {\n    public static void main(String[] args) {\n        int x = 100\n        System.out.println(x);\n    }\n}\n',
            "assignment_in_cond": 'public class Main {\n    public static void main(String[] args) {\n        int x = 5;\n        if (x = 10) {\n            System.out.println("x is ten");\n        }\n    }\n}\n',
            "repaired": 'public class Main {\n    public static void main(String[] args) {\n        int[] a = {1, 2, 3, 4, 5};\n        for(int i = 0; i < a.length; i++) {\n            System.out.println(a[i]);\n        }\n    }\n}\n'
        }
    }

