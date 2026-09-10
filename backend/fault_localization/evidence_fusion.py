"""
Hybrid Evidence Fusion Engine.
Combines signals from Compiler Diagnostics, Static Analysis, Runtime Execution,
AST Complexity, and AI/ML Suspiciousness to rank candidate fault locations.
"""

from typing import Dict, Any, Optional
from backend.models.schemas import EvidenceBreakdown


class EvidenceFusionEngine:
    def __init__(
        self,
        weight_compiler: float = 0.30,
        weight_runtime: float = 0.25,
        weight_static: float = 0.20,
        weight_ast: float = 0.15,
        weight_ml: float = 0.10,
    ):
        self.w_compiler = weight_compiler
        self.w_runtime = weight_runtime
        self.w_static = weight_static
        self.w_ast = weight_ast
        self.w_ml = weight_ml

        # Normalize weights to sum to 1.0
        total_w = self.w_compiler + self.w_runtime + self.w_static + self.w_ast + self.w_ml
        if total_w > 0:
            self.w_compiler /= total_w
            self.w_runtime /= total_w
            self.w_static /= total_w
            self.w_ast /= total_w
            self.w_ml /= total_w

    def fuse(
        self,
        compiler_score: float = 0.0,
        compiler_msg: str = "No compiler diagnostics",
        static_score: float = 0.0,
        static_msg: str = "No static analysis flag",
        runtime_score: float = 0.0,
        runtime_msg: str = "No runtime exception",
        ast_score: float = 0.0,
        ast_msg: str = "Standard AST metrics",
        ml_score: float = 0.0,
        ml_msg: str = "Baseline model prediction",
    ) -> EvidenceBreakdown:
        """
        Compute the weighted suspiciousness and return a complete EvidenceBreakdown.
        """
        c_val = max(0.0, min(1.0, compiler_score))
        s_val = max(0.0, min(1.0, static_score))
        r_val = max(0.0, min(1.0, runtime_score))
        a_val = max(0.0, min(1.0, ast_score))
        m_val = max(0.0, min(1.0, ml_score))

        total = (
            self.w_compiler * c_val
            + self.w_runtime * r_val
            + self.w_static * s_val
            + self.w_ast * a_val
            + self.w_ml * m_val
        )
        total_score = round(max(0.0, min(0.99, total)), 3)

        return EvidenceBreakdown(
            compiler_score=round(c_val, 2),
            compiler_evidence=compiler_msg,
            static_score=round(s_val, 2),
            static_evidence=static_msg,
            runtime_score=round(r_val, 2),
            runtime_evidence=runtime_msg,
            ast_score=round(a_val, 2),
            ast_evidence=ast_msg,
            ml_score=round(m_val, 2),
            ml_evidence=ml_msg,
            total_suspiciousness=total_score,
        )


# Global singleton instance
fusion_engine = EvidenceFusionEngine()
