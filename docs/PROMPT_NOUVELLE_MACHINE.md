# Prompt prêt à coller pour benchmarker une nouvelle machine

Ce document contient un prompt autonome à coller dans une session Claude Code
ouverte sur une autre machine. Il ne suppose rien d'autre que le dépôt et un
accès réseau.

La procédure détaillée, elle, est dans [BENCHMARK_MULTI_MACHINE.md](BENCHMARK_MULTI_MACHINE.md).

## Le prompt

````markdown
Je veux exécuter le benchmark SLM de ce projet sur cette machine, puis publier les
résultats. Le dépôt est https://github.com/Aliquanto3/wavelocalai

Contexte à connaître avant de commencer :
- Les scripts multi-machines sont sur la branche `feat/benchmark-multi-machine`
  (PR #1). Si elle est déjà fusionnée dans `master`, utilise `master`.
- `data/` est exclu de git : n'y commite jamais rien. Les résultats partagés vont
  dans `benchmarks/results/<machine>.json`, un fichier par machine.
- La procédure complète est dans `docs/BENCHMARK_MULTI_MACHINE.md` : lis-la d'abord.

Déroulé attendu :

1. Prépare le dépôt : clone-le s'il est absent, sinon `git fetch` puis place-toi
   sur la bonne branche et mets-la à jour. Signale-moi tout travail local non
   commité avant de toucher à quoi que ce soit.

2. Prépare l'environnement : venv Python, puis installe uniquement
   `ollama codecarbon psutil python-dotenv "huggingface_hub[hf_xet]"`.
   N'installe pas tout `requirements.txt`, qui tire torch et docling pour rien.
   Vérifie qu'Ollama est présent et en version 0.30 minimum (0.34+ recommandé) :
   en dessous, les modèles récents et les GGUF en 1 bit ne se chargent pas.

3. Lance `python scripts/bench_here.py plan --label <nom-court-de-la-machine>` et
   montre-moi le résultat : matériel détecté, budget mémoire, modèles retenus et
   volume à télécharger. Choisis un label parlant, par exemple `tour-rtx4090` ou
   `pro-thinkpad`.

4. **Attends ma validation avant tout téléchargement**, et dis-moi le volume total.
   Si je suis en partage de connexion, je te donnerai un plafond. Ensuite :
   `python scripts/bench_here.py install --label <label>`

5. Lance le benchmark : `python scripts/bench_here.py run --label <label>`
   Fais-le tourner en arrière-plan et préviens-moi de l'avancement. Machine au
   repos : ne télécharge rien pendant ce temps, cela coûte jusqu'à 30 % de débit.
   Compte deux à trois minutes par modèle avec GPU, bien plus sans.

6. Exporte et publie :
   `python scripts/bench_here.py export --label <label>`
   puis crée la branche `bench/<machine_id>`, commite le seul fichier de résultats,
   pousse, et ouvre une PR avec `gh pr create`. Dans la description, indique le
   matériel, le mode (GPU ou CPU), le nombre de modèles testés et toute anomalie.

7. Termine en me donnant la comparaison avec les autres machines :
   `python scripts/merge_results.py`

Anomalies connues, à signaler sans bricoler :
- « SWAP disque détecté » : le modèle pagine, la montée en contexte s'arrête. Normal
  si la RAM est juste.
- « blocked redirect to a different host » sur un `ollama pull hf.co/...` : c'est
  prévu, le script bascule seul sur `hf download` puis `ollama create`.
- « unexpected EOF » à l'import d'un GGUF : le gabarit copié est incomplet.
- Le MoE `qwen3.6:35b-a3b` occupe 21 Go de RAM. Sur une machine à 32 Go ou moins,
  ne le lance pas : il s'est fait tuer deux fois par le système sur mon poste.

Règles de travail : demande-moi confirmation avant tout téléchargement volumineux
ou tout push. Si une mesure te paraît incohérente, dis-le plutôt que de la publier.
````

## À surveiller selon la machine

**Sans GPU.** La sélection bascule sur les paramètres *actifs* (plafond 8 milliards)
et réduit le contexte à 8K. Le run reste long : comptez plusieurs heures pour une
quinzaine de modèles. Un MoE y est souvent plus rapide qu'un modèle dense deux fois
plus petit, puisque seule une fraction des poids est active.

**VRAM mal détectée.** Sans pilote NVIDIA ou AMD, le relevé WMI de Windows est
tronqué à 4 Go et absent des cartes récentes. Le profil le signale ; forcez alors
la valeur :

```bash
python scripts/machine_profile.py --label mon-pc --vram-gb 12
```

**Espace disque.** La sélection complète représente une soixantaine de gigaoctets
sur une machine généreuse en VRAM. `plan` affiche le volume à télécharger et
l'espace libre avant toute décision.
