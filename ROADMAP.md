# Roadmap du Projet

Ce document liste les fonctionnalités prévues, classées par priorité stratégique.

## 🚀 Court Terme : Consolidation Benchmark & Évaluation
L'objectif est de renforcer la capacité de l'outil à comparer objectivement les modèles (LLM-as-a-Judge, Métriques).

- [ ] **Script de Benchmark automatisé** : Tester tous les modèles sur un prompt donné, enregistrer inputs/outputs et métriques (latence, tokens/s).
- [ ] **Interface "Arena" (Comparaison)** : Nouvel onglet permettant de sélectionner N modèles, les exécuter en parallèle sur un prompt et afficher les résultats côte à côte.
- [ ] **Évaluation RAG** : Intégration de pipelines d'évaluation (Ragas ou Giskard) pour scorer la qualité des réponses sur documents.
- [ ] **Fichiers de test RAG** : Fournir un set de documents par défaut pour faciliter les démos et tests immédiats.
- [ ] **Intégration Mistral API** : Ajout du provider Mistral AI pour comparaison Cloud vs Local.

## 🛠 Moyen Terme : Industrialisation & UX
Améliorer la robustesse et l'expérience utilisateur.

- [ ] **Impact Environnemental Avancé** : Distinction claire entre l'impact calculé (Local/CodeCarbon) et l'impact estimé (Cloud/API) avec ventilation par scope.
- [ ] **Refonte UX** : Condenser l'interface (sidebar, affichage des métriques) pour plus de densité d'information.
- [ ] **Dockerisation** : Génération d'une image Docker pour déploiement facile.

## 🔮 Futur / Exploration
Fonctionnalités avancées d'orchestration.

- [ ] **Mode Multi-agents** : Exploration de frameworks comme CrewAI pour des tâches complexes.
- [ ] **LLM Council** : Système de vote entre modèles pour déterminer la meilleure réponse (synthèse).

---
*Dernière mise à jour : 13/12/2025*