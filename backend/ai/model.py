"""
Machine Learning Suspiciousness Model.
Utilizes a trained Scikit-Learn Random Forest Classifier to infer bug likelihood
from AST structural feature vectors.
"""

from typing import Tuple
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from .feature_extractor import extract_features_from_statement


class FaultLocalizationModel:
    def __init__(self):
        self.model = RandomForestClassifier(n_estimators=50, random_state=42, max_depth=6)
        self.is_trained = False
        self._train_baseline_model()

    def _train_baseline_model(self):
        """
        Train a baseline Random Forest model on curated syntactic and structural patterns.
        """
        # Feature order: [depth, loop, boundary, assign_cond, subscript, div, null, cyclo, tokens]
        # X: feature vectors
        # y: 0 for clean, 1 for suspicious / fault-inducing
        X_train = np.array([
            # Clean patterns (Class 0)
            [0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 0.1],  # simple variable assignment: int a = 5;
            [0.2, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.4, 0.3],  # safe loop: for(int i=0; i<n; i++)
            [0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.4, 0.2],  # safe equality: if (x == 10)
            [0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 0.1],  # return statement: return total;
            [0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 0.2],  # print call: cout << a[i];
            [0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.4, 0.2],  # safe inequality: if (x != 0)
            [0.3, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.4, 0.3],  # normal safe array read: arr[i]

            # Suspicious / Defect patterns (Class 1)
            [0.3, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.6, 0.3],  # boundary loop defect: for(int i=0; i<=n; i++)
            [0.2, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.6, 0.2],  # assignment in condition: if (x = 10)
            [0.2, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.4, 0.2],  # division expression: x / 0
            [0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.4, 0.2],  # null assignment/dereference: ptr = NULL; *ptr
            [0.4, 1.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.8, 0.4],  # loop boundary + subscript access
            [0.2, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.6, 0.3],  # range(len(a) + 1)
        ], dtype=np.float32)

        y_train = np.array([
            0, 0, 0, 0, 0, 0, 0,
            1, 1, 1, 1, 1, 1
        ], dtype=np.int32)

        self.model.fit(X_train, y_train)
        self.is_trained = True

    def predict_suspiciousness(self, text: str, node_type: str = "statement", depth: int = 1, is_loop: bool = False, is_cond: bool = False) -> Tuple[float, str]:
        """
        Run inference using the trained Random Forest model.
        Returns: (probability_suspicious: float, explanation: str)
        """
        if not self.is_trained:
            return 0.5, "Model not trained (fallback)"

        features = extract_features_from_statement(text, node_type, depth, is_loop, is_cond).reshape(1, -1)
        prob = self.model.predict_proba(features)[0][1]
        score = round(float(prob), 3)

        explanation = f"RandomForest inference: {score:.1%} defect likelihood from structural AST features"
        return score, explanation


# Global singleton instance
ml_model = FaultLocalizationModel()
