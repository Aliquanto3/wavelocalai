# Benchmarker plusieurs machines et comparer les résultats

Le benchmark SLM mesure ce qui dépend du poste : ce modèle-là, dans cette
quantification-là, tient-il en mémoire, et à quelle vitesse ? La réponse change
d'une machine à l'autre. Ce document décrit comment l'exécuter ailleurs et
rassembler les résultats au même endroit.

## Où vivent les fichiers

| Chemin | Contenu | Suivi par git |
|--------|---------|---------------|
| `config/models_catalog.json` | Catalogue partagé : tags, tailles, empreinte mesurée de référence | ✅ |
| `benchmarks/results/<machine>.json` | Résultats d'**une** machine | ✅ |
| `benchmarks/comparison.csv` | Fusion de toutes les machines | ✅ |
| `data/models.json` | Copie de travail locale (catalogue + mesures en cours) | ❌ |
| `data/logs/benchmarks/` | Logs détaillés | ❌ |

Un fichier de résultats par machine : deux PC peuvent publier le même jour sans
provoquer le moindre conflit de fusion.

## Sur une nouvelle machine

### 1. Préparer

```bash
git clone <url> && cd wavelocalai
python -m venv .venv
.venv/Scripts/python -m pip install ollama codecarbon psutil python-dotenv huggingface_hub[hf_xet]
# Ollama 0.30 minimum (0.34+ recommandé) : https://ollama.com/download
```

### 2. Savoir quoi tester

```bash
python scripts/bench_here.py plan --label tour-rtx4090
```

Le script détecte CPU, RAM, GPU et VRAM, en déduit un budget mémoire, puis
filtre le catalogue. Trois règles :

- **Avec GPU** : un modèle est retenu si son empreinte mesurée tient dans
  `VRAM × 0,85`. Entre une et 1,6 fois le budget, il est gardé mais annoncé
  comme « débordement CPU partiel » — utile pour mesurer le coût de ce
  débordement.
- **Sans GPU** : c'est la bande passante RAM qui limite. Le script écarte les
  modèles de plus de 8 milliards de paramètres **actifs** et réduit le contexte
  à 8K. Un MoE (peu de paramètres actifs) y est souvent plus rapide qu'un dense
  deux fois plus petit.
- **MoE** : jamais dimensionné sur la VRAM. Ollama place les experts en RAM ;
  c'est donc la RAM totale qui décide.

Si la VRAM est mal détectée (pilote absent, relevé WMI), forcez-la :
`python scripts/machine_profile.py --label mon-pc --vram-gb 12`.

### 3. Installer ce qui manque

```bash
python scripts/bench_here.py install --label tour-rtx4090
```

Compare `ollama list` à la sélection, annonce le volume à télécharger, demande
confirmation, puis récupère les modèles. Les modèles absents de la bibliothèque
Ollama (Bonsai, quantifications Unsloth) passent par un repli automatique :
téléchargement du GGUF via `hf download`, puis `ollama create` avec le gabarit
d'un modèle officiel voisin — Ollama 0.34 refusant la redirection du CDN
Hugging Face (`blocked redirect to a different host`).

### 4. Mesurer

```bash
python scripts/bench_here.py run --label tour-rtx4090
```

Machine au repos : un téléchargement en arrière-plan coûte jusqu'à 30 % de
débit. Comptez deux à trois minutes par modèle avec GPU, davantage sans.

### 5. Publier

```bash
python scripts/bench_here.py export --label tour-rtx4090
git checkout -b bench/tour-rtx4090-<hash>
git add benchmarks/results/tour-rtx4090-<hash>.json
git commit -m "Bench: tour-rtx4090"
git push -u origin bench/tour-rtx4090-<hash>
gh pr create --fill
```

L'export embarque le profil matériel **et le SHA git de `benchmark_slm.py`**.
Sans cette empreinte, comparer deux machines n'a pas de sens : une correction de
notation suffit à déplacer les scores.

## Comparer

```bash
python scripts/merge_results.py            # tableau par modèle et par machine
python scripts/merge_results.py --csv      # benchmarks/comparison.csv
python scripts/merge_results.py --metric gpu_offload_pct
```

Le script avertit explicitement quand deux machines n'ont pas tourné avec la
même version du benchmark, plutôt que d'aligner des chiffres trompeurs.

## Ce qui se compare, et ce qui ne se compare pas

| Métrique | Comparable entre machines ? |
|----------|------------------------------|
| Raisonnement, instructions, outils, JSON | Oui, à version identique : le modèle ne change pas |
| Génération (tok/s), lecture du prompt | Oui, c'est précisément l'objet de la comparaison |
| Empreinte mémoire, % en VRAM | Oui, mais dépend du contexte testé |
| Empreinte carbone | Non directement : elle dépend du mix électrique (`WAVELOCAL_COUNTRY_ISO`) et du matériel |
| Latence ressentie | Oui, mais sensible à la charge de la machine |

## Mettre le catalogue à jour

Après une campagne qui ajoute des modèles ou affine les empreintes :

```bash
python scripts/build_catalog.py     # data/models.json -> config/models_catalog.json
```

Les empreintes de référence proviennent d'une seule machine (indiquée dans
`_reference_machine`). Elles servent à dimensionner, pas à comparer.
