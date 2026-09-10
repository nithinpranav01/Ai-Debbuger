"""
Environment check utility for detecting compilers, interpreters, and runtime tools.
Checks PATH and standard directories for Python, GCC, G++, Java, and Javac.
"""

import os
import shutil
import subprocess
from typing import Dict, Any, Optional


def find_tool(tool_name: str, common_dirs: Optional[list] = None) -> Optional[str]:
    """Find a binary in PATH or specified common directories."""
    path = shutil.which(tool_name)
    if path:
        return path

    if common_dirs:
        for d in common_dirs:
            if os.path.isdir(d):
                candidate = os.path.join(d, f"{tool_name}.exe")
                if os.path.isfile(candidate):
                    return candidate
                candidate_no_ext = os.path.join(d, tool_name)
                if os.path.isfile(candidate_no_ext):
                    return candidate_no_ext
    return None


def get_tool_version(executable_path: str, version_flag: str = "--version") -> Optional[str]:
    """Execute the tool with version flag and return first line of output."""
    try:
        proc = subprocess.run(
            [executable_path, version_flag],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3,
            check=False
        )
        output = (proc.stdout or proc.stderr or "").strip()
        if output:
            return output.splitlines()[0]
    except Exception:
        pass
    return None


def check_system_environment() -> Dict[str, Any]:
    """
    Check the installation status and versions of all target compilers and runtimes.
    """
    common_c_dirs = [
        r"C:\msys64\mingw64\bin",
        r"C:\msys64\ucrt64\bin",
        r"C:\mingw64\bin",
        r"C:\TDM-GCC-64\bin",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\w64devkit\bin"),
        os.path.expandvars(r"%USERPROFILE%\scoop\shims"),
    ]

    common_java_dirs = [
        r"C:\Program Files\Java\jdk-21\bin",
        r"C:\Program Files\Java\jdk-17\bin",
        r"C:\Program Files\Eclipse Adoptium\jdk-21.0.0-hotspot\bin",
        os.path.expandvars(r"%JAVA_HOME%\bin"),
    ]

    gcc_path = find_tool("gcc", common_c_dirs)
    gpp_path = find_tool("g++", common_c_dirs)
    javac_path = find_tool("javac", common_java_dirs)
    java_path = find_tool("java", common_java_dirs)
    python_path = shutil.which("python") or shutil.which("python3")

    env_status = {
        "python": {
            "available": python_path is not None,
            "path": python_path,
            "version": get_tool_version(python_path) if python_path else None,
            "role": "Native execution, AST analysis, Bytecode inspection, ML models"
        },
        "gcc": {
            "available": gcc_path is not None,
            "path": gcc_path,
            "version": get_tool_version(gcc_path) if gcc_path else None,
            "role": "C compiler diagnostics and test binary compilation"
        },
        "g++": {
            "available": gpp_path is not None,
            "path": gpp_path,
            "version": get_tool_version(gpp_path) if gpp_path else None,
            "role": "C++ compiler diagnostics and test binary compilation"
        },
        "javac": {
            "available": javac_path is not None,
            "path": javac_path,
            "version": get_tool_version(javac_path, "-version") if javac_path else None,
            "role": "Java bytecode compiler and compiler diagnostics"
        },
        "java": {
            "available": java_path is not None,
            "path": java_path,
            "version": get_tool_version(java_path, "-version") if java_path else None,
            "role": "Java runtime virtual machine"
        },
        "tree_sitter": {
            "available": True,
            "languages": ["C", "C++", "Java", "Python AST"],
            "role": "Deterministic AST parser, exact source-location mapper, and syntax checker"
        }
    }

    # Generate helpful installation advice for any missing tools
    missing = []
    if not env_status["gcc"]["available"]:
        missing.append("GCC (C compiler)")
    if not env_status["g++"]["available"]:
        missing.append("G++ (C++ compiler)")
    if not env_status["javac"]["available"]:
        missing.append("javac (Java compiler)")

    env_status["missing_tools"] = missing
    env_status["ast_fallback_active"] = len(missing) > 0

    return env_status
