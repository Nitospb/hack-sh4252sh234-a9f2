"""Index the 1000 existing object groups of the ORIGINAL 10000 topics; no new business topics."""
import json
from model_backend import ROOT,TorchE5Model,sha256
from prepare_embeddings import load
import numpy as np


def main():
    topics=load(ROOT.parent/'taxonomy/output/business_topics.jsonl');families={}
    for t in topics:
        key=t['sector_id']+'::'+t['object']
        family=families.setdefault(key,dict(family_key=key,sector_id=t['sector_id'],sector_name=t['sector_name'],object=t['object'],object_keywords=t['object_keywords'],member_topic_ids=[]))
        family['member_topic_ids'].append(t['topic_id'])
    families=list(families.values());assert len(families)==1000 and all(len(f['member_topic_ids'])==10 for f in families)
    model=TorchE5Model();metadata=json.loads((ROOT/'output/embedding_metadata.json').read_text())
    assert sha256(model.path)==metadata['fingerprint']['model_sha256']
    vectors=model.embed(['query: '+f['object']+'. '+f['sector_name']+'. '+', '.join(f['object_keywords']) for f in families],max_length=160,batch_size=32,progress='Existing object-group embeddings')
    np.save(ROOT/'output/object_family_embeddings.npy',vectors)
    (ROOT/'output/object_families.json').write_text(json.dumps(families,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'output/object_family_embedding_metadata.json').write_text(json.dumps({'model_sha256':metadata['fingerprint']['model_sha256'],'families':1000,'member_topics':10000,'source':'Grouping existing sector_id/object fields; NOT added topics','vectors_sha256':sha256(ROOT/'output/object_family_embeddings.npy')},indent=2)+'\n')


if __name__=='__main__':main()
