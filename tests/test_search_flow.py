import asyncio
import json
import os
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import bot
from bot import Criteria, Scout
from research import Research, google, shortlist, hit_score
from supplier_data import schema, candidates


class SearchFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.scout=Scout(':memory:')
        self.scout.demo=False
        schema(self.scout.db)

    def tearDown(self):
        self.scout.db.close()

    def add_company(self,name,status='H100 offered / quoted',conditions='United States; allocation requires confirmation',row=2):
        data={'Company':name,'H100 / response status':status,'Pricing and evidence':'H100 SXM quote from October; reconfirm price','Conditions / availability':conditions}
        self.scout.db.execute('INSERT INTO supplier_audit VALUES(?,?,?,?)',('Companies',row,'hash',json.dumps(data)))
        self.scout.db.commit()

    async def test_find_automatically_searches_google_without_provider_keys(self):
        self.add_company('Saved supplier')
        message=SimpleNamespace(text='/find 8 H100 SXM in US under $2.50 per GPU-hour',reply_text=AsyncMock())
        update=SimpleNamespace(effective_chat=SimpleNamespace(type='private'),effective_user=SimpleNamespace(id=10),effective_message=message)
        results=[{'title':'GPU rental supplier','link':'https://gpu.example/h100','snippet':'H100 SXM in the US. Ask for a quote.'}]
        with patch.dict(os.environ,{'KEIKI_API_KEY':'','VAST_API_KEY':'','LAMBDA_API_KEY':'','ALLOWED_USER_IDS':'','SUPERMEMORY_API_KEY':''}),patch.object(bot,'scout',self.scout),patch('research.google',AsyncMock(return_value=results)) as search:
            await bot.handle(update,SimpleNamespace())
        self.assertEqual(search.await_count,3)
        replies='\n'.join(call.args[0] for call in message.reply_text.await_args_list)
        self.assertIn('https://gpu.example/h100',replies)
        self.assertIn('Saved supplier',replies)
        self.assertNotIn('not configured',replies)
        self.assertNotIn('No matching offers',replies)
        self.assertIn('/research 1',replies)

    async def test_google_failure_still_returns_saved_suppliers(self):
        self.add_company('Historical supplier')
        with patch('research.google',AsyncMock(side_effect=TimeoutError())):
            report=await Research(self.scout.db).run(1,10,Criteria('H100_SXM',8,2.5,'US'),deep=False)
        self.assertEqual(report['suppliers'][0]['name'],'Historical supplier')
        self.assertIn('could not complete',shortlist(report,1))
        self.assertIn('historical',shortlist(report,1))

    async def test_redacted_and_unavailable_companies_are_excluded(self):
        self.add_company('[redacted due to NDA]',row=2)
        self.add_company('No stock','No current H100 / priced but out of stock',row=3)
        self.add_company('Regional lead',conditions='India; H100',row=4)
        found=candidates(self.scout.db,Criteria('H100_SXM',8,2.5,'US'))
        self.assertEqual([s['name'] for s in found],['Regional lead'])
        self.assertIn('require confirmation',found[0]['fit'])

    async def test_google_relevance(self):
        criteria=Criteria('H100_SXM',8,2.5,'US')
        self.assertIsNone(hit_score({'title':'What is a GPU?', 'link':'https://aws.amazon.com/what-is/gpu/','snippet':'H100 GPU cloud'},criteria))
        supplier=hit_score({'title':'Rent H100 SXM GPUs','link':'https://gpu.example/h100','snippet':'GPU cloud pricing'},criteria)
        comparison=hit_score({'title':'H100 SXM rental prices across providers','link':'https://comparison.example/blog/h100'},criteria)
        self.assertLess(supplier,comparison)

    async def test_serper_and_serpapi_use_their_own_contracts(self):
        original_client=httpx.AsyncClient
        seen=[]
        def respond(request):
            seen.append(request)
            field='organic' if 'serper.dev' in request.url.host else 'organic_results'
            return httpx.Response(200,json={field:[{'title':'test','link':'https://gpu.example'}]})
        def client(**kwargs):
            return original_client(transport=httpx.MockTransport(respond),**kwargs)
        with patch('research.httpx.AsyncClient',client):
            with patch.dict(os.environ,{'SERPER_API_KEY':'serper-test','SERPAPI_API_KEY':''}):
                self.assertEqual(len(await google('H100')),1)
            with patch.dict(os.environ,{'SERPER_API_KEY':'','SERPAPI_API_KEY':'serpapi-test'}):
                self.assertEqual(len(await google('H100')),1)
        self.assertEqual(seen[0].headers['X-API-KEY'],'serper-test')
        self.assertEqual(seen[0].method,'POST')
        self.assertEqual(seen[1].url.params['api_key'],'serpapi-test')


class WebhookQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_webhook_acknowledges_and_deduplicates_before_research(self):
        import webhook_server
        from starlette.requests import Request
        scout=Scout(':memory:')
        scout.db.execute('CREATE TABLE telegram_updates(update_id INTEGER PRIMARY KEY,payload TEXT,state TEXT)')
        application=SimpleNamespace(process_update=AsyncMock())
        async def receive():
            return {'type':'http.request','body':b'{"update_id":123,"message":{"text":"/find H100"}}'}
        with patch.object(bot,'scout',scout),patch.object(webhook_server,'application',application),patch.dict(os.environ,{'TELEGRAM_WEBHOOK_SECRET':'test-secret'}):
            for _ in range(2):
                self.assertEqual(await webhook_server.telegram(Request({'type':'http'},receive), 'test-secret'),{'ok':True})
        application.process_update.assert_not_called()
        self.assertEqual(scout.db.execute('SELECT count(*) FROM telegram_updates').fetchone()[0],1)
        scout.db.close()
