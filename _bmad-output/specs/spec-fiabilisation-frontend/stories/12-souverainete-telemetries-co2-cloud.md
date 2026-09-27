---
title: 'Souveraineté et CO₂ : télémétries coupées, CO₂ cloud juste'
type: 'bugfix'
created: '2026-09-27'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Sur poste-rtx3060, l'évaluation RAG a résolu `t.explodinggradients.com` : Ragas 0.4.3 envoie sa télémétrie tant que `RAGAS_DO_NOT_TRACK` n'est pas défini, et l'app ne coupe aucune télémétrie hors des tests (Chroma comprise). Dans la Discussion, `chat.py:228` passe le libellé du sélecteur (« Nom · Cloud ») à `_calculate_metrics` : la fiche du modèle n'est jamais trouvée et un modèle cloud reçoit la formule de CO₂ locale.

**Approach:** Un module `src/core` sans `streamlit` définit une fois pour toutes les variables qui coupent les télémétries (Ragas, Chroma, CrewAI, OpenTelemetry, Hugging Face, LangSmith, `DO_NOT_TRACK`), sans écraser une valeur déjà définie ; l'app l'appelle au démarrage, avant tout import de `src`, et `eval_engine.py` avant l'import de Ragas. Ne rien ajouter à `APP_ENV` de `tests/e2e/conftest.py` : la garde réseau e2e doit continuer de vérifier l'app elle-même. `src/core/config.py` n'est pas modifié (importé par le benchmark). Dans la Discussion, le CO₂ est calculé à partir du tag (nom du catalogue) et de l'origine réelle du modèle (celle du badge).

</frozen-after-approval>

## Implementation Notes

- `src/core/telemetry.py` (nouveau) : `TELEMETRY_OPT_OUTS` et `disable_telemetry()`, qui lit d'abord le .env (même fichier que `config.py`) puis pose chaque variable par `setdefault`. Variables vérifiées dans les paquets installés : `RAGAS_DO_NOT_TRACK` (Ragas 0.4.3 ignore `DO_NOT_TRACK`), `ANONYMIZED_TELEMETRY` (Chroma), `CREWAI_DISABLE_TELEMETRY`, `OTEL_SDK_DISABLED`, `HF_HUB_DISABLE_TELEMETRY`, LangSmith. LiteLLM n'est pas installé.
- Appelée par `Accueil.py` avant tout import de `src`, par `eval_engine.py` avant l'import de Ragas, et par `tests/e2e/launch_app.py` avant ses imports (même ordre que l'app).
- `tests/e2e/conftest.py` : les variables de télémétrie sont retirées d'`APP_ENV` ; la garde réseau vérifie désormais l'app, et un test unitaire empêche de les y remettre.
- `chat.py` : `_calculate_metrics(metrics, tag, is_cloud)` ; cloud hors catalogue → CO₂ inconnu (« — »), le total de session l'ignore.
- `config.py` non modifié (importé par le benchmark).
- Vérifié : `tests/e2e/test_documents.py` 3/3 (plus de DNS `t.explodinggradients.com`) ; sans le correctif, `ragas._analytics.do_not_track()` vaut False.

## Review Triage Log

Revue Blind Hunter (13 constats) :

- `.env` lu après `disable_telemetry()`, réactivation impossible — medium, corrigé (lecture du .env d'abord, test).
- Cloud hors catalogue affiché « 0 mgCO₂ » — medium, corrigé (None, total de session tolérant, test).
- `_calculate_metrics` recopie `answer_carbon_mg` — medium, différé (factorisation de la règle de CO₂, question ouverte 8).
- Quatre autres onglets ignorent l'origine réelle — medium, différé (antérieur à cette story).
- Le test ne vérifie pas l'appel — low, corrigé (test AST de l'appel).
- 123B codé en dur — false : la valeur vient du catalogue de test de `tests/app/conftest.py`, comme dans les tests existants.
- `APP_ENV` masque les opt-outs de l'app — medium, corrigé (variables retirées, test anti-dérive).
- Seuls Ragas et Chroma sont prouvés — low, rejeté (les autres variables sont vérifiées dans le code installé ; un test par bibliothèque coûterait plus qu'il ne protège).
- API privée de Ragas, échec au lieu d'un skip — low, corrigé (`importorskip`).
- `import src…` non vu par le test AST — low, corrigé.
- Autres points d'entrée sans opt-out — medium, différé (hors de l'app).
- Documentation utilisateur absente — low, différé (touche AGENTS.md).
- Deux listes qui dérivent — corrigé avec le point `APP_ENV`.

