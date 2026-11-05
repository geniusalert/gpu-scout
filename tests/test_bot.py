import unittest, os, asyncio
from unittest.mock import AsyncMock
from bot import Scout, Criteria, render

class Tests(unittest.TestCase):
    def test_validation(self):
        with self.assertRaises(ValueError): Criteria('H100',0)
        with self.assertRaises(ValueError): Criteria('H100',1,-2)
    def test_owner_isolation(self):
        s=Scout(':memory:'); s.save(123,Criteria('H100'))
        self.assertEqual(s.db.execute('SELECT count(*) FROM tasks WHERE owner=456').fetchone()[0],0)
    def test_budget_and_ranking(self):
        s=Scout(':memory:'); s.demo=False
        os.environ['VAST_API_KEY']='test-placeholder'
        s.request=AsyncMock(return_value={'offers':[{'id':1,'num_gpus':8,'dph_total':24},{'id':2,'num_gpus':8,'dph_total':16},{'id':3,'num_gpus':4,'dph_total':4}]})
        result=asyncio.run(s.search_vast(Criteria('H100',8,2.5)))
        self.assertEqual([o['id'] for o in result],[2])
    def test_demo_label(self):
        s=Scout(':memory:'); s.demo=True
        self.assertIn('SIMULATED',render(asyncio.run(s.search(Criteria('H100',8,2)))))
if __name__=='__main__': unittest.main()
