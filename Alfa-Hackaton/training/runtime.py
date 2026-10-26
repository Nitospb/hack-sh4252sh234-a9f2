"""Local E5 encoder and exact feature-gradient replay with dropout disabled."""
from pathlib import Path
from training.common import require


def device_for(config):
    import torch
    requested = config['device']
    if requested == 'auto':
        requested = 'cuda' if torch.cuda.is_available() else ('mps' if torch.backends.mps.is_available() else 'cpu')
    if requested == 'mps':
        require(torch.backends.mps.is_available(), 'MPS is unavailable')
        torch.mps.set_per_process_memory_fraction(config['mps_memory_fraction'])
    if requested == 'cuda':
        require(torch.cuda.is_available(), 'CUDA is unavailable')
    torch.set_num_threads(2)
    return requested


def load_encoder(config, model_dir=None):
    import torch
    from transformers import AutoModel, AutoTokenizer
    device = device_for(config)
    path = Path(model_dir or config['model_dir'])
    tokenizer_path = path if (path/'tokenizer.json').exists() else Path(config['tokenizer_dir'])
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, local_files_only=True, trust_remote_code=False)
    model = AutoModel.from_pretrained(path, local_files_only=True, trust_remote_code=False,
                                      torch_dtype=torch.float32, attn_implementation='sdpa').to(device)
    # eval() disables dropout, not autograd. Both cache and replay see the same
    # function, so no RNG replay is required and cached gradients remain exact.
    model.eval()
    return model, tokenizer, device


def pooled(model, batch):
    import torch
    hidden = model(**batch).last_hidden_state.float()
    mask = batch['attention_mask'].unsqueeze(-1)
    vector = (hidden*mask).sum(1)/mask.sum(1).clamp(min=1)
    return torch.nn.functional.normalize(vector, p=2, dim=1)


def token_batches(tokenizer, texts, config):
    size = config['micro_batch_size']
    return [tokenizer(texts[i:i+size], padding='max_length', truncation=True,
                      max_length=config['max_length'], return_tensors='pt')
            for i in range(0, len(texts), size)]


def free_cache(device):
    if device == 'mps':
        import torch
        torch.mps.empty_cache()


def encode(model, tokenizer, texts, config, device):
    import numpy as np
    import torch
    values = []
    with torch.no_grad():
        for batch in token_batches(tokenizer, texts, config):
            moved = {k: v.to(device) for k, v in batch.items()}
            vector = pooled(model, moved)
            require(bool(torch.isfinite(vector).all()), 'Non-finite evaluation embedding')
            values.append(vector.cpu().numpy())
            del moved, vector
            free_cache(device)
    return np.concatenate(values) if values else np.empty((0, model.config.hidden_size), np.float32)


def document_chunks(tokenizer, article):
    """Same 256/32 body coverage and 64-token title policy as catalog inference."""
    title = article['title'][:500]
    title_tokens = tokenizer(title, add_special_tokens=False, return_offsets_mapping=True)
    if len(title_tokens['input_ids']) > 64:
        title = title[:title_tokens['offset_mapping'][63][1]]
    offsets = tokenizer(article['text'], add_special_tokens=False, return_offsets_mapping=True)['offset_mapping']
    if not offsets:
        return [title]
    values = []
    for start in range(0, len(offsets), 224):
        end = min(start+256, len(offsets))
        values.append(title+'\n'+article['text'][offsets[start][0]:offsets[end-1][1]])
        if end == len(offsets):
            break
    return values


def feature_loss(features, rows, config):
    import torch
    import torch.nn.functional as F
    size = len(rows)
    query, positive = features[:size], features[size:2*size]
    if config['mode'] == 'weak_title_body':
        scores = query @ positive.T / config['temperature']
        # Equal short headlines need not be negatives even if copy heuristics did
        # not merge the stories. Retain the paired positive and mask those peers.
        names = [' '.join(row['query'].casefold().split()) for row in rows]
        duplicate = torch.tensor([[i!=j and a==b for j,b in enumerate(names)] for i,a in enumerate(names)],
                                 dtype=torch.bool, device=scores.device)
        scores = scores.masked_fill(duplicate, float('-inf'))
        return F.cross_entropy(scores, torch.arange(size, device=scores.device))
    negative = features[2*size:]
    difference = ((query*negative).sum(1)-(query*positive).sum(1))/config['temperature']
    # Only the human-approved negative for this query is a negative. Other
    # queries' unjudged examples are never silently given a negative label.
    return F.softplus(difference).mean()


def gradient_cached_backward(model, tokenizer, rows, config, device):
    """Backward only. The caller owns zero_grad, clipping and optimizer.step."""
    import torch
    require(not model.training, 'Gradient replay requires disabled dropout: keep model.eval()')
    texts = ['query: '+r['query'] for r in rows]+['passage: '+r['positive'] for r in rows]
    if config['mode'] == 'supervised_objects':
        texts += ['passage: '+r['negative'] for r in rows]
    batches = token_batches(tokenizer, texts, config)
    cached = []
    with torch.no_grad():
        for batch in batches:
            moved = {k: v.to(device) for k,v in batch.items()}
            cached.append(pooled(model, moved).detach().cpu())
            del moved
            free_cache(device)
    features = torch.cat(cached).to(device).requires_grad_(True)
    loss = feature_loss(features, rows, config)
    require(bool(torch.isfinite(loss)), 'Non-finite contrastive loss')
    (embedding_gradient,) = torch.autograd.grad(loss, features)
    value = float(loss.detach().cpu())
    gradient = embedding_gradient.detach().cpu()
    del features, embedding_gradient, loss, cached
    offset = 0
    for batch in batches:
        moved = {k: v.to(device) for k,v in batch.items()}
        vectors = pooled(model, moved)
        count = len(vectors)
        # The loss gradient already includes the logical-batch mean. Do not
        # divide it by micro-batch count again.
        surrogate = (vectors*gradient[offset:offset+count].to(device)).sum()
        surrogate.backward()
        offset += count
        del moved, vectors, surrogate
        free_cache(device)
    return value
