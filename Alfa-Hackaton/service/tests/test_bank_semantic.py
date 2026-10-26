from pathlib import Path
import hashlib
import json
import sqlite3
import tempfile
import unittest
import numpy as np
from service import bank


class SemanticBankTests(unittest.TestCase):
    def test_event_channel_preserves_dates_hashes_and_encoder_pairing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);assets=root/'assets.sqlite';index=root/'index.sqlite'
            text='Стоимость фондирования изменилась. Компаниям следует оценить структуру обязательств.'
            vector=np.zeros(384,dtype=np.float32);vector[0]=1
            with sqlite3.connect(assets) as db:
                bank.schema(db)
                for did,date in [('current','2026-10-01'),('future','2027-01-01'),('old','2021-01-01'),('unknown',None)]:
                    db.execute('INSERT INTO bank_documents VALUES(?,?,?,?,?,1)',(did,did,'original.pdf','pdf-sha',date))
                    db.execute('INSERT INTO bank_passages VALUES(?,?,1,?,?)',(did,did,text,'ocr'))
                    db.execute('INSERT INTO bank_fts VALUES(?,?)',(did,text))
            with sqlite3.connect(index) as db:
                db.executescript('CREATE TABLE metadata(key TEXT,value TEXT);CREATE TABLE embeddings(id TEXT,text_sha256 TEXT,document_sha256 TEXT,vector BLOB);')
                db.execute('INSERT INTO metadata VALUES("report",?)',(json.dumps({'encoder_sha256':'encoder'}),))
                for did in ('current','future','old','unknown'):
                    db.execute('INSERT INTO embeddings VALUES(?,?,?,?)',(did,hashlib.sha256(text.encode()).hexdigest(),'pdf-sha',vector.tobytes()))
            args=dict(event_vector=vector,encoder_sha='encoder',semantic_index=index)
            found=bank.search(assets,'совсем иная лексика','2026-10-26T00:00:00Z',**args)
            self.assertEqual([r['id'] for r in found],['current'])
            self.assertEqual(found[0]['retrieval_methods'],['semantic_event'])
            args['encoder_sha']='wrong'
            self.assertEqual(bank.search(assets,'иная лексика','2026-10-26T00:00:00Z',**args),[])
            args['encoder_sha']='encoder'
            with sqlite3.connect(assets) as db:db.execute('UPDATE bank_passages SET text="Новая версия распознанного текста" WHERE id="current"')
            self.assertEqual(bank.search(assets,'иная лексика','2026-10-26T00:00:00Z',**args),[])
