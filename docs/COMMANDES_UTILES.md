# Commandes utiles pour publier une mise à jour et en commencer une autre

## Passer les tests
```bash
.venv\Scripts\python -m pytest tests/
```

## Commit et push

### Vérifier l'état des fichiers à commit
```bash
git status
```
### Ajouter tous les fichiers modifiés au commit
```bash
git add .
```

### Déclencher les tests et soumettre un message de commit
```bash
git commit -m "message de commit"
```
__REMARQUE__ : il faut parfois refaire "git add ." après un "git commit", car ce dernier risque de modifier automatiquement certains fichiers via les hooks.

### Push les changements sur GitHub
```bash
git push
```

## Exporter le code en un format lisible pour un LLM
```bash
.venv\Scripts\python llm_review/prepare_review.py
```
=> Voir résultats dans */llm_review/exports/*.

## Mettre à jour les dépendances
```bash
.venv\Scripts\python -m pip install -r requirements.txt
```

## Lancer l'application
```bash
.venv\Scripts\python -m streamlit run src/app/Accueil.py
```
