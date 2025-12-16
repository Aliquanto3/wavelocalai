# CONTEXTE
Tu es un Technical Writer expert et Developer Advocate spécialisé dans la documentation de projets open-source d'envergure. Tu maîtrises les meilleures pratiques GitHub pour maximiser l'engagement et la clarté technique.

# OBJECTIF
Créer un README.md professionnel et engageant pour "WaveLocalAI", un workbench local d'audit et de benchmarking de LLMs, en mettant l'accent sur les aspects Local-First, Privacy et Green IT.

# CONTRAINTES
- Format Markdown strict compatible GitHub
- Ton professionnel mais accessible
- Structure claire avec ancres de navigation
- Badges pertinents et à jour
- Placeholders d'images explicites
- Code snippets testables
- Sections pliables pour le contenu dense

# INPUTS FOURNIS
[COLLER LE CONTENU DE REVIEW_ME.TXT ICI]

# STRUCTURE OBLIGATOIRE

## 1. Header
- Titre avec émoji pertinent (🔬/🧪/⚡)
- Slogan percutant (15 mots max) centré sur la value proposition
- Ligne de badges : ![Python](badge) ![License](badge) ![Streamlit](badge) ![Status](badge)

## 2. Introduction (3-4 paragraphes)
**Paragraphe 1:** Le problème résolu (Why?)
**Paragraphe 2:** La solution WaveLocalAI (What?)
**Paragraphe 3:** Les avantages clés (Local-First, Privacy-Preserving, Energy-Efficient)
**Paragraphe 4:** Public cible (Data Scientists, AI Engineers, Consultants)

## 3. Démonstration Visuelle
````markdown
## 📸 Aperçu des Modules

### Module 1: Hardware Profiler
![Hardware Profiler Interface](docs/screenshots/hardware_profiler.png)
*Description en 1 ligne de la fonctionnalité*

[Répéter pour les 4 modules avec placeholders clairs]
````

## 4. Features Principales
Utilise ce format :
````markdown
## ✨ Fonctionnalités

### 🔧 Hardware Profiler
- [x] **Feature 1** - Description technique brève
- [x] **Feature 2** - Bénéfice utilisateur

[Répéter pour Arena, RAG Studio, Agent Playground]
````

## 5. Quick Start
````markdown
## 🚀 Installation

### Prérequis
- Python 3.11+
- pip
- [Autres si nécessaires]

### Installation en 3 commandes
```bash
# Commande 1 : clone
# Commande 2 : install
# Commande 3 : run
```

**Important:** Reprends EXACTEMENT la méthode "Invocation Directe" de `INSTALL_TROUBLESHOOT.md`
````

## 6. Usage
````markdown
## 💻 Utilisation

### Lancer l'application
```bash
[commande précise]
```

### Navigation
1. Étape 1
2. Étape 2
````

## 7. Roadmap
````markdown
## 🗺️ Roadmap

### Q1 2025
- [ ] Intégration CrewAI pour orchestration multi-agents
- [ ] Framework RAGAS pour évaluation RAG

### Q2 2025
- [ ] [Autres features mentionnées]

💡 *Suggestions bienvenues via Issues !*
````

## 8. Footer
````markdown
## 👥 Contributeurs
[Nom] - [Rôle] - [LinkedIn/GitHub]

## 📄 Licence
Ce projet est sous licence [TYPE]. Voir [LICENSE](LICENSE) pour détails.

## 🙏 Remerciements
- [Bibliothèques clés]
- [Inspirations]

---
Fait avec ❤️ par [Nom/Organisation]
````

# RÈGLES DE STYLE
1. **Émojis:** 1 par section principale maximum
2. **Listes:** Préférer `- [ ]` pour roadmap, `-` pour features
3. **Code:** Toujours spécifier le langage (```bash, ```python)
4. **Liens:** Utiliser les références `[texte][ref]` pour la lisibilité
5. **Call-to-Action:** Ajouter "⭐ Star ce projet si utile !" avant le footer

# DIFFÉRENCIATEURS À METTRE EN AVANT
- 🔒 **Privacy-First:** Aucune donnée ne quitte la machine
- 🌱 **Green IT:** Métriques d'empreinte carbone incluses
- 📊 **Audit-Ready:** Exports et rapports professionnels
- 🎓 **Pédagogique:** Idéal pour formations IA responsable

# OUTPUT ATTENDU
Un README.md complet de 200-300 lignes, prêt à commit, qui :
- Se charge en <2s sur GitHub
- Passe les linters Markdown
- Incite à l'installation dans les 30 premières secondes de lecture
- Positionne le projet comme référence dans l'audit local de LLMs

# CHECKLIST DE VALIDATION
Avant de générer, assure-toi que :
- [ ] Tous les badges sont générables via shields.io
- [ ] Les chemins d'images suivent la convention `/docs/screenshots/`
- [ ] Les snippets bash sont testables ligne par ligne
- [ ] La roadmap contient au minimum 5 items concrets
- [ ] Le ton reste factuel sans marketing agressif

Génère maintenant le README.md complet.
