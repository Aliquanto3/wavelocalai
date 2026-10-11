"""Génération sur les deux pistes (AD-7, AD-9, AD-11, AD-13, AD-14) : préflight des modèles
(``preflight.py``), conversation et outils (``conversation.py``), boucle ordonnée, essais,
pannes et chauffe (``runner.py``), et commande ``generate`` (``commands.py``), seule à écrire
``campaigns/<c>/manifest.json``, ``generation.jsonl`` et ``warmups.jsonl``.

N'importe jamais ``grading/``, ``judge/``, ``stats/``, ``report/`` ni ``questions/importers/`` :
les phases se lisent par fichiers (spine, sens des dépendances)."""
