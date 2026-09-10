"""
Tests for whole-program multi-bug analysis and sequential one-by-one rectification.
Verifies that:
1. All 4 language analyzers find multiple bugs across different lines.
2. Dynamic total bug count reflects the exact number of detected defects.
3. Sequential repairs progressively decrement bug counts upon whole-program re-analysis.
4. Final program transitions to CLEAN with 0 defects remaining.
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.core.state import AnalysisState, SupportedLanguage
from backend.analyzers.python_analyzer import PythonAnalyzer
from backend.analyzers.c_analyzer import CAnalyzer
from backend.analyzers.cpp_analyzer import CppAnalyzer
from backend.analyzers.java_analyzer import JavaAnalyzer
from backend.repair.code_stitcher import apply_patch, apply_multiple_patches

client = TestClient(app)


def test_python_multi_bug_detection_and_dynamic_count():
    py_code = (
        "def compute_values(arr)\n"
        "    total = 0\n"
        "    for i in range(len(arr) + 1):\n"
        "        total += arr[i]\n"
        "    scale = 100 / 0\n"
        "    return total * scale\n"
    )
    analyzer = PythonAnalyzer()
    bugs, corrected_code, metrics = analyzer.analyze(py_code)

    # Must detect multiple bugs on different lines
    assert len(bugs) >= 3, f"Expected at least 3 bugs, found {len(bugs)}"
    lines = [b.root_cause_line for b in bugs]
    assert len(set(lines)) >= 2, "Bugs must be localized across different lines"

    # Verify bug categories
    categories = [b.category.value for b in bugs]
    assert any("Syntax" in c for c in categories)
    assert any("Bounds" in c or "Index" in c or "Logic" in c for c in categories)
    assert any("Division" in c for c in categories)

    # Cumulative repair must resolve all bugs
    clean_bugs, _, _ = analyzer.analyze(corrected_code)
    assert len(clean_bugs) == 0, f"Expected 0 bugs in corrected code, found: {len(clean_bugs)}"


def test_python_sequential_one_by_one_rectification():
    """
    Simulates a user rectifying bugs one-by-one with whole-program re-analysis
    after every patch application.
    """
    code = (
        "def compute_values(arr)\n"
        "    total = 0\n"
        "    for i in range(len(arr) + 1):\n"
        "        total += arr[i]\n"
        "    scale = 100 / 0\n"
        "    return total * scale\n"
    )
    analyzer = PythonAnalyzer()

    # Step 1: Initial analysis
    bugs1, _, _ = analyzer.analyze(code)
    initial_count = len(bugs1)
    assert initial_count >= 3

    # Step 2: Fix bug #1 (syntax error missing colon)
    patch1 = bugs1[0].patch
    assert patch1 is not None
    code_after_fix1 = apply_patch(code, patch1)

    # Whole-program re-analysis
    bugs2, _, _ = analyzer.analyze(code_after_fix1)
    assert len(bugs2) < initial_count, f"Bug count should decrement after fix 1. Before: {initial_count}, After: {len(bugs2)}"

    # Step 3: Fix next remaining bug
    patch2 = bugs2[0].patch
    assert patch2 is not None
    code_after_fix2 = apply_patch(code_after_fix1, patch2)

    # Whole-program re-analysis
    bugs3, _, _ = analyzer.analyze(code_after_fix2)
    assert len(bugs3) < len(bugs2), f"Bug count should decrement after fix 2. Before: {len(bugs2)}, After: {len(bugs3)}"

    # Step 4: Fix final remaining bug
    if bugs3:
        patch3 = bugs3[0].patch
        assert patch3 is not None
        code_after_fix3 = apply_patch(code_after_fix2, patch3)

        bugs4, _, _ = analyzer.analyze(code_after_fix3)
        assert len(bugs4) == 0, f"Expected clean program with 0 bugs, found: {len(bugs4)}"


def test_cpp_multi_bug_detection():
    cpp_code = (
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
    analyzer = CppAnalyzer()
    bugs, corrected_code, metrics = analyzer.analyze(cpp_code)
    assert len(bugs) >= 2, f"Expected at least 2 bugs in C++, found {len(bugs)}"

    # Distinct lines
    lines = [b.root_cause_line for b in bugs]
    assert len(set(lines)) >= 2, f"Expected bugs on multiple lines, got lines: {lines}"


def test_c_multi_bug_detection():
    c_code = (
        "#include <stdio.h>\n\n"
        "int main(void) {\n"
        "    int n = 5;\n"
        "    int a[5] = {1, 2, 3, 4, 5};\n"
        "    int x = 10\n\n"
        "    for(int i = 0; i <= n; i++) {\n"
        "        printf(\"%d\\n\", a[i]);\n"
        "    }\n\n"
        "    if (x = 20) {\n"
        "        printf(\"Match\\n\");\n"
        "    }\n"
        "    return 0;\n"
        "}\n"
    )
    analyzer = CAnalyzer()
    bugs, corrected_code, metrics = analyzer.analyze(c_code)
    assert len(bugs) >= 2, f"Expected at least 2 bugs in C, found {len(bugs)}"
    lines = [b.root_cause_line for b in bugs]
    assert len(set(lines)) >= 2, f"Expected bugs on multiple lines, got lines: {lines}"


def test_java_multi_bug_detection():
    java_code = (
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
    bugs, corrected_code, metrics = analyzer.analyze(java_code)
    assert len(bugs) >= 2, f"Expected at least 2 bugs in Java, found {len(bugs)}"
    lines = [b.root_cause_line for b in bugs]
    assert len(set(lines)) >= 2, f"Expected bugs on multiple lines, got lines: {lines}"


def test_api_multi_bug_endpoint():
    py_code = (
        "def compute_values(arr)\n"
        "    total = 0\n"
        "    for i in range(len(arr) + 1):\n"
        "        total += arr[i]\n"
        "    scale = 100 / 0\n"
        "    return total * scale\n"
    )
    response = client.post(
        "/api/analyze",
        json={
            "language": "python",
            "code": py_code,
            "test_input": "",
            "request_id": "test-multi-1"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "BUG_DETECTED"
    assert data["total_bugs"] >= 3
    assert len(data["bugs"]) == data["total_bugs"]
    assert "analysis_summary" in data
    assert data["analysis_summary"]["confirmed_bugs"] == data["total_bugs"]


def test_api_apply_single_patch_endpoint():
    py_code = "def compute_values(arr)\n    return arr\n"
    patch = {
        "file": "source",
        "start_line": 1,
        "start_column": 24,
        "end_line": 1,
        "end_column": 24,
        "original_code": "",
        "replacement_code": ":",
        "reason": "Missing colon"
    }
    response = client.post(
        "/api/repair/apply",
        json={
            "code": py_code,
            "patch": patch
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "def compute_values(arr):" in data["code"]

