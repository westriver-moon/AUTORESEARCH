---
zotero_item_key: SKYPQKLJ
doi: 10.1609/aaai.v37i2.25273
year: 2023
generated_at: 2026-07-04T10:10:34+00:00
---

# Learning Progressive Modality-Shared Transformers for Effective Visible-Infrared Person Re-identification

## Metadata
- Zotero item: zotero://select/library/items/SKYPQKLJ
- DOI: 10.1609/aaai.v37i2.25273
- Year/date: 2023
- Venue: Proceedings of the AAAI Conference on Artificial Intelligence
- Authors: Hu Lu, Xuezhang Zou, Pingping Zhang
- PDF: D:\Users\pbrii\AppData\Local\zotero\storage\YQHC8645\Lu 等 - 2023 - Learning Progressive Modality-Shared Transformers for Effective Visible-Infrared Person Re-identific.pdf

## Why It Matters For This Project
- Directly matches visible-infrared / VI-ReID.
- Targets cross-modality representation or matching.
- Mentions SYSU-MM01, the current server baseline dataset.
- Connects to PMT-style modality-shared transformer baselines.
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
Visible-Infrared Person Re-Identification (VI-ReID) is a challenging retrieval task under complex modality changes. Existing methods usually focus on extracting discriminative visual features while ignoring the reliability and commonality of visual features between different modalities. In this paper, we propose a novel deep learning framework named Progressive Modality-shared Transformer (PMT) for effective VI-ReID. To reduce the negative effect of modality gaps, we first take the gray-scale images as an auxiliary modality and propose a progressive learning strategy. Then, we propose a Modality-Shared Enhancement Loss (MSEL) to guide the model to explore more reliable identity information from modality-shared features. Finally, to cope with the problem of large intra-class differences and small interclass differences, we propose a Discriminative Center Loss (DCL) combined with the MSEL to further improve the discrimination of reliable features. Extensive experiments on SYSU-MM01 and RegDB datasets show that our proposed framework performs better than most state-of-the-art methods. For model reproduction, we release the source code at https://github.com/hulu88/PMT.

## Extracted Method Signal
tract Visible-Infrared Person Re-Identification (VI-ReID) is a chal- lenging retrieval task under complex modality changes. Ex- isting methods usually focus on extracting discriminative vi- sual features while ignoring the reliability and commonal- ity of visual features between different modalities. In this paper, we propose a novel deep learning framework named Progressive Modality-shared Transformer (PMT) for effec- tive VI-ReID. To reduce the negative effect of modality gaps, we first take the gray-scale images as an auxiliary modal- ity and propose a progressive learning strategy. Then, we propose a Modality-Shared Enhancement Loss (MSEL) to guide the model to explore more reliable identity informa- tion from modality-shared features. Finally, to cope with the problem of large intra-class differences and small inter- class differences, we propose a Discriminative Center Loss (DCL) combined with the MSEL to further improve the dis- crimination of reliable features. Extensive experiments on SYSU-MM01 and RegDB datasets show that our proposed framework performs better than most state-of-the-art meth- ods. For model reproduction, we release the source code at https://github.com/hulu88/PMT. Introduction Person Re-Identification (ReID) aims to retrieve the same person under different cameras and times. It can be utilized in many real-world applications, such as video surveillance, smart security, etc. Recently, with the advances of deep learning, person ReID has witnessed great success in perfor- mance and deployment. However, most of the existing ReID methods target on the visible environment. Thus, they can be regarded as visible-visible ReID. In fact, most of visible- visible ReID methods can not work well at nighttime. To addr

## Extracted Experiment Signal
he existing ReID methods target on the visible environment. Thus, they can be regarded as visible-visible ReID. In fact, most of visible- visible ReID methods can not work well at nighttime. To address this problem, images captured by infrared cameras are considered in practical scenarios, which greatly help the ReID under different modalities and result in Visible- Infrared Person Re-Identification (VI-ReID). Compared with single-modality ReID, VI-ReID has three main challenges: 1) The large modality gap will make it dif- ficult to align the identify-related features of the two modali- ties. 2) Infrared images are more sensitive to light conditions *The corresponding author. Copyright © 2023, Association for the Advancement of Artificial Intelligence (www.aaai.org). All rights reserved. Figure 1: Several typical cases in visible-infrared person re- identification. (a) Discriminative information is not always visible due to posture or viewpoint changes. (b) Partial infor- mation may disappear due to the modality shift and different lighting conditions. (c) Modality-based clothing change due to the large time span. than visible images, resulting in less discriminative features for cross-modality matching. 3) Modality-based clothing changes can occur due to the large time span, which further increases the difficulty of robust feature extraction. To reduce the heterogeneous differences between two modalities, existing approaches (Ye et al. 2021; Gao et al. 2021; Chen et al. 2021b) mainly use a dual-stream network structure. The non-shared weight components are first used to extract modality-specific features separately before learn- ing modality-shared features. Although these methods can effectively benefit from modality-specifi

## Detected Entities
- Tasks: visible-infrared person re-identification, VI-ReID, cross-modality person re-identification, person re-identification, object re-identification
- Datasets: SYSU-MM01, RegDB
- Methods: PMT, Transformer, Vision Transformer, Token, Cross-modal, Cross-modality, Modality, Attention
- Metrics: Rank-1, mAP, mINP, CMC

## Manual Notes
- [ ] Confirm relevance.
- [ ] Mark key figures/tables in Zotero.
- [ ] Move accepted papers out of the candidate collection.
