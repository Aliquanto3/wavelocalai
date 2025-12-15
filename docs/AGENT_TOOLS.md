# 🧰 Guide des Outils Agents - WaveLocalAI

Ce document détaille les **9 outils** disponibles pour les agents autonomes (Mode Solo) et les équipes multi-agents (Mode Crew).

---

## 📋 Vue d'Ensemble

| Outil | Catégorie | Description | Config requise |
|-------|-----------|-------------|----------------|
| 🕒 **Time** | System | Heure système actuelle | Non |
| 🧮 **Calculator** | Computation | Calculs mathématiques sécurisés | Non |
| 🏢 **Wavestone Search** | Data | Recherche interne simulée | Non |
| 📧 **Email Sender** | Communication | Envoi d'emails via SMTP | **Oui** (SMTP) |
| 📊 **CSV Analyzer** | Data | Analyse de fichiers CSV/Excel | Non |
| 📝 **Document Generator** | Output | Création de fichiers DOCX | Non |
| 📈 **Chart Generator** | Output | Génération de graphiques PNG | Non |
| 📄 **Markdown Report** | Output | Rapports structurés MD | Non |
| 💻 **System Monitor** | System | Métriques CPU/RAM/Disque | Non |

---

## 🕒 1. Time (get_current_time)

### Description
Retourne l'heure système au format ISO 8601.

### Utilisation
**Prompt exemple :**
```
Quelle heure est-il exactement ?
```

**Sortie :**
```
L'heure actuelle est : 2024-12-15 14:32:45
```

### Cas d'usage
- Horodatage de rapports
- Calculs de durée
- Planification de tâches
- Logs temporels

### Notes techniques
- Format : `YYYY-MM-DD HH:MM:SS`
- Timezone : Système local
- Précision : Seconde

---

## 🧮 2. Calculator (calculator)

### Description
Exécute des calculs mathématiques de manière sécurisée (protection contre les injections).

### Utilisation
**Prompt exemple :**
```
Calcule 15% de 1250, puis multiplie par 3
```

**Appel interne :**
```python
calculator("(1250 * 0.15) * 3")
# Résultat : 562.5
```

### Opérateurs supportés
- Addition : `+`
- Soustraction : `-`
- Multiplication : `*`
- Division : `/`
- Puissance : `**`
- Parenthèses : `( )`

### Protections de sécurité
✅ Expressions jusqu'à 100 caractères
✅ Validation des caractères (pas de `eval()` ou `exec()`)
✅ Timeout de 2 secondes
✅ Détection de division par zéro

