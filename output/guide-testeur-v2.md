# WaveLocalAI v2 : guide du testeur

Version testée : **2.0.0a8** (préversion, branche `master`). Durée conseillée : 45 à 60 min.

WaveLocalAI fait tourner de petits modèles de langage **sur le poste** (Ollama), les compare et mesure ce que chaque réponse coûte en temps, en énergie et en carbone.

## Avant de commencer
- Ollama lancé, avec au moins deux petits modèles (ex. `qwen2.5:1.5b`, `llama3.2:3b`).
- Lancement : `uv sync`, puis `uv run wavelocalai-v2`. Le navigateur s'ouvre sur `http://127.0.0.1:8502`.
- **N'indexez aucun document confidentiel** : prenez un PDF ou un DOCX public.

## Parcours à tester, dans l'ordre

| # | Écran | À faire | Ce qu'on attend |
|---|---|---|---|
| 1 | **Accueil** | Ouvrir l'application, lire l'état du poste. | L'état d'Ollama, la mémoire et les modèles s'affichent en quelques secondes. |
| 2 | **Modèles** | Installer un petit modèle, ouvrir sa fiche, puis le décharger. | Le poste dit avant l'installation si le modèle tient en mémoire. La fiche explique le débit. |
| 3 | **Arène, Chat** | Poser une question simple, puis une question longue. | La réponse s'affiche au fil de l'eau, avec son coût (temps, énergie, CO₂). |
| 4 | **Arène, comparaison** | Comparer 2 à 4 modèles sur la même question. | Un résumé dit lequel conclut le mieux, chiffres à l'appui. Un modèle qui tourne en boucle est arrêté, avec la raison. On voit le juge travailler. |
| 5 | **Arène, banc d'essai et évaluation** | Lancer un scénario, puis une évaluation de qualité. | Les étapes sont visibles et le verdict de format est lisible. |
| 6 | **Documents** | Installer le modèle de représentation si demandé, indexer un document, l'interroger. | La réponse cite sa source et on peut ouvrir l'extrait. Le bouton du reranker fonctionne. |
| 7 | **Agents** | Confier une tâche à un agent seul, puis à une équipe. | Chaque étape s'affiche. **Aucun e-mail ne part sans validation explicite.** |
| 8 | **Sobriété** | Regarder la session en direct, l'historique, puis ouvrir une nouvelle session. | Les compteurs bougent pendant une réponse. L'historique se conserve. |
| 9 | **Cloud** (facultatif) | Seulement avec une clé d'API. | La comparaison local / cloud est claire. |

## Points à regarder en particulier
La nouvelle mise en page date de l'Epic 9 et vos retours sont les bienvenus sur :
- la **lisibilité** en projection (vidéoprojecteur, zoom à 150 %) et sur un écran étroit ;
- la **largeur de l'écran Évaluation** et un éventuel **doublon « SCÉNARIO »** dans le Banc d'essai ;
- l'écran **Modèles** avec vos vrais modèles (noms longs, nombreux modèles) ;
- la **clarté des textes** : un débutant comprend-il ce que chaque chiffre veut dire ?

## Blocages connus
- **Réponse de plus d'une minute** : le modèle est trop gros pour le poste. Prenez-en un plus petit.
- **« Ollama ne répond pas » alors qu'il tourne** : relancez Ollama, puis rechargez la page.
- **Écran blanc ou « Cet écran n'a pas pu être chargé »** : rechargez (F5) et notez l'écran et l'action.

## Comment remonter un retour
Une ligne par écart, dans ce format :

> **Écran** · **Action faite** · **Attendu** · **Obtenu** · **Gravité** (bloquant / gênant / cosmétique) · capture si possible

Les **remarques d'ergonomie** comptent autant que les bugs (« je n'ai pas compris où cliquer » est un bon retour). Les captures ne doivent pas montrer le contenu d'un document client.
