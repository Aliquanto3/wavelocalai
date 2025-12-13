"""
Script de détection de secrets potentiels dans le code source.
Usage: python scripts/scan_secrets.py
"""
import re
from pathlib import Path

# Patterns de détection (regex)
PATTERNS = {
    "API Key (Generic)": r'["\']?(?:api[_-]?key|apikey)["\']?\s*[:=]\s*["\']([A-Za-z0-9_\-]{20,})["\']',
    "API Key (Prefixed)": r'["\']?(sk-|pk-|xoxb-|ghp_|gho_)[A-Za-z0-9_\-]{20,}["\']?',
    "Password": r'["\']?password["\']?\s*[:=]\s*["\']([^"\']{8,})["\']',
    "Secret": r'["\']?secret["\']?\s*[:=]\s*["\']([^"\']{8,})["\']',
    "Token": r'["\']?token["\']?\s*[:=]\s*["\']([A-Za-z0-9_\-]{20,})["\']',
    "Database URL": r'(?:postgres|mysql|mongodb)://[^\s<>"\']+',
    "Private Key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "AWS Key": r"AKIA[0-9A-Z]{16}",
}

# Extensions de fichiers à scanner
SCAN_EXTENSIONS = {".py", ".txt", ".md", ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg"}

# Dossiers à ignorer
IGNORE_DIRS = {".venv", "venv", "env", "node_modules", ".git", "__pycache__", "build", "dist"}

# Faux positifs connus (à adapter selon votre projet)
FALSE_POSITIVES = [
    "your_api_key_here",
    "example_key",
    "placeholder",
    "changeme",
    "secret_key_here",
    "enter_your_key",
]


def is_false_positive(match: str) -> bool:
    """Vérifie si le match est un faux positif connu."""
    match_lower = match.lower()
    return any(fp in match_lower for fp in FALSE_POSITIVES)


def scan_file(file_path: Path) -> list[dict[str, any]]:
    """
    Scanne un fichier à la recherche de secrets potentiels.

    Returns:
        Liste de détections avec ligne et pattern
    """
    findings = []

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            for pattern_name, pattern in PATTERNS.items():
                matches = re.finditer(pattern, line, re.IGNORECASE)
                for match in matches:
                    matched_text = match.group(0)

                    # Filtrer les faux positifs
                    if is_false_positive(matched_text):
                        continue

                    findings.append(
                        {
                            "file": str(file_path),
                            "line": line_num,
                            "pattern": pattern_name,
                            "match": matched_text[:60] + "..."
                            if len(matched_text) > 60
                            else matched_text,
                            "full_line": line.strip()[:100],
                        }
                    )

    except Exception as e:
        print(f"⚠️  Erreur lecture {file_path}: {e}")

    return findings


def scan_project(root_dir: Path) -> list[dict]:
    """Scanne tout le projet."""
    all_findings = []

    for file_path in root_dir.rglob("*"):
        # Ignorer les dossiers exclus
        if any(ignore_dir in file_path.parts for ignore_dir in IGNORE_DIRS):
            continue

        # Vérifier l'extension
        if file_path.suffix not in SCAN_EXTENSIONS:
            continue

        # Scanner le fichier
        findings = scan_file(file_path)
        all_findings.extend(findings)

    return all_findings


def main():
    print("🔍 WaveLocalAI - Scan de Secrets")
    print("=" * 60)

    ROOT_DIR = Path(__file__).parent.parent

    print(f"📂 Dossier scanné : {ROOT_DIR}")
    print(f"🎯 Extensions : {', '.join(SCAN_EXTENSIONS)}")
    print(f"🚫 Dossiers ignorés : {', '.join(IGNORE_DIRS)}")
    print("\n🔎 Scan en cours...\n")

    findings = scan_project(ROOT_DIR)

    if not findings:
        print("✅ AUCUN SECRET DÉTECTÉ !")
        print("\n👍 Votre code semble propre.")
        return 0

    # Affichage des résultats
    print(f"⚠️  {len(findings)} DÉTECTION(S) POTENTIELLE(S) :\n")

    for i, finding in enumerate(findings, 1):
        print(f"{i}. 📄 {finding['file']}:{finding['line']}")
        print(f"   🔑 Pattern : {finding['pattern']}")
        print(f"   💡 Match : {finding['match']}")
        print(f"   📝 Ligne : {finding['full_line']}")
        print()

    print("=" * 60)
    print("⚠️  ACTIONS RECOMMANDÉES :")
    print("1. Vérifiez chaque détection manuellement")
    print("2. Déplacez les vraies clés vers .env")
    print("3. Committez .env dans .gitignore")
    print("4. Utilisez des placeholders dans le code (ex: os.getenv('API_KEY'))")

    return 1 if findings else 0


if __name__ == "__main__":
    exit(main())
