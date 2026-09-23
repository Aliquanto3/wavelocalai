# Guide pas à pas : benchmarker les SLM sur votre machine

Ce guide s'adresse à une personne qui exécute le benchmark **elle-même**, sans
assistant. Il ne suppose aucune connaissance du projet. Comptez **30 minutes**
d'installation, puis une à quatre heures de mesures selon la machine, pendant
lesquelles vous n'avez rien à faire.

À la fin, vous aurez produit un fichier de résultats comparable à ceux des autres
machines, et ouvert une *pull request* pour le partager.

- Vous cherchez la version courte ? [BENCHMARK_MULTI_MACHINE.md](BENCHMARK_MULTI_MACHINE.md)
- Vous utilisez Claude Code ? [PROMPT_NOUVELLE_MACHINE.md](PROMPT_NOUVELLE_MACHINE.md)
- Vous voulez comprendre ce qui est mesuré ? [../scripts/BENCHMARK.md](../scripts/BENCHMARK.md)

---

## Sommaire

1. [Ce qu'il faut avant de commencer](#1-ce-quil-faut-avant-de-commencer)
2. [Installer les outils](#2-installer-les-outils)
3. [Récupérer le projet](#3-récupérer-le-projet)
4. [Préparer l'environnement Python](#4-préparer-lenvironnement-python)
5. [Découvrir ce que votre machine peut faire tourner](#5-découvrir-ce-que-votre-machine-peut-faire-tourner)
6. [Télécharger les modèles](#6-télécharger-les-modèles)
7. [Lancer les mesures](#7-lancer-les-mesures)
8. [Lire les résultats](#8-lire-les-résultats)
9. [Publier vos résultats](#9-publier-vos-résultats)
10. [Comparer avec les autres machines](#10-comparer-avec-les-autres-machines)
11. [Optionnel : la campagne « au mieux »](#11-optionnel--la-campagne-au-mieux)
12. [Problèmes courants](#12-problèmes-courants)
13. [Questions fréquentes](#13-questions-fréquentes)

---

## 1. Ce qu'il faut avant de commencer

| Besoin | Minimum | Confortable |
|--------|---------|-------------|
| Système | Windows 10/11, macOS 12+, ou Linux | — |
| RAM | 8 Go | 16 Go et plus |
| Carte graphique | aucune (mode CPU) | 6 Go de VRAM et plus |
| Espace disque | 20 Go | 80 Go |
| Réseau | 10 Go de téléchargement | connexion fixe |

**Sans carte graphique, tout fonctionne**, simplement plus lentement : le script
s'en rend compte seul et adapte sa sélection de modèles.

⚠️ **Évitez le partage de connexion mobile.** Les modèles pèsent de 0,7 à 7 Go
pièce. Sur un forfait limité, lisez d'abord l'étape 5, qui annonce le volume exact
avant tout téléchargement.

---

## 2. Installer les outils

Trois logiciels sont nécessaires : **Git**, **Python** et **Ollama**.

### Windows

1. **Git** : téléchargez [git-scm.com/download/win](https://git-scm.com/download/win),
   installez avec les options par défaut.
2. **Python 3.11 ou plus** : [python.org/downloads](https://www.python.org/downloads/).
   ⚠️ Cochez **« Add python.exe to PATH »** sur le premier écran de l'installeur.
3. **Ollama** : [ollama.com/download](https://ollama.com/download). Une icône de lama
   apparaît dans la barre des tâches après l'installation.

### macOS

```bash
brew install git python ollama
```

### Linux (Debian/Ubuntu)

```bash
sudo apt update && sudo apt install -y git python3 python3-venv
curl -fsSL https://ollama.com/install.sh | sh
```

### Vérifier que tout répond

Ouvrez un terminal — sur Windows, **PowerShell** (touche Windows, tapez
« PowerShell ») — et lancez :

```bash
git --version
python --version
ollama --version
```

Vous devez obtenir trois numéros de version. Pour Ollama, **0.30 est le minimum** et
0.34 ou plus est recommandé : en dessous, les modèles récents et les fichiers
quantifiés en 1 bit ne se chargent pas.

> Sur Windows, si `python --version` ouvre le Microsoft Store, c'est que Python
> n'est pas dans le PATH. Réinstallez-le en cochant la case mentionnée plus haut.

---

## 3. Récupérer le projet

Placez-vous dans un dossier de travail, puis :

```bash
git clone https://github.com/Aliquanto3/wavelocalai.git
cd wavelocalai
git checkout feat/benchmark-multi-machine
```

> La dernière ligne bascule sur la branche qui contient les scripts multi-machines.
> Si elle renvoie `error: pathspec ... did not match`, c'est qu'elle a été fusionnée :
> restez simplement sur `master`.

Si le projet est déjà présent sur la machine, mettez-le à jour :

```bash
cd wavelocalai
git fetch origin
git status          # vérifiez qu'aucune modification locale ne va être perdue
git pull
```

---

## 4. Préparer l'environnement Python

Un « environnement virtuel » isole les bibliothèques du projet du reste de votre
machine.

```bash
python -m venv .venv
```

Installez ensuite les cinq bibliothèques nécessaires. **Windows :**

```powershell
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install ollama codecarbon psutil python-dotenv "huggingface_hub[hf_xet]"
```

**macOS / Linux :**

```bash
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install ollama codecarbon psutil python-dotenv "huggingface_hub[hf_xet]"
```

> **Pourquoi ne pas faire `pip install -r requirements.txt` ?** Ce fichier installe
> toute l'application (PyTorch, Docling, CrewAI), soit plusieurs gigaoctets inutiles
> pour le benchmark.

> **Pourquoi écrire `.venv\Scripts\python` au lieu d'activer l'environnement ?**
> En entreprise, la politique de sécurité Windows bloque souvent les scripts
> d'activation. Invoquer directement l'exécutable contourne le problème. C'est aussi
> ce que recommande [TROUBLESHOOT.md](TROUBLESHOOT.md).

Dans la suite du guide, **remplacez `python` par `.venv\Scripts\python`** (Windows)
ou `.venv/bin/python` (macOS/Linux).

---

## 5. Découvrir ce que votre machine peut faire tourner

```powershell
.venv\Scripts\python scripts\bench_here.py plan --label mon-pc
```

Choisissez une étiquette courte et parlante à la place de `mon-pc` : `tour-rtx4090`,
`portable-pro`, `mac-m3`. Elle identifiera vos résultats.

Vous obtenez d'abord votre matériel :

```
Machine       : portable-pro-22601cd4
OS            : Windows 11
CPU           : AMD Ryzen 7 5800H (8 cœurs physiques)
RAM           : 31.4 Go
GPU           : NVIDIA GeForce RTX 3060 Laptop GPU — 6.0 Go de VRAM
Ollama        : 0.34.2
Disque libre  : 179.5 Go

Mode retenu   : GPU
Budget modèle : 5.1 Go
```

Le **budget modèle** est le poids maximal qu'un modèle peut occuper tout en restant
entièrement sur la carte graphique. Au-delà, il déborde sur le processeur et devient
trois à cinq fois plus lent.

Puis la liste des modèles retenus, et surtout, en bas :

```
À télécharger : 16.6 Go — disque libre : 179.5 Go
```

**C'est le moment de décider.** Si le volume vous paraît trop élevé, passez à
l'étape suivante en ne prenant qu'une partie des modèles.

---

## 6. Télécharger les modèles

```powershell
.venv\Scripts\python scripts\bench_here.py install --label mon-pc
```

Le script liste ce qui manque, annonce le volume, puis **demande confirmation**.
Répondez `o` pour lancer.

Comptez 10 à 40 minutes selon votre connexion. Vous verrez défiler des barres de
progression Ollama.

### Ne prendre qu'une partie des modèles

Pour tester d'abord quelques modèles, installez-les à la main. Exemple avec trois
modèles légers (environ 5 Go au total) :

```bash
ollama pull gemma4:e2b-it-qat
ollama pull qwen3.5:4b
ollama pull granite4.2:3b
```

Le benchmark ne testera que les modèles réellement installés.

### Les modèles hors bibliothèque Ollama

Certains modèles (Bonsai en 1 bit, quantifications Unsloth, MiniCPM5) ne sont pas
dans la bibliothèque officielle. Le script les télécharge depuis Hugging Face puis
les importe. C'est automatique, mais plus lent, et un message
`blocked redirect to a different host` peut s'afficher : **c'est normal**, le script
bascule seul sur la méthode alternative.

---

## 7. Lancer les mesures

Fermez les applications lourdes — navigateur avec cinquante onglets, jeux, machines
virtuelles. **Une machine occupée fausse les mesures jusqu'à 30 %.**

```powershell
.venv\Scripts\python scripts\bench_here.py run --label mon-pc
```

Le script affiche, modèle par modèle :

```
[3/14] 🔬 Gemma 4 E2B (QAT)
   🔧 Tests fonctionnels...
      Mode raisonnement : désactivé
      Tools: 100% (4/4) détail={'simple_call': True, ...}
      JSON: valides=1.0, schémas respectés=1.0
      Abstention: 100%
      Raisonnement: 86% par catégorie={'logic': 1.0, 'arithmetic': 1.0, ...}
      Instructions: 100% échecs=[]
   📊 Tests de montée en contexte...
      ⚡ Contexte 2048...
      ✅ OK | 109.3 tok/s | TTFT 44ms | RAM 0.001GB
      ⚡ Contexte 4096...
         Needle-in-haystack: ✅
```

Ce que signifient ces lignes :

| Ligne | Sens |
|-------|------|
| `Tools: 100% (4/4)` | le modèle appelle correctement les outils, et s'abstient quand il ne faut pas |
| `Raisonnement: 86%` | 12 bonnes réponses sur 14 questions de logique, calcul et pièges |
| `Instructions: 100%` | les 8 contraintes de format sont respectées |
| `109.3 tok/s` | vitesse de génération, hors chargement du modèle |
| `TTFT 44ms` | délai avant le premier mot, modèle déjà chargé |
| `Needle-in-haystack: ✅` | le modèle retrouve une information cachée dans un long texte |
| `↪️ Report CPU probable` | le modèle déborde sur le processeur : normal s'il est gros |
| `📉 SWAP disque détecté` | la mémoire est saturée, la montée en contexte s'arrête là |

**Durée attendue :** deux à trois minutes par modèle avec une carte graphique, cinq
à quinze minutes sans. Vous pouvez laisser tourner et revenir plus tard.

Pour interrompre proprement : `Ctrl+C`. Les modèles déjà mesurés sont conservés ;
relancez la même commande en ajoutant `--skip-tested` pour reprendre où vous en étiez.

---

## 8. Lire les résultats

Les mesures s'accumulent dans `data/models.json`. Pour un tableau lisible :

```powershell
.venv\Scripts\python scripts\benchmark_slm.py --report-only
```

Cela écrit `data/benchmark_report.md`, ouvrable dans n'importe quel éditeur de texte
ou sur GitHub.

Ce qu'il faut regarder en priorité :

- **La part en VRAM (`gpu_offload_pct`)**. À 100 %, le modèle est entièrement sur la
  carte graphique et rapide. En dessous, il déborde et ralentit fortement.
- **La vitesse de génération**. Au-dessus de 30 tok/s, la lecture est confortable ;
  en dessous de 15, l'attente devient pénible.
- **Les scores de qualité**, entre 0 et 1. Un écart inférieur à 0,15 n'est pas
  significatif : sur 14 questions, deux réponses d'écart peuvent relever du hasard.

---

## 9. Publier vos résultats

### Générer le fichier

```powershell
.venv\Scripts\python scripts\bench_here.py export --label mon-pc
```

Cela crée `benchmarks/results/mon-pc-<identifiant>.json`, contenant votre profil
matériel, vos mesures et la version exacte du benchmark utilisée.

> **Vie privée :** l'identifiant est un condensé du matériel, pas votre nom
> d'utilisateur ni le nom de votre machine. Aucune donnée personnelle n'est incluse.

### Envoyer sur GitHub

```bash
git checkout -b bench/mon-pc
git add benchmarks/results/
git commit -m "Bench: mon-pc"
git push -u origin bench/mon-pc
```

> Si `git push` demande un mot de passe, GitHub n'accepte plus celui du compte :
> créez un *personal access token* dans Settings → Developer settings → Tokens, et
> utilisez-le comme mot de passe.

### Ouvrir la pull request, sans ligne de commande

1. Rendez-vous sur https://github.com/Aliquanto3/wavelocalai
2. Un bandeau jaune propose **« Compare & pull request »** : cliquez dessus.
3. Titre : `Bench: mon-pc`. Dans la description, indiquez votre matériel (GPU, VRAM,
   RAM), le nombre de modèles testés, et toute anomalie rencontrée.
4. Cliquez sur **« Create pull request »**.

C'est terminé. Vos résultats sont partagés.

---

## 10. Comparer avec les autres machines

Une fois plusieurs fichiers de résultats présents :

```powershell
.venv\Scripts\python scripts\merge_results.py
.venv\Scripts\python scripts\merge_results.py --csv
```

Le tableau affiche un modèle par ligne et une machine par colonne. Le script
**avertit** si deux machines n'ont pas utilisé la même version du benchmark : dans ce
cas, les scores de qualité ne sont pas comparables.

---

## 11. Optionnel : la campagne « au mieux »

La campagne standard impose à tous les modèles une température de 0 et désactive
leur mode raisonnement, pour que la comparaison soit stricte. Ce choix pénalise les
modèles conçus pour raisonner.

Une seconde campagne les mesure dans leurs conditions optimales :

```powershell
.venv\Scripts\python scripts\benchmark_slm.py --params vendor --thinking on --max-context 8192 --force-tool-test
```

Elle écrit sous une clé séparée (`benchmark_stats_vendor`) et **n'écrase pas** la
campagne standard. Comptez environ deux fois plus de temps, le raisonnement
produisant beaucoup plus de texte.

---

## 12. Problèmes courants

| Message ou symptôme | Cause | Solution |
|---|---|---|
| `ollama: command not found` | Ollama absent du PATH | Redémarrez le terminal ; sous Windows, vérifiez l'icône dans la barre des tâches |
| `Ollama non détecté. Lancez 'ollama serve'` | le service ne tourne pas | Lancez `ollama serve` dans un second terminal |
| `blocked redirect to a different host` | Ollama refuse la redirection Hugging Face | Aucune action : le script bascule seul sur `hf download` |
| `Error: unexpected EOF` à l'import | gabarit de discussion incomplet | Signalez-le : le modèle a besoin d'un gabarit dédié |
| `📉 SWAP disque détecté` | mémoire saturée | Normal sur un gros modèle ; fermez des applications ou ignorez |
| Le processus est tué pendant un gros modèle | RAM insuffisante | Évitez les modèles MoE (23 Go) en dessous de 32 Go de RAM |
| `VRAM non fiable (relevé WMI)` | pilote graphique absent | Forcez la valeur : `scripts\machine_profile.py --label mon-pc --vram-gb 12` |
| Téléchargement interrompu qui reprend à zéro | l'outil Hugging Face perd les fichiers partiels | Relancez : les fichiers déjà complets sont conservés |
| `running scripts is disabled on this system` | politique PowerShell | N'activez pas l'environnement : utilisez `.venv\Scripts\python` directement |
| Vitesses anormalement basses | machine occupée | Fermez les applications lourdes et recommencez |

---

## 13. Questions fréquentes

**Combien de temps cela prend-il en tout ?**
Trente minutes d'installation, de 10 à 40 minutes de téléchargement, puis une à
quatre heures de mesures automatiques.

**Puis-je utiliser mon ordinateur pendant les mesures ?**
Pour de la bureautique légère, oui, mais les vitesses mesurées seront un peu
pessimistes. Évitez les tâches lourdes.

**Cela envoie-t-il des données quelque part ?**
Non. Tout tourne en local. Seuls les téléchargements de modèles sortent, et le
fichier de résultats que *vous* choisissez de publier.

**Combien d'espace disque cela occupe-t-il ?**
Les modèles vont de 0,7 à 7 Go. L'étape 5 annonce le total avant toute décision.
Pour libérer de la place ensuite : `ollama rm <nom-du-modèle>`.

**Puis-je ne tester que trois ou quatre modèles ?**
Oui, voyez la fin de l'étape 6. Les résultats restent comparables, sur ces modèles.

**Que faire si un modèle échoue ?**
Le script passe au suivant et le signale. Mentionnez-le dans la description de votre
pull request.

**Mon ordinateur n'a pas de carte graphique, est-ce utile ?**
Oui, et c'est même précieux : aucune mesure sans GPU n'existe encore dans ce
projet. Le script adapte la sélection et réduit la taille du contexte.
