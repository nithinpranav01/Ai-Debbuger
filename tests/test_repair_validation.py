"""
Tests for Automated Program Repair (APR) and fix validation.
Verifies that:
1. Candidate fixes are applied to working copies via structured patches.
2. Repaired code compiles/executes in an isolated sandbox.
3. Re-analysis of repaired code confirms bugs are resolved and state transitions to CLEAN.
"""

import pytest
from backend.core.state import SupportedLanguage, AnalysisState
from backend.repair.code_stitcher import apply_patch
from backend.models.schemas import StructuredPatch
from backend.validation.validator import validate_repaired_program
from backend.analyzers.python_analyzer import PythonAnalyzer
from backend.analyzers.cpp_analyzer import CppAnalyzer


def test_structured_patch_application():
    orig_code = """#include <iostream>
int main() {
    for(int i = 0; i <= 5; i++) {
        std::cout << i;
    }
    return 0;
}"""

    patch = StructuredPatch(
        start_line=3,
        start_column=22,
        end_line=3,
        end_column=24,
        original_code="<=",
        replacement_code="<",
        reason="Fix loop bound"
    )

    result = apply_patch(orig_code, patch)
    assert "i < 5" in result
    assert "int main()" in result
    assert "return 0;" in result


def test_python_repair_and_reanalysis_lifecycle():
    analyzer = PythonAnalyzer()
    buggy_code = """a = [1, 2, 3]
total = 0
for i in range(len(a) + 1):
    total += a[i]
print(total)
"""

    # 1. Analyze buggy code -> Bug detected
    bugs, corrected_code, metrics = analyzer.analyze(buggy_code)
    assert len(bugs) == 1
    assert corrected_code is not None

    # 2. Validate repaired code
    val = validate_repaired_program(SupportedLanguage.PYTHON, corrected_code)
    assert val.compile_success is True
    assert val.run_success is True
    assert val.runtime_error_removed is True

    # 3. Re-analyze repaired code -> Clean!
    re_bugs, re_corrected, re_metrics = analyzer.analyze(corrected_code)
    assert len(re_bugs) == 0
    assert re_metrics.bugs_detected == 0


def test_cpp_repair_and_reanalysis_lifecycle():
    analyzer = CppAnalyzer()
    buggy_code = """#include <iostream>
using namespace std;

int main() {
    int n = 5;
    int a[5] = {1, 2, 3, 4, 5};
    for(int i = 0; i <= n; i++) {
        cout << a[i] << endl;
    }
    return 0;
}
"""

    # 1. Analyze buggy code
    bugs, corrected_code, metrics = analyzer.analyze(buggy_code)
    assert len(bugs) == 1
    assert corrected_code is not None
    assert "i < n" in corrected_code

    # 2. Re-analyze repaired code -> Clean!
    re_bugs, re_corrected, re_metrics = analyzer.analyze(corrected_code)
    assert len(re_bugs) == 0
