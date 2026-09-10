"""
Comprehensive test suite for language analyzers:
Python, C, C++, and Java.
Verifies exact fault localization, root cause vs failure line distinction,
and repair generation.
"""

import pytest
from backend.analyzers.python_analyzer import PythonAnalyzer
from backend.analyzers.cpp_analyzer import CppAnalyzer
from backend.analyzers.c_analyzer import CAnalyzer
from backend.analyzers.java_analyzer import JavaAnalyzer
from backend.core.state import BugCategory, BugSeverity


class TestPythonAnalyzer:
    def setup_method(self):
        self.analyzer = PythonAnalyzer()

    def test_clean_python_code(self):
        code = """def add(a, b):
    return a + b
print(add(2, 3))
"""
        bugs, corrected, metrics = self.analyzer.analyze(code)
        assert len(bugs) == 0
        assert metrics.bugs_detected == 0

    def test_syntax_error_missing_colon(self):
        code = """def test()
    print("Hello")
"""
        bugs, corrected, metrics = self.analyzer.analyze(code)
        assert len(bugs) == 1
        bug = bugs[0]
        assert bug.category == BugCategory.SYNTAX_ERROR
        assert bug.line == 1
        assert bug.patch is not None
        assert "def test():" in bug.patch.replacement_code
        assert corrected is not None
        assert "def test():" in corrected

    def test_logic_error_off_by_one_root_cause_vs_failure(self):
        code = """a = [1, 2, 3, 4, 5]
total = 0

for i in range(len(a) + 1):
    total += a[i]

print(total)
"""
        bugs, corrected, metrics = self.analyzer.analyze(code)
        assert len(bugs) == 1
        bug = bugs[0]
        assert bug.category == BugCategory.INDEX_OUT_OF_BOUNDS
        # Root cause line is the for loop range
        assert bug.root_cause_line == 4
        assert "range(len(a) + 1)" in bug.root_cause_code
        # Failure location is the subscript access
        assert bug.failure_line == 5
        assert "total += a[i]" in bug.failure_code
        # Patch removes + 1
        assert bug.patch is not None
        assert corrected is not None
        assert "range(len(a))" in corrected

    def test_division_by_zero(self):
        code = """x = 10
y = x / 0
print(y)
"""
        bugs, corrected, metrics = self.analyzer.analyze(code)
        assert len(bugs) >= 1
        assert any(b.category == BugCategory.DIVISION_BY_ZERO for b in bugs)


class TestCppAnalyzer:
    def setup_method(self):
        self.analyzer = CppAnalyzer()

    def test_clean_cpp_code(self):
        code = """#include <iostream>
using namespace std;

int main() {
    int a[5] = {1, 2, 3, 4, 5};
    for(int i = 0; i < 5; i++) {
        cout << a[i] << " ";
    }
    return 0;
}
"""
        bugs, corrected, metrics = self.analyzer.analyze(code)
        assert len(bugs) == 0

    def test_cpp_boundary_condition_root_vs_failure(self):
        code = """#include <iostream>
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
        bugs, corrected, metrics = self.analyzer.analyze(code)
        assert len(bugs) == 1
        bug = bugs[0]
        assert bug.category == BugCategory.INDEX_OUT_OF_BOUNDS
        assert bug.root_cause_line == 8
        assert "i <= n" in bug.root_cause_code
        assert bug.failure_line == 9
        assert "cout << a[i]" in bug.failure_code
        assert bug.patch.replacement_code == "<"
        assert corrected is not None
        assert "i < n" in corrected

    def test_cpp_assignment_in_condition(self):
        code = """#include <iostream>
using namespace std;

int main() {
    int x = 5;
    if (x = 10) {
        cout << "ten";
    }
    return 0;
}
"""
        bugs, corrected, metrics = self.analyzer.analyze(code)
        assert len(bugs) == 1
        bug = bugs[0]
        assert bug.category == BugCategory.INCORRECT_ASSIGNMENT_IN_CONDITION
        assert "x == 10" in bug.patch.replacement_code


class TestCAnalyzer:
    def setup_method(self):
        self.analyzer = CAnalyzer()

    def test_clean_c_code(self):
        code = """#include <stdio.h>

int main(void) {
    int n = 5;
    int a[5] = {1, 2, 3, 4, 5};
    for(int i = 0; i < n; i++) {
        printf("%d ", a[i]);
    }
    return 0;
}
"""
        bugs, corrected, metrics = self.analyzer.analyze(code)
        assert len(bugs) == 0

    def test_c_boundary_condition(self):
        code = """#include <stdio.h>

int main(void) {
    int n = 5;
    int a[5] = {1, 2, 3, 4, 5};

    for(int i = 0; i <= n; i++) {
        printf("%d\\n", a[i]);
    }

    return 0;
}
"""
        bugs, corrected, metrics = self.analyzer.analyze(code)
        assert len(bugs) == 1
        bug = bugs[0]
        assert bug.category == BugCategory.INDEX_OUT_OF_BOUNDS
        assert bug.root_cause_line == 7
        assert "i <= n" in bug.root_cause_code
        assert bug.failure_line == 8
        assert "printf" in bug.failure_code
        assert corrected is not None
        assert "i < n" in corrected


class TestJavaAnalyzer:
    def setup_method(self):
        self.analyzer = JavaAnalyzer()

    def test_clean_java_code(self):
        code = """public class Main {
    public static void main(String[] args) {
        int[] a = {1, 2, 3, 4, 5};
        for(int i = 0; i < a.length; i++) {
            System.out.println(a[i]);
        }
    }
}
"""
        bugs, corrected, metrics = self.analyzer.analyze(code)
        assert len(bugs) == 0

    def test_java_boundary_condition(self):
        code = """public class Main {
    public static void main(String[] args) {
        int[] a = {1, 2, 3, 4, 5};
        for(int i = 0; i <= a.length; i++) {
            System.out.println(a[i]);
        }
    }
}
"""
        bugs, corrected, metrics = self.analyzer.analyze(code)
        assert len(bugs) == 1
        bug = bugs[0]
        assert bug.category == BugCategory.INDEX_OUT_OF_BOUNDS
        assert bug.root_cause_line == 4
        assert "i <= a.length" in bug.root_cause_code
        assert bug.failure_line == 5
        assert "System.out.println(a[i])" in bug.failure_code
        assert corrected is not None
        assert "i < a.length" in corrected
