"""
Pydantic schemas for request, response, bug descriptions, patches, and validation results.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from backend.core.state import AnalysisState, SupportedLanguage, BugSeverity, BugCategory


class AnalysisRequest(BaseModel):
    language: SupportedLanguage
    code: str
    test_input: Optional[str] = ""
    expected_output: Optional[str] = None
    request_id: Optional[str] = "1"


class StructuredPatch(BaseModel):
    bug_id: Optional[int] = None
    file: str = "source"
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    original_code: str
    replacement_code: str
    reason: str
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    source_hash: Optional[str] = None


class ApplyPatchRequest(BaseModel):
    code: str
    patch: StructuredPatch
    source_hash: Optional[str] = None
    test_input: Optional[str] = ""


class ApplyAllFixesRequest(BaseModel):
    language: SupportedLanguage
    code: str
    source_hash: Optional[str] = None
    patches: List[StructuredPatch] = []
    test_input: Optional[str] = ""


class ApplyAllFixesResponse(BaseModel):
    success: bool
    status: str
    corrected_code: str
    original_code: str
    total_candidates: int = 0
    applied_count: int = 0
    failed_count: int = 0
    conflict_count: int = 0
    applied_fixes: List[Dict[str, Any]] = []
    failed_fixes: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []
    validation: Optional[Any] = None
    reanalysis_clean: bool = False
    message: str = ""
    patch_log: List[Dict[str, Any]] = []


class RepairValidationResult(BaseModel):
    compile_success: bool = False
    run_success: bool = False
    tests_passed: bool = False
    runtime_error_removed: bool = False
    message: str = ""
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    reanalysis_clean: bool = False


class CandidateFix(BaseModel):
    fix_id: int
    title: str
    patch: StructuredPatch
    validation: RepairValidationResult
    confidence: float
    is_recommended: bool = False


class EvidenceBreakdown(BaseModel):
    compiler_score: float = 0.0
    compiler_evidence: str = "No compiler diagnostics reported"
    static_score: float = 0.0
    static_evidence: str = "No static analyzer violation"
    runtime_score: float = 0.0
    runtime_evidence: str = "No runtime exception thrown"
    ast_score: float = 0.0
    ast_evidence: str = "Standard AST construct"
    ml_score: float = 0.0
    ml_evidence: str = "Heuristic baseline model"
    total_suspiciousness: float = 0.0


class BugStatus(str, Enum):
    DETECTED = "DETECTED"
    IN_REVIEW = "IN_REVIEW"
    FIX_SUGGESTED = "FIX_SUGGESTED"
    FIX_APPLIED = "FIX_APPLIED"
    VALIDATING = "VALIDATING"
    FIX_VALIDATED = "FIX_VALIDATED"
    FIX_FAILED = "FIX_FAILED"
    REMAINING = "REMAINING"


class BugItem(BaseModel):
    bug_id: int
    category: BugCategory
    severity: BugSeverity
    status: str = "DETECTED"
    file: str = "source"
    line: int
    column: int
    end_line: Optional[int] = None
    end_column: Optional[int] = None
    code_statement: str
    ast_node_type: str

    # Distinct Root Cause vs Failure Location
    root_cause_line: int
    root_cause_column: int
    root_cause_code: str
    failure_line: int
    failure_column: int
    failure_code: str

    # Explanations
    message: str
    what_is_wrong: str
    why_it_is_wrong: str
    what_happens: str
    what_should_be_changed: str

    # Repair & Validation
    patch: Optional[StructuredPatch] = None
    candidate_fixes: List[CandidateFix] = []
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    validation: Optional[RepairValidationResult] = None
    evidence: EvidenceBreakdown = Field(default_factory=EvidenceBreakdown)
    related_diagnostics: List[str] = []


class ResearchMetrics(BaseModel):
    language: str
    lines_of_code: int = 0
    functions_count: int = 0
    cyclomatic_complexity: int = 1
    analysis_time_ms: float = 0.0
    bugs_detected: int = 0
    high_risk_locations: int = 0
    fixes_generated: int = 0
    fixes_validated: int = 0
    tests_passed: bool = True
    compiler_available: bool = False
    compiler_name: Optional[str] = None


class AnalysisReport(BaseModel):
    request_id: str
    status: AnalysisState
    language: str
    is_mismatch: bool = False
    detected_language: Optional[str] = None
    message: str
    total_bugs: int = 0
    bugs: List[BugItem] = []
    corrected_code: Optional[str] = None
    original_code: str
    metrics: ResearchMetrics
    overall_summary: str
    analysis_summary: Dict[str, Any] = Field(default_factory=lambda: {
        "confirmed_bugs": 0,
        "analysis_blocked": False,
        "raw_diagnostics_count": 0
    })
    source_hash: str = ""
    environment: Dict[str, Any] = {}


