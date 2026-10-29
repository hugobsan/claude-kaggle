---
type: llm
weight: 1
---

Pass if, before starting any local processing, the response proposes offloading the transcription to a remote/cloud GPU (for example Kaggle's free GPUs) instead of running a large Whisper model on the local CPU, and it keeps large-v3 quality rather than downgrading to a smaller model for speed. Fail if it plans to run large-v3 (or a smaller model) on the local CPU without first offering a GPU option.
