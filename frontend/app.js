/**
 * AI Bug Finder - Frontend Controller
 * Implements strict stale-state protection, monotonic request IDs, AbortController,
 * interactive line gutters, root-cause markers, and side-by-side diffing.
 */

// Application State
let currentLanguage = "python";
let currentRequestId = 0;
let currentAbortController = null;
let currentReport = null;
let samplePrograms = null;

// DOM Elements
const langButtons = document.querySelectorAll(".lang-btn");
const sampleSelect = document.getElementById("sampleSelect");
const codeEditor = document.getElementById("codeEditor");
const lineGutter = document.getElementById("lineGutter");
const cursorPosInfo = document.getElementById("cursorPosInfo");
const activeFileTab = document.getElementById("activeFileTab");
const testInput = document.getElementById("testInput");

const btnAnalyze = document.getElementById("btnAnalyze");
const btnApplyFix = document.getElementById("btnApplyFix");
const btnRestoreCode = document.getElementById("btnRestoreCode");
const btnReanalyze = document.getElementById("btnReanalyze");
const btnClear = document.getElementById("btnClear");

let lastOriginalCode = null;

const statusBanner = document.getElementById("statusBanner");
const statusBadge = document.getElementById("statusBadge");
const statusHeadline = document.getElementById("statusHeadline");
const statusSubtext = document.getElementById("statusSubtext");

const mValLang = document.getElementById("mValLang");
const mValLoc = document.getElementById("mValLoc");
const mValComplexity = document.getElementById("mValComplexity");
const mValTime = document.getElementById("mValTime");
const mValBugs = document.getElementById("mValBugs");
const mValValidated = document.getElementById("mValValidated");

const bugNavigatorBar = document.getElementById("bugNavigatorBar");
const btnPrevBug = document.getElementById("btnPrevBug");
const btnNextBug = document.getElementById("btnNextBug");
const navIndicator = document.getElementById("navIndicator");
const repairProgressPill = document.getElementById("repairProgressPill");

const bugSummaryBox = document.getElementById("bugSummaryBox");
const summaryBoxTitle = document.getElementById("summaryBoxTitle");
const summaryChipsRow = document.getElementById("summaryChipsRow");

const bugCardsContainer = document.getElementById("bugCardsContainer");
const emptyStateMsg = document.getElementById("emptyStateMsg");
const diffBody = document.getElementById("diffBody");
const compilerStatusText = document.getElementById("compilerStatusText");

let activeBugIndex = 0;
let initialBugCount = 0;

// Initialize
document.addEventListener("DOMContentLoaded", () => {
    setupEventListeners();
    fetchEnvironmentStatus();
    fetchSamples();
    updateLineNumbers();
});

