# Baseline validee — Qwen3.6-35B-A3B sur le portable

## Runtime
llama.cpp b10537, build CUDA 12.4
Modele : unsloth/Qwen3.6-35B-A3B-GGUF, fichier UD-IQ4_XS (17,7 Go / 16,50 GiB)

## Commande retenue
llama-server -m <gguf> -ngl 99 --n-cpu-moe 37 -c 32768 -fa on -t 8 --jinja -np 1
  --load-mode none --temp 1.0 --top-p 0.95 --top-k 20 --min-p 0
  --presence-penalty 1.5 --host 127.0.0.1 --port 8080

## Resultats
- Generation : ~26 tok/s
- Prefill : ~280 tok/s
- VRAM a --n-cpu-moe 40 : 3161 MiB / 6144

## Contraintes du modele
- 40 couches exactement : --n-cpu-moe 40 = tous les experts en RAM (plafond)
- Architecture hybride Gated DeltaNet + Gated Attention : 10 couches sur 40
  seulement ont un cache KV, donc le contexte long coute peu de VRAM
- Experts ~0,43 Go par couche en IQ4_XS

## Pieges runtime
- --load-mode none obligatoire avec --n-cpu-moe (sinon mmap page depuis le disque)
- --min-p 0 explicite (defaut llama.cpp = 0.1)
- --jinja obligatoire (sinon balisage <think> casse)
- -np 1 (le serveur alloue 4 slots par defaut)

## Methode de bench validee
llama-bench avec -r 5 minimum : les ecarts-types atteignent +/-1,4 tok/s,
aucune conclusion sous 10 % d'ecart n'est fiable.

## Pistes explorees et ecartees
- Sweep --n-cpu-moe 40->35 : +8 % seulement, dans le bruit
- Sweep threads 4/6/7/8 : 8 est optimal, les autres valeurs ne changent rien
- Comparatif IQ4_XS vs UD-Q3_K_XL : +6,9 % explique par la taille, pas le format
- MTP / decodage speculatif : supporte (PR #22673, --spec-type draft-mtp) mais
  rendement negatif documente sur Ampere grand public + cible Q4 + MoE 35B-A3B