"""
State definitions and constants for the AI Bug Finder system.
"""

from enum import Enum


class AnalysisState(str, Enum):
    VALID_SOURCE = "VALID_SOURCE"
    INVALID_SOURCE = "INVALID_SOURCE"
    LANGUAGE_MISMATCH = "LANGUAGE_MISMATCH"
    CLEAN = "CLEAN"
    BUG_DETECTED = "BUG_DETECTED"
    ANALYSIS_ERROR = "ANALYSIS_ERROR"
    TIMEOUT = "TIMEOUT"
    COMPILATION_ERROR = "COMPILATION_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    REPAIR_FAILED = "REPAIR_FAILED"
    REPAIR_VALIDATED = "REPAIR_VALIDATED"


class SupportedLanguage(str, Enum):
    C = "c"
    CPP = "cpp"
    PYTHON = "python"
    JAVA = "java"


class BugSeverity(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class BugCategory(str, Enum):
    SYNTAX_ERROR = "Syntax Error"
    COMPILATION_ERROR = "Compilation Error"
    TYPE_ERROR = "Type Error"
    UNDEFINED_VARIABLE = "Undefined Variable"
    RUNTIME_ERROR = "Runtime Error"
    INDEX_OUT_OF_BOUNDS = "Array Index Out of Bounds"
    OFF_BY_ONE = "Off-by-One Boundary Error"
    DIVISION_BY_ZERO = "Division by Zero"
    NULL_DEREFERENCE = "Null / NoneType Dereference"
    INCORRECT_ASSIGNMENT_IN_CONDITION = "Incorrect Assignment in Condition"
    INFINITE_LOOP = "Infinite Loop / Non-terminating Condition"
    LOGIC_ERROR = "Logic Error"
    RESOURCE_LEAK = "Resource Leak"
