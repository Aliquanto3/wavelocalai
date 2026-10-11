"""Écrivain de test : écrit les clés ``k0..k<N>`` par ``open_for_append``, en sautant celles
déjà présentes, sous le verrou du fichier. Sert aux tests d'arrêt brutal et de verrou occupé.

Usage : ``python append_loop.py <jsonl> <verrou> <dernier indice> <pause en s>``.
Affiche ``ready <pid>`` une fois le verrou pris, puis ``wrote <clé>`` après chaque ligne.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.quality_bench.common.jsonl import open_for_append  # noqa: E402
from scripts.quality_bench.common.locks import FileLock  # noqa: E402


def main() -> int:
    jsonl_path, lock_path, last, pause = sys.argv[1:5]
    with FileLock(lock_path) as lock, open_for_append(jsonl_path, lock) as writer:
        print(f"ready {os.getpid()}", flush=True)
        for index in range(int(last) + 1):
            key = f"k{index}"
            if key in writer:
                continue
            writer.append({"key": key, "index": index, "padding": "é" * 200})
            print(f"wrote {key}", flush=True)
            time.sleep(float(pause))
    return 0


if __name__ == "__main__":
    sys.exit(main())
