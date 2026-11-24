# Credits and source pins

The turn-tail checkpoint change and the GX10 measurements are by sxuff. GR8 and the base single-Spark serving recipe are by KindlingAI and the upstream GR8 contributors. Z.ai developed GLM-5.3-Flash. KindlingAI published the EXLR8 checkpoint, and IncoAI published the DFlash2 drafter.

| Component | Source used for the run |
| --- | --- |
| GR8 engine | [Public commit d598965](https://github.com/kindlingai/gr8/tree/d598965a1bbf3cd220ad9ad856bfd63da2466424). Its complete Git tree is `3c0f8ddf3fe179e2444e1444599bfec9407a6b19`, the same tree as the source extracted from the measured base image before applying the patch. |
| Base recipe and image | [Recipe commit 30d5790](https://github.com/kindlingai/glm-5.3-flash-exlr8-1x-spark/tree/30d5790d5720ef7a181217b93c6041c7814be90a). The Dockerfile names the published image by digest. |
| Turn-tail patch | SHA-256 `4e939f1faea365381586cfcb8959f1cbc7e60d99894430d8288138b24c4795ec`. |
| Measured local image | Docker image ID `sha256:2b2a2d9cee7ab07be7b035f21fdb6eceda55947d63c2f1fe0ea3f8572b106413`. The GX10's engine binary from that build had SHA-256 `2ac0f69fc7a80f382534a5a84ee629e2cc0c10f052b9bd8904a0ceb9b2c4b7d4`. These identify the measured build. A fresh build can produce different digests. |
| Target | [KindlingAI EXLR8 bit201, revision 901ad08](https://huggingface.co/kindlingai/glm-5.3-flash-exlr8-k2-k3-k4/tree/901ad084f0afd2400820504910d3e684133ce183). The model card identifies the MIT license. |
| Drafter | [IncoAI GLM-5.3-Flash DFlash2, revision bf582e4](https://huggingface.co/incoai/GLM-5.3-Flash-DFlash2/tree/bf582e4eacc1810f76656d1811693ff6c6737d2a). The model card identifies CC BY-NC-ND 4.0. |

The November 24 settings run ([results/2026-11-24-gx10-skill](results/2026-11-24-gx10-skill/README.md)) followed [0xSero](https://github.com/0xSero)'s [inference-optimisation skill](https://github.com/sybil-solutions/inference-optimisation-skill) (commit `fda968e`); its method and its `bench.py` ran unchanged on the GB10.

The patch includes context from GR8, and the launch options and cache configuration follow KindlingAI's single-Spark recipe. Both upstream repositories carry the same MIT notice, reproduced in [GR8-LICENSE.txt](GR8-LICENSE.txt). The benchmark's separate attribution is in [bench/README.md](bench/README.md). Model files and pretrained drafter weights download from their respective repositories on first boot.
