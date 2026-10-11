## 4. Enseignements transversaux

Ces cinq constats n'apparaissent qu'en croisant les trois dimensions.

1. **La contamination se règle dans les items, pas dans le harnais.**
   - Aucun framework n'offre de protection contre la contamination (section 2).
   - Les jeux statiques connus sont saturés ou contaminés [D1-2][D1-28].
   - Les jeux qui résistent sont des **générateurs** : OneRuler (MIT, français inclus) [D1-35], RULER [D1-33], et la recette VAR-MATH, à réimplémenter [D1-29].
   - Il faut donc investir dans les générateurs et les items privés, pas dans le harnais.
2. **Les jeux en français seul manquent d'items pour détecter un écart de 10 points.**
   - M-IFEval FR ne compte que 235 prompts [D1-5], sous les 249 à 329 items requis pour 10 points dès que les modèles divergent sur 30 % des questions ou plus (section 3.2).
   - Utilisé seul, son écart minimal détectable est d'environ 12 à 15 points.
   - Pour détecter 10 points, il faut soit le combiner à IFBench (EN, 300) dans une même piste d'instructions, soit l'étendre avec des prompts maison qui réutilisent ses vérificateurs.
3. **Les items groupés réduisent le N effectif.**
   - Les tâches multi-turn de BFCL, les questions OneRuler sur une même botte de foin, les questions PIAF sur un même passage et les variantes d'un même gabarit mathématique partagent leur contexte.
   - L'erreur-type groupée peut alors atteindre environ 3 fois l'erreur naïve [D3-3].
   - Le format de résultat doit porter un identifiant de groupe par item [D2-9][D3-3], et le N par piste se compte en **groupes** plutôt qu'en items.
4. **Fiabilité de la mesure et validité statistique sont liées.**
   - McNemar à un seul tirage (K = 1) suppose qu'un modèle répond toujours de la même façon à un item.
   - Or `format` peut être ignoré avec `think` [D2-21], et un réglage censé être déterministe varie d'une exécution à l'autre [D3-7].
   - Il faut donc mesurer le taux de réponses qui changent sur un sous-ensemble rejoué. S'il n'est pas négligeable devant la part de questions discordantes entre modèles, il faut passer à K > 1 tirages et à l'erreur-type appariée sur les moyennes [D3-3].
5. **Items privés et dépôt public.** Des items **privés** anti-contamination publiés dans un dépôt public perdent leur intérêt. Ils doivent vivre hors du dépôt, avec seulement leur empreinte versionnée. Pour les exclusions de licence, voir 1.3.

## 5. Recommandations

Chaque recommandation est rattachée à son consommateur (`bmad-spec`, puis architecture du banc) et à sa base de confiance.

| # | Recommandation | Pour | Base de confiance |
|---|---|---|---|
| R1 | **Harnais maison sur `/api/chat`**, sans dépendance à lm-eval, Inspect ou bfcl-eval. Copier dans le dépôt : vérificateurs IFBench (Apache-2.0), vérificateurs M-IFEval FR (Apache-2.0, plus 2 modèles spaCy), `ast_checker` et `type_convertor` de BFCL (Apache-2.0) | spec, contraintes ; architecture | haute [D2-7][D2-13][D2-15][D2-16][D1-6] |
| R2 | **Composition des pistes** (proposition, à arbitrer dans `bmad-spec`) : voir le tableau ci-dessous | spec, périmètre | moyenne : notes de la matrice 1.2 issues du jugement de l'auteur |
| R3 | **Au moins ≈ 330 items, ou groupes indépendants, par piste** pour détecter un écart de 10 points ; une sous-piste de 85 suffit pour un écart de 20 points. Mesurer la part de questions où les modèles divergent sur un pilote, puis réajuster le N | spec, exigences non fonctionnelles | haute [D3-1][D3-3][D3-20] |
| R4 | **Statistiques** : McNemar exact par paire ; différence avec erreur-type appariée et IC à 95 % ; erreurs-types groupées par identifiant de groupe ; Holm sur les k−1 comparaisons au meneur (`method='holm'`) ; rang approché à la Chatbot Arena dans le rapport | spec, sorties ; architecture, module d'analyse | haute [D3-3][D3-9][D3-10][D3-11][D3-17] |
| R5 | **Format de résultat par item**, en JSONL, une ligne par item, écrite sitôt l'item terminé : id, groupe, piste, empreinte du prompt, réponse brute, réponse parsée, score, `epoch`, `think`, backend, version d'Ollama, `seed`, `num_ctx`, tokens et énergie. Ce format sert aussi la reprise après arrêt | spec, données ; architecture | haute pour le contenu [D2-5][D2-9] |
| R6 | **Hygiène Ollama** : épingler la version ; `OLLAMA_NUM_PARALLEL=1` ; requête de chauffe jetée ; `seed`, `temperature` et `num_ctx` fixés à chaque requête ; lire les capacités via `/api/show` avant d'envoyer `tools` ou `think` ; valider chaque sortie JSON côté client ; contrôle de stabilité sur un sous-ensemble rejoué | spec, contraintes ; procédure de campagne | moyenne : issues en partie anciennes ou à source unique [D2-18][D2-19][D2-21][D2-23] |
| R7 | **Items privés et générés hors du dépôt public**, seule leur empreinte étant versionnée. Générateurs (OneRuler, maths à la VAR-MATH) avec graine fixée et versionnée | spec, contraintes ; architecture | moyenne [D1-29][D1-35] |
| R8 | **Élimination adaptative : ne pas l'implémenter en v1.** Le budget de 5 à 6 jours suffit. Si on en a besoin plus tard, prendre O'Brien-Fleming ou Hoeffding races avec un ordre d'items figé, après une simulation de l'erreur de type I | spec, hors périmètre | faible : synthèse non publiée [D3-12][D3-13] |

