# 🌍 Méthodologie d'Évaluation Carbone (GreenOps)

> **Version :** 2.0 (Calibration Avancée)
> **Sources :** ACV Mistral AI (2025) & Régression EcoLogits.

Ce document détaille comment **WaveLocalAI** calcule l'empreinte carbone, en distinguant la mesure locale de l'estimation API.

## 1. Modèles Locaux (Mesure Physique)
L'évaluation repose sur une mesure électrique directe via des sondes matérielles.

* **Outil :** CodeCarbon (Sondes Intel RAPL / Nvidia NVML).
* **Formule :** `Impact = Énergie_Consommée (kWh) × Intensité_Carbone_Locale (g/kWh)`
* **Périmètre :** **Scope 2** (Usage électrique uniquement). La fabrication de votre PC n'est pas incluse.

---

## 2. API Mistral (Estimation Calibrée)
Pour l'API, nous utilisons une formule théorique (EcoLogits) que nous avons **calibrée** pour qu'elle corresponde exactement aux données officielles de l'Analyse de Cycle de Vie (ACV) de Mistral.

### A. La Formule Énergétique (EcoLogits)
La consommation d'énergie est estimée par régression linéaire en fonction de la taille du modèle :

$$E_{Wh} = N_{tokens} \times (\alpha \cdot P_{actifs} + \beta)$$

* **$\alpha$** ($8.91 \times 10^{-5}$) : Coût énergétique dynamique par milliard de paramètres.
* **$\beta$** ($1.43 \times 10^{-3}$) : Coût énergétique statique par token.
* **$P_{actifs}$** : Nombre de paramètres actifs du modèle (ex: 123 pour Large, 24 pour Small).

### B. La Calibration Carbone (Vérité Terrain)
Nous avons calculé un **"Mix Énergétique Implicite"** en inversant la formule à partir du point de référence ACV de Mistral :
* **Référence :** Mistral Large 2 ([123 Mrds Params](https://mistral.ai/fr/news/mistral-large-2407)) pour 400 tokens génère **[1,14 gCO₂e](https://mistral.ai/fr/news/our-contribution-to-a-global-environmental-standard-for-ai)**.

Ce mix implicite (~0,24 gCO₂e/Wh) agrège tout ce que la mesure locale ignore :
* Le PUE du datacenter (refroidissement).
* **L'amortissement de la fabrication des serveurs (Scope 3).**

### C. Calcul Final
Pour n'importe quel autre modèle Mistral générant $Y$ tokens :

$$Impact_{gCO2} = \text{Mix}_{implicite} \times \left[ Y \times (\alpha \cdot P_{modele} + \beta) \right]$$

De manière complète :

#### 📐 Formule de l'Impact Carbone (API Mistral)

L'impact carbone d'une requête est calculé en croisant la modélisation énergétique théorique ([EcoLogits](https://genai-impact.github.io/)) avec la calibration réelle issue de l'ACV Mistral.

$$
\text{Impact}_{\text{gCO}_2} = \underbrace{\left( \frac{1,14}{400 \times (\alpha \cdot 123 + \beta)} \right)}_{\text{Mix Énergétique Implicite (Calibration)}} \times \underbrace{\left( YYY \times (\alpha \cdot P_{actif} + \beta) \right)}_{\text{Consommation Énergétique Cible}}
$$

#### Légende des variables :

* **$YYY$** : Nombre de tokens générés en sortie (*Output Tokens*).
* **$P_{actif}$** : Nombre de paramètres actifs du modèle cible en Milliards (ex: `24` pour Mistral Small, `123` pour Mistral Large 2).
* **$1,14$** : Émissions de référence en gCO₂e (Scope 3 complet) pour Mistral Large 2.
* **$400$** : Nombre de tokens de référence pour ce score de 1,14g.
* **$123$** : Nombre de paramètres actifs du modèle de référence (Mistral Large 2).

#### Constantes de régression (EcoLogits) :
* **$\alpha$** = $8,91 \times 10^{-5}$ (Pente dynamique)
* **$\beta$** = $1,43 \times 10^{-3}$ (Overhead statique)

---

### 🧠 Explication de la logique

1.  **Le Facteur de Calibration (Gauche) :**
    Nous calculons l'énergie théorique du modèle de référence (Mistral Large, 123B) pour 400 tokens. En divisant l'impact réel (1,14g) par cette énergie théorique, nous obtenons un **"Mix Énergétique Implicite"** (en gCO₂e/Wh). Ce facteur capture l'efficacité réelle du datacenter, le PUE et l'amortissement du matériel (Scope 3).

2.  **L'Estimation Cible (Droite) :**
    Nous calculons l'énergie théorique de votre requête spécifique (pour $YYY$ tokens sur un modèle de taille $P_{actif}$) et nous la multiplions par le facteur de calibration obtenu ci-dessus.


---

## 3. Biais de Comparaison
⚠️ **Note importante pour l'interprétation :**

Les chiffres **API** incluent la fabrication du matériel (Scope 3), tandis que les chiffres **Locaux** ne reflètent que la facture électrique immédiate (Scope 2).
C'est pourquoi l'impact API apparaîtra systématiquement plus élevé : il est **plus complet et plus réaliste** sur le plan environnemental global.

## Sources

Mistral - [Notre contribution pour la création d'un standard environnemental mondial pour l'IA](https://mistral.ai/fr/news/our-contribution-to-a-global-environmental-standard-for-ai)

EcoLogits - [Environmental Impacts of LLM Inference](https://ecologits.ai/0.4/methodology/llm_inference/)
