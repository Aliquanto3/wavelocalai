# Coquille, barre haute, états communs, simulateur

## (a) États couverts

- Barre haute : pastille Ollama (vérification, disponible, ne répond pas, état inconnu si la connexion est perdue) et son panneau (version, mémoire, modèles chargés, erreur `ollama_down`, « Réessayer ») ; interrupteur « Autoriser le cloud » (store seulement, perdu au rechargement, pied de page qui suit) ; CO₂ de session et son panneau (total, Local, Cloud, non mesurables, mis à jour à chaque `metrics`) ; menu Affichage (clair, sombre, système, projection) ; menu replié sous 1 024 px ; bandeaux « Connexion au serveur perdue, nouvelle tentative… » (après trois échecs) et « Le serveur a redémarré » avec « Recharger ».
- États communs : catalogue `#/maquette/etats` (vide, chargement lent, messages, 409 rejoint, étapes d'un run, score et « non évalué », CO₂ mesuré, estimé ou « non mesurable », cloud désactivé puis activé, garde-fou mémoire, confirmation de « Vider », validation d'email, chaque code d'erreur de `donnees/erreurs.json`).
- États globaux du panneau Scénarios : Ollama arrêté, cloud, connexion perdue, serveur redémarré, garde-fou mémoire, premier chargement lent, aucun modèle local, onglet masqué, thème, projection, vitesse.

## (b) Écarts

- Contrat d'écran : la consigne disait `render(root, ctx)` ; la maquette suit AD-20 (`mount(host, ctx)` qui rend `unmount`) et accepte `render` comme alias.
- Thème « Système » ajouté (demande de la consigne) : UX-DR2 et la story 1.8 ne prévoient que clair et sombre.
- Routes : les onze d'UX-DR4, plus `#/arene/references` (FR47, onglet « Références ») et les sous-routes `#/arene/banc/<run_id>`, `#/documents/evaluation/<run_id>`, `#/modeles/<tag>` d'EXPERIENCE.md. Dans le front définitif, tous les modules sont disponibles : aucun lien « Pas encore disponible ».
- Codes d'erreur : UX-DR16 dit `interrupted`, `errors.py` dit `generation_interrupted` ; le message de `timeout` d'`errors.py` ne cite pas le délai, 03 §3.8 le cite (« 2 min ») : la maquette le cite. Les boutons d'action sont dans `donnees/erreurs.json` (champ `buttons`) ; AD-18 les fait déduire du code par l'écran.
- `cloud_not_allowed` : texte de 03 §3.8, plus court que celui d'`errors.py`.
- Icônes : sprite de 37 symboles (19 Material Symbols Rounded d'origine, 18 tracés Material Icons ajoutés à l'intégration, à remplacer : voir icons.LICENSE.txt) ; DESIGN.md cite `leaderboard` pour l'Arène, le sprite a `swords`.
- Le panneau Scénarios, fixé en bas à droite, peut recouvrir du contenu quand il est ouvert (outil de maquette, replié par défaut).

## (c) Décisions d'Anaël (2026-10-18)

Questions tranchées ; numéros du README §6.

1. Thème « Système » dans le menu Affichage ? (A) le garder, défaut « Clair » ; (B) le garder et en faire le défaut ; (C) le retirer (UX-DR2 strict). Recommandation : A.
   **Décision n° 7** : Thème : Clair (défaut), Sombre, Système. État : déjà conforme.
2. Où placer « Références » ? (A) quatrième onglet de l'Arène (FR47) ; (B) section de Modèles ; (C) carte de l'Accueil seulement. Recommandation : A, avec la carte d'Accueil en plus.
   **Décision n° 8** : Références : quatrième onglet de l'Arène et carte sur l'Accueil. État : déjà conforme.
3. Boutons d'action des erreurs : (A) déduits du code par le front (AD-18 actuel) ; (B) champ `actions` dans l'enveloppe du serveur. Recommandation : A tant que la liste reste courte.
   **Décision n° 4** : Boutons d'action des erreurs déduits du code par le front (AD-18). État : déjà conforme.

## Note technique

Chromium et Edge bloquent les modules ES et `fetch` en `file://` : la maquette doit être servie. `ouvrir.cmd` lance `serveur.py` (port libre, 127.0.0.1, types MIME fixés : sous Windows, `python -m http.server` sert parfois `.js` en `text/plain`, ce que les modules refusent) et ouvre le navigateur. Ouverte en `file://`, `index.html` affiche la marche à suivre.
