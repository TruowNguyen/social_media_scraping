import unittest
from engine.classification_view import query_rows


class ClassificationViewTests(unittest.TestCase):
    def row(self,id='1',**overrides):
        row=dict(node_id=id,node_type='COMMENT',source_ids=['group'],raw_text='Phản ánh kẹt cổng',
            published_at='2026-10-09T17:00:00Z',collected_at='2026-10-10T01:00:00Z',publication_precision='INSTANT',
            processing_status='DONE',analysis={'relevance':'KEEP','content_intents':['COMPLAINT'],
            'project_matches':[{'project_id':'vincons'}],'issues':[{'issue_id':'ENTRY_QUEUE'}]})
        return dict(row,**overrides)

    def test_vietnamese_day_boundary_unknown_time_and_collected_basis(self):
        rows=[self.row(),self.row('2',publication_precision='UNKNOWN')]
        self.assertEqual(query_rows(rows,{'start_date':'2026-10-10','end_date':'2026-10-10'})['total'],1)
        self.assertEqual(query_rows(rows,{'date_basis':'collected_at','start_date':'2026-10-10'})['total'],2)
        self.assertEqual(query_rows(rows,{'end_date':'2026-10-09'})['total'],0)

    def test_combined_filters_and_accent_insensitive_keyword(self):
        rows=[self.row()]
        filters=dict(keyword='ket cong',node_type='COMMENT',source_id='group',project_id='vincons',issue_id='ENTRY_QUEUE',intent='COMPLAINT')
        self.assertEqual(query_rows(rows,filters)['total'],1)
        self.assertEqual(query_rows(rows,dict(filters,project_id='__unknown__'))['total'],0)

    def test_intent_filter_only_uses_rule_labels_for_filter_drop(self):
        rows=[self.row('pending',analysis=None,processing_status='PENDING',filter_decision={'content_intents':['SALES']}),
              self.row('filtered',analysis=None,processing_status='FILTER_DROP',filter_decision={'content_intents':['SALES']}),
              self.row('model',analysis={'content_intents':['COMPLAINT']},filter_decision={'content_intents':['SALES']})]
        self.assertEqual([r['node_id'] for r in query_rows(rows,{'intent':'SALES'})['rows']],['filtered'])
        self.assertEqual([r['node_id'] for r in query_rows(rows,{'intent':'COMPLAINT'})['rows']],['model'])

    def test_pagination_facets_and_missing_dates(self):
        rows=[self.row(str(n)) for n in range(30)]
        view=query_rows(rows,dict(page='2',page_size='25'))
        self.assertEqual(len(view['rows']),5);self.assertEqual(view['total'],30)
        self.assertEqual(view['summary']['KEEP'],30)
        self.assertEqual(query_rows(rows,dict(relevance='DROP'))['summary']['KEEP'],30)
        with self.assertRaises(ValueError):query_rows(rows,dict(start_date='2026-10-10',end_date='2026-10-09'))
