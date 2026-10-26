"""Synthetic gradient arithmetic only: no E5 weights, optimizer or updates."""
from types import SimpleNamespace
import unittest
import torch
from training.runtime import feature_loss, gradient_cached_backward, pooled


class Tokenizer:
    def __call__(self, texts, **kwargs):
        size = kwargs['max_length']
        values = [[(ord(c)%30)+1 for c in text][:size] for text in texts]
        ids = torch.tensor([row+[0]*(size-len(row)) for row in values])
        return {'input_ids':ids,'attention_mask':(ids!=0).long()}


class TinyEncoder(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.embedding = torch.nn.Embedding(32,8)
        self.projection = torch.nn.Linear(8,8)
    def forward(self,input_ids,attention_mask):
        return SimpleNamespace(last_hidden_state=self.projection(self.embedding(input_ids)))


class ReplayTests(unittest.TestCase):
    def compare_gradient(self, mode):
        torch.manual_seed(9)
        model = TinyEncoder().eval()
        tokenizer = Tokenizer()
        config = {'mode':mode,'micro_batch_size':2,'max_length':32,'temperature':.05}
        rows = [{'query':'query '+str(i), 'positive':'body '+str(i)+' details', 'negative':'other '+str(i)} for i in range(3)]
        texts = ['query: '+r['query'] for r in rows]+['passage: '+r['positive'] for r in rows]
        if mode=='supervised_objects':texts += ['passage: '+r['negative'] for r in rows]
        loss = feature_loss(pooled(model, tokenizer(texts,max_length=32)),rows,config)
        loss.backward()
        expected = [p.grad.clone() for p in model.parameters()]
        model.zero_grad(set_to_none=True)
        actual_loss = gradient_cached_backward(model,tokenizer,rows,config,'cpu')
        self.assertAlmostEqual(float(loss.detach()),actual_loss,places=5)
        for parameter, gradient in zip(model.parameters(),expected):
            self.assertTrue(torch.allclose(parameter.grad,gradient,atol=2e-5,rtol=2e-5))

    def test_full_batch_matches_cached_replay_weak(self):
        self.compare_gradient('weak_title_body')
    def test_full_batch_matches_cached_replay_supervised(self):
        self.compare_gradient('supervised_objects')
    def test_dropout_mode_required(self):
        with self.assertRaises(ValueError):
            gradient_cached_backward(TinyEncoder().train(),Tokenizer(),[],{},'cpu')


if __name__=='__main__':unittest.main()
