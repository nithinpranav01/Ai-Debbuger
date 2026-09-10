"""
Unit & Integration Tests for Verified Patch Application & Transactional Multi-Patch Repairs.
Validates:
1. Exact bug reported: Clean replacement without duplicating original erroneous code.
2. Bottom-to-top sorting: Prevents offset drift across multiple fixes.
3. Multiple identical substrings across different lines: Exact offset precision.
4. Source hash versioning: Rejection of stale/conflicting sources.
5. Overlapping patch conflict detection.
6. API endpoint /api/repair/apply_all and /api/repair/apply integration across C, C++, Java, Python.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.schemas import StructuredPatch, ApplyAllFixesRequest
from backend.core.state import SupportedLanguage
from backend.repair.code_stitcher import (
    compute_source_hash,
    position_to_offset,
    apply_single_patch_verified,
    apply_multiple_patches_transactional
)
from backend.analyzers.cpp_analyzer import CppAnalyzer
from backend.analyzers.c_analyzer import CAnalyzer
from backend.analyzers.java_analyzer import JavaAnalyzer
from backend.analyzers.python_analyzer import PythonAnalyzer

client = TestClient(app)


def test_clean_replacement_no_duplication():
    """
    Test 1: User's reported bug case:
    for(int i = 0; i <= n; i++) {
        cout << arr[i];
    }
    Must cleanly replace '<=' with '<' without duplicate loops or code corruption.
    """
    original_code = (
        "#include <iostream>\n"
        "using namespace std;\n\n"
        "int main() {\n"
        "    int n = 5;\n"
        "    int arr[5] = {1, 2, 3, 4, 5};\n"
        "    for(int i = 0; i <= n; i++) {\n"
        "        cout << arr[i];\n"
        "    }\n"
        "    return 0;\n"
        "}\n"
    )

    analyzer = CppAnalyzer()
    bugs, corrected_code, metrics = analyzer.analyze(original_code)

    assert len(bugs) >= 1
    # Check that the corrected code has '<' and NOT '<='
    assert "i <= n" not in corrected_code
    assert "i < n" in corrected_code

    # Check that loop header is NOT duplicated
    assert corrected_code.count("for(") == 1 or corrected_code.count("for (") == 1
    assert "for(int i = 0; i <= n; i++)" not in corrected_code
    assert "for(int i = 0; i < n; i++)" in corrected_code


def test_multiple_fixes_bottom_to_top_no_drift():
    """
    Test 2: Multiple fixes on different lines with length changes.
    Applies bottom-to-top so earlier line offsets never shift.
    """
    code = (
        "def compute():\n"
        "    a = 10\n"
        "    b = 0\n"
        "    c = a / 0\n"
        "    for i in range(len([1, 2]) + 1):\n"
        "        pass\n"
        "    return c\n"
    )

    analyzer = PythonAnalyzer()
    bugs, corrected, metrics = analyzer.analyze(code)

    assert len(bugs) >= 2
    # Check division by zero fixed
    assert "/ 0" not in corrected
    assert "/ 1" in corrected

    # Check loop boundary fixed
    assert "+ 1" not in corrected
    assert "range(len([1, 2]))" in corrected

    # Verify no corrupted text
    assert "def compute():" in corrected
    assert "return c" in corrected


def test_identical_substrings_on_different_lines():
    """
    Test 3: Multiple occurrences of the same substring (e.g. '<=') across different lines.
    Ensures exact character offset replacement without global substitution.
    """
    code = (
        "#include <stdio.h>\n"
        "int main(void) {\n"
        "    int n = 5;\n"
        "    int a[5] = {1, 2, 3, 4, 5};\n"
        "    // Loop 1:\n"
        "    for (int i = 0; i <= n; i++) {\n"
        "        printf(\"%d\\n\", a[i]);\n"
        "    }\n"
        "    // Loop 2:\n"
        "    for (int j = 0; j <= n; j++) {\n"
        "        printf(\"%d\\n\", a[j]);\n"
        "    }\n"
        "    return 0;\n"
        "}\n"
    )

    analyzer = CAnalyzer()
    bugs, corrected, metrics = analyzer.analyze(code)

    assert len(bugs) == 2
    assert "i <= n" not in corrected
    assert "j <= n" not in corrected
    assert "i < n" in corrected
    assert "j < n" in corrected

    # Confirm neither loop is duplicated
    assert corrected.count("for (int i = 0; i < n; i++)") == 1
    assert corrected.count("for (int j = 0; j < n; j++)") == 1


def test_stale_source_hash_rejection():
    """
    Test 4: Verifies source hash versioning protects against stale edits.
    If the user modifies the source code, applying a patch with the old hash must be rejected.
    """
    orig_code = "int x = 10\nint y = 20;\n"
    source_hash = compute_source_hash(orig_code)

    patch = StructuredPatch(
        file="main.c",
        start_line=1,
        start_column=1,
        end_line=1,
        end_column=11,
        original_code="int x = 10",
        replacement_code="int x = 10;",
        start_offset=0,
        end_offset=10,
        source_hash=source_hash,
        reason="Add semicolon"
    )

    # User modifies code in editor before clicking apply
    modified_code = "int x = 999\nint y = 20;\n"

    # Direct verified application test
    res = apply_single_patch_verified(modified_code, patch, expected_hash=source_hash)
    assert res["success"] is False
    assert res["status"] == "STALE_SOURCE"

    # Multi-patch transactional test
    res_multi = apply_multiple_patches_transactional(modified_code, [patch], expected_hash=source_hash)
    assert res_multi["success"] is False
    assert res_multi["status"] == "STALE_SOURCE"


def test_overlapping_conflict_detection():
    """
    Test 5: Overlapping patches must be detected and conflicts isolated.
    """
    code = "int counter = 0;\n"
    h = compute_source_hash(code)

    patch1 = StructuredPatch(
        file="main.c",
        start_line=1,
        start_column=1,
        end_line=1,
        end_column=12,
        original_code="int counter",
        replacement_code="long counter",
        start_offset=0,
        end_offset=11,
        source_hash=h,
        reason="Change type"
    )

    patch2 = StructuredPatch(
        file="main.c",
        start_line=1,
        start_column=5,
        end_line=1,
        end_column=16,
        original_code="counter = 0",
        replacement_code="counter = 1",
        start_offset=4,
        end_offset=15,
        source_hash=h,
        reason="Change init"
    )

    res = apply_multiple_patches_transactional(code, [patch1, patch2], expected_hash=h)
    assert res["conflict_count"] > 0
    assert len(res["conflicts"]) > 0


def test_api_apply_all_endpoint():
    """
    Test 6: Integration test with POST /api/repair/apply_all endpoint.
    """
    code = (
        "#include <iostream>\n"
        "using namespace std;\n\n"
        "int main() {\n"
        "    int n = 5;\n"
        "    int a[5] = {1, 2, 3, 4, 5};\n"
        "    int x = 10\n\n"
        "    for(int i = 0; i <= n; i++) {\n"
        "        cout << a[i] << endl;\n"
        "    }\n\n"
        "    if (x = 20) {\n"
        "        cout << \"Match\" << endl;\n"
        "    }\n"
        "    return 0;\n"
        "}\n"
    )

    # 1. Analyze first
    an_res = client.post("/api/analyze", json={"language": "cpp", "code": code})
    assert an_res.status_code == 200
    report = an_res.json()
    assert report["total_bugs"] >= 3
    source_hash = report["source_hash"]

    patches = [b["patch"] for b in report["bugs"] if b.get("patch")]
    assert len(patches) >= 3

    # 2. Call /api/repair/apply_all
    apply_res = client.post("/api/repair/apply_all", json={
        "language": "cpp",
        "code": code,
        "source_hash": source_hash,
        "patches": patches
    })
    assert apply_res.status_code == 200
    result = apply_res.json()
    assert result["success"] is True
    assert result["applied_count"] >= 3
    corr = result["corrected_code"]

    # Verify original erroneous lines are completely replaced
    assert "int x = 10\n" not in corr
    assert "int x = 10;" in corr
    assert "i <= n" not in corr
    assert "i < n" in corr
    assert "if (x = 20)" not in corr
    assert "if (x == 20)" in corr

    # Verify no loop duplication
    assert corr.count("for(int i = 0; i < n; i++)") == 1
    assert "for(int i = 0; i <= n; i++)" not in corr


def test_java_multi_patch_clean():
    """
    Test 7: Java whole-program multi-bug detection and clean repair.
    """
    code = (
        "public class Main {\n"
        "    public static void main(String[] args) {\n"
        "        int[] a = {1, 2, 3, 4, 5};\n"
        "        int x = 10\n\n"
        "        for(int i = 0; i <= a.length; i++) {\n"
        "            System.out.println(a[i]);\n"
        "        }\n\n"
        "        if (x = 20) {\n"
        "            System.out.println(\"Match\");\n"
        "        }\n"
        "    }\n"
        "}\n"
    )

    analyzer = JavaAnalyzer()
    bugs, corrected, metrics = analyzer.analyze(code)

    assert len(bugs) == 3
    assert "int x = 10\n" not in corrected
    assert "int x = 10;" in corrected
    assert "i <= a.length" not in corrected
    assert "i < a.length" in corrected
    assert "x = 20" not in corrected
    assert "x == 20" in corrected

    # Ensure no duplication
    assert corrected.count("for(int i = 0; i < a.length; i++)") == 1
