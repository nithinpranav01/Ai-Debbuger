"""
Code stitcher module for applying structured patches to source code.
Guarantees:
1. Exact replacement (not insertion or duplication).
2. Verification of expected original code prior to slicing.
3. Bottom-to-top (descending start_offset) application of multiple patches.
4. Overlap and conflict detection.
5. Source versioning / hashing to reject stale patches.
"""

import hashlib
from typing import Tuple, List, Dict, Any, Optional
from backend.models.schemas import StructuredPatch


def compute_source_hash(source: str) -> str:
    """Compute normalized SHA-256 hash of source code for version verification."""
    normalized = source.replace("\r\n", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def position_to_offset(source: str, line: int, col: int) -> int:
    """
    Convert 1-indexed (line, column) coordinates to a 0-indexed byte/char offset.
    Column is 1-indexed. If line is beyond range, clamps to end of source.
    """
    lines = source.splitlines(keepends=True)
    if not lines:
        return 0
    if line < 1:
        line = 1
    if line > len(lines):
        return len(source)

    offset = sum(len(lines[i]) for i in range(line - 1))
    target_line = lines[line - 1]
    col_offset = max(0, min(col - 1, len(target_line)))
    return offset + col_offset


def resolve_patch_offsets(source_code: str, patch: StructuredPatch) -> Tuple[int, int, bool, str]:
    """
    Resolves the exact [start_offset, end_offset] for a patch against source_code.
    Verifies that source_code[start_offset:end_offset] matches patch.original_code.

    Returns:
        (start_offset, end_offset, is_valid, error_message)
    """
    if not source_code:
        return (0, 0, True, "")

    lines = source_code.splitlines(keepends=True)
    total_lines = len(lines)
    orig_code = patch.original_code

    # Fast path: If pre-calculated offsets exist and are valid against current source
    if patch.start_offset is not None and patch.end_offset is not None:
        s_off = patch.start_offset
        e_off = patch.end_offset
        if 0 <= s_off <= e_off <= len(source_code):
            if source_code[s_off:e_off] == orig_code:
                return (s_off, e_off, True, "")

    # Path 2: Calculate from (start_line, start_column) and (end_line, end_column)
    s_line = max(1, min(patch.start_line, total_lines))
    e_line = max(s_line, min(patch.end_line or patch.start_line, total_lines))

    s_off = position_to_offset(source_code, s_line, patch.start_column)
    e_off = position_to_offset(source_code, e_line, patch.end_column)
    if s_off > e_off:
        s_off, e_off = e_off, s_off

    # Check direct slice match
    if source_code[s_off:e_off] == orig_code:
        return (s_off, e_off, True, "")

    # Path 3: Search specifically on the target line (preserving line-specificity)
    if 1 <= s_line <= total_lines:
        target_line = lines[s_line - 1]
        line_start_off = sum(len(lines[i]) for i in range(s_line - 1))
        if orig_code and orig_code in target_line:
            col_0 = max(0, patch.start_column - 1)
            # 1. Check exact match at start_column
            if col_0 + len(orig_code) <= len(target_line) and target_line[col_0:col_0 + len(orig_code)] == orig_code:
                real_s = line_start_off + col_0
                real_e = real_s + len(orig_code)
                return (real_s, real_e, True, "")
            # 2. Find all occurrences on target_line and pick closest to start_column
            occurrences = [m.start() for m in re.finditer(re.escape(orig_code), target_line)]
            if occurrences:
                best_idx = min(occurrences, key=lambda idx: abs(idx - col_0))
                real_s = line_start_off + best_idx
                real_e = real_s + len(orig_code)
                if source_code[real_s:real_e] == orig_code:
                    return (real_s, real_e, True, "")

    # Special case: pure insertion (orig_code is empty)
    if orig_code == "":
        return (s_off, s_off, True, "")

    return (
        -1,
        -1,
        False,
        f"Conflict: Expected original text '{orig_code}' not found at line {s_line} in current source."
    )


def detect_conflicts(resolved_patches: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Detects overlapping patch ranges among candidate patches.
    Separates patches into non_conflicting and conflicting lists.
    """
    if len(resolved_patches) <= 1:
        return resolved_patches, []

    # Sort ascending by start_offset to check overlaps
    sorted_by_start = sorted(resolved_patches, key=lambda x: (x["start_offset"], x["end_offset"]))

    conflicting_ids = set()
    conflicts_details = []

    for i in range(len(sorted_by_start)):
        p1 = sorted_by_start[i]
        s1 = p1["start_offset"]
        e1 = p1["end_offset"]

        for j in range(i + 1, len(sorted_by_start)):
            p2 = sorted_by_start[j]
            s2 = p2["start_offset"]
            e2 = p2["end_offset"]

            # Check for overlap: max(s1, s2) < min(e1, e2) or identical insertion point
            if max(s1, s2) < min(e1, e2) or (s1 == e1 == s2 == e2):
                conflicting_ids.add(id(p1))
                conflicting_ids.add(id(p2))
                bug1_id = getattr(p1["patch"], "bug_id", None) or f"#{i+1}"
                bug2_id = getattr(p2["patch"], "bug_id", None) or f"#{j+1}"
                conflicts_details.append({
                    "patch_1_bug_id": bug1_id,
                    "patch_2_bug_id": bug2_id,
                    "range_1": f"[{s1}:{e1}]",
                    "range_2": f"[{s2}:{e2}]",
                    "reason": f"Fix conflict: Patch for Bug {bug1_id} and Bug {bug2_id} modify overlapping source ranges."
                })

    non_conflicting = [p for p in resolved_patches if id(p) not in conflicting_ids]
    conflicting = [p for p in resolved_patches if id(p) in conflicting_ids]

    return non_conflicting, conflicts_details


def apply_single_patch_verified(
    source_code: str,
    patch: StructuredPatch,
    expected_hash: Optional[str] = None
) -> Dict[str, Any]:
    """
    Apply a single structured patch with verification of source hash and original code.
    Guarantees original range is removed and replacement inserted into that exact range.
    """
    if not source_code:
        return {
            "code": patch.replacement_code,
            "success": True,
            "status": "APPLIED",
            "message": "Applied to empty source"
        }

    # Stale source check
    if expected_hash:
        curr_hash = compute_source_hash(source_code)
        if curr_hash != expected_hash:
            return {
                "code": source_code,
                "success": False,
                "status": "STALE_SOURCE",
                "message": "Source code has changed since the analysis. Please re-analyze before applying fixes."
            }

    s_off, e_off, is_valid, err_msg = resolve_patch_offsets(source_code, patch)
    if not is_valid:
        return {
            "code": source_code,
            "success": False,
            "status": "ORIGINAL_CODE_MISMATCH",
            "message": err_msg
        }

    # Conceptually: source[start:end] = replacement
    corrected_code = source_code[:s_off] + patch.replacement_code + source_code[e_off:]

    # Verification: replacement is present
    if patch.replacement_code and patch.replacement_code not in corrected_code:
        return {
            "code": source_code,
            "success": False,
            "status": "VERIFICATION_FAILED",
            "message": "Verification failed: Replacement code not found in patched source."
        }

    # Verification: original erroneous slice was cleanly excised
    if patch.original_code and patch.original_code != patch.replacement_code:
        if not patch.replacement_code.startswith(patch.original_code):
            slice_check = corrected_code[s_off:s_off + len(patch.original_code)]
            if slice_check == patch.original_code:
                return {
                    "code": source_code,
                    "success": False,
                    "status": "ORIGINAL_CODE_NOT_REMOVED",
                    "message": f"Verification failed: Erroneous original code '{patch.original_code}' was not removed."
                }

    return {
        "code": corrected_code,
        "success": True,
        "status": "APPLIED",
        "message": "Patch applied successfully."
    }


def apply_multiple_patches_transactional(
    source_code: str,
    patches: List[StructuredPatch],
    expected_hash: Optional[str] = None
) -> Dict[str, Any]:
    """
    Apply multiple structured patches to the SAME source code:
    1. Validates source hash (stale state protection).
    2. Resolves exact absolute character offsets for every patch.
    3. Verifies original text at each range.
    4. Detects overlapping patch ranges and marks conflicts.
    5. Sorts non-conflicting patches in DESCENDING order of start_offset (bottom to top).
    6. Replaces source[start:end] = replacement for each patch.
    7. Performs post-application verification.
    """
    total_candidates = len(patches)
    if not patches:
        return {
            "success": True,
            "status": "NO_PATCHES",
            "corrected_code": source_code,
            "total_candidates": 0,
            "applied_count": 0,
            "failed_count": 0,
            "conflict_count": 0,
            "applied_fixes": [],
            "failed_fixes": [],
            "conflicts": [],
            "patch_log": [],
            "message": "No patches to apply."
        }

    # Stale source version check
    if expected_hash:
        curr_hash = compute_source_hash(source_code)
        if curr_hash != expected_hash:
            return {
                "success": False,
                "status": "STALE_SOURCE",
                "corrected_code": source_code,
                "total_candidates": total_candidates,
                "applied_count": 0,
                "failed_count": total_candidates,
                "conflict_count": 0,
                "applied_fixes": [],
                "failed_fixes": [{"error": "Source code has changed since analysis."}],
                "conflicts": [],
                "patch_log": [],
                "message": "Source code has changed since fixes were generated. Please re-analyze the code before applying all fixes."
            }

    # Step 1: Resolve all patch offsets and verify original code
    resolved_patches = []
    failed_fixes = []
    patch_log = []

    for i, patch in enumerate(patches, start=1):
        s_off, e_off, is_valid, err_msg = resolve_patch_offsets(source_code, patch)
        bug_id = getattr(patch, "bug_id", None) or i

        if not is_valid:
            failed_info = {
                "bug_id": bug_id,
                "line": patch.start_line,
                "original_code": patch.original_code,
                "replacement_code": patch.replacement_code,
                "reason": err_msg,
                "status": "FAILED"
            }
            failed_fixes.append(failed_info)
            patch_log.append(failed_info)
        else:
            resolved_patches.append({
                "patch": patch,
                "bug_id": bug_id,
                "start_offset": s_off,
                "end_offset": e_off,
                "original_code": patch.original_code,
                "replacement_code": patch.replacement_code,
                "line": patch.start_line
            })

    # Step 2: Detect overlapping patch ranges
    applicable_patches, conflict_details = detect_conflicts(resolved_patches)

    for c in conflict_details:
        patch_log.append({
            "bug_id": f"{c['patch_1_bug_id']} & {c['patch_2_bug_id']}",
            "status": "CONFLICT",
            "reason": c["reason"]
        })

    # Step 3: Sort non-conflicting patches by start_offset DESCENDING (bottom to top)
    sorted_patches = sorted(applicable_patches, key=lambda x: x["start_offset"], reverse=True)

    # Step 4: Transactional bottom-to-top slicing
    working_code = source_code
    applied_fixes = []

    for item in sorted_patches:
        s = item["start_offset"]
        e = item["end_offset"]
        repl = item["replacement_code"]
        patch_obj = item["patch"]
        bug_id = item["bug_id"]

        # source[start:end] = replacement
        working_code = working_code[:s] + repl + working_code[e:]

        applied_info = {
            "bug_id": bug_id,
            "line": item["line"],
            "original_code": item["original_code"],
            "replacement_code": repl,
            "status": "APPLIED"
        }
        applied_fixes.append(applied_info)
        patch_log.append(applied_info)

    # Step 5: Post-application verification
    for item in applied_fixes:
        repl = item["replacement_code"]
        if repl and repl not in working_code:
            # Rollback if verification fails
            return {
                "success": False,
                "status": "VERIFICATION_FAILED",
                "corrected_code": source_code,
                "total_candidates": total_candidates,
                "applied_count": 0,
                "failed_count": total_candidates,
                "conflict_count": len(conflict_details),
                "applied_fixes": [],
                "failed_fixes": [{"error": f"Verification failed: '{repl}' not found after patching."}],
                "conflicts": conflict_details,
                "patch_log": patch_log,
                "message": "Patch application failed verification pass. Original source preserved."
            }

    success = len(applied_fixes) > 0 and len(conflict_details) == 0

    return {
        "success": success or (len(applied_fixes) > 0),
        "status": "APPLIED" if not conflict_details else "APPLIED_WITH_CONFLICTS",
        "corrected_code": working_code,
        "total_candidates": total_candidates,
        "applied_count": len(applied_fixes),
        "failed_count": len(failed_fixes),
        "conflict_count": len(conflict_details),
        "applied_fixes": applied_fixes,
        "failed_fixes": failed_fixes,
        "conflicts": conflict_details,
        "patch_log": patch_log,
        "message": f"Successfully applied {len(applied_fixes)} of {total_candidates} candidate fixes."
    }


def apply_patch(source_code: str, patch: StructuredPatch) -> str:
    """Convenience backward-compatible wrapper using verified offset slicing."""
    res = apply_single_patch_verified(source_code, patch)
    return res["code"] if res["success"] else source_code


def apply_multiple_patches(source_code: str, patches: list) -> str:
    """Convenience backward-compatible wrapper using transactional bottom-to-top slicing."""
    res = apply_multiple_patches_transactional(source_code, patches)
    return res["corrected_code"]


def replace_line_slice(source_code: str, line_no: int, old_slice: str, new_slice: str) -> str:
    """Convenience function to replace a specific snippet on a target line."""
    lines = source_code.splitlines(keepends=True)
    if 1 <= line_no <= len(lines):
        target_line = lines[line_no - 1]
        if old_slice in target_line:
            idx = target_line.find(old_slice)
            col_start = idx + 1
            col_end = col_start + len(old_slice)
            patch = StructuredPatch(
                start_line=line_no,
                start_column=col_start,
                end_line=line_no,
                end_column=col_end,
                original_code=old_slice,
                replacement_code=new_slice,
                reason="Direct slice substitution"
            )
            return apply_patch(source_code, patch)
    return source_code
