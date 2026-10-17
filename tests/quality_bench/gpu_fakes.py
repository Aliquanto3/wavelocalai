"""Sous-processus ``nvidia-smi`` simulé (sorties relevées sur Windows 11, pilote WDDM)."""

from __future__ import annotations

import subprocess

LLAMA_SERVER = (
    r"C:\Users\Utilisateur\Documents\GitHub\service-public-slm-fine-tuning\vendor"
    r"\llama.cpp\b11429\bin-cuda\llama-server.exe"
)
OLLAMA_RUNNER = r"C:\Users\Utilisateur\AppData\Local\Programs\Ollama\ollama.exe"

# Relevé réel : mémoire par processus « [N/A] » sous WDDM.
LLAMA_SERVER_LINE = f"22792, {LLAMA_SERVER}, [N/A]"
OLLAMA_LINE = f"4012, {OLLAMA_RUNNER}, [N/A]"


class FakeSmi:
    """Remplace ``gpu.RUN`` : ``apps`` = lignes de ``--query-compute-apps``, ``used`` =
    ``memory.used`` par GPU ; ``error`` = exception levée à l'appel ; ``returncode`` ≠ 0 simule
    un échec de ``nvidia-smi``."""

    def __init__(self, apps=(), used=(300,), error=None, returncode=0, stderr=""):
        self.apps = list(apps)
        self.used = list(used)
        self.error = error
        self.returncode = returncode
        self.stderr = stderr
        self.commands: list[list[str]] = []

    def __call__(self, command, **kwargs):
        self.commands.append(list(command))
        assert kwargs.get("timeout"), "délai court obligatoire"
        if self.error is not None:
            raise self.error
        if "--query-compute-apps=pid,process_name,used_memory" in command:
            lines = self.apps
        else:
            assert "--query-gpu=index,memory.used" in command
            lines = [f"{index}, {value}" for index, value in enumerate(self.used)]
        return subprocess.CompletedProcess(
            command, self.returncode, "\n".join(lines) + ("\n" if lines else ""), self.stderr
        )
