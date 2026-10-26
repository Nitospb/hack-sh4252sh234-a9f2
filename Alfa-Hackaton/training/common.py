"""Portable data/config validation; importing this module never trains a model."""
import hashlib
import json
import math
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
START = '2026-09-24T20:40:35.362238+00:00'
END = '2026-10-24T20:40:35.362238+00:00'
MODES = ('weak_title_body', 'supervised_objects')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_jsonl(path):
    with Path(path).open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def load_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text())
    for key in ('data_dir', 'model_dir', 'tokenizer_dir', 'output_dir'):
        config[key] = str((path.parent / config[key]).resolve())
    require(config['mode'] in MODES, 'Unknown objective')
    require(config['logical_batch_size'] >= 2, 'logical_batch_size must be >=2')
    require(1 <= config['micro_batch_size'] <= config['logical_batch_size'], 'Invalid micro batch size')
    require(config['epochs'] >= 1 and config['max_length'] in range(32, 513), 'Invalid epochs/length')
    require(0 < config['learning_rate'] <= .001, 'Invalid learning rate')
    require(config['temperature'] > 0 and config['checkpoint_every_updates'] >= 1, 'Invalid temperature/checkpoint interval')
    require(0 <= config['warmup_fraction'] < 1 and config['weight_decay'] >= 0 and config['max_grad_norm'] > 0,
            'Invalid warmup, decay or clipping')
    require(config['device'] in ('auto', 'cpu', 'mps', 'cuda'), 'Invalid device')
    require(0 < config['mps_memory_fraction'] <= 1, 'Keep MPS memory limits enabled')
    out = Path(config['output_dir'])
    require(out != APP/'pipeline/output' and APP/'pipeline/output' not in out.parents,
            'Training output cannot be the production catalog')
    require(out != Path(config['model_dir']) and Path(config['model_dir']) not in out.parents,
            'Do not overwrite source model weights')
    return config


def config_fingerprint(config):
    # A run may be resumed on another device/in another directory.
    portable = {k: v for k, v in config.items() if k not in
                ('device', 'output_dir', 'data_dir', 'model_dir', 'tokenizer_dir', 'mps_memory_fraction')}
    return hashlib.sha256(json.dumps(portable, sort_keys=True).encode()).hexdigest()


def verify_bundle(directory):
    directory = Path(directory)
    manifest = json.loads((directory/'manifest.json').read_text())
    require(manifest['schema_version'] == 1, 'Unknown training data version')
    for relative, expected in manifest['files_sha256'].items():
        path = (directory/relative).resolve()
        require(directory.resolve() in path.parents, 'Unsafe bundle path')
        require(digest(path) == expected, f'Training data checksum mismatch: {relative}')
    return manifest


def batches(indices, size):
    result = [indices[i:i+size] for i in range(0, len(indices), size)]
    # A singleton gives no in-batch negative; merge it into the preceding batch.
    if len(result) > 1 and len(result[-1]) == 1:
        result[-2].extend(result.pop())
    return result


def learning_rate_factor(step, total, warmup_fraction):
    warmup = max(1, int(total*warmup_fraction))
    if step < warmup:
        return (step+1)/warmup
    progress = (step-warmup)/max(1, total-warmup)
    return .5*(1+math.cos(math.pi*min(1, progress)))


def retrieval_metrics(scores, relevant, ks=(1, 5, 10)):
    """Rows are query->doc scores; relevance is a set of graded-positive indices."""
    import numpy as np
    require(len(scores) == len(relevant), 'Metric row mismatch')
    values = {f'recall@{k}': [] for k in ks}
    values.update({'mrr@10': [], 'ndcg@10': []})
    for row, positives in zip(scores, relevant):
        if not positives:
            continue
        order = np.argsort(-np.asarray(row), kind='stable')
        for k in ks:
            values[f'recall@{k}'].append(sum(int(i) in positives for i in order[:k])/len(positives))
        ranks = [rank+1 for rank, i in enumerate(order[:10]) if int(i) in positives]
        values['mrr@10'].append(1/ranks[0] if ranks else 0.)
        dcg = sum(1/math.log2(rank+1) for rank in ranks)
        ideal = sum(1/math.log2(i+2) for i in range(min(10, len(positives))))
        values['ndcg@10'].append(dcg/ideal)
    return {**{k: sum(v)/len(v) if v else None for k, v in values.items()},
            'evaluated_queries': len(values['mrr@10'])}
