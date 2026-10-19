"""Phase 0 manual smoke check for Ollama Qwen, code and math prompts."""

from __future__ import annotations

import subprocess
import time

from config import MODEL_NAME, NUM_CTX, OLLAMA_HOST, OLLAMA_TIMEOUT_SECONDS, TEMPERATURE
from src.llm import ollama_client
from src.metrics import capture_resource_metrics


def run_command(*args: str) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15)
        return (result.stdout or result.stderr).strip()
    except Exception as exc:
        return f"Unavailable: {exc}"


def run_prompt(client, label: str, prompt: str) -> None:
    print(f"\n--- {label} ---")
    started = time.perf_counter()
    response = client.chat(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        think=False,
        options={"num_ctx": NUM_CTX, "temperature": TEMPERATURE, "num_predict": 300},
        stream=False,
    )
    content = str(response.message.content or "").strip()
    if not content:
        raise RuntimeError(f"{label} prompt returned no visible answer.")
    print(content)
    print(f"Latency: {time.perf_counter() - started:.2f}s")


def main() -> int:
    print(f"Ollama host: {OLLAMA_HOST}")
    print(f"Model: {MODEL_NAME}; num_ctx={NUM_CTX}")
    print("Resources before:", capture_resource_metrics())
    client = ollama_client()
    try:
        run_prompt(
            client,
            "Math",
            "Which exact loss symbol is multiplied by lambda in L = L_cls + lambda L_reg? Answer only with the symbol.",
        )
        run_prompt(
            client,
            "Code",
            "In one concise sentence, explain this Python snippet: for i in range(3):\n    print(i)",
        )
    except Exception as exc:
        print(f"Smoke check failed: {exc}")
        return 1
    print("\nOllama placement (PROCESSOR column):")
    print(run_command("ollama", "ps"))
    print("Resources after:", capture_resource_metrics())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
