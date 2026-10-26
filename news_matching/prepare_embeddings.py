"""Embed original topics and every article chunk with multilingual E5; deterministic local cache."""
import argparse
import json
import time
from collections import Counter
from pathlib import Path
import numpy as np
from model_backend import ROOT,OnnxTextModel,TorchE5Model,sha256


def load(path):
    with Path(path).open(encoding='utf-8') as stream:
        return [json.loads(l) for l in stream if l.strip()]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--backend',choices=['cpu','mps'],default='cpu');args=parser.parse_args()
    output=ROOT/'output';output.mkdir(exist_ok=True)
    topic_file=ROOT.parent/'taxonomy/output/business_topics.jsonl'
    article_file=ROOT/'input/data/articles-all.jsonl'
    topics=load(topic_file);articles=load(article_file)
    assert len(topics)==10000 and len({t['topic_id'] for t in topics})==10000
    assert len(articles)==3446 and len({a['id'] for a in articles})==3446
    model=TorchE5Model() if args.backend=='mps' else OnnxTextModel('embedding',threads=4)
    fingerprint={'model_sha256':sha256(model.path),'topic_file_sha256':sha256(topic_file),'article_file_sha256':sha256(article_file),
                 'prefixes':{'topics':'query:','articles':'passage:'},'body_chunk_tokens':256,'body_overlap_tokens':32,
                 'title_max_tokens':64,'max_model_tokens':384,'embedding_dim':384,'encoder':'intfloat/multilingual-e5-small','pooling':'attention_mask_mean_then_l2',
                 'torch_version':str(model.torch.__version__) if args.backend=='mps' else None,'transformers_version':'4.46.3' if args.backend=='mps' else None,'onnxruntime':'1.19.2','quantization':'original_weights_fp16_inference_fp32_pooling' if args.backend=='mps' else 'original_repo_qint8_avx512_vnni','device':'local Apple MPS' if args.backend=='mps' else 'local CPU'}
    previous=output/'embedding_metadata.json'
    if previous.exists() and json.loads(previous.read_text()).get('fingerprint')==fingerprint and (output/'article_chunk_embeddings.npy').exists():
        print('Embedding cache verified by source/model hashes; reuse',flush=True);return
    start=time.time()
    texts=['query: '+t['sector_name']+'. '+t['name']+'. '+', '.join(t['object_keywords']) for t in topics]
    vectors=model.embed(texts,max_length=160,batch_size=32,progress='Topic embeddings')
    assert vectors.shape==(10000,384) and np.all(np.isfinite(vectors))
    np.save(output/'topic_embeddings.npy',vectors)
    (output/'topic_embedding_index.json').write_text(json.dumps([t['topic_id'] for t in topics])+'\n')
    chunks=[];counts=Counter();max_title_chars=500
    for a in articles:
        for i,c in enumerate(model.article_chunks(a['title'][:max_title_chars],a['text'])):
            chunks.append({'article_id':a['id'],'content_hash':a['content_hash'],'chunk_index':i,**c});counts[a['id']]+=1
    with (output/'article_chunks.jsonl').open('w') as f:
        for c in chunks:f.write(json.dumps(c,ensure_ascii=False)+'\n')
    print('Articles',len(articles),'chunks',len(chunks),'max chunks/article',max(counts.values()),flush=True)
    vectors=model.embed(['passage: '+c['text'] for c in chunks],max_length=384,batch_size=24,progress='Article chunk embeddings')
    assert vectors.shape==(len(chunks),384) and np.all(np.isfinite(vectors))
    np.save(output/'article_chunk_embeddings.npy',vectors)
    (output/'embedding_metadata.json').write_text(json.dumps({'fingerprint':fingerprint,'articles':len(articles),'topics':len(topics),'chunks':len(chunks),
        'max_chunks_per_article':max(counts.values()),'full_body_token_coverage':True,'max_title_chars':max_title_chars,
        'seconds':round(time.time()-start,2),'topic_vectors_sha256':sha256(output/'topic_embeddings.npy'),
        'chunk_vectors_sha256':sha256(output/'article_chunk_embeddings.npy')},ensure_ascii=False,indent=2)+'\n')
    print('Embedding phase finished',round(time.time()-start,1),'seconds',flush=True)


if __name__=='__main__':main()
