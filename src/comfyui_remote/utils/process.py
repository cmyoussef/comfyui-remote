"""Proc utils."""
import os
import signal
import subprocess


def terminate_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        try: proc.terminate()
        except Exception: pass
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try: proc.terminate()
            except Exception: pass
