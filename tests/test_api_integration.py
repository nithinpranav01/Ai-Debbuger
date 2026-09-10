"""
End-to-end integration tests for FastAPI REST API endpoints.
Verifies:
1. Environment status endpoint (/api/env)
2. Sample programs endpoint (/api/samples)
3. Full analysis pipeline (/api/analyze)
4. Symmetrical language mismatch rejection
5. Stale-state protection lifecycle (Clean -> Buggy -> Fixed -> Clean)
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.core.state import AnalysisState

client = TestClient(app)


def test_api_env():
    response = client.get("/api/env")
    assert response.status_code == 200
    data = response.json()
    assert "python" in data
    assert "gcc" in data
    assert "tree_sitter" in data


def test_api_samples():
    response = client.get("/api/samples")
    assert response.status_code == 200
    data = response.json()
    assert "python" in data
    assert "cpp" in data
    assert "c" in data
    assert "java" in data


def test_api_language_mismatch():
    # User selects Python, but submits C++ code
    cpp_code = """#include <iostream>
using namespace std;
int main() {
    cout << "Hello C++";
    return 0;
}"""

    response = client.post("/api/analyze", json={
        "language": "python",
        "code": cpp_code,
        "request_id": "req-1"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == AnalysisState.LANGUAGE_MISMATCH.value
    assert data["is_mismatch"] is True
    assert data["detected_language"] == "cpp"
    assert len(data["bugs"]) == 0
    assert "Language Mismatch" in data["message"]


def test_api_stale_state_lifecycle():
    """
    Test Rule 21 sequence:
    Step 1: Clean code -> Analyze -> CLEAN
    Step 2: Modify to introduce bug -> Analyze -> BUG_DETECTED
    Step 3: Modify back to clean -> Analyze -> CLEAN
    Verifies no stale state persists between requests.
    """
    clean_code = """def multiply(a, b):
    return a * b
print(multiply(3, 4))
"""
    buggy_code = """a = [1, 2, 3]
total = 0
for i in range(len(a) + 1):
    total += a[i]
print(total)
"""

    # Step 1: Clean Code
    res1 = client.post("/api/analyze", json={
        "language": "python",
        "code": clean_code,
        "request_id": "1"
    })
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == AnalysisState.CLEAN.value
    assert len(data1["bugs"]) == 0

    # Step 2: Buggy Code
    res2 = client.post("/api/analyze", json={
        "language": "python",
        "code": buggy_code,
        "request_id": "2"
    })
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == AnalysisState.BUG_DETECTED.value
    assert len(data2["bugs"]) == 1
    assert data2["bugs"][0]["root_cause_line"] == 3
    assert data2["corrected_code"] is not None

    # Step 3: Fixed Code (Applying repair)
    repaired_code = data2["corrected_code"]
    res3 = client.post("/api/analyze", json={
        "language": "python",
        "code": repaired_code,
        "request_id": "3"
    })
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["status"] == AnalysisState.CLEAN.value
    assert len(data3["bugs"]) == 0
