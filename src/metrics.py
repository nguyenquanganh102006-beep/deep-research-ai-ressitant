"""Best-effort local CPU, RAM and GPU snapshots without CUDA dependencies."""

from __future__ import annotations

import subprocess
from typing import Any


def capture_resource_metrics() -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    try:
        import psutil

        process = psutil.Process()
        metrics["process_rss_mb"] = round(process.memory_info().rss / (1024 * 1024), 1)
        metrics["system_ram_used_mb"] = round(
            psutil.virtual_memory().used / (1024 * 1024), 1
        )
    except Exception as exc:
        metrics["ram_error"] = str(exc)

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        metrics["gpu"] = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except Exception as exc:
        metrics["gpu_error"] = str(exc)
    return metrics
