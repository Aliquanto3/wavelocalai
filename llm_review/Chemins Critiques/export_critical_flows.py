import json
from pathlib import Path

# Configuration des chemins
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
# On suppose que le JSON est généré dans llm_review/exports/
FLOWS_JSON = SCRIPT_DIR / "exports" / "critical_flows.json"
OUTPUT_BASE = SCRIPT_DIR / "exports" / "flows"


def generate_merged_flow_report(json_path: Path):
    """Génère un fichier Markdown unique par flux critique."""
    if not json_path.exists():
        print(
            f"❌ Erreur : {json_path} introuvable. Génère-le avec le prompt 'Architectural Mapper'."
        )
        return

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)

    for flow in data.get("flows", []):
        flow_name = flow["name"].replace(" ", "_").lower()
        report_path = OUTPUT_BASE / f"audit_ready_{flow_name}.md"

        print(f"📦 Traitement du flux : {flow['name']}...")

        with open(report_path, "w", encoding="utf-8") as md:
            md.write(f"# AUDIT DATA: {flow['name']}\n")
            md.write(f"**Description**: {flow['description']}\n\n")
            md.write("---")

            for rel_path in flow["files"]:
                source_path = ROOT_DIR / rel_path
                md.write(f"\n\n## FILE: {rel_path}\n")
                if source_path.exists():
                    with open(source_path, encoding="utf-8") as src:
                        content = src.read()
                        # Utilisation de quadruples backticks pour la compatibilité
                        md.write(f"````python\n{content}\n````\n")
                    print(f"  ✅ Inclus : {rel_path}")
                else:
                    md.write(f"\n> ⚠️ FICHIER MANQUANT : {rel_path}\n")
                    print(f"  ⚠️ Manquant : {rel_path}")

    print(f"\n🚀 Rapports prêts dans : {OUTPUT_BASE}")


if __name__ == "__main__":
    generate_merged_flow_report(FLOWS_JSON)
