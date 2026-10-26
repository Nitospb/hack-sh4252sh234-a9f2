import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
# build.py is also a documented standalone script with local module imports.
sys.path.insert(0,str(ROOT/'pipeline'))
spec=importlib.util.spec_from_file_location('live_build_under_test',ROOT/'pipeline/build.py')
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)


class IncrementalEmbeddingTests(unittest.TestCase):
    def test_only_new_content_is_encoded_with_same_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/'news_matching/output';old.mkdir(parents=True)
            reuse=root/'previous';reuse.mkdir();out=root/'candidate';out.mkdir()
            model=root/'encoder';model.write_bytes(b'original checkpoint');sha=build.sha256(model)
            vector=np.zeros(384,dtype=np.float32);vector[0]=1
            np.save(old/'object_family_embeddings.npy',np.asarray([vector]))
            (old/'object_families.json').write_text(json.dumps([{'object':'test'}]))
            (old/'object_family_embedding_metadata.json').write_text(json.dumps({'model_sha256':sha}))
            (reuse/'embedding_metadata.json').write_text(json.dumps({'fingerprint':{'model_sha256':sha}}))
            (reuse/'article_chunks.jsonl').write_text(json.dumps({'article_id':'old','content_hash':'v1','text':'unchanged'})+'\n')
            np.save(reuse/'article_chunk_embeddings.npy',np.asarray([vector]))
            encoded=[]
            class Model:
                path=model
                def article_chunks(self,title,text):return [{'text':title+' '+text}]
                def embed(self,texts,**kwargs):encoded.extend(texts);return np.asarray([vector for _ in texts])
            articles=[{'id':'old','content_hash':'v1','title':'Original','text':'unchanged'},
                      {'id':'new','content_hash':'v2','title':'New','text':'fresh'}]
            with patch.object(build,'ROOT',root),patch.object(build,'OUT',out),patch.object(build,'TorchE5Model',return_value=Model()):
                chunks,matrix,_,_=build.embeddings(articles,'mps',reuse_from=reuse)
            self.assertEqual(encoded,['passage: New fresh'])
            self.assertEqual(matrix.shape,(2,384))
            self.assertEqual(chunks[0]['content_hash'],'v1')
            metadata=json.loads((out/'embedding_metadata.json').read_text())
            self.assertEqual((metadata['reused'],metadata['new']),(1,1))
