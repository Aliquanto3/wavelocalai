# Machines cibles

## Portable — Asus TUF Gaming A17 (machine de dev principale)
- CPU : Ryzen 7 5800H, 8 coeurs / 16 threads (Zen3, AVX2, pas d'AVX-512)
- RAM : 32 Go DDR4-3200 dual channel (~40 Go/s theorique, ~14 Go/s effectifs mesures)
- GPU : RTX 3060 Laptop, 6 Go VRAM dont ~5,1 Go allouables (reserve WDDM)
- Driver NVIDIA 572.70, plafond CUDA 12.8
- Disques : C: 475 Go / D: 931 Go — modeles sur D:\ia\models
- OS : Windows 11

## Tour — machine secondaire
- CPU : Ryzen 5 7600
- RAM : 32 Go DDR5-6000 CL36 (~2,4x la bande passante du portable)
- GPU : RTX 3050, 8 Go VRAM
- Disque : Samsung 990 PRO 1 To NVMe
- OS : Windows 11

## Implication de conception
La bande passante memoire determine le debit de generation, la VRAM determine
quels modeles chargent. Les metriques runtime ne sont PAS reproductibles entre
ces deux machines : chaque mesure doit embarquer sa fiche materiel.