# 🔍 Wavestone AI Code Auditor (WACA)

## Proposition de Valeur
WACA est une méthodologie d'audit de code à haute efficacité conçue pour analyser des bases de code Python/Streamlit dépassant les **10 000 lignes de code**. En utilisant une approche "Bottom-Up" (Squelette -> Flux -> Audit), il permet de contourner les limites de contexte des LLM (Gemini 3.0) tout en garantissant une analyse systémique profonde.

## 🛠 Architecture du Kit d'Audit
Le dossier `llm_review/` est structuré pour isoler la logique d'audit du code source de production :
- [cite_start]`generate_audit_skeleton.py` : Extracteur de signatures et de contrats d'interface[cite: 1].
- `export_critical_flows.py` : Orchestrateur de fusion des fichiers par flux métier.
- `exports/` : Contient les fichiers TXT et MD prêts pour l'ingestion par le LLM.

## 🚀 Méthodologie "Incremental Deep-Dive"

### Phase 1 : Cartographie (The Map)
1. **Génération du Squelette** : Exécutez `generate_audit_skeleton.py`. Ce script extrait uniquement les signatures (fonctions, classes, docstrings) sans la logique interne.
2. **Identification des Flux** : Fournissez `audit_skeleton.txt` à Gemini avec le prompt **"Architectural Mapper"**.
3. **Configuration** : Enregistrez le JSON retourné par Gemini dans `exports/critical_flows.json`.

### Phase 2 : Extraction Verticale (The Slices)
1. **Fusion des Flux** : Exécutez `export_critical_flows.py`. Le script crée des rapports Markdown fusionnés dans `exports/flows/` (ex: `audit_ready_rag_flow.md`).
2. **Contextualisation** : Chaque rapport contient le code complet des fichiers liés à un flux spécifique, permettant au LLM de comprendre les interactions inter-modules.

### Phase 3 : Audit Profond (The Zoom)
Envoyez le contenu d'un flux fusionné à Gemini avec vos prompts spécialisés :
- **Audit Performance** : Focus sur les goulots d'étranglement I/O et la RAM.
- **Audit Sécurité** : Focus sur l'OWASP for LLM et les fuites de données.
- **Audit Qualité** : Focus sur la dette technique et SOLID.

## 📊 Matrices d'Évaluation
Chaque audit génère une scorecard standardisée pour faciliter la prise de décision managériale :
- **Score Global** : Notation sur 100.
- **ROI d'Optimisation** : Gain estimé vs Effort de développement.
- **Roadmap de Remédiation** : Classée par criticité (P0 à P2).

## 🧪 Standards de Qualité
- **Clean Code** : Compatibilité stricte Ruff et Mypy.
- **GreenOps** : Mesure de l'impact carbone via CodeCarbon.
- **Documentation** : Format Google (PEP 257) pour tous les nouveaux composants.

---
*Développé pour Wavestone - Senior AI Tech Lead Strategy.*
