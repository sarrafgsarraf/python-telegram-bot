"""Job runner — CI fixture: command built from job spec, executed via shell."""

import subprocess


def run(spec: dict) -> int:
    """Run job from spec. Returns exit code."""
    cmd = spec.get("command", "")
    args = spec.get("args", [])
    full = cmd + " " + " ".join(str(a) for a in args)
    return subprocess.call(full, shell=True)
