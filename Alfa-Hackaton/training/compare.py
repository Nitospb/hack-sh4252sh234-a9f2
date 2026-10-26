"""Compare matching held-out reports; never promotes weights or changes catalog."""
import argparse
import json
from pathlib import Path
from training.common import require, write_json


def compare(baseline, candidate):
    for key in ('mode', 'split', 'data_manifest_sha256', 'evaluated_queries', 'documents'):
        require(baseline[key]==candidate[key], f'Evaluation mismatch: {key}')
    keys = ('recall@1','recall@5','recall@10','mrr@10','ndcg@10')
    delta = {key:candidate[key]-baseline[key] for key in keys}
    return {'mode':candidate['mode'], 'split':candidate['split'], 'deltas':delta,
            'retrieval_improved':delta['mrr@10']>0 and delta['recall@10']>=0,
            'production_changed':False, 'automatic_promotion':False,
            'decision':'Manual quality review and separate candidate reindex required; weak title/body scores do not establish business-topic relevance.'}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = compare(json.loads(args.baseline.read_text()), json.loads(args.candidate.read_text()))
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
