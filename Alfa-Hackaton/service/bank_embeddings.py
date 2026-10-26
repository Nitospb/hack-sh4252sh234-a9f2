"""Offline inference-only E5 bank index paired with the serving news encoder."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import numpy as np


def build(assets,output,backend='mps'):
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/'news_matching'))
    from model_backend import TorchE5Model,sha256
    model=TorchE5Model(device=backend)
    with sqlite3.connect(Path(assets).resolve().as_uri()+'?mode=ro',uri=True) as db:
        rows=db.execute('SELECT p.id,p.text,d.sha256 FROM bank_passages p JOIN bank_documents d ON d.id=p.document_id ORDER BY p.id').fetchall()
    vectors=model.embed(['passage: '+text for _,text,_ in rows],max_length=384,batch_size=8,progress='Bank passages')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);temp=output.with_suffix('.building.sqlite');temp.unlink(missing_ok=True)
    with sqlite3.connect(temp) as db:
        db.executescript('CREATE TABLE embeddings(id TEXT PRIMARY KEY,text_sha256 TEXT,document_sha256 TEXT,vector BLOB);CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);')
        for (pid,text,document_sha),vector in zip(rows,vectors):
            db.execute('INSERT INTO embeddings VALUES(?,?,?,?)',(pid,hashlib.sha256(text.encode()).hexdigest(),document_sha,np.asarray(vector,dtype=np.float32).tobytes()))
        metadata={'encoder_sha256':sha256(model.path),'dimensions':384,'passages':len(rows),'purpose':'retrieval_inference_only','prefix':'passage: '}
        db.execute('INSERT INTO metadata VALUES(?,?)',('report',json.dumps(metadata)))
    temp.replace(output);return metadata


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--backend',choices=('mps','cpu','cuda'),default='mps')
    a=p.parse_args();print(json.dumps(build(a.assets,a.output,a.backend),indent=2))