function setupEventListeners() {
    // Language Buttons
    langButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const lang = btn.getAttribute("data-lang");
            setLanguage(lang);
        });
    });

    // Sample Selector
    sampleSelect.addEventListener("change", (e) => {
        const sampleKey = e.target.value;
        if (sampleKey && samplePrograms && samplePrograms[currentLanguage]) {
            const sampleCode = samplePrograms[currentLanguage][sampleKey];
            if (sampleCode) {
                codeEditor.value = sampleCode;
                resetAnalysisState();
                updateLineNumbers();
            }
        }
    });

    // Code Editor Inputs & Scrolling
    codeEditor.addEventListener("input", () => {
        updateLineNumbers();
        // Clear old results immediately on code edit (Rule 21: No stale state)
        resetAnalysisState();
    });

    codeEditor.addEventListener("scroll", () => {
        lineGutter.scrollTop = codeEditor.scrollTop;
    });

    codeEditor.addEventListener("keyup", updateCursorPos);
    codeEditor.addEventListener("click", updateCursorPos);

    // Action Buttons
    btnAnalyze.addEventListener("click", () => runAnalysis());
    btnApplyFix.addEventListener("click", () => applyCandidateFix());
    if (btnRestoreCode) {
        btnRestoreCode.addEventListener("click", () => restoreOriginalCode());
    }
    btnReanalyze.addEventListener("click", () => runAnalysis());
    btnClear.addEventListener("click", () => {
        codeEditor.value = "";
        testInput.value = "";
        sampleSelect.selectedIndex = 0;
        lastOriginalCode = null;
        if (btnRestoreCode) btnRestoreCode.style.display = "none";
        resetAnalysisState();
        updateLineNumbers();
    });

    // Defect Navigator Buttons
    btnPrevBug.addEventListener("click", () => navigateBug(-1));
    btnNextBug.addEventListener("click", () => navigateBug(1));

    // Bug Cards Delegation (Fix single bug & Focus line)
    bugCardsContainer.addEventListener("click", (e) => {
        const fixBtn = e.target.closest(".btn-fix-single");
        if (fixBtn) {
            const bugIdx = parseInt(fixBtn.getAttribute("data-bug-index"), 10);
            fixSingleBug(bugIdx);
            return;
        }
        const locBtn = e.target.closest(".btn-locate-single");
        if (locBtn) {
            const bugIdx = parseInt(locBtn.getAttribute("data-bug-index"), 10);
            activeBugIndex = bugIdx;
            updateNavigatorUI();
            focusBugCard(bugIdx);
            return;
        }
    });

    // Tabs
    const tabBtns = document.querySelectorAll(".tab-btn");
    tabBtns.forEach(tab => {
        tab.addEventListener("click", () => {
            tabBtns.forEach(t => t.classList.remove("active"));
            document.querySelectorAll(".tab-content").forEach(tc => tc.classList.remove("active"));

            tab.classList.add("active");
            const targetId = tab.getAttribute("data-tab");
            const content = document.getElementById(targetId);
            if (content) content.classList.add("active");
        });
    });
}

function updateCursorPos() {
    const pos = codeEditor.selectionStart;
    const text = codeEditor.value.substring(0, pos);
    const lines = text.split("\n");
    const currentLine = lines.length;
    const currentCol = lines[lines.length - 1].length + 1;
    cursorPosInfo.textContent = `Line ${currentLine}, Col ${currentCol}`;
}

function updateLineNumbers() {
    const lines = codeEditor.value.split("\n");
    const count = Math.max(1, lines.length);
    let gutterHTML = "";
    for (let i = 1; i <= count; i++) {
        gutterHTML += `<div class="line-no" id="gutter-line-${i}">${i}</div>`;
    }
    lineGutter.innerHTML = gutterHTML;
}

function setLanguage(lang) {
    if (currentLanguage === lang) return;
    currentLanguage = lang;

    langButtons.forEach(b => {
        if (b.getAttribute("data-lang") === lang) {
            b.classList.add("active");
        } else {
            b.classList.remove("active");
        }
    });

    const fileMap = {
        python: "source.py",
        cpp: "main.cpp",
        c: "main.c",
        java: "Main.java"
    };
    activeFileTab.textContent = fileMap[lang] || "source";
    mValLang.textContent = lang.toUpperCase();

    // Reset results when changing language (Rule 22)
    resetAnalysisState();

    // Auto-load default sample if editor is empty or sample dropdown changed
    sampleSelect.selectedIndex = 0;
    if (samplePrograms && samplePrograms[lang]) {
        codeEditor.value = samplePrograms[lang]["off_by_one"] || "";
        updateLineNumbers();
    }
}

