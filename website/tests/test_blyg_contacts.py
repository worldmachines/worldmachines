import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import blyg_contacts as K  # noqa: E402

AUTHORS = {'authors': {
    'aneesh': {'name': 'Aneesh Sathe', 'blyg': 'https://blyg.aneeshsathe.com/'},
    'sean': {'name': 'Sean Stevenson', 'blyg': None},
    'venkat': {'name': 'Venkatesh Rao', 'blyg': 'https://venkateshrao.com/blyg/'},
}, 'handles': {'vgr': 'venkat'}}


class ContactsPlanTest(unittest.TestCase):
    def test_only_members_with_a_blyg(self):
        self.assertEqual([c['handle'] for c in K.wanted_contacts(AUTHORS)], ['aneesh', 'venkat'])

    def test_create_update_and_leave_others_alone(self):
        existing = [{'id': 'c1', 'handle': 'venkat', 'name': 'Venkat', 'url': 'https://venkateshrao.com/blyg/'},
                    {'id': 'c2', 'handle': 'someone', 'name': 'Someone Else', 'url': 'https://x.example/'}]
        creates, updates = K.plan(K.wanted_contacts(AUTHORS), existing)
        self.assertEqual([c['handle'] for c in creates], ['aneesh'])
        self.assertEqual(updates, [('c1', {'name': 'Venkatesh Rao'})])

    def test_in_step_means_nothing_to_do(self):
        existing = [dict(c, id=c['handle']) for c in K.wanted_contacts(AUTHORS)]
        self.assertEqual(K.plan(K.wanted_contacts(AUTHORS), existing), ([], []))


if __name__ == '__main__':
    unittest.main()
