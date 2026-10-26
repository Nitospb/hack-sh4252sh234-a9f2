"""Evaluate a candidate against held-out retrieval tasks, never update weights."""
import argparse
from collections import defaultdict
from pathlib import Path

from training.common import digest, load_config, read_jsonl, require, retrieval_metrics, verify_bundle, write_json
from training.runtime import document_chunks, encode, load_encoder


def evaluate_model(model, tokenizer, config, device, split='validation'):
    directory = Path(config['data_dir'])
    if config['mode'] == 'weak_title_body':
        rows = read_jsonl(directory/f'weak/{split}.jsonl')
        require(len(rows) >= 2, 'Weak holdout needs >=2 distinct stories')
        queries = ['query: '+r['query'] for r in rows]
        documents = ['passage: '+r['positive'] for r in rows]
        relevant = [{i} for i in range(len(rows))]
        scores = encode(model, tokenizer, queries, config, device) @ encode(model, tokenizer, documents, config, device).T
        metrics = retrieval_metrics(scores, relevant)
        return {**metrics, 'split': split, 'mode': config['mode'], 'documents': len(documents),
                'meaning': 'Title-to-body retrieval on unseen news; NOT measured business-topic relevance',
                'telegram_records': 0}
    stories = {r['id']: r for r in read_jsonl(directory/'corpus/stories.jsonl')}
    families = {r['family_key']: r for r in __import__('json').loads((directory/'taxonomy/object_families.json').read_text())}
    labels = read_jsonl(directory/f'supervised/{split}-qrels.jsonl')
    by_query = defaultdict(list)
    for row in labels:
        if row['judgment'] in (0, 2):
            by_query[row['family_key']].append(row)
    results = []
    documents = 0
    for key, judgments in sorted(by_query.items()):
        if not any(r['judgment']==2 for r in judgments) or not any(r['judgment']==0 for r in judgments):
            continue
        family = families[key]
        query = family['object']+'. '+family['sector_name']+'. '+', '.join(family.get('object_keywords', []))
        docs = [stories[r['article_id']] for r in judgments]
        q = encode(model, tokenizer, ['query: '+query], config, device)
        # Never use human evidence to select evaluation text: score all chunks.
        scores = []
        for article in docs:
            chunks = document_chunks(tokenizer, article)
            vectors = encode(model, tokenizer, ['passage: '+text for text in chunks], config, device)
            scores.append(float((q@vectors.T).max()))
        positive = {i for i,r in enumerate(judgments) if r['judgment']==2}
        results.append(retrieval_metrics([scores], [positive]))
        documents += len(docs)
    require(results, 'No human-reviewed positive/negative holdout queries; annotate before supervised evaluation')
    metrics = {key: sum(r[key] for r in results)/len(results) for key in results[0] if key!='evaluated_queries'}
    return {**metrics, 'evaluated_queries':len(results), 'split':split, 'mode':config['mode'],
            'documents':documents, 'meaning':'Human judged-pool-only direct-object retrieval; unjudged and industry-only rows excluded, NOT full-catalog recall'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--model', type=Path)
    parser.add_argument('--split', choices=['validation','test'], default='validation')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    verify_bundle(config['data_dir'])
    model, tokenizer, device = load_encoder(config, args.model)
    result = evaluate_model(model, tokenizer, config, device, args.split)
    model_path = args.model or Path(config['model_dir'])
    result.update(data_manifest_sha256=digest(Path(config['data_dir'])/'manifest.json'),
                  model_sha256=digest(model_path/'model.safetensors'))
    write_json(args.output, result)
    print(result)
