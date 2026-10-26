# Компоненты

- Embeddings: `intfloat/multilingual-e5-small`, MIT. Model repository: https://huggingface.co/intfloat/multilingual-e5-small . Revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`. Main run uses original safetensors weights on local Apple MPS with FP16 inference and FP32 pooling; the original ONNX dynamic-int8 artifact is an available CPU fallback. Official model instructions require query/passage prefixes, mean pooling with attention mask and L2 normalization; those are implemented.
- Reranker: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, Apache-2.0. Model repository: https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 . Original repository ONNX `model_qint8_arm64.onnx`; exact file SHA-256 stored in result report. This is a passage relevance ranker, not an entailment or probability model.
- PyTorch: BSD-3-Clause, GPU runtime version pinned in requirements-gpu.lock.
- Transformers and Safetensors: Apache-2.0, GPU loader versions pinned in requirements-gpu.lock.
- ONNX Runtime: MIT, version pinned in requirements.
- Hugging Face Tokenizers: Apache-2.0, version pinned in requirements.
- NumPy: BSD-3-Clause, version pinned in requirements.
- Snowball stemmer: BSD-3-Clause, version pinned in requirements. Rule-based stemming is not complete morphology.
- Text: user-provided frozen news snapshot; original publisher URLs and provenance retained. This project does not acquire ownership of publisher text or claim publication accuracy.
- Topic dictionary and OKVED mappings: project-authored data from `taxonomy/`; original `bt_` IDs used without additions.

Model inference is local. The only external downloads during preparation were public model weights/tokenizers and software packages; news and company data were not sent to those services. No custom remote model code is executed.

Online analysis is implemented separately in `service/`: selected news, bank passages and anonymized company facts are sent to the approved organizer LLM gateway. The local-model preparation statement above does not imply that the generative web scenario is fully offline. Server-side keys are excluded from Git and images.