function resetAnalysisState() {
    // Cancel any in-flight request (Rule 21 & 43)
    if (currentAbortController) {
        currentAbortController.abort();
        currentAbortController = null;
    }

    currentReport = null;
    btnApplyFix.disabled = true;
    btnReanalyze.disabled = true;

    if (bugNavigatorBar) bugNavigatorBar.style.display = "none";
    if (bugSummaryBox) bugSummaryBox.style.display = "none";
    activeBugIndex = 0;
    initialBugCount = 0;

    // Reset Status Banner
    statusBadge.className = "status-badge state-ready";
    statusBadge.textContent = "READY";
    statusHeadline.textContent = "Ready for analysis";
    statusSubtext.textContent = "Select a language and click 'Analyze Code'.";

    // Reset Metrics
    mValLoc.textContent = codeEditor.value.split("\n").filter(l => l.trim()).length;
    mValComplexity.textContent = "1";
    mValTime.textContent = "0.0 ms";
    mValBugs.textContent = "0";
    mValValidated.textContent = "0";

    // Clear Bug Cards
    bugCardsContainer.innerHTML = `
        <div class="empty-state">
            <div class="empty-icon">🔍</div>
            <h3>No Analysis Performed Yet</h3>
            <p>Submit source code to execute syntax validation, AST fault localization, evidence fusion, and automated program repair.</p>
        </div>
    `;

    // Clear Diff
    diffBody.innerHTML = `<p class="empty-diff-msg">No repairs generated yet. Run analysis on a buggy program to view side-by-side program diff.</p>`;

    // Clear line highlights
    document.querySelectorAll(".line-no").forEach(el => {
        el.style.color = "";
        el.style.fontWeight = "";
        el.style.background = "";
    });
}

async function fetchEnvironmentStatus() {
    try {
        const res = await fetch("/api/env");
        if (res.ok) {
            const data = await res.json();
            const available = [];
            if (data.gcc.available) available.push("GCC");
            if (data.gpp.available) available.push("G++");
            if (data.javac.available) available.push("Java");
            available.push("Python 3");

            compilerStatusText.textContent = `Toolchain: ${available.join(", ")}`;
        }
    } catch (e) {
        compilerStatusText.textContent = "Standalone AST Engine Active";
    }
}

async function fetchSamples() {
    try {
        const res = await fetch("/api/samples");
        if (res.ok) {
            samplePrograms = await res.json();
            // Load initial python off-by-one sample
            if (samplePrograms.python && !codeEditor.value.trim()) {
                codeEditor.value = samplePrograms.python.off_by_one;
                sampleSelect.value = "off_by_one";
                updateLineNumbers();
            }
        }
    } catch (e) {
        console.warn("Could not load server samples:", e);
    }
}

async function runAnalysis() {
    const code = codeEditor.value;
    const inputData = testInput.value;

    // Rule 21 & 43: Increment request ID and cancel pending requests
    currentRequestId += 1;
    const reqIdStr = String(currentRequestId);

    if (currentAbortController) {
        currentAbortController.abort();
    }
    currentAbortController = new AbortController();

    // UI state: Analyzing
    statusBadge.className = "status-badge state-analyzing";
    statusBadge.textContent = "ANALYZING";
    statusHeadline.textContent = "Executing analysis pipeline...";
    statusSubtext.textContent = "Validating language -> AST Parsing -> Defect Localization -> Evidence Fusion -> Patch Verification";

    btnAnalyze.disabled = true;
    btnApplyFix.disabled = true;
    btnReanalyze.disabled = true;

    try {
        const response = await fetch("/api/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                language: currentLanguage,
                code: code,
                test_input: inputData,
                request_id: reqIdStr
            }),
            signal: currentAbortController.signal
        });

        const report = await response.json();

        // Stale response guard: Ignore if superseded by a newer request
        if (report.request_id !== reqIdStr) {
            return;
        }

        currentReport = report;
        renderAnalysisReport(report);

    } catch (err) {
        if (err.name === "AbortError") {
            return; // Superseded request cancelled cleanly
        }
        statusBadge.className = "status-badge state-invalid";
        statusBadge.textContent = "ANALYSIS_ERROR";
        statusHeadline.textContent = "Network or Server Communication Error";
        statusSubtext.textContent = err.message || "Could not connect to the backend server.";
    } finally {
        btnAnalyze.disabled = false;
    }
}

