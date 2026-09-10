# AI-Based Bug Finder for Automated Bug Detection, Fault Localization, Explanation and Automated Program Repair

**A research-grade system for multi-language automated bug detection, statement-level fault localization distinguishing root causes from failure locations, human-readable defect explanations, structured candidate repairs, and isolated sandbox validation.**

---

## 1. Problem Statement & Research Gap

Traditional static analyzers and compiler diagnostics often fall short in modern software engineering workflows:
1. **Shallow Diagnostic Reporting**: Most existing tools output error traces such as *"IndexError"* or *"Segmentation Fault at line 12"*, pointing only to the point of program crash rather than the originating root cause (e.g. an off-by-one loop boundary on line 5).
2. **The Debugging Gap**: Detecting that a bug exists is only the first step. Developers need actionable automated assistance that answers five fundamental questions:
   - **WHAT** is the error?
   - **WHERE** is the root cause versus the point of failure?
   - **WHY** is the construct invalid?
   - **WHAT** exact replacement corrects the fault?
   - **DOES** the repaired program actually compile, execute, and pass verification?
3. **Cross-Language Ambiguity**: Development platforms frequently misclassify inputs when users submit code in a different language than selected, leading to invalid syntax reports rather than a graceful mismatch notification.

This research project bridges this gap by unifying **Syntactic Validation**, **Compiler Diagnostics**, **Deterministic AST Fault Localization**, **Explainable AI/ML Evidence Fusion**, and **Automated Program Repair (APR) with Re-Analysis Validation**.

---

## 2. Research Objectives

1. **Deterministic Statement-Level Fault Localization**: Map AST nodes and statements directly to exact line and column numbers without relying on hallucinated model offsets.
2. **Separation of Root Cause from Failure Location**: Disentangle the fault-inducing statement (e.g., loop bound `i <= n`) from the symptom site (e.g., subscript dereference `a[i]`).
3. **Transparent Multi-Source Evidence Fusion**: Combine signals from compiler diagnostics, static rules, runtime tracebacks, AST complexity, and trained Machine Learning models into an explainable suspiciousness ranking.
4. **Automated Program Repair & Sandbox Verification**: Automatically generate structured patches, reconstruct the complete repaired source code, and validate candidate repairs in an isolated workspace with timeouts and re-analysis.
5. **Symmetrical Language Mismatch Detection**: Enforce two-way validation across all 12 combinations of C, C++, Python, and Java to halt invalid pipelines before analysis.

---

## 3. High-Level Architecture

```
User Input (Source Code + Selected Language)
               │
               ▼
┌─────────────────────────────────────────┐
│     Language Mismatch Validator         │  ---> If Mismatch: Return LANGUAGE_MISMATCH
└─────────────────────────────────────────┘
               │
               ▼ (Valid Language)
┌─────────────────────────────────────────┐
│   Language-Specific AST & Parsers       │
│  - Python: ast / bytecode               │
│  - C: Tree-Sitter C CST                 │
│  - C++: Tree-Sitter C++ CST             │
│  - Java: Tree-Sitter Java CST           │
└─────────────────────────────────────────┘
               │
       ┌───────┴───────────────┐
       ▼                       ▼
┌──────────────┐       ┌──────────────┐
│ Compiler &   │       │ Static AST   │
│ Diagnostics  │       │ Semantic     │
│ (GCC/G++/    │       │ Pattern      │
│  javac/py)   │       │ Detectors    │
└──────────────┘       └──────────────┘
       │                       │
       └───────┬───────────────┘
               ▼
┌─────────────────────────────────────────┐
│   Code Unit Feature Extraction          │
│   (Depth, Loop, Boundary, Cyclomatic)   │
└─────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│   Random Forest ML Suspiciousness Model │
└─────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│   Hybrid Evidence Fusion Engine         │
│   S = w_comp + w_stat + w_rt + w_ast+w_ml│
└─────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│   Fault Localization: Root vs Failure   │
└─────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│   Structured Candidate Patch Generator  │
└─────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│   Isolated Sandbox & Re-Analysis        │
│   (Compile -> Execute -> Re-analyze)    │
└─────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│   Research Dashboard & Side-by-Side Diff│
└─────────────────────────────────────────┘
```

---

## 4. Supported Languages & Analysis Pipelines

