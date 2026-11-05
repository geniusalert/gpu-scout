import unittest, asyncio, sqlite3, os
from unittest.mock import AsyncMock, patch
from integrations import Outreach, lambda_search
from bot import Criteria, Scout

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.request=AsyncMock(return_value={'thread_id':'thread'})
        self.o=Outreach(self.db,self.request)
        self.o.draft(1,1,'supplier@example.com','Exact reviewed body')
        self.token=self.db.execute('SELECT id FROM inquiries').fetchone()[0]
    def test_ownership(self):
        with self.assertRaises(ValueError): asyncio.run(self.o.approve(2,self.token,False))
        self.request.assert_not_called()
    def test_demo_no_send(self):
        with self.assertRaises(ValueError): asyncio.run(self.o.approve(1,self.token,True))
        self.request.assert_not_called()
    @patch.dict(os.environ,{'AGENTMAIL_API_KEY':'test','AGENTMAIL_INBOX_ID':'test@example.com'})
    def test_single_send(self):
        asyncio.run(self.o.approve(1,self.token,False))
        with self.assertRaises(ValueError): asyncio.run(self.o.approve(1,self.token,False))
        self.assertEqual(self.request.call_count,1)
        self.assertEqual(self.request.call_args.kwargs['json']['text'],'Exact reviewed body')
    @patch.dict(os.environ,{'AGENTMAIL_API_KEY':'test','AGENTMAIL_INBOX_ID':'test@example.com'})
    def test_ambiguous_failure_no_retry(self):
        self.request.side_effect=TimeoutError()
        for _ in range(2):
            with self.assertRaises(ValueError): asyncio.run(self.o.approve(1,self.token,False))
        self.assertEqual(self.request.call_count,1)
    @patch.dict(os.environ,{'LAMBDA_API_KEY':'test'})
    def test_lambda_capacity(self):
        self.request.return_value={'data':{'h':{'instance_type':{'name':'h','gpu_description':'H100 SXM','specs':{'gpus':8},'price_cents_per_hour':1600},'regions_with_capacity_available':[{'name':'us-east-1'},{'name':'eu-west-1'}]}}}
        out=asyncio.run(lambda_search(Criteria('H100_SXM',8,2.5,'US'),self.request))
        self.assertEqual(len(out),1);self.assertEqual(out[0]['dph_total'],16)
    @patch.dict(os.environ,{'VAST_API_KEY':'test','LAMBDA_API_KEY':'test'})
    def test_cross_provider_failure(self):
        s=Scout(':memory:');s.demo=False;s.search_vast=AsyncMock(side_effect=TimeoutError())
        with patch('bot.lambda_search',AsyncMock(return_value=[dict(id='l',num_gpus=8,dph_total=16)])):
            out=asyncio.run(s.search(Criteria('H100',8,3)))
        self.assertEqual(out[0]['provider'],'Lambda');self.assertIn('Vast.ai: unavailable',s.coverage)