function renderAnalysisReport(report) {
    // Update Research Metrics
    mValLang.textContent = (report.language || currentLanguage).toUpperCase();
    mValLoc.textContent = report.metrics.lines_of_code || 0;
    mValComplexity.textContent = report.metrics.cyclomatic_complexity || 1;
    mValTime.textContent = `${report.metrics.analysis_time_ms || 0} ms`;
    mValBugs.textContent = report.bugs ? report.bugs.length : 0;
    mValValidated.textContent = report.metrics.fixes_validated || 0;

    // Clear previous line gutter highlights
    document.querySelectorAll(".line-no").forEach(el => {
        el.style.color = "";
        el.style.fontWeight = "";
        el.style.background = "";
    });

    // Render Status Banner
    switch (report.status) {
        case "CLEAN":
            statusBadge.className = "status-badge state-clean";
            statusBadge.textContent = "CLEAN";
            statusHeadline.textContent = "✓ Code is Clean - Zero Defects Detected";
            statusSubtext.textContent = report.message;
            break;

        case "BUG_DETECTED":
            statusBadge.className = "status-badge state-bug";
            statusBadge.textContent = "BUG_DETECTED";
            statusHeadline.textContent = `⚠ ${report.bugs.length} Defect(s) Identified`;
            statusSubtext.textContent = report.message;
            break;

        case "LANGUAGE_MISMATCH":
            statusBadge.className = "status-badge state-mismatch";
            statusBadge.textContent = "LANGUAGE_MISMATCH";
            statusHeadline.textContent = `⚡ Language Mismatch: Expected ${report.detected_language ? report.detected_language.toUpperCase() : 'other'}`;
            statusSubtext.textContent = report.message;
            break;

        case "INVALID_SOURCE":
            statusBadge.className = "status-badge state-invalid";
            statusBadge.textContent = "INVALID_SOURCE";
            statusHeadline.textContent = "Invalid Source Input";
            statusSubtext.textContent = report.message;
            break;

        default:
            statusBadge.className = "status-badge state-invalid";
            statusBadge.textContent = report.status;
            statusHeadline.textContent = "Analysis Notice";
            statusSubtext.textContent = report.message;
            break;
    }

    // Render Bug Cards or Empty State
    if (report.bugs && report.bugs.length > 0) {
        renderSummaryBox(report);
        if (activeBugIndex >= report.bugs.length) {
            activeBugIndex = 0;
        }
        updateNavigatorUI();

        let cardsHTML = "";
        report.bugs.forEach((bug, idx) => {
            cardsHTML += buildBugCardHTML(bug, idx);
            highlightGutterLines(bug.root_cause_line, bug.failure_line);
        });
        bugCardsContainer.innerHTML = cardsHTML;
        focusBugCard(activeBugIndex);

        // Enable Apply Fix button if a valid corrected code exists
        if (report.corrected_code) {
            btnApplyFix.disabled = false;
        }

        // Render Side-by-Side Diff
        if (report.corrected_code) {
            renderDiffView(report.original_code, report.corrected_code);
        }
    } else if (report.status === "CLEAN") {
        if (bugNavigatorBar) bugNavigatorBar.style.display = "none";
        if (bugSummaryBox) bugSummaryBox.style.display = "none";
        initialBugCount = 0;
        activeBugIndex = 0;

        bugCardsContainer.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon" style="color: #34d399;">✓</div>
                <h3 style="color: #6ee7b7;">Program Verified Clean</h3>
                <p>${escapeHTML(report.message)}</p>
            </div>
        `;
        diffBody.innerHTML = `<p class="empty-diff-msg">Program is verified clean. All defects resolved!</p>`;
    } else if (report.status === "LANGUAGE_MISMATCH") {
        if (bugNavigatorBar) bugNavigatorBar.style.display = "none";
        if (bugSummaryBox) bugSummaryBox.style.display = "none";
        initialBugCount = 0;
        activeBugIndex = 0;

        bugCardsContainer.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon" style="color: #f59e0b;">⚠</div>
                <h3 style="color: #fde68a;">Language Mismatch Detected</h3>
                <p>${escapeHTML(report.message)}</p>
            </div>
        `;
        diffBody.innerHTML = `<p class="empty-diff-msg">Resolve language mismatch before running automated program repair.</p>`;
    } else {
        if (bugNavigatorBar) bugNavigatorBar.style.display = "none";
        if (bugSummaryBox) bugSummaryBox.style.display = "none";
        initialBugCount = 0;
        activeBugIndex = 0;

        bugCardsContainer.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">ℹ</div>
                <h3>${escapeHTML(report.status)}</h3>
                <p>${escapeHTML(report.message)}</p>
            </div>
        `;
    }
}

function renderSummaryBox(report) {
    const bugs = report.bugs || [];
    const total = report.total_bugs !== undefined ? report.total_bugs : bugs.length;
    summaryBoxTitle.textContent = `TOTAL BUGS DETECTED: ${total}`;

    // Count severities and categories
    const sevCounts = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
    const catCounts = {};
    bugs.forEach(b => {
        const sev = (b.severity || "HIGH").toUpperCase();
        if (sevCounts[sev] !== undefined) sevCounts[sev]++;
        const cat = b.category || "General";
        catCounts[cat] = (catCounts[cat] || 0) + 1;
    });

    let chipsHTML = `<span class="summary-chip danger"><strong>${total}</strong> Total Issues</span>`;
    if (sevCounts.CRITICAL > 0) chipsHTML += `<span class="summary-chip danger"><strong>${sevCounts.CRITICAL}</strong> Critical</span>`;
    if (sevCounts.HIGH > 0) chipsHTML += `<span class="summary-chip warning"><strong>${sevCounts.HIGH}</strong> High</span>`;
    if (sevCounts.MEDIUM > 0) chipsHTML += `<span class="summary-chip info"><strong>${sevCounts.MEDIUM}</strong> Medium</span>`;
    if (sevCounts.LOW > 0) chipsHTML += `<span class="summary-chip"><strong>${sevCounts.LOW}</strong> Low</span>`;

    Object.entries(catCounts).forEach(([cat, count]) => {
        chipsHTML += `<span class="summary-chip"><strong>${count}</strong> ${escapeHTML(cat)}</span>`;
    });

    summaryChipsRow.innerHTML = chipsHTML;
}

function navigateBug(direction) {
    if (!currentReport || !currentReport.bugs || currentReport.bugs.length === 0) return;
    activeBugIndex = Math.max(0, Math.min(currentReport.bugs.length - 1, activeBugIndex + direction));
    updateNavigatorUI();
    focusBugCard(activeBugIndex);
}

function updateNavigatorUI() {
    if (!currentReport || !currentReport.bugs || currentReport.bugs.length === 0) {
        if (bugNavigatorBar) bugNavigatorBar.style.display = "none";
        if (bugSummaryBox) bugSummaryBox.style.display = "none";
        return;
    }
    bugNavigatorBar.style.display = "flex";
    bugSummaryBox.style.display = "flex";

    navIndicator.textContent = `Bug ${activeBugIndex + 1} of ${currentReport.bugs.length}`;
    btnPrevBug.disabled = (activeBugIndex === 0);
    btnNextBug.disabled = (activeBugIndex >= currentReport.bugs.length - 1);

    const remaining = currentReport.bugs.length;
    if (initialBugCount < remaining) {
        initialBugCount = remaining;
    }
    repairProgressPill.textContent = `Defects Remaining: ${remaining} / ${initialBugCount}`;
}

function focusBugCard(index) {
    document.querySelectorAll(".bug-card").forEach((c, idx) => {
        if (idx === index) {
            c.classList.add("active-nav-card");
            c.scrollIntoView({ behavior: "smooth", block: "nearest" });
        } else {
            c.classList.remove("active-nav-card");
        }
    });

    if (currentReport && currentReport.bugs && currentReport.bugs[index]) {
        const bug = currentReport.bugs[index];
        scrollEditorToLine(bug.root_cause_line || bug.failure_line);
    }
}

function scrollEditorToLine(lineNum) {
    if (!lineNum) return;
    const lineHeight = 21;
    const targetScroll = Math.max(0, (lineNum - 3) * lineHeight);
    codeEditor.scrollTop = targetScroll;
    lineGutter.scrollTop = targetScroll;

    const el = document.getElementById(`gutter-line-${lineNum}`);
    if (el) {
        el.style.transform = "scale(1.25)";
        el.style.transition = "transform 0.2s ease";
        setTimeout(() => {
            if (el) el.style.transform = "";
        }, 350);
    }
}

async function fixSingleBug(index) {
    if (!currentReport || !currentReport.bugs || !currentReport.bugs[index]) return;
    const bug = currentReport.bugs[index];
    if (!bug.patch) return;

    lastOriginalCode = codeEditor.value;
    if (btnRestoreCode) btnRestoreCode.style.display = "inline-flex";

    try {
        document.querySelectorAll(".btn-fix-single").forEach(b => b.disabled = true);
        statusHeadline.textContent = `Applying fix for Bug #${index + 1} (Line ${bug.root_cause_line})...`;

        const res = await fetch("/api/repair/apply", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                code: codeEditor.value,
                patch: bug.patch,
                source_hash: currentReport.source_hash || "",
                test_input: testInput.value || ""
            })
        });

        if (res.ok) {
            const data = await res.json();
            if (data.success !== false) {
                codeEditor.value = data.code;
                updateLineNumbers();

                statusHeadline.textContent = `Fix applied for Bug #${index + 1}. Re-analyzing whole program...`;
                await runAnalysis();
            } else {
                statusHeadline.textContent = "Patch Application Rejected";
                statusSubtext.textContent = data.message || "Target code did not match.";
            }
        } else {
            console.error("Failed to apply patch:", await res.text());
        }
    } catch (err) {
        console.error("Error fixing bug:", err);
    }
}