| Language | Primary AST Parser | Compiler / Runtime Engine | Specific Flaws Localized |
| :--- | :--- | :--- | :--- |
| **Python** | Python `ast` & `tokenize` | Sandboxed Python subprocess | Off-by-one (`range(len(a) + 1)`), missing colons, ZeroDivisionError, NameError, NoneType dereference |
| **C** | Tree-Sitter C (`tree_sitter_c`) | GCC (diagnostics & test compilation) | Loop bounds (`i <= n`), assignment in condition (`if (x = 10)`), missing semicolons, division by zero |
| **C++** | Tree-Sitter C++ (`tree_sitter_cpp`)| G++ (diagnostics & test compilation) | Loop bounds (`i <= n`), assignment in condition (`if (x = 10)`), missing semicolons, null pointer dereference |
| **Java** | Tree-Sitter Java (`tree_sitter_java`)| javac / java (diagnostics & execution) | Loop bounds (`i <= arr.length`), type errors in `if`, missing semicolons, division by zero |

---

## 5. Symmetrical Language Mismatch Matrix

The system validates all 12 combinations before executing any bug analysis. If code belonging to another language is supplied, the system immediately returns `LANGUAGE_MISMATCH`:

- **C selected**: Rejects C++ (detected via `<iostream>`, namespaces, `cout`), Python (`def`, indentation), and Java (`public class`, `System.out`).
- **C++ selected**: Rejects C (pure C headers without C++ idioms), Python, and Java.
- **Python selected**: Rejects C, C++, and Java.
- **Java selected**: Rejects C, C++, and Python.

Rule 33 Guarantee: A language mismatch is **never** reported as `CLEAN` or `0 bugs detected`.

---

## 6. Root Cause vs. Failure Location Distinction

Consider this classic boundary overrun:
```cpp
int n = 5;
int a[5] = {1, 2, 3, 4, 5};

for(int i = 0; i <= n; i++) {   // Line 8: ROOT CAUSE
    cout << a[i] << endl;       // Line 9: FAILURE POINT
}
```

- **Root Cause Location (Line 8)**: The boundary condition `i <= n` permits index `i` to reach `5`.
- **Failure Location (Line 9)**: The subscript dereference `a[i]` triggers undefined memory access.
- **Explanation**: Valid indexes for an array of size $n$ are $0$ through $n-1$.
- **Structured Patch**: Replaces `<=\` with `<`.
- **Validation**: Program re-compiled and verified clean.

---

## 7. Whole-Program Multi-Bug Analysis & Sequential Rectification

A critical research enhancement is **whole-program multi-defect analysis and sequential rectification**:

1. **Whole-Program Inspection**:
   - Analyzers do not halt after discovering the first error. Instead, they parse and traverse the complete AST, identifying all independent syntax errors, boundary violations, invalid assignments in conditions, and division-by-zero hazards across lines.
   - Dynamic total defect count: `TOTAL BUGS DETECTED: N`, reporting the true total without artificial caps.

2. **Interactive Defect Navigator**:
   - Defect Navigator bar (`◄ Previous`, `Bug X of Y`, `Next ►`) allows seamless cycling between defects.
   - Automatically synchronizes with the source code editor: jumping to and highlighting the exact root cause line in the gutter with animated focus pulses.
   - Severity and category breakdown chips display critical, high, medium, and low distributions.

3. **Sequential One-by-One Rectification**:
   - Each bug card provides an independent **"Fix This Bug"** button.
   - Upon clicking, the single patch is applied deterministically using `apply_patch` without side effects on remaining code.
   - The entire program is **immediately re-analyzed**.
   - Defect counts dynamically decrement (`Defects Remaining: 2 / 3` $\to$ `1 / 3` $\to$ `0 / 3`), line numbers update to match the new source, and upon resolving the final defect, the program smoothly transitions to `CLEAN`.

4. **Cumulative Reverse-Order Patch Application**:
   - If the user selects "Apply All Fixes", `apply_multiple_patches` sorts candidate patches in **reverse source order (bottom-to-top)**.
   - This ensures character offsets of earlier lines remain pristine, eliminating offset drift hazards.

---

## 8. Evidence Fusion & Explainable ML Model

Each localized defect includes a transparent evidence breakdown:
$$\text{Suspiciousness} = w_{\text{compiler}} S_{\text{compiler}} + w_{\text{runtime}} S_{\text{runtime}} + w_{\text{static}} S_{\text{static}} + w_{\text{ast}} S_{\text{ast}} + w_{\text{ml}} S_{\text{ml}}$$

- **Compiler Evidence**: Diagnostic warning and error tokens emitted during parsing/compilation.
- **Static Analysis Evidence**: Structural AST pattern violations (e.g. assignment inside conditional expression).
- **Runtime Evidence**: Stack frame proximity and exception signals captured in the sandbox.
- **AST Complexity**: Nesting depth, branch density, and cyclomatic contribution.
- **Machine Learning Inference**: Scikit-Learn `RandomForestClassifier` trained on normalized AST statement feature vectors.

---

## 9. Installation & Setup

### Prerequisites
- **Python 3.10+** (Tested on Python 3.12)
- Optional for native binary compilation: **GCC / G++** (MinGW-w64 or w64devkit) and **JDK 17+** (`javac`).
  *(Note: If compilers are not in PATH, the system seamlessly uses Tree-Sitter AST static semantic engines and clearly informs the user in the dashboard).*

### Installation Steps

1. Clone or navigate to the workspace:
   ```bash
   cd "ai-bug-finder"
   ```

2. Install Python dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```

