"""
Abstract base class for all language-specific analyzers.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Dict, Any
import time
from backend.core.state import SupportedLanguage, BugSeverity, BugCategory
from backend.models.schemas import BugItem, ResearchMetrics, StructuredPatch, CandidateFix, EvidenceBreakdown
from backend.fault_localization.evidence_fusion import fusion_engine
from backend.ai.model import ml_model


class BaseAnalyzer(ABC):
    def __init__(self, language: SupportedLanguage):
        self.language = language

    @abstractmethod
    def analyze(self, code: str, test_input: str = "") -> Tuple[List[BugItem], Optional[str], ResearchMetrics]:
        """
        Analyze source code and return:
        (detected_bugs, corrected_full_program, research_metrics)
        """
        pass

    def compute_metrics(self, code: str, bugs: List[BugItem], elapsed_ms: float, funcs_count: int = 1, cyclo: int = 1) -> ResearchMetrics:
        """Helper to construct ResearchMetrics."""
        lines = [l for l in code.splitlines() if l.strip()]
        loc = len(lines)
        validated_count = sum(1 for b in bugs if b.validation and b.validation.compile_success and b.validation.run_success)

        return ResearchMetrics(
            language=self.language.value,
            lines_of_code=loc,
            functions_count=max(1, funcs_count),
            cyclomatic_complexity=max(1, cyclo),
            analysis_time_ms=round(elapsed_ms, 2),
            bugs_detected=len(bugs),
            high_risk_locations=sum(1 for b in bugs if b.severity in [BugSeverity.CRITICAL, BugSeverity.HIGH]),
            fixes_generated=sum(1 for b in bugs if b.patch is not None),
            fixes_validated=validated_count,
            tests_passed=len(bugs) == 0 or validated_count > 0,
            compiler_available=False,
            compiler_name=None
        )
