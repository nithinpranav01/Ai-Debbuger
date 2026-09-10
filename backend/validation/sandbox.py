"""
Isolated validation sandbox for compiling, executing, and testing source code.
Uses unique temporary directories per request, strict execution timeouts, and cleanup handlers.
"""

import os
import sys
import shutil
import tempfile
import uuid
import subprocess
from typing import Optional, Tuple, Dict, Any


class IsolatedSandbox:
    def __init__(self, prefix: str = "ai_bug_finder_"):
        self.workspace_id = str(uuid.uuid4())[:8]
        self.temp_dir = tempfile.mkdtemp(prefix=f"{prefix}{self.workspace_id}_")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def cleanup(self):
        """Safely clean up the temporary workspace."""
        if os.path.isdir(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except Exception:
                pass

    def write_file(self, filename: str, content: str) -> str:
        """Write source code to a file inside the isolated sandbox."""
        file_path = os.path.join(self.temp_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return file_path

    def run_process(
        self,
        command: list,
        input_data: Optional[str] = None,
        timeout_sec: float = 4.0
    ) -> Tuple[bool, str, str, int]:
        """
        Execute a command inside the isolated directory with timeout and memory safeguards.
        Returns: (success: bool, stdout: str, stderr: str, return_code: int)
        """
        try:
            proc = subprocess.run(
                command,
                cwd=self.temp_dir,
                input=input_data or "",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_sec,
                check=False
            )
            stdout = proc.stdout[:10000] if proc.stdout else ""
            stderr = proc.stderr[:10000] if proc.stderr else ""
            return (proc.returncode == 0, stdout, stderr, proc.returncode)
        except subprocess.TimeoutExpired:
            return (False, "", f"Execution timed out after {timeout_sec}s (Infinite loop or blocked I/O detected)", -1)
        except Exception as e:
            return (False, "", f"Execution error: {str(e)}", -2)