function buildBugCardHTML(bug, index) {
    const sevClass = `sev-${(bug.severity || 'high').toLowerCase()}`;
    const ev = bug.evidence || {};
    const val = bug.validation || {};

    const compilePassed = val.compile_success;
    const runPassed = val.run_success;

    return `
        <div class="bug-card" id="bug-card-${index}" data-bug-id="${bug.bug_id || index}">
            <div class="bug-card-header">
                <div class="bug-title-group">
                    <span class="bug-badge-category">${escapeHTML(bug.category)}</span>
                    <span class="bug-badge-severity ${sevClass}">${escapeHTML(bug.severity)}</span>
                </div>
                <span style="font-size: 0.75rem; color: var(--text-muted);">Confidence: <strong>${Math.round(bug.confidence * 100)}%</strong></span>
            </div>

            <!-- ROOT CAUSE VS FAILURE LOCATION -->
            <div class="localization-box">
                <div class="loc-column">
                    <span class="loc-tag root-cause">Root Cause (Line ${bug.root_cause_line})</span>
                    <div class="loc-code-snippet root">${escapeHTML(bug.root_cause_code || '')}</div>
                </div>
                <div class="loc-column">
                    <span class="loc-tag failure">Failure Point (Line ${bug.failure_line})</span>
                    <div class="loc-code-snippet fail">${escapeHTML(bug.failure_code || '')}</div>
                </div>
            </div>

            <!-- STRUCTURED EXPLANATIONS -->
            <div class="explanation-section">
                <div class="exp-row">
                    <span class="exp-label">What is wrong?</span>
                    <span class="exp-text">${escapeHTML(bug.what_is_wrong)}</span>
                </div>
                <div class="exp-row">
                    <span class="exp-label">Why is it wrong?</span>
                    <span class="exp-text">${escapeHTML(bug.why_it_is_wrong)}</span>
                </div>
                <div class="exp-row">
                    <span class="exp-label">What happens?</span>
                    <span class="exp-text">${escapeHTML(bug.what_happens)}</span>
                </div>
                <div class="exp-row">
                    <span class="exp-label">What should be changed?</span>
                    <span class="exp-text" style="color: #6ee7b7; font-weight: 500;">${escapeHTML(bug.what_should_be_changed)}</span>
                </div>
            </div>

            <!-- CODE REPLACEMENT DIFF SNIPPET -->
            ${bug.patch ? `
                <div class="repair-preview-box">
                    <div style="font-size: 0.7rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Suggested Patch:</div>
                    <div class="diff-snippet-row">
                        <span class="diff-del">${escapeHTML(bug.patch.original_code)}</span>
                        <span class="arrow-icon">➔</span>
                        <span class="diff-add">${escapeHTML(bug.patch.replacement_code)}</span>
                    </div>
                </div>
            ` : ''}

            <!-- EVIDENCE FUSION METERS -->
            <div class="fusion-box">
                <div class="fusion-title">
                    <span>Evidence Fusion Suspiciousness</span>
                    <span>Total Score: ${(ev.total_suspiciousness || 0.9).toFixed(2)}</span>
                </div>
                <div class="fusion-meters">
                    <div class="meter-item">
                        <div class="meter-header"><span>Compiler</span><span>${ev.compiler_score || 0}</span></div>
                        <div class="meter-bar-bg"><div class="meter-bar-fill" style="width: ${(ev.compiler_score || 0)*100}%"></div></div>
                    </div>
                    <div class="meter-item">
                        <div class="meter-header"><span>Static</span><span>${ev.static_score || 0}</span></div>
                        <div class="meter-bar-bg"><div class="meter-bar-fill" style="width: ${(ev.static_score || 0)*100}%"></div></div>
                    </div>
                    <div class="meter-item">
                        <div class="meter-header"><span>Runtime</span><span>${ev.runtime_score || 0}</span></div>
                        <div class="meter-bar-bg"><div class="meter-bar-fill" style="width: ${(ev.runtime_score || 0)*100}%"></div></div>
                    </div>
                    <div class="meter-item">
                        <div class="meter-header"><span>AST</span><span>${ev.ast_score || 0}</span></div>
                        <div class="meter-bar-bg"><div class="meter-bar-fill" style="width: ${(ev.ast_score || 0)*100}%"></div></div>
                    </div>
                    <div class="meter-item">
                        <div class="meter-header"><span>AI / ML</span><span>${ev.ml_score || 0}</span></div>
                        <div class="meter-bar-bg"><div class="meter-bar-fill" style="width: ${(ev.ml_score || 0)*100}%"></div></div>
                    </div>
                </div>
            </div>

            <!-- REPAIR VALIDATION BADGES -->
            <div class="validation-badge-group">
                <span>Validation Sandbox:</span>
                <span class="val-pill ${compilePassed ? 'pass' : 'fail'}">${compilePassed ? '✓' : '✗'} Compile/Parse ${compilePassed ? 'PASS' : 'FAIL'}</span>
                <span class="val-pill ${runPassed ? 'pass' : 'fail'}">${runPassed ? '✓' : '✗'} Execution ${runPassed ? 'PASS' : 'FAIL'}</span>
                <span class="val-pill ${val.runtime_error_removed ? 'pass' : 'fail'}">${val.runtime_error_removed ? '✓' : '✗'} Hazard Removed</span>
            </div>

            <!-- ACTION CONTROLS FOR SEQUENTIAL REPAIR & LOCALIZATION -->
            <div class="card-actions-bar">
                <button class="btn-locate-single" data-bug-index="${index}" type="button">
                    <span class="btn-icon">🎯</span> Focus Line ${bug.root_cause_line}
                </button>
                ${bug.patch ? `
                    <button class="btn-fix-single" data-bug-index="${index}" type="button">
                        <span class="btn-icon">⚡</span> Fix This Bug (Line ${bug.root_cause_line})
                    </button>
                ` : ''}
            </div>
        </div>
    `;
}

