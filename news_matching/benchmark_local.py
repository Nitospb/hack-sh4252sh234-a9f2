"""Bounded inference and disposable training probe; never saves model weights.

Run with the pinned requirements-gpu.lock environment. All models and input are
local. Title/body pairs are only a resource probe, not relevance supervision.
"""
import argparse
import gc
import json
from pathlib import Path
import platform
import resource
import time

from model_backend import ROOT, TorchE5Model, OnnxTextModel


def memory(torch, device):
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result = {'peak_rss_gib': round(rss / (1024**3 if platform.system() == 'Darwin' else 1024**2), 3)}
    if device == 'mps':
        result.update(mps_allocated_gib=round(torch.mps.current_allocated_memory()/1024**3, 3),
                      mps_driver_gib=round(torch.mps.driver_allocated_memory()/1024**3, 3))
    elif device == 'cuda':
        result['cuda_peak_allocated_gib'] = round(torch.cuda.max_memory_allocated()/1024**3, 3)
    return result


def synchronize(torch, device):
    if device == 'mps':
        torch.mps.synchronize()
    elif device == 'cuda':
        torch.cuda.synchronize()


def benchmark(args):
    import numpy as np
    import torch
    from transformers import AutoModel, AutoTokenizer
    torch.set_num_threads(2)
    torch.manual_seed(42)
    device = args.device
    if device == 'auto':
        device = 'mps' if torch.backends.mps.is_available() else ('cuda' if torch.cuda.is_available() else 'cpu')
    records = []
    with args.input.open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row.get('kind') in {'telegram', 'telegram_post'} or row.get('ml_export_allowed') is False:
                raise ValueError('Use news-only training-news.jsonl, not Telegram')
            records.append(row)
            if len(records) >= args.inference_records:
                break
    if len(records) < 2:
        raise ValueError('Need at least two news records')
    report = {'device': device, 'torch': torch.__version__, 'machine': platform.machine(),
              'training_weights_saved': False, 'input': str(args.input.resolve()),
              'semantics': 'Resource probe only; title/body pairs are not gold relevance labels.'}
    encoder = TorchE5Model() if device == 'mps' else OnnxTextModel('embedding')
    passages = []
    for row in records:
        passages.extend('passage: '+c['text'] for c in encoder.article_chunks(row['title'][:500], row['text']))
        if len(passages) >= args.inference_records:
            passages = passages[:args.inference_records]
            break
    encoder.embed(passages[:2], batch_size=2)
    synchronize(torch, device)
    start = time.perf_counter()
    vectors = encoder.embed(passages, batch_size=args.batch_size, progress='Benchmark')
    synchronize(torch, device)
    elapsed = time.perf_counter()-start
    assert np.isfinite(vectors).all() and np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=.001)
    report['inference'] = {'chunks': len(passages), 'seconds': round(elapsed, 3),
                           'chunks_per_second': round(len(passages)/elapsed, 3),
                           'batch_size': min(args.batch_size, 8) if device == 'mps' else args.batch_size,
                           **memory(torch, device)}
    del encoder, vectors
    gc.collect()
    if device == 'mps':
        torch.mps.empty_cache()
    checkpoint = ROOT/'models/e5-torch'
    if args.training_steps:
        tokenizer = AutoTokenizer.from_pretrained(ROOT/'models/e5-tokenizer', local_files_only=True)
        model = AutoModel.from_pretrained(checkpoint, local_files_only=True, trust_remote_code=False,
                                         torch_dtype=torch.float32, attn_implementation='sdpa').to(device).train()
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-5, foreach=False)
        report['parameters'] = sum(p.numel() for p in model.parameters())
        durations, losses = [], []
        for step in range(args.training_steps):
            pairs = [records[(step*args.training_batch_size+i) % len(records)] for i in range(args.training_batch_size)]
            texts = ['query: '+r['title'] for r in pairs] + ['passage: '+r['text'][:3000] for r in pairs]
            batch = tokenizer(texts, padding='max_length', truncation=True, max_length=384, return_tensors='pt').to(device)
            synchronize(torch, device)
            start = time.perf_counter()
            optimizer.zero_grad(set_to_none=True)
            hidden = model(**batch).last_hidden_state
            mask = batch['attention_mask'].unsqueeze(-1)
            pooled = (hidden*mask).sum(1)/mask.sum(1).clamp(min=1)
            pooled = torch.nn.functional.normalize(pooled, dim=1)
            queries, docs = pooled.chunk(2)
            scores = queries @ docs.T / .05
            loss = torch.nn.functional.cross_entropy(scores, torch.arange(len(pairs), device=device))
            if not torch.isfinite(loss):
                raise RuntimeError('Non-finite training loss')
            loss.backward()
            grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
            if not torch.isfinite(grad_norm):
                raise RuntimeError('Non-finite gradients')
            optimizer.step()
            synchronize(torch, device)
            durations.append(time.perf_counter()-start)
            losses.append(float(loss.detach().cpu()))
            del batch, hidden, mask, pooled, queries, docs, scores, loss
            if device == 'mps':
                torch.mps.empty_cache()
        report['training_probe'] = {'steps': args.training_steps, 'batch_size': args.training_batch_size,
            'sequence_max_length': 384, 'precision': 'float32', 'optimizer': 'AdamW',
            'step_seconds': [round(v, 3) for v in durations], 'losses': losses,
            'final_grad_norm': float(grad_norm.cpu()), **memory(torch, device)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'output/local-benchmark.json')
    parser.add_argument('--device', choices=['auto', 'mps', 'cuda', 'cpu'], default='auto')
    parser.add_argument('--inference-records', type=int, default=192)
    parser.add_argument('--batch-size', type=int, default=12)
    parser.add_argument('--training-steps', type=int, default=3)
    parser.add_argument('--training-batch-size', type=int, default=2)
    args = parser.parse_args()
    if args.training_batch_size < 2 or args.training_steps < 0 or args.inference_records < 2 or args.batch_size < 1:
        parser.error('Positive batch sizes, >=2 news records, >=0 steps; training batch must be >=2')
    benchmark(args)
