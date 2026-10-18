# Accueil (`#/`)

## (a) États couverts

Scénarios : `nominal`, `premier-chargement` (squelettes), `ollama-arrete` (« Indisponible », marche à suivre, « Réessayer », liens actifs), `ollama-arrete-cloud` (démo : « Aucun modèle local disponible » et modèles cloud proposés), `aucun-modele-local`, `cloud-autorise` (carte Mode en Cloud), `connexion-perdue` (Système « Inconnu »), `memoire-haute`, `onglet-masque` (cartes figées), `suivre-demo-recommandee` (étape du Flow 1). Résumés des modules chargés derrière un squelette, CO₂ de session en direct.

## (b) Écarts

- `h1` « Accueil » (03 §3.9 : nom du module, comme la branche feat/v2-accueil) ; EXPERIENCE.md place le titre « WaveLocalAI » en tête.
- Libellés des liens : « Assistant documentaire », « Agents autonomes », « Sobriété et matériel » (maquette 03 §3.5) alors que le menu dit « Documents », « Agents », « Sobriété » ; EXPERIENCE.md veut un nom unique partout.
- Carte « Références » (FR47) ajoutée aux modules, avec l'icône de l'Arène (DESIGN.md : icône jamais partagée).
- Carte Mode : « N appels cloud dans cette session » (maquette 03), compté sur les runs cloud de la session ; aucune story ne définit ce compteur.

## (c) Questions pour Anaël

1. Titre : (A) « Accueil » ; (B) « WaveLocalAI » ; (C) « WaveLocalAI » en `h1`, « Accueil » dans l'onglet du navigateur. Recommandation : A (cohérence avec les autres écrans).
2. Noms des modules sur l'Accueil : (A) noms longs (03) ; (B) noms courts du menu ; (C) court en titre, long en sous-titre. Recommandation : C.
3. « Lancer une comparaison » sans modèle local prêt : (A) actif, l'Arène dit quoi faire ; (B) désactivé avec la raison. Recommandation : A (03 : « les liens restent actifs »).
