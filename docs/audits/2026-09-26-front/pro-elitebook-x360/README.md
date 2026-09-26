# Audit front : pro-elitebook-x360 (2026-09-26)

Test fonctionnel du front Streamlit v1 sur `pro-elitebook-x360`, avec des recommandations et un plan de correctifs. Un audit du même type est mené sur une autre machine, dans un dossier voisin. Les deux seront fusionnés avant l'implémentation.

| Fichier | Contenu |
|---|---|
| [`rapport.md`](rapport.md) | Méthode, résultats par module, 13 défauts (F-01 à F-13), 8 recommandations d'interface (U-01 à U-08) et 4 fonctionnalités (N-01 à N-04) |
| [`plan-bmad.md`](plan-bmad.md) | Plan d'implémentation au format BMAD : initiative, 3 epics, entrées avec `blocked_by`, `covers` et `Verify:` |
| [`e2e/`](e2e/) | Parcours Playwright rejouable, avec une assertion par comportement attendu |
| [`captures/`](captures/) | Captures d'écran de ce passage. Celles de la RAG ne sont pas publiées : la réponse du modèle y résume les documents indexés, et le repo est public |

## Rejouer le parcours

Il faut Ollama démarré, les modèles Gemma 3 1B, Granite 4.0 350M et Qwen 3.5 0.8B, ainsi que Node.js et Google Chrome.

```powershell
# 1. Lancer l'app (localhost uniquement)
.venv\Scripts\python -m streamlit run src/app/Accueil.py --server.headless true --server.address localhost

# 2. Dans un autre terminal
cd docs\audits\2026-09-26-front\pro-elitebook-x360\e2e
$env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1"
npm install
node e2e.js --skip-arena
```

- **Autres modèles :** `$env:MODEL_CHAT`, `$env:MODEL_SMALL` et `$env:MODEL_AGENT` prennent le libellé affiché dans l'app, par exemple `"Llama 3.2 3B"`.
- **`--with-upload` :** ajoute l'étape d'indexation RAG. Tant que F-03 n'est pas corrigé, elle n'écrit rien. Une fois corrigé, elle indexera `sample_doc.md` dans la collection Chroma active.
- **Sorties :** les captures vont dans `e2e/out/`. Le code de sortie vaut 0 seulement si toutes les étapes passent.
