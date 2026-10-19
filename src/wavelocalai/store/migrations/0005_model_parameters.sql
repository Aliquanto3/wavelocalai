-- Paramètres publiés par Ollama pour un modèle (`parameters` de `/api/show`, texte brut) : la
-- créativité par défaut du modèle (`temperature`) en est lue (D-12, AD-15). `NULL` : les détails
-- n'ont pas été lus (lignes écrites avant cette migration, relues au prochain rafraîchissement) ;
-- chaîne vide : lus, aucun paramètre.
ALTER TABLE model_facts ADD COLUMN parameters TEXT;
