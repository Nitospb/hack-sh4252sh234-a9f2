"""Explicit opt-in E5 training. Without --run, no model or optimizer is created."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import math
from pathlib import Path
import random
import shutil
import signal
import time
import uuid

from training.common import (batches, config_fingerprint, digest, learning_rate_factor,
    load_config, read_jsonl, require, verify_bundle, write_json)


def plan(config):
    directory = Path(config['data_dir'])
    manifest = verify_bundle(directory)
    subdir = 'weak' if config['mode']=='weak_title_body' else 'supervised'
    rows = {split: read_jsonl(directory/f'{subdir}/{split}.jsonl') for split in ('train','validation','test')}
    require(len(rows['train']) >= 2, 'No training pairs: supervised mode requires approved positive AND negative labels')
    require(len(rows['validation']) >= 2 and len(rows['test']) >= 2, 'Independent validation and test pairs are required')
    require(Path(config['model_dir'],'model.safetensors').exists(), 'Missing local Torch model; restore full release')
    require(Path(config['tokenizer_dir'],'tokenizer.json').exists(), 'Missing local tokenizer')
    if config['mode']=='supervised_objects':
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(config['tokenizer_dir'], local_files_only=True, trust_remote_code=False)
        for row in rows['train']:
            quote = row['positive_evidence']
            require(len(tokenizer.encode('passage: '+quote))+4 <= config['max_length'],
                    'Positive evidence exceeds token budget; use a shorter exact evidence span')
    update_count = len(batches(list(range(len(rows['train']))), config['logical_batch_size']))
    report = {'training_started':False, 'mode':config['mode'],
        'counts':{key:len(value) for key,value in rows.items()}, 'updates_per_epoch':update_count,
        'total_updates':update_count*config['epochs'], 'epochs':config['epochs'],
        'logical_batch_size':config['logical_batch_size'], 'micro_batch_size':config['micro_batch_size'],
        'gradient_strategy':'feature-gradient cache/replay; dropout disabled, FP32',
        'data_manifest_sha256':digest(directory/'manifest.json'),
        'source_model_sha256':digest(Path(config['model_dir'])/'model.safetensors'),
        'tokenizer_sha256':digest(Path(config['tokenizer_dir'])/'tokenizer.json'),
        'config_fingerprint':config_fingerprint(config), 'telegram_records':manifest['telegram_records']}
    source_files = [Path(__file__).with_name(name) for name in ('train.py','runtime.py','common.py','evaluate.py')]
    report['code_sha256'] = __import__('hashlib').sha256(''.join(digest(path) for path in source_files).encode()).hexdigest()
    require(report['telegram_records']==0, 'Telegram cannot enter this training run')
    return report, rows


def replace_directory(temp, destination):
    """Recover the previous complete generation if publishing the next fails."""
    previous = destination.with_name(destination.name+'.previous')
    if previous.exists() and not destination.exists():
        previous.rename(destination)
    if previous.exists():
        shutil.rmtree(previous)
    if destination.exists():
        destination.rename(previous)
    try:
        temp.rename(destination)
    except BaseException:
        if previous.exists():
            previous.rename(destination)
        raise
    if previous.exists():
        shutil.rmtree(previous)


def save_checkpoint(output, model, tokenizer, optimizer, state, device):
    import torch
    parent = output/'checkpoints'
    parent.mkdir(parents=True, exist_ok=True)
    # Only the lock owner enters this function; abandoned writes are disposable.
    for abandoned in parent.glob('.saving-*'):
        shutil.rmtree(abandoned)
    temp = parent/('.saving-'+uuid.uuid4().hex)
    temp.mkdir()
    model.save_pretrained(temp/'model', safe_serialization=True)
    tokenizer.save_pretrained(temp/'model')
    torch.save({'optimizer':optimizer.state_dict(), 'torch_rng':torch.get_rng_state(),
                'mps_rng':torch.mps.get_rng_state().cpu() if device=='mps' else None,
                'cuda_rng':torch.cuda.get_rng_state_all() if device=='cuda' else None}, temp/'optimizer.pt')
    write_json(temp/'state.json', state)
    write_json(temp/'CHECKSUMS.json', {p.relative_to(temp).as_posix():digest(p) for p in temp.rglob('*') if p.is_file()})
    replace_directory(temp, parent/'latest')


def load_resume(path, expected):
    previous = path.with_name(path.name+'.previous')
    if not path.exists() and previous.exists():
        previous.rename(path)
    checks = json.loads((path/'CHECKSUMS.json').read_text())
    for relative, value in checks.items():
        target = (path/relative).resolve()
        require(path.resolve() in target.parents and digest(target)==value, 'Checkpoint checksum mismatch')
    state = json.loads((path/'state.json').read_text())
    for key in ('data_manifest_sha256','source_model_sha256','tokenizer_sha256','config_fingerprint','code_sha256'):
        require(state[key]==expected[key], f'Resume mismatch: {key}')
    return state


def run(config, expected, data, resume=None, stop_after=None):
    # This function is called only after the CLI requires an explicit --run.
    import torch
    from training.evaluate import evaluate_model
    from training.runtime import free_cache, gradient_cached_backward, load_encoder
    output = Path(config['output_dir'])
    if output.exists() and any(output.iterdir()) and not resume:
        raise ValueError('Run output already exists; resume explicitly or choose a new output_dir')
    output.mkdir(parents=True, exist_ok=True)
    require(shutil.disk_usage(output).free >= 4*1024**3, 'Need >=4 GiB free for atomic checkpoints')
    with (output/'.run.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('This training run is already active') from None
        torch.manual_seed(config['seed'])
        state = load_resume(resume, expected) if resume else {**expected, 'epoch':0, 'next_batch':0,
            'global_step':0, 'history':[], 'best_validation_mrr':-1., 'device':None}
        model, tokenizer, device = load_encoder(config, resume/'model' if resume else None)
        state['device'] = device
        state['training_started'] = True
        named = list(model.named_parameters())
        groups = [{'params':[p for n,p in named if not ('bias' in n or 'LayerNorm.weight' in n)], 'weight_decay':config['weight_decay']},
                  {'params':[p for n,p in named if 'bias' in n or 'LayerNorm.weight' in n], 'weight_decay':0.}]
        optimizer = torch.optim.AdamW(groups, lr=config['learning_rate'], foreach=False)
        if resume:
            # Trusted local checkpoints only; never load arbitrary pickle code.
            saved = torch.load(resume/'optimizer.pt', map_location='cpu', weights_only=True)
            optimizer.load_state_dict(saved['optimizer'])
            torch.set_rng_state(saved['torch_rng'])
            if device=='mps' and saved['mps_rng'] is not None:
                torch.mps.set_rng_state(saved['mps_rng'])
            if device=='cuda' and saved['cuda_rng'] is not None:
                torch.cuda.set_rng_state_all(saved['cuda_rng'])
            del saved
        else:
            baseline = evaluate_model(model, tokenizer, config, device)
            state['baseline_validation'] = baseline
            write_json(output/'baseline-validation.json', baseline)
        write_json(output/'resolved-config.json', config)
        stop = {'requested':False}
        def request_stop(signum, frame):
            stop['requested'] = True
        old_signals = {s:signal.signal(s, request_stop) for s in (signal.SIGINT, signal.SIGTERM)}
        started = time.monotonic()
        try:
            if not resume:
                # An OOM before update 100 can still resume from a complete base.
                save_checkpoint(output, model, tokenizer, optimizer, state, device)
            while state['epoch'] < config['epochs']:
                epoch = state['epoch']
                indices = list(range(len(data['train'])))
                random.Random(config['seed']+epoch).shuffle(indices)
                schedule = batches(indices, config['logical_batch_size'])
                for batch_index in range(state['next_batch'], len(schedule)):
                    rows = [data['train'][i] for i in schedule[batch_index]]
                    optimizer.zero_grad(set_to_none=True)
                    for group in optimizer.param_groups:
                        group['lr'] = config['learning_rate']*learning_rate_factor(state['global_step'], expected['total_updates'], config['warmup_fraction'])
                    loss = gradient_cached_backward(model, tokenizer, rows, config, device)
                    grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), config['max_grad_norm'])
                    require(bool(torch.isfinite(grad_norm)), 'Non-finite model gradient; checkpoint was not advanced')
                    optimizer.step()
                    optimizer.zero_grad(set_to_none=True)
                    state.update(next_batch=batch_index+1, global_step=state['global_step']+1)
                    free_cache(device)
                    event = {'epoch':epoch+1, 'update':state['global_step'], 'loss':loss,
                             'grad_norm':float(grad_norm.detach().cpu()), 'seconds':round(time.monotonic()-started, 3)}
                    with (output/'updates.jsonl').open('a') as stream:
                        stream.write(json.dumps(event)+'\n')
                    if state['global_step']%10==0:
                        print(json.dumps(event), flush=True)
                    stopping = stop['requested'] or (stop_after is not None and state['global_step']>=stop_after)
                    if stopping or state['global_step']%config['checkpoint_every_updates']==0:
                        save_checkpoint(output, model, tokenizer, optimizer, state, device)
                    if stopping:
                        write_json(output/'run-status.json', {'status':'stopped_after_complete_update', 'global_step':state['global_step']})
                        return
                validation = evaluate_model(model, tokenizer, config, device)
                state['history'].append({'epoch':epoch+1, 'validation':validation})
                score = validation['mrr@10']
                if score > state['best_validation_mrr']:
                    state['best_validation_mrr'] = score
                    temp = output/('.best-'+uuid.uuid4().hex)
                    model.save_pretrained(temp/'model', safe_serialization=True)
                    tokenizer.save_pretrained(temp/'model')
                    write_json(temp/'validation.json', validation)
                    replace_directory(temp, output/'best')
                state.update(epoch=epoch+1, next_batch=0)
                save_checkpoint(output, model, tokenizer, optimizer, state, device)
                write_json(output/'history.json', state['history'])
            write_json(output/'run-status.json', {'status':'completed_not_promoted',
                'global_step':state['global_step'], 'best_validation_mrr':state['best_validation_mrr'],
                'baseline_validation_mrr':state['baseline_validation']['mrr@10'],
                'production_changed':False, 'test_split_evaluated':False,
                'finished_at':datetime.now(timezone.utc).isoformat()})
        finally:
            for sig, handler in old_signals.items():
                signal.signal(sig, handler)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).parent/'configs/mac-m4.json')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-only', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--resume', type=Path)
    parser.add_argument('--stop-after-updates', type=int)
    args = parser.parse_args()
    parser.error('--resume requires --run') if args.resume and not args.run else None
    config = load_config(args.config)
    expected, data = plan(config)
    print(json.dumps(expected, ensure_ascii=False, indent=2), flush=True)
    if args.run:
        run(config, expected, data, args.resume.resolve() if args.resume else None, args.stop_after_updates)