3. Run the automated test suite:
   ```bash
   python -m pytest tests/ -v
   ```

4. Launch the web server:
   ```bash
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
   ```

5. Open the web dashboard in your browser:
   ```
   http://127.0.0.1:8000
   ```

---

## 10. Verification & Test Suite

The project includes an automated test suite with **41 comprehensive tests**:
- `tests/test_multi_bug.py` (7 tests): Multi-bug detection in Python, C, C++, Java, sequential one-by-one rectification re-analysis loop, and single patch endpoint.
- `tests/test_language_validator.py` (16 tests): All 12 cross-language mismatch pairs + 4 self-consistency checks.
- `tests/test_analyzers.py` (11 tests): Python, C, C++, Java clean programs, syntax errors, boundary logic errors, and division by zero.
- `tests/test_repair_validation.py` (3 tests): Structured patch generation, sandbox execution, and re-analysis confirming bug removal.
- `tests/test_api_integration.py` (4 tests): End-to-end FastAPI endpoint tests and stale-state lifecycle verification (Clean -> Buggy -> Fixed -> Clean).

Run tests at any time with:
```bash
python -m pytest tests/ -v
```

Or execute the live multi-bug test script:
```bash
python scripts/verify_live.py
```

---

## 11. Research Project Directory Structure

```
ai-bug-finder/
├── backend/
│   ├── main.py                     # FastAPI application entrypoint & static mount
│   ├── api/
│   │   ├── routes.py               # REST endpoints (/api/analyze, /api/env, /api/samples, /api/repair/apply)
│   │   └── models/
│   │       └── schemas.py          # Pydantic schema models (BugItem, StructuredPatch, AnalysisReport)
│   ├── core/
│   │   ├── state.py                # AnalysisState enums and severity constants
│   │   └── language_validator.py   # Symmetrical 12-pair cross-language validator
│   ├── analyzers/
│   │   ├── base_analyzer.py        # Abstract base analyzer interface
│   │   ├── python_analyzer.py      # Whole-program Python AST, boundary & multi-bug analyzer
│   │   ├── c_analyzer.py           # Whole-program C Tree-sitter & GCC multi-bug analyzer
│   │   ├── cpp_analyzer.py         # Whole-program C++ Tree-sitter & G++ multi-bug analyzer
│   │   └── java_analyzer.py        # Whole-program Java Tree-sitter & javac multi-bug analyzer
│   ├── fault_localization/
│   │   ├── code_unit.py            # AST statement mapping to exact line/col
│   │   └── evidence_fusion.py      # Multi-source weighted suspiciousness engine
│   ├── ai/
│   │   ├── feature_extractor.py    # AST syntactic and complexity feature vectorization
│   │   └── model.py                # Scikit-Learn Random Forest inference model
│   ├── repair/
│   │   └── code_stitcher.py        # Exact coordinate patch applicator (single & bottom-to-top multiple)
│   ├── validation/
│   │   ├── sandbox.py              # Isolated temp workspaces with timeouts
│   │   └── validator.py            # Compilation, execution, and test validation
│   └── utils/
│       └── env_check.py            # Host toolchain discovery utility
├── frontend/
│   ├── index.html                  # Research dashboard with Defect Navigator & Summary Bar
│   ├── style.css                   # Dark theme, glassmorphism, chips, and responsive layout
│   └── app.js                      # Multi-bug navigation, sequential repair controller & diff viewer
├── test_programs/
│   ├── c/                          # multi_bug.c, clean.c, syntax_error.c, etc.
│   ├── cpp/                        # multi_bug.cpp, clean.cpp, syntax_error.cpp, etc.
│   ├── python/                     # multi_bug.py, clean.py, syntax_error.py, etc.
│   └── java/                       # multi_bug.java, clean.java, syntax_error.java, etc.
├── tests/
│   ├── test_multi_bug.py           # 7 multi-bug detection & sequential repair tests
│   ├── test_language_validator.py  # 16 language validation tests
│   ├── test_analyzers.py           # 11 language analyzer unit tests
│   ├── test_repair_validation.py   # 3 repair & re-analysis tests
│   └── test_api_integration.py     # 4 API integration & stale-state tests
├── scripts/
│   └── verify_live.py              # Automated live HTTP test runner with sequential repair loop
├── requirements.txt                # Python package dependencies
└── README.md                       # Research documentation
```

"# Ai-Debbuger" 
"# Ai-Debbuger" 
