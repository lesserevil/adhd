"""Pure conservation comparator guards; no server, artifact or export invoked."""
import copy
import unittest
from acme_protocol_contracts import conservation_delta


class Conservation(unittest.TestCase):
    def fixture(self):
        return {'$defs':{'Unaffected':{'type':'object','required':['b','a'],
          'properties':{'a':{'type':'string'},'b':{'const':{'required':['b','a']}}},
          'enum':[{'required':['b','a']}],'default':{'required':['b','a']},
          'x-literal':{'required':['b','a']},'oneOf':[{'type':'string'},{'type':'integer'}]}}}

    def test_only_schema_required_order_is_equivalent_raw_difference_retained(self):
        before=self.fixture();after=copy.deepcopy(before);after['$defs']['Unaffected']['required'].reverse()
        raw,semantic,_,_=conservation_delta(after,before)
        self.assertEqual(raw,{'Unaffected'});self.assertEqual(semantic,set())

    def test_unallowlisted_membership_constraint_literal_or_other_array_change_survives(self):
        before=self.fixture()
        for mutate in [lambda d:d['required'].pop(),lambda d:d['required'].append('a'),
                       lambda d:d.update(type='array'),lambda d:d['properties']['a'].update(minLength=1),
                       lambda d:d['properties']['b']['const']['required'].reverse(),
                       lambda d:d['enum'][0]['required'].reverse(),lambda d:d['default']['required'].reverse(),
                       lambda d:d['x-literal']['required'].reverse(),lambda d:d['oneOf'].reverse()]:
            after=copy.deepcopy(before);mutate(after['$defs']['Unaffected'])
            raw,semantic,_,_=conservation_delta(after,before)
            self.assertEqual(raw,{'Unaffected'});self.assertEqual(semantic,{'Unaffected'})


if __name__=='__main__':unittest.main()