**R2, composition proposée des pistes** (effectifs indicatifs, à confronter au budget de 5 à 6 jours) :

| Piste | Sources | Correction |
|---|---|---|
| Suivi d'instructions | IFBench 300 (EN) [D1-2] + M-IFEval FR 235 [D1-5] ; IFEval seulement pour les modèles < 2B, ou abandonné | vérificateurs |
| Appel d'outils | BFCL v4 : live AST, multi-turn, irrelevance (pour l'abstention) ; ni non-live AST, saturé, ni web search, qui exige le réseau [D1-12][D1-14]. Plus une traduction FR maison d'environ 200 items, noms de fonctions et de paramètres inchangés | AST, état |
| Extraction JSON | échantillon stratifié de JSONSchemaBench (test) [D1-36] + documents FR maison à extraire | validation de schéma + valeurs attendues |
| RAG / contexte long FR | OneRuler FR (NIAH, recherche d'une aiguille dans une botte de foin, dont la variante « aucune aiguille » ; CWE, extraction des mots les plus fréquents) à 8K–32K selon la mémoire disponible [D1-34] + échantillon de PIAF [D1-37] | correspondance exacte, F1 |
| Raisonnement | BBEH mini 460 [D1-24] + maths FR générées (recette VAR-MATH, score strict) [D1-29] | correspondance exacte, réponse numérique |
| Abstention | variante « aucune aiguille » de OneRuler [D1-34] + irrelevance de BFCL [D1-11] + items maison | déterministe |
| Rédaction FR | juge cloud (décision déjà prise ; hors du périmètre de cette recherche) | juge |

## 6. Questions ouvertes

| Question | Pourquoi c'est important | Pour y répondre |
|---|---|---|
| Quelle part de questions discordantes (ψ) entre deux SLM du catalogue ? | elle fixe le N réel entre 155 et 330 | pilote de 2 modèles sur 100 à 200 items par piste |
| Ollama 0.40.x est-il stable d'une exécution à l'autre sur tour-rtx3050 ? | conditionne le choix K = 1 | rejouer 10 fois un sous-ensemble, mesurer la part de réponses qui changent |
| Effectifs BFCL v4 live ; la catégorie memory s'exécute-t-elle hors ligne ? | dimensionner la piste outils | lire `BFCL_v4_live_*.json` ; tester l'embedder hors ligne |
| Scores OneRuler en français des modèles de 7–8B ; 32K tient-il en mémoire ? | éviter un plancher et un dépassement mémoire | figure 17 de l'article ; essai local |
| Les traductions de le-leadboard (bbh-fr, musr-fr, MATH_LVL5_fr) sont-elles fiables ? | possibles items FR gratuits | relire un échantillon de 30 items par jeu |
| Licence propre des gabarits GitHub de GSM-Symbolic | possible source de gabarits | lire le LICENSE de `apple/ml-gsm-symbolic` |
| Erreur de type I de l'élimination adaptative | seulement si R8 est rouvert | simulation Monte-Carlo |
| Statistiques d'accord entre juge cloud et étiquettes humaines | hors périmètre ici, nécessaire pour la piste rédaction | recherche dédiée ou pilote de calibration (déjà prévu) |
| Les vérificateurs d'IFBench fonctionnent-ils en français ? | seulement si IFBench est traduit | lire `instructions_util.py` |
