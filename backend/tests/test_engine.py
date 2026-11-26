import tempfile
import unittest
from pathlib import Path
from eden import engine

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); engine.DB_PATH=Path(self.temp.name)/'test.db'; engine.init_db(); engine.reset(seed=11,condition='C')
    def tearDown(self): self.temp.cleanup()
    def test_seeded_progression_reproducible(self):
        engine.step(seed=11); first=engine.snapshot(); engine.reset(seed=11,condition='C'); engine.step(seed=11); second=engine.snapshot()
        self.assertEqual([a['food'] for a in first['agents']],[a['food'] for a in second['agents']]); self.assertEqual(first['metrics'],second['metrics'])
    def test_trade_validation_and_persistence(self):
        with engine.connect() as d:
            before=d.execute("SELECT food FROM agents WHERE id='a1'").fetchone()[0]
            engine.execute(d,'a1',engine.Action(type='TRADE',target_id='a2',resource='food',amount=10))
            after=d.execute("SELECT food FROM agents WHERE id='a1'").fetchone()[0]
            self.assertEqual(before,after)
            self.assertIn('declined',d.execute('SELECT data FROM events ORDER BY id DESC LIMIT 1').fetchone()[0])
    def test_trade_moves_goods_and_records_success(self):
        with engine.connect() as d:
            d.execute("UPDATE agents SET money=5 WHERE id='a1'")
            before_a=d.execute("SELECT food FROM agents WHERE id='a1'").fetchone()[0]
            before_b=d.execute("SELECT food FROM agents WHERE id='a2'").fetchone()[0]
            engine.execute(d,'a1',engine.Action(type='TRADE',target_id='a2',resource='food',amount=1))
            self.assertEqual(d.execute("SELECT food FROM agents WHERE id='a1'").fetchone()[0],before_a+1)
            self.assertEqual(d.execute("SELECT food FROM agents WHERE id='a2'").fetchone()[0],before_b-1)
            self.assertEqual(engine.metrics(d)['trade_volume'],1)
    def test_daily_food_consumption_and_survival_metric(self):
        state=engine.step(seed=11); self.assertEqual(state['day'],1); self.assertEqual(len(state['agents']),8); self.assertEqual(state['metrics']['survival_rate'],1.0)
    def test_experiment_archives_events_and_metrics(self):
        engine.step(seed=11); state=engine.snapshot(); self.assertGreater(state['metrics']['measured_events'],1); self.assertIn('wealth_gini',state['metrics'])

if __name__=='__main__': unittest.main()
