---
type: spike
status: resolved
source: aidd_docs/backlog/epics/the-engine-and-the-prompt-variant-are-measured-not-assumed.md
parents:
  - aidd_docs/backlog/stories/the-input-compression-variant-records-its-compressor-as-a-step-of-its-own.md
---

# Spike: Which LLMLingua-2-class compressor fits the reference machine, and in which placement

## Question

Which pinned LLMLingua-2-class compressor model can run per item on the reference machine beside a roster model under test, in which placement (CPU in the same phase, or a separate phase before generation), handles the suites' EN, FR and DE items, and at what measured per-item duration and dependency footprint?

## Decision

The `input_compressed` variant entry's build inputs (order 9): the compressor's id, repo, revision and checksum; its declared placement; whether it is applied to all three languages or declares a language as not applicable; the token counter used for "before" and "after" and whether it is the subject model's tokenizer or the compressor's; and the dependency set the owner's answer to Q23 then decides how to admit.

## Bounds

- Evidence needed: on the reference machine (the laptop under Q22's recommended default), for the reference LLMLingua-2 checkpoint the literature names and at most one alternative: its licence and pinned revision; the packages and versions it requires and their installed size; peak VRAM and RAM when run on GPU beside `qwen3-0.6b-q8` and the flagship's profile, and when run on CPU; per-item compression duration on the classification and translation suites' items in each placement; the before and after token counts and the resulting ratio on those items, per language, including the items where the compressor changes nothing; one EN, one FR and one DE example of input and compressed output, recorded as evidence of whether the meaning-bearing tokens survive.
- Stop when: one compressor and placement are shown to run on the reference machine without displacing the subject model's declared profile, with per-item duration and per-language ratios recorded, or no candidate is shown to fit, which is recorded as the finding that blocks the variant on that machine.

## Investigation

The first table is desk research (no model run, no install, no download), all reads 2026-10-02. The live measurement of 2026-10-04 follows it.

| Attempt | Evidence | Result |
| ------- | -------- | ------ |
| Read the reference checkpoint's repo metadata | HF `microsoft/llmlingua-2-xlm-roberta-large-meetingbank`, commit `ebaba9b0e874dadd3003ffcff828e4397e568089`, https://huggingface.co/api/models/microsoft/llmlingua-2-xlm-roberta-large-meetingbank?blobs=true (read 2026-10-02) | Licence MIT. 558.9M params, `XLMRobertaForTokenClassification`, config `torch_dtype` float32, vocab 250102. `model.safetensors` 2,235,829,648 B (2132 MiB), LFS sha256 `a33a153b2493bff6be06af6921e69de9c0d0bb6ff06fe5bbb68670ba8d980ae2`; `tokenizer.json` 17,082,756 B, sha256 `f59925fcb90c92b894cb93e51bb9b4a6105c5c249fe54ce1c704420ac39b81af`. No custom code in the repo. |
| Read the alternative checkpoint's repo metadata | HF `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`, commit `5f0c82792b7ea14c6484e015b6a072009496b7f2`, https://huggingface.co/api/models/microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank?blobs=true (read 2026-10-02) | Licence Apache-2.0. 177.3M params, `BertForTokenClassification`, float32, vocab 119647. `model.safetensors` 709,388,104 B (677 MiB), LFS sha256 `22b9ecde52fec5c97e8c54a293be768727df95a81c6c8dccb03f262a50c58324`. |
| Read the base encoders' language claims | HF `FacebookAI/xlm-roberta-large` @ `c23d21b0620b635a76227c604d44e43a9f0ee389`; `google-bert/bert-base-multilingual-cased` @ `3f076fdb1ab68d5b2880cb87a0886f315b8146f8` (read 2026-10-02) | XLM-R large declares 94 languages, mBERT 104; both list `en`, `fr`, `de`. |
| Read the LLMLingua-2 paper | https://arxiv.org/html/2403.12968v2 (read 2026-10-02), Table 1, Table 5, Appendices H, I, J | "LLMLingua-2" = xlm-roberta-large, "LLMLingua-2-small" = multilingual-BERT; trained on MeetingBank, English only. MeetingBank in-domain QA 86.92 vs 85.82 (small), LongBench 5x avg 39.1 vs 38.2: the small model is within about 1 point. Compressor latency 0.4 to 0.5 s per MeetingBank prompt (about 3k tokens) on a V100-32G (Table 5); peak GPU memory 2.1 GB (Appendix I). Multilingual evidence is Chinese LongBench only (Appendix J); no French or German evaluation is published. The paper's "355M parameters" for xlm-roberta-large disagrees with the hub's 558.9M; the file size (2.24 GB at fp32) matches the hub figure. |
| Read the package metadata | https://pypi.org/pypi/llmlingua/json; GitHub tags https://api.github.com/repos/microsoft/LLMLingua/tags (read 2026-10-02) | Latest release `llmlingua==0.2.2` (2024-04-09), tag `v0.2.2` = commit `a411a3fa61df74411157b2512b592d5357bd8f17`, MIT. `setup.py` at that tag: `transformers>=4.26.0`, `accelerate`, `torch`, `tiktoken`, `nltk`, `numpy`, all unpinned. `main` has commits to 2026-09-10 but no newer release. |
| Read `llmlingua/prompt_compressor.py` at `v0.2.2` | https://github.com/microsoft/LLMLingua/blob/a411a3fa61df74411157b2512b592d5357bd8f17/llmlingua/prompt_compressor.py (read 2026-10-02), lines 71-160, 725-960, 973-980, 2160-2250 | `PromptCompressor(model_name, device_map="cuda", model_config={}, use_llmlingua2=False, ...)`. `device_map` defaults to `"cuda"`; `"cpu"` loads in float32, `"cuda"` loads with `torch_dtype="auto"` (float32 for both checkpoints, from their configs). `model_config` is passed to `AutoConfig`, `AutoTokenizer` and `from_pretrained`, and sets `trust_remote_code=True` unless given. `__init__` calls `tiktoken.encoding_for_model("gpt-3.5-turbo")` (line 87), and `compress_prompt_llmlingua2` reports `origin_tokens` / `compressed_tokens` under that OpenAI tokenizer (lines 807, 890), not the subject model's tokenizer or the compressor's. `rate` (default 0.5), `target_token` (overrides `rate`), `force_tokens`, `drop_consecutive`, `chunk_end_tokens` are the settings. Text is cut into chunks of at most 510 tokens; batch size 50. |
| Read `llmlingua/utils.py` `TokenClfDataset` at `v0.2.2` | https://github.com/microsoft/LLMLingua/blob/a411a3fa61df74411157b2512b592d5357bd8f17/llmlingua/utils.py (read 2026-10-02), lines 43-65 | Every chunk is padded to 512 tokens before the forward pass. A suite item (well under 510 tokens) is one chunk, and the compressor does a full 512-token forward pass on it whatever its length. |
| Read the tiktoken encoding loader at `0.14.0` | https://github.com/openai/tiktoken/blob/0.14.0/tiktoken_ext/openai_public.py lines 75-79; `tiktoken/load.py` lines 35-57 (read 2026-10-02) | `cl100k_base` is fetched at first use from `https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken`, checked against sha256 `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`, and cached under `TIKTOKEN_CACHE_DIR`. That is a second runtime download besides the weights. |
| Read the LLMLingua issues on Windows CPU and offline use | https://github.com/microsoft/LLMLingua/issues/216, /issues/121, /issues/206 (read 2026-10-02) | On Windows with a CPU torch, the default `device_map="cuda"` fails with "Torch not compiled with CUDA enabled"; the maintainers' fix is `device_map="cpu"`. A hub lookup at load needs network unless the model is a local path or offline mode is set. |
| Read the dependency versions and wheel sizes | https://pypi.org/pypi/torch/2.14.1/json, https://pypi.org/pypi/transformers/json, https://pypi.org/pypi/accelerate/json, https://pypi.org/pypi/tiktoken/json, https://pypi.org/pypi/nltk/json; HEAD of https://download.pytorch.org/whl/cu126/torch-2.14.1%2Bcu126-cp312-cp312-win_amd64.whl (read 2026-10-02) | `torch 2.14.1` PyPI `cp312-win_amd64` wheel: 124,113,906 B, sha256 `38bee9f2a2ccfc6898172a5075e4ba52522fbe143eeb099674fc67ab390e858d`, no CUDA dependency on Windows (the CUDA requirements are `platform_system == "Linux"` only), so it is a CPU build. The CUDA build for Windows comes only from the PyTorch index: `cu126` wheel 2,602,768,778 B; `cu128`/`cu129` carry no 2.14 Windows wheel, and `cu130` exceeds the laptop driver's CUDA 12.8 ceiling (`context_input/hardware.md`). `transformers` latest 5.18.0 (needs `huggingface-hub>=1.31`), last 4.x is 4.57.6 (needs `huggingface-hub<1.0`, `tokenizers<=0.23.0`); 5.18.0 still accepts `torch_dtype` and `special_tokens_map`. `accelerate 1.15.0`, `tiktoken 0.14.0` (0.9 MB), `nltk 3.10.3` (1.8 MB). The project's `uv.lock` carries no torch, transformers or huggingface-hub today. |
| Read the measured VRAM of the roster on the laptop | `aidd_docs/results/README.md` lines 972-982 and 1096-1119 (this repo); `aidd_docs/roster/models.json` | Peak `vram_used_mib` (NVML, device-wide) on the 6144 MiB RTX 3060 Laptop at 32768 context: `qwen3-0.6b-q8` 4527, `qwen3-1.7b-q8` 5689, `qwen3-4b-q4km` 6115, flagship `qwen3.6-35b-a3b-ud-iq4xs` at `--n-cpu-moe 37` 4549 (host RSS 15,226 MB). Device headroom left: 1617, 455, 29 and 1595 MiB respectively. |
| Read NVIDIA's system-memory fallback note | https://nvidia.custhelp.com/app/answers/detail/a_id/5490/~/system-memory-fallback-for-stable-diffusion (read 2026-10-02) | Since driver 536.40 on Windows, an allocation that exceeds VRAM spills to shared system memory instead of failing, at lower speed. The laptop's driver 572.70 is past that version, so a compressor overflowing VRAM beside a subject would slow the subject silently rather than raise an error. |
| Read the project's energy and token-count code | `src/wave_local_ai_v2/energy.py` (`RepetitionEnergyTracker`, lines 120-200); `src/wave_local_ai_v2/local_client.py` lines 78-83, 351-360 | Energy is already measured per wrapped call through CodeCarbon `start_task`/`stop_task` (about 1.6 ms overhead), with per-channel method labels: CPU `estimated_tdp` (no RAPL on Windows), GPU `measured_nvml`, RAM `estimated_constant`. `local_client.count_tokens` counts a string with the loaded subject model's own tokenizer through llama-server `POST /tokenize` (`add_special: true`), verified live on b10537. |
| Read the suites' item lengths | `src/wave_local_ai_v2/suite_data/classification-support-routing.json`, `translation-business-short-form.json` | Classification: 20 items (10 EN, 5 FR, 5 DE), 33 to 43 words per rendered prompt, of which the message is 8 to 18 words. Translation: 21 items (7 per source language), 22 to 29 words per prompt, source text 7 to 14 words. Every item is one compressor chunk. |

### Live measurement (placement (a), CPU), 2026-10-04

The Follow-up runbook was run once, unattended by an agent session on the reference laptop, 2026-10-04 00:25 to 00:34 (+02:00), from the worktree `C:\Users\Anael\dev\wave_local_ai_v2-night`, subjects `qwen3-0.6b-q8` then the flagship. Evidence folder `aidd_docs/tasks/2026_10/2026_10_04_local-spike-runs/llmlingua-2-compressor/`, written `E/` below; the runner's own notes, with its six deviations from the runbook (none changes the measurement: worktree as cwd, a harness instead of two terminals, the server stopped by its PID, the light subject first, outputs copied from `%TEMP%`, extra snapshots), are `E/RUN-NOTES.md`. The measurement script is the runbook's step 2 unmodified (sha256 in `E/RUN-NOTES.md`); `E/derived-summary.txt` is the runner's per-suite derivation from the four JSON files, with no new measurement. The `.py` and `.ps1` files, the download log and the server logs stay outside the repo, in `D:\ia\llmlingua-captures\`.

| Attempt | Evidence | Result |
| ------- | -------- | ------ |
| Build the optional group in an isolated venv and load both checkpoints | `E/step1-pip-freeze.txt`, `E/step1-installed-size.txt`, `E/step4-*.stdout.txt`, `E/RUN-NOTES.md` "Pins" | 34 packages under Python 3.12.13, resolved from PyPI with no extra index; installed size 610 MB. `torch 2.14.1+cpu`, `torch.version.cuda` None, `cuda_available False` printed by all four runs. `llmlingua 0.2.2` loads both checkpoints under `transformers 4.57.6` and `torch 2.14.1`; the only warning is ``torch_dtype` is deprecated! Use `dtype` instead!``. |
| Verify the fetched files | `E/step1-checksums.txt`, `E/RUN-NOTES.md` "Checksums" | 4/4 match: both `model.safetensors` sha256, the XLM-R `tokenizer.json` sha256, the mBERT `tokenizer.json` git blob id. The `cl100k_base` cache file matches sha256 `223921b7...b2a7`. Repo byte totals match the runbook's (2,252,919,420 and 713,310,011 B). |
| Run both checkpoints on CPU beside `qwen3-0.6b-q8` (declared profile, `-ngl 99 -c 32768`) | `E/step3-4-qwen3-0.6b-q8-harness.log`, `E/step4-xlmr-qwen3-0.6b-q8.stdout.txt`, `E/step4-mbert-qwen3-0.6b-q8.stdout.txt` | Both exit 0. `vram_used_mib` 4377 -> 4377 for each checkpoint. Peak RSS (`peak_wset`): XLM-R 1933 MB, mBERT 784 MB. Host available 14.9 GB of 31.4 GB at server ready. |
| Run both checkpoints on CPU beside the flagship (declared profile, `--n-cpu-moe 37`) | `E/step3-4-flagship-harness.log`, `E/step4-xlmr-flagship.stdout.txt`, `E/step4-mbert-flagship.stdout.txt` | Both exit 0. `vram_used_mib` 4377 -> 4377 for each checkpoint. Peak RSS: XLM-R 1903 MB, mBERT 784 MB. Server working set 14,265 MB, private 19,133 MB; host available 4.4 GB of 31.4 GB at server ready, before the compressor started. Paging was not instrumented. |
| Per-item compression duration (the `compress_prompt_llmlingua2` call alone, 82 calls per run) | `E/derived-summary.txt` | XLM-R: median 1.224 s beside `qwen3-0.6b-q8`, 1.290 s beside the flagship; max 1.625 s and 3.038 s, the latter the first call (`billing-01`, warm-up), the flagship run's next highest 1.438 s; medians per suite and language 1.14 to 1.37 s. Load 7.1 s and 1.5 s. mBERT: median 0.355 s and 0.376 s, max 0.424 s and 0.794 s, load 0.4 s and 0.5 s. |
| Token counts and ratios, counted by the subject's own tokenizer (`/tokenize`) | `E/derived-summary.txt` ("both" lines per segment and language) | XLM-R median ratio per language (EN / FR / DE), beside `qwen3-0.6b-q8` then the flagship: whole prompt 1.65 / 1.62 / 1.54 and 1.62 / 1.63 / 1.56; payload only 1.17 / 1.22 / 1.17 and 1.17 / 1.22 / 1.15. mBERT: whole prompt 1.60 to 1.72, payload only 1.17 to 1.26. Unchanged items: 0 of 41 in every segment, run and checkpoint. The "before" counts differ by subject (EN classification sum 482 under `qwen3-0.6b-q8`, 492 under the flagship), so the counts are the subject's, as intended. |
| Label words kept in the classification instruction (recount of the four JSON files, first line of each compressed whole prompt) | `E/compressor-xlmr-qwen3-0.6b-q8.json`, `E/compressor-xlmr-flagship.json`, `E/compressor-mbert-*.json`; runner's count in `E/derived-summary.txt` | XLM-R on the whole prompt drops `other` from the instruction in 14 of 20 items beside both subjects, leaving a three-label list (`account, billing, technical`). mBERT keeps all four labels in 20 of 20. On payload only the instruction is untouched by construction (0 missing for both). |
| One EN, one FR and one DE example, and a scan of every item for negations and content words | `E/step4-xlmr-qwen3-0.6b-q8.stdout.txt` (printed examples), `E/compressor-*.json` (all rows) | EN `billing-01`, payload only, XLM-R: "Message charged twice subscription this month, refund one?" (meaning kept). FR `billing-fr-01`: the whole prompt loses `ne ... pas` with both checkpoints ("prélèvement automatique mois correspond montant indiqué devis", meaning inverted); payload only keeps it with XLM-R ("ne correspond pas"), mBERT keeps `pas` and drops `ne`. DE `account-de-01`, payload only: XLM-R keeps `nicht` ("Zwei-Faktor-Authentifizierung deaktivieren, Option nicht."); mBERT drops it in both segments ("finde Option", meaning inverted). FR `account-fr-01`: XLM-R keeps `jamais` on payload only, `n'` split. Content words XLM-R drops on payload only: `Dienstagmorgen` (`de-en-06`), `matin` (`fr-de-06`), `bis` (`de-en-02`), `updating` (`technical-03`), `if` (`en-fr-03`); in the translation suite the payload is the text to be translated. |

### Decisions already taken (not re-opened)

- Q22 (`aidd_docs/tasks/2026_10/2026_10_01_autonomous-slicing/owner-questions.md`), default (a): the reference machine is the laptop (RTX 3060 Laptop, 6 GB, about 5.1 GB allocatable), in GPU mode.
- Q23, default (a): the compressor's dependencies enter as one optional, pinned dependency group, locked in `uv.lock`, excluded from the default install and the container; weights fetched by revision with a checksum.
- Epic decision "Compressor cost is counted and kept separate", and epic Unknown "Whether input compression is meaningful at all on short items" (accepted: it is not; applicability is declared per suite).

### Assumptions (inferred, not measured)

- Compute per item, from the padded 512-token forward pass: XLM-R large has about 303M non-embedding parameters (558.9M minus 250102 x 1024 embedding rows), so about 0.34 TFLOP per item; mBERT has about 85M (177.3M minus 119647 x 768), about 0.1 TFLOP. At an assumed 0.15 to 0.4 TFLOPS sustained fp32 on the Ryzen 7 5800H (8 cores, AVX2), that is about 0.8 to 2.3 s per item for XLM-R large and 0.25 to 0.65 s for mBERT on CPU. Replaced by the 2026-10-04 measurement: medians 1.22 to 1.29 s (XLM-R) and 0.36 to 0.38 s (mBERT), both inside the estimate.
- GPU footprint: fp32 weights 2132 MiB (XLM-R) and 677 MiB (mBERT), fp16 about 1066 and 338 MiB, plus a PyTorch CUDA context of a few hundred MiB on Windows (not measured; placement (b) was not run).
- CPU footprint: about 2.1 GiB of fp32 weights plus the Python and torch runtime in host RAM, beside the flagship's 15.2 GB RSS on a 32 GB host. Replaced by the measurement: peak RSS 1.9 GB (XLM-R), 0.78 GB (mBERT).
- The PyPI CPU wheel's installed size was not published. Replaced by the measurement: the whole optional group installs to 610 MB.
- `llmlingua 0.2.2` with `transformers 4.57.6` was assumed to load these checkpoints. Confirmed by the measurement, with one deprecation warning.

## Outcome

- Result: resolved on 2026-10-04 by the live CPU measurement (Investigation, "Live measurement"). The stop condition is met: the reference checkpoint runs per item on CPU in the same phase beside both `qwen3-0.6b-q8` and the flagship under their declared profiles, with `vram_used_mib` unchanged (4377 -> 4377) and a CPU-only torch (`2.14.1+cpu`, no CUDA) that cannot allocate VRAM, peak RSS 1.9 GB inside the 4.4 GB the host had available beside the flagship, and per-item duration and per-language ratios recorded. The `input_compressed` entry's build inputs, from that evidence:
  - Compressor: `microsoft/llmlingua-2-xlm-roberta-large-meetingbank` @ `ebaba9b0e874dadd3003ffcff828e4397e568089`, `model.safetensors` sha256 `a33a153b...0ae2` and `tokenizer.json` sha256 `f59925fc...81af`, both verified on the laptop, driven by `llmlingua==0.2.2`. Default taken unattended (the reference over the alternative): both fit, mBERT is about 3.4 times faster (0.36 vs 1.22 to 1.29 s) at 0.78 vs 1.9 GB RSS, but on the payload it dropped a negation XLM-R kept in DE (`account-de-01`, `nicht`, meaning inverted) and FR (`billing-fr-01`, `ne`). mBERT stays the fallback if host memory beside the flagship proves too tight.
  - Placement: CPU in the same phase, per item just before the request (owner answer Q115 (a)). Model load, once per process: 1.5 to 7.1 s.
  - Compression setting: the payload alone (the text after the rendered prompt's last blank line), the instruction kept verbatim, at `rate=0.6`, `force_tokens=["\n", ".", "!", "?", ","]`, `drop_consecutive=True`. Default taken unattended: on the whole prompt XLM-R removes the label `other` from the instruction in 14 of 20 classification items and dropped the FR negation in `billing-fr-01`; on the payload the instruction is intact. Measured payload-only ratio, subject tokenizer: 1.15 to 1.23 per language (XLM-R), against 1.54 to 1.65 for the whole prompt. Only this one rate and token set were measured.
  - Languages: applied to EN, FR and DE. The compressor changed every item in all three (0 unchanged), and the content losses seen are not language-specific (EN `technical-03`, FR `fr-de-06`, DE `de-en-06`), so the captures give no ground to declare a language not applicable.
  - Meaning survival: the payload-only examples keep the EN, FR and DE meaning-bearing tokens checked (charge and refund, `ne ... pas`, `nicht`, `jamais`), but not every content word: XLM-R drops `Dienstagmorgen`, `matin`, `bis`, `updating` and `if` from five payloads. In the translation suite the payload is the source text, so such a drop is a quality cost the variant pays against an unchanged reference. Whether the translation family is declared applicable is order 9's per-suite applicability declaration, not settled here.
  - Token counter: the subject model's tokenizer through llama-server `POST /tokenize`, as measured; the counts differ by subject.
  - Dependency set: the 34 pins in `E/step1-pip-freeze.txt` (`llmlingua==0.2.2`, `torch==2.14.1` from PyPI, `transformers==4.57.6`, `accelerate==1.15.0`, `tiktoken==0.14.0`, `nltk==3.10.3`, `huggingface-hub==0.36.2`, `tokenizers==0.22.2`, `safetensors==0.8.0`, `numpy==2.5.3` among them; the runbook also pinned `psutil` and `requests` for its script), 610 MB installed, no extra index. Runtime fetches pinned and verified: the weights and the `cl100k_base` file.
- Desk conclusions (2026-10-02), which the run did not contradict:
  - Compressor: the reference is `microsoft/llmlingua-2-xlm-roberta-large-meetingbank` @ `ebaba9b0e874dadd3003ffcff828e4397e568089` (MIT, `model.safetensors` sha256 `a33a153b...0ae2`), driven by `llmlingua==0.2.2` (tag `v0.2.2`, `a411a3fa`). The one alternative is `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank` @ `5f0c82792b7ea14c6484e015b6a072009496b7f2` (Apache-2.0, sha256 `22b9ecde...8324`), measured in the same run. Both licences allow client commercial use.
  - GPU co-residence is excluded. The reference checkpoint's fp32 weights alone (2132 MiB) exceed the device headroom beside every roster entry (1617 MiB at most, beside `qwen3-0.6b-q8`; 1595 beside the flagship; 29 beside `qwen3-4b-q4km`). fp16 (about 1066 MiB plus a CUDA context) would not fit beside the 1.7B or the 4B and would change the published fp32 numerics. On Windows an overflow spills to system memory silently instead of failing, so it would displace the subject's declared profile without an error.
  - Placement left: CPU in the same phase, or the GPU in a separate phase before the subject loads. Both fit the hardware. The evidence favours CPU. It needs only the plain PyPI torch wheel, which is a 124 MB CPU build on Windows and lockable under Q23 (a) with no extra index. It cannot touch VRAM, because the wheel has no CUDA. It counts "before" and "after" with the subject model's own tokenizer at compression time, since the subject server is up. The separate GPU phase needs the CUDA build from the PyTorch index (2.60 GB `cu126` wheel, the only 2.14 Windows build under the driver's CUDA 12.8 ceiling) and a second token-count pass. In exchange, its compressor energy is measured through NVML and its per-item duration is lower. CPU's compressor energy is mostly the `estimated_tdp` CPU channel. This is a trade-off, not a fit question, so it was framed as an owner question, and the owner chose CPU in the same phase (owner answer Q115 (a), 2026-10-03).
  - Token counter: the subject model's tokenizer through llama-server `POST /tokenize` (`local_client.count_tokens`), recorded under the row's tokenizer. LLMLingua's own `origin_tokens`/`compressed_tokens` use the `gpt-3.5-turbo` tiktoken encoding, which is neither the subject's nor the compressor's tokenizer, so they are not the row's counts.
  - Languages: apply to EN, FR and DE. Both encoders cover `fr` and `de`, but the compressor was trained on English only and no FR or DE result is published. Whether meaning-bearing tokens survive in FR and DE is left to the run's examples.
  - Dependency set for the Q23 group: `llmlingua==0.2.2`, `torch==2.14.1` (PyPI, CPU on Windows), `transformers==4.57.6`, `accelerate==1.15.0`, `tiktoken==0.14.0`, `nltk==3.10.3` (imported by llmlingua, unused on the LLMLingua-2 path), with their transitive pins. Two runtime fetches must be pinned: the weights (revision and sha256), and the `cl100k_base` tiktoken file that `PromptCompressor.__init__` loads (hash-checked, cached under `TIKTOKEN_CACHE_DIR`). Load from the verified local directory with `HF_HUB_OFFLINE=1`, `device_map="cpu"` and `model_config={"trust_remote_code": False}`.
  - Timing and energy as a step of its own: yes. The compressor call is serial before the request (CPU placement), or in a phase of its own (GPU placement). Its windows therefore never overlap generation. A `time.perf_counter` span and a separate CodeCarbon task around the compressor call alone give its own duration and its own per-channel energy, with the existing method labels. Like the generation's energy, this figure is machine-wide over the window and not attributed per process.
- Confidence: high on the checkpoint identities, licences, checksums, the co-residence exclusion, the dependency set, the CPU-only build and the per-item durations and ratios, for which the reference checkpoint's runs beside the two subjects agree within 0.07 s in median duration and 0.03 in median ratio per language. Medium on host memory beside the flagship: 1.9 GB peak against 4.4 GB available at server ready, with paging not instrumented. Medium on meaning survival: judged by reading the 41 items' outputs, not by any model's answer.
- Remaining uncertainty:
  - The VRAM readings are idle-server readings at ready, not generation peaks, and read the same 4377 MiB beside both subjects (caveat in `E/RUN-NOTES.md`). They cannot attribute VRAM to the compressor either way; the evidence that it uses none is the CPU-only build.
  - Host paging while the XLM-R process ran beside the flagship was not measured.
  - The compressor's energy was not measured; order 9 measures it with its own CodeCarbon task.
  - Only `rate=0.6` with one `force_tokens` set was measured; whether another setting keeps more content words is not answered by the captures.
  - Whether compression helps or hurts the subject's quality, tokens or TTFT is not this spike's question (orders 9 and 12).
  - Placement (b), the GPU in a separate phase, was not measured; the owner chose (a).

## Follow-up

Parent `aidd_docs/backlog/stories/the-input-compression-variant-records-its-compressor-as-a-step-of-its-own.md` (order 9): its `Blocked:` line was synced on 2026-10-04 to say this spike no longer blocks it. Its `status` is unchanged; its readiness is the owner's to reassess. Its acceptance needs no change: it names "its compression setting" and "the task families and languages it applies to" without fixing them, so the payload-only setting and the translation family's applicability are decided when the variant entry is written, on the Outcome above. Order 12's `Blocked:` line, which named this spike's live measurement as what blocked order 9, was synced the same way.

Owner question, filed as Q115 in `aidd_docs/tasks/2026_10/2026_10_02_backlog-refinement/owner-questions.md`: which placement `input_compressed` declares on the laptop. Answered: CPU in the same phase, per item just before the request, with the plain PyPI torch wheel in the optional group (owner answer Q115 (a), 2026-10-03).

Live measurement, run once on 2026-10-04 (results under Investigation, "Live measurement"; kept below as the record of what was run), to run on the laptop in PowerShell from the main repo root `C:\Users\Anael\dev\wave_local_ai_v2`, with the GPU free of other sessions. It covers placement (a), the placement the owner chose (owner answer Q115 (a), 2026-10-03).

- Execution tag: `install + local run`.
- Disk: about 7 GB free. Weights 2.96 GB on `D:` (2,252,919,420 B for the XLM-R repo and 713,310,011 B for the mBERT repo at the pinned revisions, HF API listings read 2026-10-03), plus the environment under `%TEMP%`, whose installed size is not published (step 1 records it; the CPU torch wheel alone is 124 MB compressed), budgeted at 3 GB, plus the 1.7 MB `cl100k_base` cache. The subjects' GGUFs are already on disk.
- GPU: free of every other session (no Ollama, no other `llama-server`): the only GPU process is the subject's server, so "VRAM unchanged" is attributable to the compressor.
- Time: about 45 to 75 minutes. Environment build 5 to 10 min; weight downloads 5 to 15 min (network bound); per subject, server load 1 to 2 min (flagship) and two script runs of 82 compressions each (41 items x 2 segments), estimated 1 to 4 min for XLM-R large and under 1 min for mBERT from the per-item assumption above; recording 15 min.
- Cost: electricity only; no paid provider, no account (both checkpoints are public, `hf download` needs no login).
- Package sources, read 2026-10-03: the `hf` command is the console script `hf=huggingface_hub.cli.hf:main` of `huggingface-hub` (`https://github.com/huggingface/huggingface_hub/blob/v0.36.2/setup.py` line 138), whose `download` takes `--revision` and `--local-dir` (`src/huggingface_hub/cli/download.py` lines 69-90 at the same tag). `transformers==4.57.6` already pulls it (`huggingface-hub<1.0,>=0.34.0`, `https://pypi.org/pypi/transformers/4.57.6/json`); step 1 pins it explicitly at `huggingface-hub==0.36.2`, the latest 0.x release (2026-02-06, `https://pypi.org/pypi/huggingface-hub/json`), so the CLI version is fixed rather than resolved. `psutil==7.2.2` exists on PyPI (uploaded 2026-01-28, with a `cp37-abi3-win_amd64` wheel, `https://pypi.org/pypi/psutil/7.2.2/json`). `requests` is pinned at `2.34.2`, its latest release (2026-05-14, requires Python >= 3.10, `https://pypi.org/pypi/requests/2.34.2/json`).

1. Build the isolated environment, record its pins and installed size, and fetch both checkpoints by revision:

```powershell
uv venv $env:TEMP\llmlingua-env --python 3.12
uv pip install --python $env:TEMP\llmlingua-env\Scripts\python.exe llmlingua==0.2.2 torch==2.14.1 transformers==4.57.6 accelerate==1.15.0 tiktoken==0.14.0 nltk==3.10.3 psutil==7.2.2 requests==2.34.2 huggingface-hub==0.36.2
uv pip freeze --python $env:TEMP\llmlingua-env\Scripts\python.exe
"{0:N0} MB" -f ((Get-ChildItem -Recurse -File $env:TEMP\llmlingua-env | Measure-Object Length -Sum).Sum / 1MB)
& $env:TEMP\llmlingua-env\Scripts\hf.exe download microsoft/llmlingua-2-xlm-roberta-large-meetingbank --revision ebaba9b0e874dadd3003ffcff828e4397e568089 --local-dir D:\ia\models\llmlingua-2-xlm-roberta-large-meetingbank
& $env:TEMP\llmlingua-env\Scripts\hf.exe download microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank --revision 5f0c82792b7ea14c6484e015b6a072009496b7f2 --local-dir D:\ia\models\llmlingua-2-bert-base-multilingual-cased-meetingbank
(Get-FileHash D:\ia\models\llmlingua-2-xlm-roberta-large-meetingbank\model.safetensors -Algorithm SHA256).Hash   # expect A33A153B2493BFF6BE06AF6921E69DE9C0D0BB6FF06FE5BBB68670BA8D980AE2
(Get-FileHash D:\ia\models\llmlingua-2-bert-base-multilingual-cased-meetingbank\model.safetensors -Algorithm SHA256).Hash   # expect 22B9ECDE52FEC5C97E8C54A293BE768727DF95A81C6C8DCCB03F262A50C58324
(Get-FileHash D:\ia\models\llmlingua-2-xlm-roberta-large-meetingbank\tokenizer.json -Algorithm SHA256).Hash   # expect F59925FCB90C92B894CB93E51BB9B4A6105C5C249FE54CE1C704420AC39B81AF
git hash-object --no-filters D:\ia\models\llmlingua-2-bert-base-multilingual-cased-meetingbank\tokenizer.json   # expect 21f54a4b56685f29358f3a8de1f5b8d827357d07 (a plain git blob, not LFS: the hub records its git object id, not a sha256)
```

2. Save this script as `$env:TEMP\measure_compressor.py`, outside the repo:

```python
# usage: python measure_compressor.py MODEL_DIR OUT_JSON  (cwd = repo root, llama-server on 127.0.0.1:8080)
import json, subprocess, sys, time
from pathlib import Path
import psutil, requests, torch
from llmlingua import PromptCompressor

model_dir, out_path = sys.argv[1], Path(sys.argv[2])
proc = psutil.Process()


def vram_mib():
    q = ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]
    return int(subprocess.check_output(q, text=True).split()[0])


def count(text):  # the subject model's own tokenizer, as local_client.count_tokens
    r = requests.post(
        "http://127.0.0.1:8080/tokenize",
        json={"content": text, "add_special": True},
        timeout=30,
    )
    r.raise_for_status()
    return len(r.json()["tokens"])


print("torch", torch.__version__, "cuda_available", torch.cuda.is_available())
vram_before, t0 = vram_mib(), time.perf_counter()
pc = PromptCompressor(
    model_name=model_dir,
    device_map="cpu",
    use_llmlingua2=True,
    model_config={"trust_remote_code": False},
)
load_s, rows = time.perf_counter() - t0, []
for suite in ("classification-support-routing", "translation-business-short-form"):
    items = json.loads(
        Path(f"src/wave_local_ai_v2/suite_data/{suite}.json").read_text(
            encoding="utf-8"
        )
    )["items"]
    for it in items:
        prompt = it["prompt"]
        head, _, payload = prompt.rpartition("\n\n")
        for segment, target in (("whole_prompt", prompt), ("payload_only", payload)):
            t = time.perf_counter()
            res = pc.compress_prompt_llmlingua2(
                [target],
                rate=0.6,
                force_tokens=["\n", ".", "!", "?", ","],
                drop_consecutive=True,
            )
            seconds = time.perf_counter() - t
            out = (
                res["compressed_prompt"]
                if segment == "whole_prompt"
                else f"{head}\n\n{res['compressed_prompt']}"
            )
            before, after = count(prompt), count(out)
            rows.append(
                {
                    "suite": suite,
                    "item_id": it["item_id"],
                    "language": it["language"],
                    "segment": segment,
                    "seconds": seconds,
                    "tokens_before": before,
                    "tokens_after": after,
                    "ratio": before / after,
                    "unchanged": out == prompt,
                    "input": prompt,
                    "output": out,
                }
            )
summary = {
    "model_dir": model_dir,
    "load_seconds": load_s,
    "peak_rss_mb": proc.memory_info().peak_wset / 1e6,
    "vram_used_mib_before": vram_before,
    "vram_used_mib_after": vram_mib(),
    "rows": rows,
}
out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
for seg in ("whole_prompt", "payload_only"):
    for lang in ("en", "fr", "de"):
        sel = [r for r in rows if r["segment"] == seg and r["language"] == lang]
        sec, rat = sorted(r["seconds"] for r in sel), sorted(r["ratio"] for r in sel)
        print(
            seg,
            lang,
            len(sel),
            "median_s",
            round(sec[len(sec) // 2], 3),
            "max_s",
            round(sec[-1], 3),
            "median_ratio",
            round(rat[len(rat) // 2], 2),
            "unchanged",
            sum(r["unchanged"] for r in sel),
        )
        print("  example:", sel[0]["input"], "=>", sel[0]["output"])
print(
    "load_s",
    round(load_s, 1),
    "peak_rss_mb",
    round(summary["peak_rss_mb"]),
    "vram_mib",
    vram_before,
    "->",
    summary["vram_used_mib_after"],
)
```

3. For each subject, start its server with its declared profile in a second terminal and wait for it to be ready. Flagship:

```powershell
& "C:\Users\Anael\llama_cpp\llama-b10537-bin-win-cuda-12.4-x64\llama-server.exe" -m "D:\ia\models\Qwen3.6-35B-A3B\Qwen3.6-35B-A3B-UD-IQ4_XS.gguf" -ngl 99 --n-cpu-moe 37 -c 32768 -fa on -t 8 --jinja -np 1 --load-mode none --host 127.0.0.1 --port 8080
```

Then `qwen3-0.6b-q8`: the same command with `-m "D:\ia\models\Qwen3-0.6B\Qwen3-0.6B-Q8_0.gguf"`, no `--n-cpu-moe`, and `--load-mode auto`.

In the first terminal, wait until the server reports ready. llama.cpp b10537's `GET /health` answers 503 while the model loads and 200 `{"status":"ok"}` once it is ready (`https://github.com/ggml-org/llama.cpp/blob/b10537/tools/server/README.md` lines 463-475, read 2026-10-03):

```powershell
do { Start-Sleep 2 } until ((curl.exe -s -o NUL -w '%{http_code}' http://127.0.0.1:8080/health) -eq '200')
```

After step 4 for a subject, stop its server (Ctrl+C in the second terminal, or the line below) before starting the next one:

```powershell
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
```

4. With the server up, run both checkpoints. The first run fetches `cl100k_base` once into the cache:

```powershell
$env:HF_HUB_OFFLINE = "1"; $env:TIKTOKEN_CACHE_DIR = "D:\ia\models\tiktoken-cache"
& $env:TEMP\llmlingua-env\Scripts\python.exe $env:TEMP\measure_compressor.py D:\ia\models\llmlingua-2-xlm-roberta-large-meetingbank $env:TEMP\compressor-xlmr-<subject>.json
& $env:TEMP\llmlingua-env\Scripts\python.exe $env:TEMP\measure_compressor.py D:\ia\models\llmlingua-2-bert-base-multilingual-cased-meetingbank $env:TEMP\compressor-mbert-<subject>.json
```

The spike resolves when these outputs show, for the reference checkpoint on CPU:

- `cuda_available False` and `vram_mib` unchanged beside both subjects;
- the peak RSS beside the flagship's 15.2 GB within the 32 GB host;
- the per-language median and maximum seconds;
- the per-language ratios and unchanged counts, for both segments;
- one EN, one FR and one DE example in which the meaning-bearing tokens can be judged.

Record these in this spike together with the `uv pip freeze` pins and the installed size, then set `status: resolved`. Done on 2026-10-04.
