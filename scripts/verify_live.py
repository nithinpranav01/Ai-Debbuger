import urllib.request
import json

def post(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

print("==================================================")
print("LIVE HTTP ENDPOINT VALIDATION RUN (MULTI-BUG + SEQUENTIAL REPAIR)")
print("==================================================")

# 1. Whole-Program Multi-Bug Analysis (Python)
py_multi = """def compute_values(arr)
    total = 0
    for i in range(len(arr) + 1):
        total += arr[i]
    scale = 100 / 0
    return total * scale

data = [1, 2, 3, 4, 5]
print(compute_values(data))
"""
res_multi = post("http://127.0.0.1:8000/api/analyze", {
    "language": "python",
    "code": py_multi,
    "request_id": "multi-1"
})
print("[1] Whole-Program Multi-Bug Detection (Python):")
print("    Status:", res_multi["status"])
print("    Total Bugs Reported:", res_multi["total_bugs"])
print("    Individual Bugs Found:")
for i, bug in enumerate(res_multi["bugs"], 1):
    print(f"      Bug {i}: Line {bug['root_cause_line']} [{bug['category']}] - {bug['what_is_wrong']}")

assert res_multi["total_bugs"] >= 3, "Expected at least 3 bugs detected"
assert len(res_multi["bugs"]) == res_multi["total_bugs"], "total_bugs must match len(bugs)"

# 2. Sequential One-by-One Rectification with Re-analysis
current_code = py_multi
remaining_bugs = res_multi["total_bugs"]
step = 1

print("\n[2] Sequential Rectification Loop:")
while remaining_bugs > 0:
    analysis = post("http://127.0.0.1:8000/api/analyze", {
        "language": "python",
        "code": current_code,
        "request_id": f"step-{step}"
    })
    if not analysis["bugs"]:
        print(f"    Step {step}: Code is CLEAN! 0 defects remaining.")
        break

    target_bug = analysis["bugs"][0]
    print(f"    Step {step}: Rectifying Bug at Line {target_bug['root_cause_line']} ({target_bug['category']})...")
    
    # Apply single patch via API
    repair_res = post("http://127.0.0.1:8000/api/repair/apply", {
        "code": current_code,
        "patch": target_bug["patch"]
    })
    current_code = repair_res["code"]

    # Re-analyze modified code
    new_analysis = post("http://127.0.0.1:8000/api/analyze", {
        "language": "python",
        "code": current_code,
        "request_id": f"step-{step}-recheck"
    })
    new_bugs = new_analysis["total_bugs"]
    print(f"           Re-analysis result: {new_bugs} defects remaining (Status: {new_analysis['status']})")
    assert new_bugs < remaining_bugs, "Bugs must decrement after fix!"
    remaining_bugs = new_bugs
    step += 1

# Verify final code is clean
final_analysis = post("http://127.0.0.1:8000/api/analyze", {
    "language": "python",
    "code": current_code,
    "request_id": "final-verify"
})
print("\n[3] Final Program State:")
print("    Status:", final_analysis["status"])
print("    Total Bugs:", final_analysis["total_bugs"])
print("    Message:", final_analysis["message"])
assert final_analysis["status"] == "CLEAN", "Program must transition to CLEAN"
assert final_analysis["total_bugs"] == 0, "Clean program must report 0 defects"

# 4. Multi-Bug C++ Detection
cpp_multi = """#include <iostream>
using namespace std;

int main() {
    int n = 5;
    int a[5] = {1, 2, 3, 4, 5};
    int x = 10

    for (int i = 0; i <= n; i++) {
        cout << a[i] << endl;
    }

    if (x = 20) {
        cout << "Match" << endl;
    }

    return 0;
}
"""
res_cpp = post("http://127.0.0.1:8000/api/analyze", {
    "language": "cpp",
    "code": cpp_multi,
    "request_id": "cpp-multi-1"
})
print("\n[4] Multi-Bug Detection (C++):")
print("    Status:", res_cpp["status"])
print("    Total Bugs Reported:", res_cpp["total_bugs"])
for i, bug in enumerate(res_cpp["bugs"], 1):
    print(f"      Bug {i}: Line {bug['root_cause_line']} [{bug['category']}] - {bug['what_is_wrong']}")
assert res_cpp["total_bugs"] >= 2, "Expected multiple bugs detected in C++"

# 5. Language Mismatch Detection Symmetrical (all 12 pairs preserved)
mismatch_res = post("http://127.0.0.1:8000/api/analyze", {
    "language": "python",
    "code": "#include <stdio.h>\nint main(void) { return 0; }",
    "request_id": "mismatch-1"
})
print("\n[5] Language Mismatch Check:")
print("    Status:", mismatch_res["status"])
print("    Detected Language:", mismatch_res["detected_language"])
assert mismatch_res["status"] == "LANGUAGE_MISMATCH"

print("\n==================================================")
print("ALL LIVE MULTI-BUG & SEQUENTIAL REPAIR TESTS PASSED!")
print("==================================================")
