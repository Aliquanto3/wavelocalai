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
DRIVER_VERSION = "000.00-test"


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
        elif "--query-gpu=driver_version" in command:
            lines = [DRIVER_VERSION]
        else:
            assert "--query-gpu=index,memory.used" in command
            lines = [f"{index}, {value}" for index, value in enumerate(self.used)]
        return subprocess.CompletedProcess(
            command, self.returncode, "\n".join(lines) + ("\n" if lines else ""), self.stderr
        )


class SequencedSmi(FakeSmi):
    """``FakeSmi`` dont l'état change au fil des contrôles : ``states`` = liste de couples
    ``(apps, used)``, un par paire de requêtes (le dernier reste ensuite)."""

    def __init__(self, states):
        super().__init__()
        self.states = list(states)
        self.checks = 0

    def __call__(self, command, **kwargs):
        if "--query-compute-apps=pid,process_name,used_memory" in command:
            self.apps, self.used = self.states[min(self.checks, len(self.states) - 1)]
            self.checks += 1
        return super().__call__(command, **kwargs)
