# Jeu fixe de cas du juge de l'évaluation (story 7.2)

Douze cas inventés pour le dépôt (public : aucun document client, aucune réponse RAG réelle, rien de
`data/`). Chaque cas de `cases.json` donne une question, des extraits numérotés, la réponse d'un
assistant, ses affirmations avec le **verdict attendu** et l'extrait d'appui, et les extraits utiles.

**État : verdicts proposés, non relus.** Ils sont produits par la story 7.2, pas par un humain
(`review.status: "proposed"`, `reviewed_by: null`). Décision Q4 : la relecture revient à Anaël.

## Relire (environ 30 minutes : 12 cas, 40 verdicts)

1. Pour chaque cas de `cases.json`, lire la question, les extraits et la réponse, puis chaque entrée de
   `claims` :
   - `appuyée` : un extrait dit l'affirmation ou l'implique directement ; `support` est son numéro ;
   - `contredite` : un extrait dit le contraire ; `support` est son numéro ;
   - `non appuyée` : aucun extrait ne permet de conclure, **même si l'affirmation est vraie dans le
     monde réel** (le juge ne doit pas répondre d'après ses connaissances) ; `support` vaut `null`.
   - `useful` : les numéros des extraits qui servent à répondre à la question (`[]` : aucun).
2. Corriger ce qui est faux dans `cases.json`, puis passer `review` du cas à `"confirmed"` (rien
   changé) ou `"corrected"` (modifié).
3. Une fois les douze cas relus : `review.status` (`"confirmed"` ou `"corrected"`), `reviewed_by` et
   `reviewed_on` (date) au niveau du fichier.
4. Réenregistrer le rejeu et relire son diff : `.venv\Scripts\python -m tests.v2.eval_fixed_set record`,
   puis `.venv\Scripts\python -m pytest tests/v2/unit/test_eval_fixed_set.py -q`.
5. Mesurer l'accord du juge : `.venv\Scripts\python -m tests.v2.eval_fixed_set measure --model qwen2.5:1.5b`
   (ou `pytest tests/v2/integration/test_eval_fixed_set_ollama.py -s`). Réviser au besoin
   `minimum_agreement` (`verdict`, `useful`) à la lumière d'une mesure sur des verdicts relus.
   La garde ne passe pas si l'accord est sous `minimum_agreement` **ou** si le juge ne fait pas
   mieux qu'un juge trivial (toujours le verdict le plus fréquent du jeu ; « tous utiles » ou
   « aucun utile » pour les extraits) : la mesure le dit (« juge non informatif »). Avertissement
   par défaut, échec avec `WAVELOCALAI_JUDGE_STRICT=1`.

Cas à regarder de près (verdicts les plus discutables) : `sauvegarde-frequence` (affirmations
impliquées, non dites), `jardin-partage` (« finance » pour « prend en charge »), `frais-repas-negation`
(le plafond de 25 euros est-il « appuyé » alors qu'il vaut « au-delà » de quatre heures),
`mediatheque-pret` (la répartition quatre livres et deux disques), `chantier-fin-de-journee` (les
affirmations 9 et 10 ; seules les dix premières sont vérifiées) et `prime-naissance-sans-reponse`
(aucune affirmation : la fidélité n'est pas évaluée, jamais 0).

## Fichiers

- `cases.json` : le jeu et les attendus (le seul fichier à relire et à éditer à la main) ;
- `judge-replay.json` : les sorties du juge rejouées par le test unitaire, **écrit par
  `python -m tests.v2.eval_fixed_set record`** depuis `cases.json` (ne pas l'éditer à la main) ;
  indexées par l'empreinte de l'invite, elles font échouer le test si l'invite ou le découpage change.