❌ Pas de modulo `%` (risque d'injection)
❌ Pas d'imports Python

### Cas d'usage
- Analyses financières
- Statistiques sur données
- Calculs scientifiques
- Conversions d'unités

---

## 🏢 3. Wavestone Search (search_wavestone_internal)

### Description
Moteur de recherche simulé dans une base de connaissance RH/Projets Wavestone.

### Base de données simulée
```
- Anaël Yahi : Consultant IA, spécialité GenAI et Green IT
- Projets : WaveLocalAI, Benchmarks SLM
- Expertises : LLM, RAG, Agents autonomes
```

### Utilisation
**Prompt exemple :**
```
Qui est Anaël dans l'équipe Wavestone ?
```

**Fonctionnalités :**
- Recherche insensible à la casse
- Gestion des accents (Anael = Anaël)
- Correspondance partielle
- Suggestions si aucun résultat exact

### Cas d'usage
- Recherche de compétences
- Identification d'experts
- Historique de projets
- Requêtes RH internes

### Extension
Pour ajouter des données :
```python
# Dans agent_tools.py, ligne ~85
MOCK_DB = {
    "anael": "...",
    "nouveau_collegue": "Informations détaillées...",
}
```

---

## 📧 4. Email Sender (send_email)

### Description
Envoie des emails via un serveur SMTP configuré.

### Configuration requise

**Fichier `.env` :**
```bash
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=votre-email@gmail.com
SMTP_PASSWORD=votre-app-password
```

**⚠️ Important pour Gmail :**
1. Activer la validation en 2 étapes
2. Générer un "Mot de passe d'application"
3. Utiliser ce mot de passe dans `SMTP_PASSWORD`

### Utilisation
**Prompt exemple :**
```
Envoie un email à client@example.com avec le sujet "Rapport mensuel"
et le contenu du rapport que je viens de générer
```

**Appel interne :**
```python
send_email(
    to="client@example.com",
    subject="Rapport mensuel",
    body="Contenu du rapport...",
    html=False
)
```

### Validations
- ✅ Vérification du format email
- ✅ Sujet max 200 caractères
- ✅ Corps max 10000 caractères
- ✅ Support HTML optionnel

### Cas d'usage
- Envoi automatique de rapports
- Notifications d'alertes
- Distribution de résultats d'analyse
- Workflows de validation

### Sécurité
⚠️ **Les credentials SMTP sont sensibles**
- Ne jamais commit le `.env`
- Utiliser des App Passwords
- Vérifier les logs pour les erreurs SMTP

---

## 📊 5. CSV Analyzer (analyze_csv)

### Description
Analyse des fichiers de données (CSV, Excel) avec Pandas.

### Formats supportés
- `.csv` (CSV standard)
- `.xlsx` (Excel moderne)
- `.xls` (Excel legacy)

### Commandes disponibles

#### Aperçu (`aperçu`)
```python
analyze_csv("data/sales.csv", "aperçu")
```
Affiche : nombre de lignes, colonnes, types, premières lignes

#### Statistiques (`stats`)
```python
analyze_csv("data/sales.csv", "stats")
```
Affiche : moyenne, médiane, min, max, écart-type

#### Moyenne d'une colonne
```python
analyze_csv("data/sales.csv", "moyenne de revenue")
```

#### Somme d'une colonne
```python
analyze_csv("data/sales.csv", "somme de quantity")
```

#### Comptage
```python
analyze_csv("data/sales.csv", "compte les lignes")
```

### Utilisation
**Prompt exemple :**
```
Analyse le fichier benchmarks_data.csv et donne-moi :
1. Un aperçu des données
2. La moyenne des tokens par seconde
3. Le nombre total de benchmarks
```

**L'agent fera 3 appels :**
```python
analyze_csv("benchmarks_data.csv", "aperçu")
analyze_csv("benchmarks_data.csv", "moyenne de tokens_per_second")
analyze_csv("benchmarks_data.csv", "compte les lignes")
```

### Cas d'usage
- Analyse de performances de modèles
- Reporting sur données métier
- Calculs statistiques
- Préparation de visualisations

### Limitations
- Fichiers jusqu'à 100MB
- Pas de modification des données (lecture seule)
- Pas de requêtes SQL complexes

---

## 📝 6. Document Generator (generate_document)

### Description
Crée des documents Word (.docx) professionnels à partir de Markdown.

### Utilisation
**Prompt exemple :**
```
Crée un document Word avec :
- Titre : Rapport de Benchmark SLM
- Contenu : Les résultats de l'analyse précédente, avec sections et listes
```

**Appel interne :**
```python
generate_document(
    title="Rapport de Benchmark SLM",
    content="""
    ## Introduction
    Ce rapport présente les résultats...

    ## Résultats
    - Qwen 2.5 1.5B : 45 tokens/s
    - Mistral 7B : 32 tokens/s
    """
)
```

### Formatage supporté

#### Titres
```markdown
# Titre principal (Titre 1)
## Section (Titre 2)
### Sous-section (Titre 3)
```

#### Listes à puces
```markdown
- Élément 1
- Élément 2
  - Sous-élément 2.1
```

#### Listes numérotées
```markdown
1. Premier point
2. Deuxième point
3. Troisième point
```

#### Texte brut
```
Paragraphes normaux sans formatage spécial.
```

### Sortie
- **Emplacement :** `outputs/document_YYYYMMDD_HHMMSS.docx`
- **Style :** Professionnel (marges, polices, espacements)
- **Compatible :** Word, Google Docs, LibreOffice

### Cas d'usage
- Rapports d'analyse
- Documentation technique
- Comptes-rendus de réunion
- Synthèses exécutives

---

## 📈 7. Chart Generator (generate_chart)

### Description
Génère des graphiques professionnels au format PNG avec Matplotlib.

### Types de graphiques

#### Barres (`bar`)
```python
generate_chart(
    data='{"labels": ["Q1", "Q2", "Q3"], "values": [100, 150, 200]}',
    chart_type="bar",
    title="Ventes Trimestrielles"
)
```

#### Courbe (`line`)
```python
generate_chart(
    data='{"labels": ["Jan", "Fev", "Mar"], "values": [45, 52, 48]}',
    chart_type="line",
    title="Évolution Mensuelle"
)
```

#### Camembert (`pie`)
```python
generate_chart(
    data='{"labels": ["Local", "Cloud"], "values": [65, 35]}',
    chart_type="pie",
    title="Répartition Infrastructure"
)
```

### Format de données
**JSON avec deux clés obligatoires :**
```json
{
    "labels": ["Label1", "Label2", "Label3"],
    "values": [10, 20, 30]
}
```

### Utilisation
**Prompt exemple :**
```
Crée un graphique en barres montrant les performances de 3 modèles :
- Qwen 2.5 : 45 tokens/s
- Mistral : 32 tokens/s
- Llama : 28 tokens/s
Titre : "Benchmark Débit"
```

**L'agent générera le JSON et appellera :**
```python
generate_chart(
    data='{"labels": ["Qwen 2.5", "Mistral", "Llama"], "values": [45, 32, 28]}',
    chart_type="bar",
    title="Benchmark Débit"
)
```

### Sortie
- **Emplacement :** `outputs/chart_YYYYMMDD_HHMMSS.png`
- **Résolution :** 1200x800 pixels (haute qualité)
- **Format :** PNG avec fond blanc

### Cas d'usage
- Visualisation de benchmarks
- Comparaison de performances
- Graphiques pour rapports
- Dashboards statiques

### Personnalisation
Couleurs, styles et résolution peuvent être modifiés dans `agent_tools.py` ligne ~250.

---

## 📄 8. Markdown Report (generate_markdown_report)

### Description
Crée des rapports structurés au format Markdown (.md).

### Utilisation

#### Format JSON structuré
**Prompt exemple :**
```
Crée un rapport Markdown avec :
- Introduction : Contexte du benchmark
- Méthodologie : Procédure de test
- Résultats : Tableau des métriques
- Conclusion : Recommandations
```

**Appel interne :**
```python
generate_markdown_report(
    title="Benchmark SLM 2024",
    sections='''{
        "Introduction": "Ce benchmark compare...",
        "Méthodologie": "Tests réalisés sur...",
        "Résultats": "- Qwen : 45 tok/s...",
        "Conclusion": "Qwen 2.5 recommandé pour..."
    }'''
)
```

#### Format texte libre
```python
generate_markdown_report(
    title="Notes Réunion",
    sections="Contenu libre sans structure JSON"
)
```

### Sortie
- **Emplacement :** `outputs/report_YYYYMMDD_HHMMSS.md`
- **Format :** Markdown standard
- **Compatible :** GitHub, GitLab, Obsidian, Notion

### Structure générée
```markdown
# Titre du Rapport

*Généré le 2024-12-15 14:30:00*

---

## Section 1

Contenu de la section 1...

## Section 2

Contenu de la section 2...

---

*Rapport généré par WaveLocalAI*
```

### Cas d'usage
- Documentation technique
- Notes de réunion structurées
- Wikis internes
- Rapports versionnables (Git)

---

## 💻 9. System Monitor (system_monitor)

### Description
Récupère les métriques système actuelles (CPU, RAM, Disque).

### Utilisation
**Prompt exemple :**
```
Vérifie l'état du système et dis-moi si tout va bien
```

**Sortie :**
```
📊 État du Système :

💻 CPU :
   - Utilisation : 45.2%

💾 RAM :
   - Utilisée : 12.4 GB / 16.0 GB
   - Disponible : 3.6 GB
   - Pourcentage : 77.5%

💿 Disque C:\ :
   - Utilisé : 256.0 GB / 512.0 GB
   - Libre : 256.0 GB
   - Pourcentage : 50.0%
```

### Alertes automatiques
- ⚠️ **Warning** : RAM > 80%
- 🚨 **Critical** : RAM > 90%

### Cas d'usage
- Monitoring avant lancement de tâches lourdes
- Détection de problèmes de performance
- Logs système pour diagnostics
- Rapports d'infrastructure

### Métriques disponibles
- **CPU** : Utilisation instantanée (%)
- **RAM** : Totale, utilisée, disponible, pourcentage
- **Disque** : Espace total, utilisé, libre, pourcentage
- **Alertes** : Seuils d'avertissement automatiques

---

## 🔧 Configuration des Outils

### Structure dans `agent_tools.py`

```python
TOOLS_METADATA = {
    "nom_outil": {
        "name": "Nom Convivial",           # Affiché dans l'UI
        "description": "Description courte", # Tooltip
        "category": "system",               # Catégorie d'affichage
        "requires_config": False,           # Nécessite .env ?
        "config_vars": []                   # Variables nécessaires
    }
}
```

### Catégories disponibles
- `system` : Outils système (Time, Monitor)
- `computation` : Calculs (Calculator)
- `data` : Analyse de données (CSV, Search)
- `communication` : Communication (Email)
- `output` : Génération de fichiers (DOCX, Chart, MD)

---

## 🎯 Workflows Recommandés

### Workflow 1 : Analyse Complète de Données
```
1. analyze_csv → Aperçu des données
2. analyze_csv → Statistiques clés
3. generate_chart → Visualisation
4. generate_document → Rapport final
5. send_email → Distribution
```

### Workflow 2 : Monitoring Automatisé
```
1. system_monitor → État du système
2. calculator → Calculs sur métriques
3. generate_markdown_report → Rapport technique
4. send_email → Alerte si problème
```

### Workflow 3 : Reporting Exécutif
```
1. search_wavestone_internal → Contexte projet
2. analyze_csv → Données quantitatives
3. generate_chart → Graphiques
4. generate_document → Rapport DOCX
```

---

## 🧪 Tests des Outils

### Tests unitaires
```bash
pytest tests/unit/test_new_agent_tools.py -v
```

**Couverture :**
- ✅ Validation des entrées
- ✅ Gestion des erreurs
- ✅ Création de fichiers
- ✅ Parsing de formats
- ✅ Sécurité (Calculator)

### Tests manuels

**Checklist :**
- [ ] Time : Retourne l'heure actuelle
- [ ] Calculator : Calcule `(10 + 5) * 2`
- [ ] Search : Trouve "Anaël"
- [ ] Email : Envoie un test (si SMTP configuré)
- [ ] CSV : Analyse `benchmarks_data.csv`
- [ ] Document : Crée un DOCX avec formatage
- [ ] Chart : Génère un PNG en barres
- [ ] Report : Crée un MD structuré
- [ ] Monitor : Affiche CPU/RAM/Disque

---

## 🔐 Sécurité

### Protections implémentées

#### Calculator
- Whitelist de caractères autorisés
- Timeout d'exécution (2s)
- Longueur max (100 chars)
- Pas d'évaluation dynamique

#### CSV Analyzer
- Validation du format de fichier
- Lecture seule (pas d'écriture)
- Limite de taille (100MB)

#### Email Sender
- Validation du format email
- Limites de longueur
- Credentials dans .env (jamais en code)
- Logs sanitisés (pas de mot de passe)

### Recommandations

⚠️ **Variables sensibles (.env) :**
```bash
# Toujours dans .gitignore
.env
.env.local
```

⚠️ **Fichiers générés :**
```bash
# outputs/ est aussi dans .gitignore
# Les fichiers ne sont pas versionnés
```

⚠️ **Logs :**
```python
# Jamais logger les credentials
logger.info(f"Email envoyé à {to}")  # ✅ OK
logger.info(f"Password: {pwd}")      # ❌ DANGER
```

---

## 📚 Ressources

### Documentation technique
- [LangChain Tools](https://python.langchain.com/docs/modules/agents/tools/)
- [CrewAI Tools](https://docs.crewai.com/core-concepts/Tools/)
- [Pandas Documentation](https://pandas.pydata.org/docs/)
- [Matplotlib Gallery](https://matplotlib.org/stable/gallery/)
- [python-docx](https://python-docx.readthedocs.io/)

### Exemples de prompts
Voir `src/app/tabs/agent/solo.py` ligne ~150 pour la bibliothèque complète.

---

*Dernière mise à jour : 15/12/2025*
