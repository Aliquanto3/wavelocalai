# Pistes et questions

Il y a deux pistes.

**Raisonnement coupé** (`think_off`, `think=false`) : environ 800 questions, passées par les 20 modèles.

**Raisonnement activé** (`think_on`, `think=true`) : 400 questions, tirées par strates (la moitié de chaque usage) dans celles de la piste coupée.
- Seuls les modèles qui déclarent la capacité thinking la passent.
- Plafond de tokens (réflexion et réponse) : 4 096 pour le raisonnement, 2 048 pour les autres usages. Une troncature compte comme un échec.
- Raison du plafond : à 30 tok/s, 4 096 tokens font déjà ~2 min par réponse, soit la limite d'usage d'un SLM local. Le banc mesure donc la précision sous ce budget. Les éditeurs recommandent jusqu'à 32K pour Qwen, et aucune donnée publiée ne donne la longueur de réflexion des petits modèles : le pilote la mesure.
- Raison des 400 questions : à 800, la piste activée seule prendrait 80 à 100 h de plus que la piste coupée (42 à 58 h), même à 800 tokens de réflexion en moyenne. À 400, la campagne est estimée entre 105 et 140 h, et la piste détecte encore un écart de 10 points sur le score global (≥ 330).

## Composition par usage

Les effectifs sont indicatifs (hypothèse) et seront réajustés après le pilote.

| Usage | Effectif | Sources | Correction |
|---|---|---|---|
| Raisonnement (`reasoning`) | 130 | BBEH mini (460 items, Apache-2.0 / CC-BY-4.0) ; maths FR générées selon la recette VAR-MATH | correspondance exacte ; réponse numérique ; score strict : un problème n'est réussi que si toutes ses variantes le sont |
| Consignes vérifiables (`instructions`) | 130 | IFBench (300, EN, ODC-BY-1.0) ; M-IFEval FR (235, Apache-2.0) ; prompts FR maison qui réutilisent ses vérificateurs | vérificateurs IFBench et M-IFEval |
| Outils multi-tours et parallèles (`tools`) | 130 | BFCL v4 : live AST, parallèle, multi-turn ; traduction FR maison (~200 items possibles), noms de fonctions et de paramètres inchangés | AST (`ast_checker`) ; état final |
| Extraction JSON (`extraction`) | 110 | échantillon stratifié de JSONSchemaBench (MIT) ; documents FR maison à extraire | validation du schéma côté client, puis valeurs attendues |
| RAG long contexte FR (`rag`) | 110 | OneRuler FR (code MIT) : NIAH et CWE, de 8K à 32K selon la mémoire ; échantillon de PIAF (MIT ; contamination soupçonnée, Wikipédia FR étant dans les corpus de pré-entraînement) | correspondance exacte ; F1 |
| Abstention (`abstention`) | 110 | variante « aucune aiguille » de OneRuler ; irrelevance de BFCL ; questions maison | déterministe |
| Rédaction FR (`writing`) | 80 | questions maison, versionnées (non privées : le juge cloud doit les voir) | juge (`juge-et-calibration.md`) |

**Raison de l'effectif réduit en rédaction :** contenir le coût du juge.

**Puissance :** environ 115 questions par usage détectent un écart de 20 points par usage, et environ 800 par piste un écart de 10 points sur le score global. La piste activée en a moitié moins par usage : environ 57, soit la limite pour un écart de 20 points (il faut 39 à 61 questions pour une discordance ψ de 0,2 à 0,3).

## Règles sur les questions

- Chaque question porte notamment : `id`, `usage`, `group`, `unit`, `source`, `license`, `private`, `generator_seed` (pour les questions générées), `prompt_hash` et `target_hash`. Schéma complet `qb.question/1` : AD-5 du spine.
- **`group` :** les questions qui partagent un contexte (même passage RAG, même botte de foin, même gabarit mathématique, même conversation multi-tours) partagent un identifiant de groupe. Le N de puissance se compte en groupes, et le tirage de la piste activée se fait par groupes entiers.
- **`unit` :** unité de score, l'`id` par défaut. Les variantes d'un problème VAR-MATH partagent une `unit`, réussie seulement si toutes le sont.
- **Générateurs :** graine fixée et versionnée. La même graine produit les mêmes empreintes.
- **Questions privées :** elles vivent hors du dépôt public, et seule leur empreinte est versionnée.
- **Traductions de le-leadboard** (`bbh-fr`, `musr-fr`, `MATH_LVL5_fr`) : non utilisées sans relecture préalable d'un échantillon de 30 items, à cause d'anomalies observées.

## Exclusions

| Exclu | Raison |
|---|---|
| IFEval (EN) | saturé chez les SLM récents (≥ 80 % dès 2B) |
| IFEval-fr (le-leadboard) | aucune licence déclarée |
| FQuAD | non commercial, redistribution interdite |
| GSM-Symbolic | CC-BY-NC-ND : pas d'adaptation FR distribuable |
| MATH-500 tel quel | contamination de Qwen2.5 (reproduction mot pour mot) |
| MuSR | ne discrimine pas (0,33 à 0,41 de 1B à 14B) |
| BFCL non-live AST | au plafond (~88 % dès 4B) |
| BFCL web search | exige SerpAPI, donc le réseau |

## Code emprunté (copié dans le dépôt, avec la licence)

| Composant | Provenance | Note |
|---|---|---|
| Vérificateurs IFBench | `allenai/IFBench` (Apache-2.0) | dépendances : `absl-py`, `langdetect`, `nltk`, `immutabledict`, `emoji`, `syllapy`, `pydantic` ; données NLTK (`punkt`, `punkt_tab`, `stopwords`, `averaged_perceptron_tagger_eng`) téléchargées avant la campagne, `nltk.download` neutralisé dans le code copié |
| Vérificateurs M-IFEval FR | `lightblue-tech/M-IFEval` (Apache-2.0) | fichiers FR seulement, avec un registre réduit : sans spaCy, que seuls les vérificateurs espagnols chargent |
| `ast_checker.py` et `type_convertor/` de BFCL | `ShishirPatil/gorilla`, `berkeley-function-call-leaderboard` (Apache-2.0) | ne s'importe pas seul : retirer le lien vers `MODEL_CONFIG_MAPPING` |
| Générateur OneRuler | `mungg/OneRuler` (MIT) | les bottes de foin sont des livres du domaine public |
