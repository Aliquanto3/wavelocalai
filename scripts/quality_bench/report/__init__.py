"""Rapports de campagne (AD-6, AD-17) : lecture et contrôles des entrées, agrégats statistiques
(par ``stats/``), exports versionnés en liste blanche sous ``benchmarks/quality/<c>/`` ;
rapport du pilote (``pilot``, CAP-8) sous ``campaigns/<c>/``, hors dépôt.

N'importe que ``stats/``, ``questions/schema.py`` et ``common/`` : jamais ``generation/``,
``grading/``, ``judge/``, ``ollama/``, ``questions/importers/`` ni une bibliothèque réseau. Les
phases amont se lisent par fichiers."""
