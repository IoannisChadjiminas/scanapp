"""Identity regressions found in the September photo review."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_cardmarket_photos import audit, image_product_id, number_key


def card(ident='en:base4-76', name='Goldeen', set_id='base4', set_name='Base Set 2', number='76', **extra):
    return dict(id=ident, name=name, set_id=set_id, set_name=set_name,
                collector_number=number, language='en', cardmarket_url=None,
                remote_image_url=None, **extra)


def product(name='Goldeen (B2 76)From 0,03 €', expansion='Base-Set-2', slug='Goldeen-B276'):
    return dict(url=f'https://www.cardmarket.com/en/Pokemon/Products/Singles/{expansion}/{slug}',
                name=name, expansion=expansion, matched=0, card_id=None,
                listing_image_url='https://product-images.s3.cardmarket.com/51/B2/123/123.jpg')


class AuditTests(unittest.TestCase):
    def run_audit(self, cards, products):
        return audit({'cards': cards, 'cardmarket_expansion_products': products})

    def test_b2_collision_uses_expansion_not_short_code(self):
        rows = self.run_audit([card(), card('en:B2-076', 'Other', 'B2', 'Fantastical Parade', '076')], [product()])
        self.assertEqual(rows[0]['proposed_card_id'], 'en:base4-76')

    def test_same_name_other_set_is_not_a_match(self):
        rows = self.run_audit([card('en:pl4-1', 'Charizard', 'pl4', 'Arceus', '1')],
                              [product('Charizard (s8a-P 001)', '25th-Anniversary-Edition', 'Charizard')])
        self.assertEqual(rows[0]['status'], 'no_supported_set')

    def test_collector_suffix_is_preserved(self):
        rows = self.run_audit([card('en:ecard2-95a', 'Mr. Mime', 'ecard2', 'Aquapolis', '95a'),
                               card('en:ecard2-95b', 'Mr. Mime', 'ecard2', 'Aquapolis', '95b')],
                              [product('Mr. Mime (AQ 095b)', 'Aquapolis', 'Mr-Mime-AQ95b')])
        self.assertEqual(rows[0]['proposed_card_id'], 'en:ecard2-95b')
        self.assertNotEqual(number_key('95a'), number_key('95b'))

    def test_trainer_deck_suffix_and_conflicting_name(self):
        cards = [card('en:tk-bw-e-20', 'Fighting Energy', 'tk-bw-e', 'BW trainer Kit (Excadrill)', '20'),
                 card('en:tk-bw-z-20', 'Darkness Energy', 'tk-bw-z', 'BW trainer Kit (Zoroark)', '20')]
        rows = self.run_audit(cards, [product('Darkness Energy (TK5 20E)', 'BW-Trainer-Kit', 'Darkness-Energy-TK520E'),
                                     product('Darkness Energy (TK5 20Z)', 'BW-Trainer-Kit', 'Darkness-Energy-TK520Z')])
        self.assertEqual({r['status'] for r in rows}, {'metadata_conflict', 'proposed_match'})
        self.assertEqual(rows[0]['proposed_card_id'], 'en:tk-bw-z-20')

    def test_unphotographed_sibling_still_blocks_variant(self):
        sibling = product(slug='Goldeen-V2-B276'); sibling['listing_image_url'] = None
        rows = self.run_audit([card()], [product(), sibling])
        self.assertEqual(rows[0]['status'], 'separate_variant')

    def test_existing_link_is_not_overwritten(self):
        c = card(); c['cardmarket_url'] = 'https://www.cardmarket.com/other'
        rows = self.run_audit([c], [product()])
        self.assertEqual(rows[0]['status'], 'existing_link_conflict')

    def test_oversized_is_separate(self):
        rows = self.run_audit([card()], [product(slug='Goldeen-V2-OS')])
        self.assertEqual(rows[0]['status'], 'separate_variant')

    def test_missing_official_image_does_not_remove_identity(self):
        rows = self.run_audit([card()], [product()])
        self.assertEqual(rows[0]['status'], 'proposed_match')
        self.assertFalse(rows[0]['official_image_available'])

    def test_product_id_is_scoped_to_known_host(self):
        self.assertEqual(image_product_id(product()['listing_image_url']), 123)
        self.assertIsNone(image_product_id('https://untrusted.test/51/B2/123/123.jpg'))


if __name__ == '__main__':
    unittest.main()
