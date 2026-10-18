# Résultats slm-quality-bench

Instantané des résultats de benchmark publiés par le dépôt public
[`Aliquanto3/slm-quality-bench`](https://github.com/Aliquanto3/slm-quality-bench),
qui publie une release par campagne. wavelocalai ne produit plus de résultats de benchmark.

- `slm-quality-results.json` : l'asset de la dernière release, octets inchangés, validé contre le
  JSON Schema publié au même tag.
- `SOURCE.json` : provenance (tag, URL de l'asset, sha256 de l'asset et du schéma, date de récupération).

**Ne jamais éditer ces fichiers à la main.** Ils sont écrits par `scripts/sync_slm_results.py`, lancé
chaque lundi par le workflow `.github/workflows/sync-slm-results.yml`, qui ouvre une PR
`bench/synchro-slm-<version>` quand une nouvelle version est publiée.
Une PR ouverte est mise à jour si l'asset est republié sous le même tag ; une PR fermée sans
fusion n'est pas reproposée tant que sa branche existe (la supprimer pour la reproposer). Le
workflow échoue si le dépôt source devient introuvable.

Relancer la synchro à la demande :

```bash
gh workflow run sync-slm-results.yml
```

En local (sans rien écrire) : `python scripts/sync_slm_results.py --check`.
