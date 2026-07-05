---
zotero_item_key: DH67KGHN
doi: 10.1609/aaai.v39i8.32879
year: 2025
generated_at: 2026-07-04T10:09:10+00:00
---

# MambaPro: Multi-Modal Object Re-identification with Mamba Aggregation and Synergistic Prompt

## Metadata
- Zotero item: zotero://select/library/items/DH67KGHN
- DOI: 10.1609/aaai.v39i8.32879
- Year/date: 2025
- Venue: Proceedings of the AAAI Conference on Artificial Intelligence
- Authors: Yuhao Wang, Xuehu Liu, Tianyu Yan, Yang Liu, Aihua Zheng, Pingping Zhang, Huchuan Lu
- PDF: D:\Users\pbrii\AppData\Local\zotero\storage\GNBANLVL\Wang 等 - 2025 - MambaPro Multi-Modal Object Re-identification with Mamba Aggregation and Synergistic Prompt.pdf

## Why It Matters For This Project
- Contains modern model components relevant to current ReID exploration.

## One-Pass Reading Card
- Research problem: TODO
- Core idea: TODO
- Architecture/module changes: TODO
- Datasets/protocol: TODO
- Main metrics: TODO
- Difference from PMT / current baseline: TODO
- Reproducible experiment idea: TODO
- Keep / move / discard decision: TODO

## Extracted Abstract
Multi-modal object Re-IDentification (ReID) aims to re- trieve specific objects by utilizing complementary image in- formation from different modalities. Recently, large-scale pre-trained models like CLIP have demonstrated impressive performance in traditional single-modal object ReID tasks. However, they remain unexplored for multi-modal object ReID. Furthermore, current multi-modal aggregation meth- ods have obvious limitations in dealing with long sequences from different modalities. To address above issues, we in- troduce a novel framework called MambaPro for multi- modal object ReID. To be specific, we first employ a Par- allel Feed-Forward Adapter (PFA) for adapting CLIP to multi-modal object ReID. Then, we propose the Synergis- tic Residual Prompt (SRP) to guide the joint learning of multi-modal features. Finally, leveraging Mamba’s superior scalability for long sequences, we introduce Mamba Ag- gregation (MA) to efficiently model interactions between different modalities. As a result, MambaPro could extract more robust features with lower complexity. Extensive exper- iments on three multi-modal object ReID benchmarks (i.e., RGBNT201, RGBNT100 and MSVR310) validate the effec- tiveness of our proposed methods. Introduction Object Re-IDentification (ReID) aims to re-identify specific objects across non-overlapping cameras. Due to its wide applications, object ReID has advanced significantly in re- cent years (Liu et al. 2023; Wang et al. 2024a; Liu et al. 2024a, 2021; Zhang et al. 2021; Yu et al. 2024a). However, single-modal object ReID has many limitations in challeng- ing scenarios (Li et al. 2020; Zheng et al. 2021), such as lighting changes, shadows and low image resolutions. Under such extreme conditions, single-modal object ReID methods may extract misleadi

## Extracted Method Signal
dels like CLIP have demonstrated impressive performance in traditional single-modal object ReID tasks. However, they remain unexplored for multi-modal object ReID. Furthermore, current multi-modal aggregation meth- ods have obvious limitations in dealing with long sequences from different modalities. To address above issues, we in- troduce a novel framework called MambaPro for multi- modal object ReID. To be specific, we first employ a Par- allel Feed-Forward Adapter (PFA) for adapting CLIP to multi-modal object ReID. Then, we propose the Synergis- tic Residual Prompt (SRP) to guide the joint learning of multi-modal features. Finally, leveraging Mamba’s superior scalability for long sequences, we introduce Mamba Ag- gregation (MA) to efficiently model interactions between different modalities. As a result, MambaPro could extract more robust features with lower complexity. Extensive exper- iments on three multi-modal object ReID benchmarks (i.e., RGBNT201, RGBNT100 and MSVR310) validate the effec- tiveness of our proposed methods. Introduction Object Re-IDentification (ReID) aims to re-identify specific objects across non-overlapping cameras. Due to its wide applications, object ReID has advanced significantly in re- cent years (Liu et al. 2023; Wang et al. 2024a; Liu et al. 2024a, 2021; Zhang et al. 2021; Yu et al. 2024a). However, single-modal object ReID has many limitations in challeng- ing scenarios (Li et al. 2020; Zheng et al. 2021), such as lighting changes, shadows and low image resolutions. Under such extreme conditions, single-modal object ReID methods may extract misleading features (Li et al. 2020), resulting in the loss of discriminative information (Wang et al. 2023). Fortunately, multi-modal object ReID has demonst

## Extracted Experiment Signal
ard Adapter (PFA) for adapting CLIP to multi-modal object ReID. Then, we propose the Synergis- tic Residual Prompt (SRP) to guide the joint learning of multi-modal features. Finally, leveraging Mamba’s superior scalability for long sequences, we introduce Mamba Ag- gregation (MA) to efficiently model interactions between different modalities. As a result, MambaPro could extract more robust features with lower complexity. Extensive exper- iments on three multi-modal object ReID benchmarks (i.e., RGBNT201, RGBNT100 and MSVR310) validate the effec- tiveness of our proposed methods. Introduction Object Re-IDentification (ReID) aims to re-identify specific objects across non-overlapping cameras. Due to its wide applications, object ReID has advanced significantly in re- cent years (Liu et al. 2023; Wang et al. 2024a; Liu et al. 2024a, 2021; Zhang et al. 2021; Yu et al. 2024a). However, single-modal object ReID has many limitations in challeng- ing scenarios (Li et al. 2020; Zheng et al. 2021), such as lighting changes, shadows and low image resolutions. Under such extreme conditions, single-modal object ReID methods may extract misleading features (Li et al. 2020), resulting in the loss of discriminative information (Wang et al. 2023). Fortunately, multi-modal object ReID has demonstrated a promising capability in addressing these challenges (Wang et al. 2023; Shi et al. 2024a,b). With complementary im- *Corresponding author (zhpp@dlut.edu.cn). Copyright © 2025, Association for the Advancement of Artificial Intelligence (www.aaai.org). All rights reserved. Frozen Backbone Mamba Aggregation Adapter Prompt Trainable Backbone Transformer Aggregation Fewer Params Lower FLOPs Better Performance Previous Methods MambaPr o (a) (b) Mor

## Detected Entities
- Tasks: person re-identification, object re-identification, multi-modal object re-identification
- Datasets: RGBNT201, RGBNT100, MSVR310
- Methods: Transformer, CLIP, Mamba, Token, Prompt, Contrastive, Modality, Attention
- Metrics: Rank-1, mAP, CMC

## Manual Notes
- [ ] Confirm relevance.
- [ ] Mark key figures/tables in Zotero.
- [ ] Move accepted papers out of the candidate collection.
