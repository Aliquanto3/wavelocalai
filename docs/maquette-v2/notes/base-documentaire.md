# Base documentaire (`#/documents/base`)

Fichiers : `js/screens/base-documentaire.js`, `css/screens/base-documentaire.css`, `i18n/screens/base-documentaire.fr.json`, `donnees/base-documentaire.json`, `donnees/flux/base-documentaire-ingestion.json` (stub : la liste d'événements d'un lot est construite par l'écran et passée par `vars.events`, le nombre de fichiers étant libre). Parties communes : voir notes/discussion.md. La maquette ne lit jamais un fichier choisi : seuls son nom et sa taille servent.

## (a) États couverts (scénarios)

`base-vide` (Flow 2), `base-remplie` (12 documents, 340 extraits), `chargement-liste` (squelette, zone de dépôt déjà là), `import-un-document` (Flow 2 : « 14 extraits ajoutés depuis 1 document »), `import-plusieurs-fichiers`, `envoi-en-cours` (Envoi 60 %), `import-en-cours` (Vectorisation, Annuler), `chargement-modele-representation` (8 à 26 s), `import-avec-echec` (PDF protégé, détails techniques, compteur inchangé), `format-refuse`, `deja-present`, `annulation`, `rejoint-409`, `erreur-ollama-arrete`, `garde-fou-memoire`, `document-en-indexation`, `filtrer`, `filtre-sans-resultat`, `tri-par-extraits`, `suppression-document`, `vider-confirmation` (« 340 extraits de 12 documents seront supprimés. »), `vider-annule` (Flow 2), `vider-confirme`, `reglages-ouverts`, `reglages-enregistres`, `changer-embedding` (« Vider » d'abord), `reprise-au-retour`, `connexion-perdue`, `serveur-redemarre`.

## (b) Écarts (non tranchés)

- Échec par fichier : le contrat ne dit pas comment il voyage dans un run qui continue. La maquette ajoute `error` (enveloppe `ingest_failed`) à `ingest_progress`. Même question pour un doublon (`skipped: "duplicate"`).
- « Annuler » par fichier (UX-DR22) : le contrat n'a qu'un run `ingest` par lot ; annuler une ligne arrête les fichiers restants du lot (les prêts restent). Le libellé de chaque ligne ne le dit pas.
- Un document `failed` existe en base (4.1) : la maquette ne l'affiche que dans la ligne d'import, pas dans le tableau, et il disparaît au rechargement.
- Suppression d'un document sans confirmation (EXPERIENCE : confirmation seulement pour « Vider » et l'email), message de résultat au même verbe.
- Boutons Supprimer et Vider désactivés pendant un import, avec la raison, au lieu d'un 409 affiché (le contrat prévoit le 409).
- Pas de code d'erreur au catalogue pour : changer d'embedding avec une base non vide (message d'avertissement local), `expected_count` périmé (non maquetté), 409 d'un document à run actif. Le message d'action de `ram_guard` parle de « question » : réécrit localement pour l'import.
- Le tri est fait avec des boutons d'en-tête et `aria-sort` (pas de `wl-data-table` commun) ; sous 768 px la colonne « Modèle de représentation » est masquée et le tableau défile dans son conteneur.
- Réglages (`details` replié) : représentation, taille des extraits, nombre d'extraits, stratégie par défaut, reclassement indisponible avec lien vers Modèles. La stratégie et le nombre d'extraits sont repris par la Discussion.
- Icônes manquantes dans `icons.svg` (fichier partagé non modifié) : upload, delete, folder ; les boutons sont textuels.
- Bug du simulateur commun (coupure de connexion pendant la fin d'un run) : voir notes/discussion.md.

## (c) Questions pour Anaël

1. Supprimer un document : (A) sans confirmation (maquette, EXPERIENCE) ; (B) avec `wl-confirm-dialog` comme « Vider » ; (C) sans confirmation mais avec « Annuler » dans le message. Recommandation : B (irréversible, comme Vider).
2. Annuler un import : (A) un bouton par ligne qui arrête tout le lot (maquette) ; (B) un seul « Annuler l'import » au-dessus des lignes ; (C) un run par fichier côté serveur. Recommandation : B.
3. Documents en échec : (A) seulement dans la ligne d'import ; (B) aussi dans le tableau, statut « Échec » et Supprimer. Recommandation : B.
