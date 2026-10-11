"""Environnements d'outils simulés (AD-11) : noyau pur et déterministe, sans horloge, fichier
ni réseau. Le runner (``generation/``) les exécute pendant la génération, le correcteur
(``grading/``) les rejoue depuis ``output`` ; ``make_env`` (``envs/registry.py``) en est la
seule porte d'entrée."""
