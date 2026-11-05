import asyncio,unittest
from unittest.mock import patch
from bot import Scout
class ParsingTests(unittest.TestCase):
 def test_natural_request(self):
  with patch.dict('os.environ',{'KEIKI_API_KEY':''}):
   c=asyncio.run(Scout(':memory:').parse('Find me 8 H100 SXM GPUs in US for 3 months under $2.50 per GPU-hour',1))
  self.assertEqual((c.gpu,c.count,c.max_price,c.region,c.duration),('H100_SXM',8,2.5,'US','3 months'))
 def test_missing_count_is_clear(self):
  with patch.dict('os.environ',{'KEIKI_API_KEY':''}):
   with self.assertRaisesRegex(ValueError,'quantity'):
    asyncio.run(Scout(':memory:').parse('H100 under $2',1))
