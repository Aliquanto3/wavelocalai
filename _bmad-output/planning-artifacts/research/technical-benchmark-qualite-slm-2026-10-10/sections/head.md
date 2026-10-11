# Recherche technique : benchmark qualité plus difficile pour SLM locaux (Ollama)

**Décision servie :** choisir les jeux d'évaluation, le harnais et la taille d'échantillon d'un banc qualité discriminant pour les petits modèles de langage (SLM) locaux de wavelocalai. Usages visés : agents avec appel d'outils, RAG en français, extraction JSON, plus le raisonnement, le suivi d'instructions et l'abstention.

## Résumé exécutif

**Ce que les preuves disent de faire :** construire le harnais maison sur l'API native d'Ollama. Il doit tirer ses items de jeux sous licence ouverte et, surtout, de **générateurs** (items paramétrés), avec au moins **≈ 330 items par piste** pour départager deux modèles à 10 points d'écart. Les comparaisons se font par **McNemar exact apparié avec correction de Holm**. Détail en section 5 (R1 à R8), composition des pistes en R2.

**Les trois constats qui portent la décision :**

1. **Le banc actuel ne peut pas départager les modèles.** Avec environ 30 items, un écart de 10 points n'est détecté que dans 8 à 10 % des cas. Il faut 168 à 329 items par piste (McNemar exact, selon la part de questions où les modèles divergent), et 39 à 84 pour un écart de 20 points. Ces effectifs sont calculés par le rapport à partir de la formule de Connor [D3-1], recoupée par celle de Miller [D3-3], et recalculés indépendamment (section 3.2).
2. **Les jeux publics les plus connus sont saturés, peu discriminants ou biaisés pour des SLM.**
   - IFEval plafonne à 89–90 % dès 4B chez Gemma 3 [D1-9][D1-2].
   - MuSR reste entre 0,33 et 0,41 (score sur 1) de 1B à 14B [D1-10].
   - MATH-500 est contaminé chez Qwen2.5 [D1-28], et le surapprentissage se confirme sur des variantes générées [D1-29][D1-30].
   - Les remplaçants utiles existent : IFBench (EN), M-IFEval (FR), BFCL v4 live et multi-turn, BBEH mini, OneRuler (contexte long, français inclus), JSONSchemaBench et PIAF. Tous sont sous licence redistribuable (section 1).
3. **Aucun framework n'apporte ce dont le banc a besoin.**
   - lm-eval, Inspect et BFCL passent tous par l'API compatible OpenAI d'Ollama (`/v1`), qui ne permet de régler ni `num_ctx`, ni `think`, ni `format` (schéma JSON natif) [D2-3][D2-7].
   - Aucun ne fait de comparaison appariée entre modèles.
   - Sur Ollama, lm-eval perd en outre toutes les tâches à choix multiples, dont BBH et MuSR [D2-4][D2-2].
   - Le harnais maison, déjà décidé, est donc justifié. Il reprendra les **vérificateurs** d'IFBench et de M-IFEval ainsi que le vérificateur AST de BFCL, à copier dans le dépôt (tous sous Apache-2.0) [D2-15][D2-16][D1-6].

**Principale réserve :** Ollama n'applique pas toujours la contrainte `format` quand `think` est actif (issue ouverte en octobre 2026) [D2-21], et un réglage censé être déterministe ne l'est pas toujours [D3-7][D3-8]. Le harnais doit donc valider chaque sortie côté client et mesurer la stabilité, faute de quoi des écarts dus à Ollama passeront pour des écarts entre modèles.

**Deuxième réserve :** les scores publiés qui fondent le constat n° 2 datent de la génération 2024–2025 (Llama 3.2, Qwen2.5, Gemma 3) et sont périmés selon les fenêtres de revérification (section 7). Un pilote sur les modèles réels du catalogue doit mesurer la saturation et la discordance avant de figer les pistes.

## 0. Cadre de décision

Le cadre tient compte des décisions déjà prises par l'utilisateur le 10/10/2026, relevées dans la mémoire du projet. Elles cadrent les questions, mais ne valent pas preuve :
- couvrir tous les usages ;
- campagne de 5 à 6 jours sur une seule machine (tour-rtx3050), avec 19 modèles ;
- environ 800 items par modèle et par piste ;
- reprise après arrêt sans perte au-delà de l'item en cours ;
- juge cloud accepté pour la rédaction en français ;
- harnais maison.

**Critères éliminatoires :**
- appel de l'API Ollama locale ;
- correction déterministe, sauf pour la rédaction FR jugée ;
- résultats par question ;
- exécution hors ligne pendant une campagne ;
- licence compatible avec un dépôt public ;
- Python 3.10+.

**Préférences pondérées :**
- adaptabilité au français : ×3 ;
- pertinence pour les usages : ×3 ;
- faible contamination : ×2 ;
- facilité d'intégration : ×2 ;
- pouvoir discriminant pour les SLM : ×2.

