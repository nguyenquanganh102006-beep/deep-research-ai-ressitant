from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os
os.environ['DEEPRESEARCH_DATA_DIR'] = str(Path(__file__).resolve().parents[1] / 'data/benchmark/local_llm_packets/index')
os.environ.setdefault('HF_HUB_OFFLINE', '1')
from src.benchmark.local_cli import packets_main

if __name__ == "__main__":
    raise SystemExit(packets_main())