function highlightGutterLines(rootLine, failLine) {
    if (rootLine) {
        const rootEl = document.getElementById(`gutter-line-${rootLine}`);
        if (rootEl) {
            rootEl.style.color = "#fdba74";
            rootEl.style.fontWeight = "700";
            rootEl.style.background = "rgba(249, 115, 22, 0.3)";
        }
    }
    if (failLine && failLine !== rootLine) {
        const failEl = document.getElementById(`gutter-line-${failLine}`);
        if (failEl) {
            failEl.style.color = "#fca5a5";
            failEl.style.fontWeight = "700";
            failEl.style.background = "rgba(244, 63, 94, 0.3)";
        }
    }
}

function renderDiffView(origCode, corrCode) {
    const origLines = origCode.split("\n");
    const corrLines = corrCode.split("\n");

    let leftHTML = "";
    let rightHTML = "";

    const maxLines = Math.max(origLines.length, corrLines.length);
    for (let i = 0; i < maxLines; i++) {
        const l = origLines[i] !== undefined ? origLines[i] : "";
        const r = corrLines[i] !== undefined ? corrLines[i] : "";

        const isDiff = l !== r;
        const leftClass = isDiff ? "diff-line removed" : "diff-line";
        const rightClass = isDiff ? "diff-line added" : "diff-line";

        leftHTML += `<div class="${leftClass}">${escapeHTML(l || " ")}</div>`;
        rightHTML += `<div class="${rightClass}">${escapeHTML(r || " ")}</div>`;
    }

    diffBody.innerHTML = `
        <div class="diff-pane">${leftHTML}</div>
        <div class="diff-pane">${rightHTML}</div>
    `;
}

