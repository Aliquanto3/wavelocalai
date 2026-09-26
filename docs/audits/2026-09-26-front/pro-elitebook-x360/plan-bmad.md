# Plan d'implémentation des correctifs (format BMAD)

> **Statut :** brouillon à fusionner avec l'audit de l'autre machine avant toute implémentation.
> **Source :** [`rapport.md`](rapport.md). Les identifiants F-, U- et N- y sont définis.
> **Format :** tickets conteneurs de BMAD (Requirements à identifiants stables, Outcome, Done when, Boundaries, Breakdown), vérifié sur [docs.bmad-method.org](https://docs.bmad-method.org/) le 2026-09-26.

## 0. Comment s'en servir

BMAD n'est pas installé dans ce repo. Ce document ne remplace pas ses fichiers générés : c'est l'**entrée** à lui donner. Parcours proposé, d'après la doc « Start in an Existing Codebase » :

1. **Fusionner** ce rapport avec celui de l'autre machine (voir §7 du rapport) et ajuster les `covers:` ci-dessous.
2. **Installer BMAD** en suivant [la doc officielle](https://docs.bmad-method.org/).
3. **`bmad-project-context`** : utile ici, car le repo n'a ni `AGENTS.md` ni `CLAUDE.md`. Il pourra y consigner les conventions de la section « Contraintes communes ».
4. **`bmad-spec`**, avec le rapport fusionné et ce plan en entrée : il produit `spec-<slug>.md`.
5. **`bmad-preview-ticketing`** : initiative, puis epics et entrées, à partir des Breakdown ci-dessous.
6. **`bmad-build`** entrée par entrée, dans l'ordre des `blocked_by`, puis **`bmad-code-review`**.
7. **`bmad-retrospective`** à la fin de chaque epic.

**Choix du chemin de planification :**

- Les epics A et B relèvent du chemin **epic-sized** : un résultat, plusieurs sessions de build.
- L'ensemble compte trois epics, ce qui touche le chemin **project-sized**. Les contrats partagés existent pourtant déjà (`docs/ARCHITECTURE.md`, `docs/FEATURES_GUIDE.md`), et la section U du rapport tient lieu de contrat UX léger. Je ne recommande donc pas de nouveau PRD.

**Points de vigilance sur le ticketing BMAD :**

- `bmad-preview-ticketing` est en préversion, avec des bugs ouverts au 2026-09-26.
- Le build n'écrit pas le statut du ticket ([#2936](https://github.com/bmad-code-org/BMAD-METHOD/issues/2936)) : le suivre à la main.
- La spec est toujours écrite dans `{output_folder}/specs` ([#2933](https://github.com/bmad-code-org/BMAD-METHOD/issues/2933)).

## Contraintes communes (Boundaries de l'initiative)

- **v1 seulement.** La v2 (`wavelocalai-v2`) n'est pas touchée.
- **La mesure des benchmarks ne change pas.** `benchmarks/` et le code de mesure de débit restent tels quels, pour ne pas invalider les résultats publiés en `b36cb8c`.
- **Même version de Streamlit** (1.52.1). La montée de version est hors périmètre ; F-10 la prépare seulement.
- **Données réelles protégées.** Aucun test ne touche à la collection Chroma réelle (`data/chroma`) : les tests utilisent une collection dédiée.
- **Conventions :** textes d'interface en français, pas de nouvelle dépendance Python sans justification dans la PR.

---

## Initiative : `initiative-front-v1-fiable`

**Outcome :** le front v1 montre des chiffres justes, fait ce qu'il annonce et reste sur la machine. Il devient présentable en démo client.

**Requirements**

| ID | Exigence | Couvre |
|---|---|---|
| I-R1 | Toute valeur carbone affichée est dans l'unité annoncée et cohérente avec le CSV de CodeCarbon | F-01, F-02, F-11 |
| I-R2 | Toute action annoncée comme réussie a réellement eu lieu, et rien de ce que l'utilisateur saisit ou choisit n'est perdu sans prévenir | F-03, F-04, F-06, F-12, F-13 |
| I-R3 | Par défaut, rien n'est exposé ni envoyé hors de la machine | F-05, F-07 |
| I-R4 | L'interface est cohérente et lisible (nom, icône, couleur, état du mode cloud) | U-01 à U-08, F-08, F-10 |

**Done when :** les epics A et B sont clos par leur rétrospective. La décision sur l'epic C est consignée.

**Breakdown**

- 01 epic — Mesures et fonctions annoncées fiables; covers: I-R1, I-R2, I-R3
- 02 epic — Lisibilité et identité visuelle; blocked_by: 01; covers: I-R4
- 03 epic — Fonctionnalités de démonstration; blocked_by: 01; covers: N-01, N-02, N-03

L'epic 02 attend l'epic 01 parce qu'ils touchent les mêmes fichiers : les faire en parallèle multiplierait les conflits.

---

## Epic A : `epic-mesures-fiables`

**Outcome :** le Cockpit, la RAG et l'agent Solo disent vrai. L'app n'écoute que sur la machine. Un parcours e2e le vérifie à chaque changement.

**Requirements**

| ID | Exigence | Source |
|---|---|---|
| A-R1 | Les émissions de session du Cockpit sont affichées dans l'unité annoncée ; l'écart avec la ligne CSV correspondante est ≤ 5 % | F-01 |
| A-R2 | Le suivi et l'historique utilisent un seul fichier d'émissions ; une session de l'interface apparaît dans le graphique | F-02 |
| A-R3 | « Indexer maintenant » ajoute les fichiers à Chroma et le compteur augmente ; un échec affiche une erreur, jamais un succès | F-03 |
| A-R4 | La réponse finale de l'agent Solo reste dans l'historique après un rerun, avec son badge CO₂ | F-04 |
| A-R5 | Le serveur écoute sur `localhost` par défaut ; l'ouverture au réseau est un choix explicite et documenté | F-05 |
| A-R6 | Le reranker sélectionné est appliqué, ou la liste est retirée de l'interface | F-06 |
| A-R7 | Le modèle présélectionné est un modèle local quand il en existe un | F-07 |
| A-R8 | Un combat d'Arena ne peut pas démarrer avec moins de 2 modèles | F-09 |
| A-R9 | L'origine des 112 W de CodeCarbon est établie, et la méthodologie corrigée si nécessaire | F-11 |
| A-R10 | Le modèle choisi dans l'agent Solo survit à un changement d'architecture | F-12 |
| A-R11 | Quand le garde-fou RAM bloque, la demande reste dans l'historique ou dans le champ, et le besoin estimé est expliqué | F-13 |

**Done when :**

- `node e2e.js --with-upload` passe toutes ses étapes contre une collection Chroma de test.
- La conversion g → kg est couverte par un test unitaire.
- `docs/METHODOLOGIE_CARBONE.md` reflète la conclusion du spike 10.

**Boundaries :**

- Pas de refonte visuelle : l'epic B s'en charge.
- L'epic ne change pas la façon dont CodeCarbon mesure. Il corrige l'affichage, et documente la mesure, sauf si le spike 10 conclut à une erreur de configuration.

**Breakdown**

- 01 story — Parcours e2e en non-régression, avec collection Chroma de test; covers: N-04
  Verify: `node e2e.js --skip-arena` donne OK sur 0, 2, 3, 5, 6 et 9, et KO sur 1 et 8, avec le message F-01 / F-04 attendu.
- 02 bug — Unité des émissions de session dans le Cockpit; blocked_by: 01; covers: A-R1
  Verify: l'étape e2e `1-socle` passe ; test unitaire de `get_co2_equivalencies` en kg.
- 03 bug — Un seul fichier d'émissions pour le suivi et l'historique; blocked_by: 02; covers: A-R2
  Verify: une session arrêtée dans le Cockpit apparaît dans le graphique après rafraîchissement.
- 04 bug — Ingestion RAG réelle depuis l'upload; blocked_by: 01; covers: A-R3
  Verify: l'étape e2e `7-rag-upload` passe ; `sample_doc.md` est retrouvé par la question « Quel est le mot de code du projet Zephyr ? ».
- 05 bug — Persistance de la réponse et du CO₂ de l'agent Solo; blocked_by: 01; covers: A-R4
  Verify: l'étape e2e `8-agent-solo` passe ; le badge CO₂ est visible sous la réponse.
- 06 story — `.streamlit/config.toml` avec `server.address = "localhost"`; covers: A-R5
  Verify: le démarrage n'annonce plus de « Network URL » ni d'« External URL » ; le README explique comment ouvrir l'accès au réseau.
- 07 bug — Reranker appliqué ou retiré; covers: A-R6
  Verify: avec un reranker choisi, l'ordre des sources change sur une question de test (ou la liste n'existe plus).
- 08 bug — Modèle local présélectionné; covers: A-R7
  Verify: cloud activé, le chat et la RAG présélectionnent un modèle 💻.
- 09 bug — Garde à 2 modèles dans l'Arena; covers: A-R8
  Verify: le bouton FIGHT est désactivé avec 0 ou 1 modèle.
- 10 spike — Puissance CPU mesurée par CodeCarbon sur portable Windows; covers: A-R9
  Verify: note versée dans `docs/METHODOLOGIE_CARBONE.md`, avec le mode de suivi réel de CodeCarbon et une mesure comparée.
- 11 bug — Modèle de l'agent Solo persistant; blocked_by: 05; covers: A-R10
  Verify: dans l'étape e2e `8-agent-solo`, le modèle choisi est toujours affiché après l'aller-retour Solo → Crew → Solo.
- 12 bug — Demande conservée et besoin expliqué quand la RAM manque; blocked_by: 05; covers: A-R11
  Verify: avec un modèle trop gros pour la RAM libre, la question reste visible et le message détaille le calcul du besoin.

L'entrée 01 est la *tracer bullet* : elle transforme les KO du rapport en tests qui guident les entrées 02, 04 et 05. Les entrées 06 à 10 sont indépendantes et peuvent être prises dans n'importe quel ordre. Les entrées 11 et 12 touchent `solo.py`, comme la 05, et passent donc après elle.

---

## Epic B : `epic-lisibilite`

**Outcome :** un visiteur identifie chaque module, l'état local ou cloud, et les actions principales sans explication.

**Requirements**

| ID | Exigence | Source |
|---|---|---|
| B-R1 | L'API `width=` remplace `use_container_width` partout ; aucun avertissement de dépréciation au démarrage | F-10 |
| B-R2 | Un thème Wavestone (primaire `#451DC7`) est appliqué par configuration, sans CSS injecté pour les couleurs ; la barre d'outils est minimale | U-01, U-05 |
| B-R3 | Chaque module a un seul nom et une seule icône, les mêmes dans la navigation, l'accueil et le titre | U-02, U-03 |
| B-R4 | Le mode cloud est réglé par un seul contrôle global, et son état est visible sur toutes les pages | U-04 |
| B-R5 | Les indicateurs de l'accueil et du Cockpit reflètent un état mesuré (Ollama joignable, modèles, chunks, accélérateur réel), et la version est lue depuis `pyproject.toml` | F-08 |
| B-R6 | L'Arena affiche les noms complets et un graphique à l'échelle honnête | U-06 |
| B-R7 | L'Arena prévient quand le juge est trop petit et propose par défaut le plus gros modèle local | U-07 |
| B-R8 | Les pages lentes à charger l'annoncent | U-08 |

**Done when :**

- Le parcours e2e de l'epic A passe toujours, avec des sélecteurs mis à jour si les libellés changent.
- Les captures avant/après des 5 pages sont jointes à la PR.

**Boundaries :**

- On reste dans Streamlit, sans composant React personnalisé.
- Aucune nouvelle page : elles relèvent de l'epic C.

**Breakdown**

- 01 story — Migration `use_container_width` vers `width`; covers: B-R1
  Verify: `grep use_container_width src/` ne renvoie rien ; les logs de démarrage sont propres.
- 02 story — Thème et barre d'outils dans `.streamlit/config.toml`; blocked_by: 01; covers: B-R2
  Verify: plus aucun bouton primaire rouge ; l'écran vide de la RAG reste lisible en thème clair.
- 03 story — Navigation `st.navigation` avec noms et icônes uniques; blocked_by: 01; covers: B-R3
  Verify: les noms de la barre latérale, de l'accueil et des titres de page correspondent un à un.
- 04 story — Contrôle cloud global unique; blocked_by: 03; covers: B-R4
  Verify: un seul `st.toggle` cloud dans `src/app` ; l'état est visible sur les 5 pages.
- 05 story — Indicateurs mesurés et version dynamique; covers: B-R5
  Verify: Ollama arrêté, l'accueil affiche un état dégradé ; en CPU seul, le Cockpit n'affiche pas « Actif ».
- 06 story — Lisibilité de l'Arena; covers: B-R6
  Verify: capture de l'Arena avec deux modèles aux noms longs : ni troncature ni étiquette hors du graphique.
- 07 story — Garde-fou sur le juge de l'Arena; blocked_by: 06; covers: B-R7
  Verify: avec un juge 1B, un avertissement s'affiche ; le juge par défaut est le plus gros modèle local.
- 08 story — Retour visuel au premier chargement; covers: B-R8
  Verify: le premier chargement d'Inférence affiche un indicateur explicite.

---

## Epic C : `epic-demo` (statut : draft)

**Décision préalable :** d'après les notes du projet, la v1 est devenue une référence depuis le lancement de la v2. Ces fonctionnalités ont peut-être plus de valeur dans la v2. L'entrée 01 tranche avant tout build.

**Requirements**

| ID | Exigence | Source |
|---|---|---|
| C-R1 | Une page compare les résultats de `benchmarks/results/*.json` par machine et par modèle (t/s, gCO₂ pour 1 000 tokens, qualité) | N-01 |
| C-R2 | La gestion des modèles signale ceux qui dépassent la RAM libre | N-02 |
| C-R3 | Une session s'exporte en Markdown (questions, modèles, t/s, CO₂) | N-03 |

**Breakdown**

- 01 spike — v1 ou v2 pour les fonctionnalités de démo; covers: C-R1, C-R2, C-R3
  Verify: décision écrite dans ce fichier, avec sa raison.
- 02 story — Page « Résultats de benchmark »; blocked_by: 01; covers: C-R1
- 03 story — Compatibilité modèle / RAM libre; blocked_by: 01; covers: C-R2
- 04 story — Export de session; blocked_by: 01; covers: C-R3
