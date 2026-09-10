"""
Automated unit test suite verifying symmetrical language mismatch detection
across all 12 pairwise combinations of C, C++, Python, and Java, plus valid cases.
"""

import pytest
from backend.core.language_validator import validate_language
from backend.core.state import SupportedLanguage, AnalysisState


SAMPLE_C = """#include <stdio.h>
#include <stdlib.h>

int main(void) {
    printf("Hello from standard C!\\n");
    return 0;
}
"""

SAMPLE_CPP = """#include <iostream>
using namespace std;

int main() {
    cout << "Hello from C++!" << endl;
    return 0;
}
"""

SAMPLE_PYTHON = """def calculate_total(items):
    total = 0
    for item in items:
        total += item
    return total

if __name__ == '__main__':
    print(calculate_total([1, 2, 3]))
"""

SAMPLE_JAVA = """public class Solution {
    public static void main(String[] args) {
        System.out.println("Hello from Java!");
    }
}
"""


class TestLanguageValidation:
    """Test self-consistency (valid source) for all 4 languages."""

    def test_c_with_c(self):
        result = validate_language(SupportedLanguage.C, SAMPLE_C)
        assert result["status"] == AnalysisState.VALID_SOURCE
        assert result["is_mismatch"] is False

    def test_cpp_with_cpp(self):
        result = validate_language(SupportedLanguage.CPP, SAMPLE_CPP)
        assert result["status"] == AnalysisState.VALID_SOURCE
        assert result["is_mismatch"] is False

    def test_python_with_python(self):
        result = validate_language(SupportedLanguage.PYTHON, SAMPLE_PYTHON)
        assert result["status"] == AnalysisState.VALID_SOURCE
        assert result["is_mismatch"] is False

    def test_java_with_java(self):
        result = validate_language(SupportedLanguage.JAVA, SAMPLE_JAVA)
        assert result["status"] == AnalysisState.VALID_SOURCE
        assert result["is_mismatch"] is False


class TestLanguageMismatchMatrix:
    """Test all 12 pairwise mismatch combinations."""

    # 1. C selected + C++
    def test_c_selected_cpp_input(self):
        res = validate_language(SupportedLanguage.C, SAMPLE_CPP)
        assert res["status"] == AnalysisState.LANGUAGE_MISMATCH
        assert res["detected_language"] == SupportedLanguage.CPP.value

    # 2. C selected + Python
    def test_c_selected_python_input(self):
        res = validate_language(SupportedLanguage.C, SAMPLE_PYTHON)
        assert res["status"] == AnalysisState.LANGUAGE_MISMATCH
        assert res["detected_language"] == SupportedLanguage.PYTHON.value

    # 3. C selected + Java
    def test_c_selected_java_input(self):
        res = validate_language(SupportedLanguage.C, SAMPLE_JAVA)
        assert res["status"] == AnalysisState.LANGUAGE_MISMATCH
        assert res["detected_language"] == SupportedLanguage.JAVA.value

    # 4. C++ selected + C
    def test_cpp_selected_c_input(self):
        res = validate_language(SupportedLanguage.CPP, SAMPLE_C)
        assert res["status"] == AnalysisState.LANGUAGE_MISMATCH
        assert res["detected_language"] == SupportedLanguage.C.value

    # 5. C++ selected + Python
    def test_cpp_selected_python_input(self):
        res = validate_language(SupportedLanguage.CPP, SAMPLE_PYTHON)
        assert res["status"] == AnalysisState.LANGUAGE_MISMATCH
        assert res["detected_language"] == SupportedLanguage.PYTHON.value

    # 6. C++ selected + Java
    def test_cpp_selected_java_input(self):
        res = validate_language(SupportedLanguage.CPP, SAMPLE_JAVA)
        assert res["status"] == AnalysisState.LANGUAGE_MISMATCH
        assert res["detected_language"] == SupportedLanguage.JAVA.value

    # 7. Python selected + C
    def test_python_selected_c_input(self):
        res = validate_language(SupportedLanguage.PYTHON, SAMPLE_C)
        assert res["status"] == AnalysisState.LANGUAGE_MISMATCH
        assert res["detected_language"] == SupportedLanguage.C.value

    # 8. Python selected + C++
    def test_python_selected_cpp_input(self):
        res = validate_language(SupportedLanguage.PYTHON, SAMPLE_CPP)
        assert res["status"] == AnalysisState.LANGUAGE_MISMATCH
        assert res["detected_language"] == SupportedLanguage.CPP.value

    # 9. Python selected + Java
    def test_python_selected_java_input(self):
        res = validate_language(SupportedLanguage.PYTHON, SAMPLE_JAVA)
        assert res["status"] == AnalysisState.LANGUAGE_MISMATCH
        assert res["detected_language"] == SupportedLanguage.JAVA.value

    # 10. Java selected + C
    def test_java_selected_c_input(self):
        res = validate_language(SupportedLanguage.JAVA, SAMPLE_C)
        assert res["status"] == AnalysisState.LANGUAGE_MISMATCH
        assert res["detected_language"] == SupportedLanguage.C.value

    # 11. Java selected + C++
    def test_java_selected_cpp_input(self):
        res = validate_language(SupportedLanguage.JAVA, SAMPLE_CPP)
        assert res["status"] == AnalysisState.LANGUAGE_MISMATCH
        assert res["detected_language"] == SupportedLanguage.CPP.value

    # 12. Java selected + Python
    def test_java_selected_python_input(self):
        res = validate_language(SupportedLanguage.JAVA, SAMPLE_PYTHON)
        assert res["status"] == AnalysisState.LANGUAGE_MISMATCH
        assert res["detected_language"] == SupportedLanguage.PYTHON.value