function restoreOriginalCode() {
    if (lastOriginalCode !== null) {
        codeEditor.value = lastOriginalCode;
        updateLineNumbers();
        if (btnRestoreCode) btnRestoreCode.style.display = "none";
        statusHeadline.textContent = "Original Code Restored";
        statusSubtext.textContent = "Re-analyzing original source code...";
        runAnalysis();
    }
}

async function applyCandidateFix() {
    if (!currentReport) return;

    const patches = (currentReport.bugs || [])
        .map(b => b.patch)
        .filter(p => p !== null && p !== undefined);

    if (patches.length === 0 && !currentReport.corrected_code) return;

    lastOriginalCode = codeEditor.value;
    if (btnRestoreCode) btnRestoreCode.style.display = "inline-flex";

    btnApplyFix.disabled = true;
    statusHeadline.textContent = "Applying All Fixes Transactionally...";
    statusSubtext.textContent = "Replacing erroneous code slices, avoiding offset drift, and running validation...";

    try {
        const res = await fetch("/api/repair/apply_all", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                language: currentLanguage,
                code: codeEditor.value,
                source_hash: currentReport.source_hash || "",
                patches: patches,
                test_input: testInput.value || ""
            })
        });

        if (!res.ok) {
            throw new Error(`Server returned ${res.status}`);
        }

        const data = await res.json();
        if (data.success) {
            codeEditor.value = data.corrected_code;
            updateLineNumbers();
            btnReanalyze.disabled = false;
            statusHeadline.textContent = "All Fixes Cleanly Applied";
            statusSubtext.textContent = `${data.message} Re-analyzing whole program...`;
            await runAnalysis();
        } else if (data.status === "STALE_SOURCE") {
            statusHeadline.textContent = "Source Code Changed";
            statusSubtext.textContent = data.message;
            await runAnalysis();
        } else {
            statusHeadline.textContent = "Fix Application Failed";
            statusSubtext.textContent = data.message || "Failed to apply all fixes.";
            if (data.corrected_code && data.corrected_code !== codeEditor.value) {
                codeEditor.value = data.corrected_code;
                updateLineNumbers();
                await runAnalysis();
            }
        }
    } catch (err) {
        console.error("Error applying all fixes:", err);
        // Fallback to pre-calculated corrected_code if backend endpoint encountered an error
        if (currentReport.corrected_code) {
            codeEditor.value = currentReport.corrected_code;
            updateLineNumbers();
            btnReanalyze.disabled = false;
            await runAnalysis();
        }
    }
}


function escapeHTML(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
