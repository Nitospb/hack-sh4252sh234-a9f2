"""Local ONNX inference. Text never leaves the machine."""
import hashlib
import json
import time
from pathlib import Path
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

ROOT=Path(__file__).resolve().parent


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


class OnnxTextModel:
    def __init__(self,kind,threads=4):
        self.kind=kind
        filename='e5-small-int8.onnx' if kind=='embedding' else 'reranker-int8.onnx'
        tok='e5-tokenizer' if kind=='embedding' else 'reranker-tokenizer'
        self.path=ROOT/'models'/filename
        self.tokenizer=Tokenizer.from_file(str(ROOT/'models'/tok/'tokenizer.json'))
        self.raw_tokenizer=Tokenizer.from_file(str(ROOT/'models'/tok/'tokenizer.json'))
        self.tokenizer.enable_padding(pad_id=1,pad_token='<pad>')
        options=ort.SessionOptions();options.intra_op_num_threads=threads;options.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(self.path),options,providers=['CPUExecutionProvider'])
        self.input_names={x.name for x in self.session.get_inputs()}

    def embed(self,texts,batch_size=24,max_length=384,progress=''):
        self.tokenizer.no_padding();self.tokenizer.enable_truncation(max_length=max_length)
        enc=[self.tokenizer.encode(t) for t in texts]
        return self._run_encoded(enc,sorted(range(len(enc)),key=lambda i:len(enc[i].ids)),batch_size,progress)

    def rerank(self,pairs,batch_size=24,max_length=384,progress=''):
        self.tokenizer.no_padding();self.tokenizer.enable_truncation(max_length=max_length,strategy='longest_first')
        enc=[self.tokenizer.encode(a,b) for a,b in pairs]
        return self._run_encoded(enc,sorted(range(len(enc)),key=lambda i:len(enc[i].ids)),batch_size,progress)

    def _run_encoded(self,enc,order,batch_size,progress):
        if not enc:return np.zeros((0,384),dtype=np.float32) if self.kind=='embedding' else np.zeros(0,dtype=np.float32)
        result=np.empty((len(enc),384),np.float32) if self.kind=='embedding' else np.empty(len(enc),np.float32)
        start=time.time();last_log=start
        for offset in range(0,len(order),batch_size):
            idx=order[offset:offset+batch_size];length=max(len(enc[i].ids) for i in idx)
            ids=np.ones((len(idx),length),np.int64);mask=np.zeros_like(ids);types=np.zeros_like(ids)
            for j,i in enumerate(idx):
                n=len(enc[i].ids);ids[j,:n]=enc[i].ids;mask[j,:n]=enc[i].attention_mask;types[j,:n]=enc[i].type_ids
            feed={k:v for k,v in [('input_ids',ids),('attention_mask',mask),('token_type_ids',types)] if k in self.input_names}
            raw=self.session.run(None,feed)[0]
            if self.kind=='embedding':
                vectors=(raw*mask[:,:,None]).sum(1)/np.maximum(mask.sum(1)[:,None],1)
                vectors=vectors/np.maximum(np.linalg.norm(vectors,axis=1,keepdims=True),1e-12)
                result[idx]=vectors
            else:result[idx]=raw.reshape(-1)
            now=time.time()
            if progress and (now-last_log>=20 or offset+batch_size>=len(order)):
                print(f'{progress}: {min(offset+batch_size,len(order))}/{len(order)}; {now-start:.1f}s',flush=True);last_log=now
        return result

    def article_chunks(self,title,text,size=256,overlap=32):
        # Offsets refer to the exact source text; all body tokens are covered.
        title_tokens=self.raw_tokenizer.encode(title,add_special_tokens=False)
        if len(title_tokens.ids)>64:
            title=title[:title_tokens.offsets[63][1]]
        encoded=self.raw_tokenizer.encode(text,add_special_tokens=False)
        if not encoded.ids:return [{'text':title,'body_start':0,'body_end':0}]
        chunks=[]
        for start in range(0,len(encoded.ids),size-overlap):
            end=min(start+size,len(encoded.ids));a=encoded.offsets[start][0];b=encoded.offsets[end-1][1]
            chunks.append({'text':title+'\n'+text[a:b],'body_start':a,'body_end':b})
            if end==len(encoded.ids):break
        return chunks


class TorchE5Model(OnnxTextModel):
    """Original checkpoint, local Apple GPU. CPU ONNX remains a reproducible fallback."""
    def __init__(self, model_dir=None, device='mps'):
        import torch
        from transformers import AutoModel
        if device=='mps' and not torch.backends.mps.is_available():raise RuntimeError('MPS unavailable: use a CPU backend.')
        if device=='cuda' and not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
        self.device=device
        checkpoint=Path(model_dir) if model_dir else ROOT/'models/e5-torch'
        tokenizer_dir=checkpoint if (checkpoint/'tokenizer.json').exists() else ROOT/'models/e5-tokenizer'
        self.kind='embedding';self.torch=torch;self.path=checkpoint/'model.safetensors'
        # Leave unified memory for macOS and the browser. Never disable MPS limits.
        if device=='mps':torch.mps.set_per_process_memory_fraction(.65)
        self.tokenizer=Tokenizer.from_file(str(tokenizer_dir/'tokenizer.json'))
        self.raw_tokenizer=Tokenizer.from_file(str(tokenizer_dir/'tokenizer.json'))
        self.model=AutoModel.from_pretrained(str(checkpoint),local_files_only=True,trust_remote_code=False,torch_dtype=torch.float32 if device=='cpu' else torch.float16,attn_implementation='sdpa').to(device).eval()
        torch.set_num_threads(2)

    def _run_encoded(self,enc,order,batch_size,progress):
        torch=self.torch
        result=np.empty((len(enc),384),np.float32);start=time.time();last_log=start
        if not enc:return result
        # Fixed padded shape bounds MPS graph/allocator caches on long runs.
        # Attention masks keep padding out of attention and mean pooling.
        length=max(len(e.ids) for e in enc)
        batch_size=min(batch_size,8)
        with torch.inference_mode():
            for offset in range(0,len(order),batch_size):
                idx=order[offset:offset+batch_size]
                ids=np.ones((len(idx),length),np.int64);mask=np.zeros_like(ids);types=np.zeros_like(ids)
                for j,i in enumerate(idx):
                    n=len(enc[i].ids);ids[j,:n]=enc[i].ids;mask[j,:n]=enc[i].attention_mask;types[j,:n]=enc[i].type_ids
                feed={'input_ids':torch.from_numpy(ids).to(self.device),'attention_mask':torch.from_numpy(mask).to(self.device),'token_type_ids':torch.from_numpy(types).to(self.device)}
                hidden=self.model(**feed).last_hidden_state.float();weights=feed['attention_mask'].unsqueeze(-1)
                vectors=(hidden*weights).sum(1)/weights.sum(1).clamp(min=1)
                vectors=torch.nn.functional.normalize(vectors,p=2,dim=1)
                result[idx]=vectors.cpu().numpy()
                del feed, hidden, weights, vectors
                if self.device=='mps' and torch.mps.driver_allocated_memory()>3*1024**3:
                    torch.mps.empty_cache()
                now=time.time()
                if progress and (now-last_log>=20 or offset+batch_size>=len(order)):
                    print(f'{progress} {self.device.upper()}: {min(offset+batch_size,len(order))}/{len(order)}; {now-start:.1f}s',flush=True);last_log=now
        return result
