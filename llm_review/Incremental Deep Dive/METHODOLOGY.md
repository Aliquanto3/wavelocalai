# 🛠 Méthodologie d'Audit Incrémental (Gemini 3.0)

Cette méthodologie permet d'auditer une base de code de **10k+ lignes** sans saturer la fenêtre de contexte, en transformant le LLM en un auditeur actif capable de demander les ressources nécessaires au fur et à mesure de son analyse.

## 📋 Phase 1 : Initialisation avec "The Orchestrator"

Le prompt **"The Orchestrator"** est utilisé pour la première interaction. Son rôle est de donner au LLM une vision panoramique du projet sans le noyer dans les détails d'implémentation.

### Procédure :
1. Générez le squelette du projet via `generate_audit_skeleton.py`.
2. Envoyez le contenu de `audit_skeleton.txt` accompagné du prompt **The Orchestrator**.
3. **Objectif** : Le LLM doit valider la structure globale, identifier les points névralgiques (Singletons, Managers, Orchestrateurs) et lister les fichiers manquants pour comprendre le flux de données complet.



---

## 🔍 Phase 2 : Audit Ciblé avec "Incremental Auditor"

Une fois la carte mentale établie, utilisez le prompt **"Incremental Auditor"** pour chaque module ou fichier critique identifié en Phase 1.

### Procédure :
1. Sélectionnez un fichier dans la liste des "Chemins Critiques" (ex: `src/core/rag_engine.py`).
2. Envoyez le code **complet** du fichier au LLM.
3. **Objectif** : Analyse profonde du fichier par rapport à sa responsabilité dans le système. Le LLM doit détecter les ruptures de contrat avec les fichiers précédemment analysés et signaler toute nouvelle dépendance à auditer.

---

## 🚦 Règles d'Or de l'Audit

1. **Zéro Hallucination** : Si le LLM mentionne une fonction absente du squelette, demandez-lui de rectifier en se basant uniquement sur les signatures fournies.
2. **Isolation des Données** : Priorisez systématiquement l'audit de l'isolation des données utilisateur et l'optimisation de la consommation de tokens.
3. **Compatibilité Stricte** : Chaque suggestion de correction doit impérativement respecter les standards **Mypy (strict)** et **Ruff**.
4. **Documentation PEP 257** : Toute refactorisation proposée doit inclure des docstrings au format Google (Args, Returns, Raises).

## 📈 Format de Sortie des Résultats

Chaque étape d'audit doit alimenter les grilles d'analyse définies dans vos prompts experts :
- **Performance** : TTFT, Peak RAM, Throughput.
- **Sécurité** : Framework CVSS 3.1 et Top 5 vulnérabilités.
- **Qualité** : Quality Matrix et GreenOps Metrics.
