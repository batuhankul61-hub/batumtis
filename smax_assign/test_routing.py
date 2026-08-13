"""Yonlendirme kural motoru testleri (ag baglantisi gerektirmez).

Calistirmak icin:  python -m unittest test_routing -v
"""

import unittest

import routing


def make_config():
    return routing.RulesConfig(
        vendors={
            "Proasist": {"field": "ExpertGroup", "value": "PRO-1", "aliases": ["proasist"]},
            "Ulusal": {"field": "ExpertGroup", "value": "ULS-9", "aliases": ["ulusal klima"]},
        },
        areas={
            "Sercan": {
                "match_fields": ["Location"],
                "values": ["MAGAZA-001", "Ankara Kentpark", "İzmir Optimum"],
            }
        },
        rules=[{
            "name": "Sercan alani klima -> Ulusal",
            "when": {
                "area": "Sercan",
                "any_keyword_in": {
                    "fields": ["DisplayLabel", "Description", "Category"],
                    "keywords": ["klima", "iklimlendirme", "hvac"],
                },
            },
            "then": {"route_to": "Ulusal", "forbid": ["Proasist"]},
        }],
    )


class TestNorm(unittest.TestCase):
    def test_turkish_case_folding(self):
        self.assertEqual(routing.norm("KLİMA"), "klima")
        self.assertEqual(routing.norm("Klima"), "klima")
        self.assertEqual(routing.norm("IKLIMLENDİRME"), "iklimlendirme")
        self.assertEqual(routing.norm("  Ulusal Klima "), "ulusal klima")

    def test_none_and_empty(self):
        self.assertEqual(routing.norm(None), "")
        self.assertEqual(routing.norm(""), "")


class TestEvaluate(unittest.TestCase):
    def setUp(self):
        self.config = make_config()

    def test_sercan_klima_on_proasist_is_rerouted(self):
        props = {
            "Id": "101", "DisplayLabel": "Klima calismiyor",
            "Location": "MAGAZA-001 - Ankara", "ExpertGroup": "PRO-1",
        }
        d = routing.evaluate(props, self.config)
        self.assertEqual(d.action, "reroute")
        self.assertEqual(d.current_vendor, "Proasist")
        self.assertEqual(d.target_vendor, "Ulusal")
        self.assertEqual(d.field, "ExpertGroup")
        self.assertEqual(d.value, "ULS-9")
        self.assertTrue(d.needs_update)

    def test_uppercase_turkish_keyword_matches(self):
        props = {"Id": "102", "DisplayLabel": "KLİMA ARIZASI",
                 "Location": "Ankara Kentpark", "ExpertGroup": "PRO-1"}
        self.assertEqual(routing.evaluate(props, self.config).action, "reroute")

    def test_unassigned_request_is_routed(self):
        props = {"Id": "103", "DisplayLabel": "Klima bakimi",
                 "Location": "MAGAZA-001", "ExpertGroup": ""}
        d = routing.evaluate(props, self.config)
        self.assertEqual(d.action, "route")
        self.assertEqual(d.current_vendor, "")
        self.assertTrue(d.needs_update)

    def test_already_on_ulusal_is_left_alone(self):
        props = {"Id": "104", "DisplayLabel": "Klima arizasi",
                 "Location": "MAGAZA-001", "ExpertGroup": "ULS-9"}
        d = routing.evaluate(props, self.config)
        self.assertEqual(d.action, "already_correct")
        self.assertFalse(d.needs_update)

    def test_other_location_klima_is_untouched(self):
        """Sercan Bey'in alani disindaki klima talebi kural disi kalir."""
        props = {"Id": "105", "DisplayLabel": "Klima arizasi",
                 "Location": "MAGAZA-999 - Bursa", "ExpertGroup": "PRO-1"}
        d = routing.evaluate(props, self.config)
        self.assertEqual(d.action, "no_match")
        self.assertFalse(d.needs_update)

    def test_non_klima_request_in_sercan_area_is_untouched(self):
        """Ayni lokasyondaki klima disi is Proasist'te kalir."""
        props = {"Id": "106", "DisplayLabel": "Elektrik prizi arizali",
                 "Location": "MAGAZA-001", "ExpertGroup": "PRO-1"}
        d = routing.evaluate(props, self.config)
        self.assertEqual(d.action, "no_match")
        self.assertFalse(d.needs_update)

    def test_keyword_found_in_description(self):
        props = {"Id": "107", "DisplayLabel": "Sogutma sorunu",
                 "Description": "Kaset tipi iklimlendirme unitesi ariza verdi",
                 "Location": "İzmir Optimum", "ExpertGroup": "PRO-1"}
        self.assertEqual(routing.evaluate(props, self.config).action, "reroute")

    def test_vendor_detected_by_alias_text(self):
        """Alan Id yerine metin dondurdugunde takma ad ile eslesir."""
        props = {"Id": "108", "DisplayLabel": "Klima arizasi",
                 "Location": "MAGAZA-001", "ExpertGroup": "Proasist Teknik Servis"}
        d = routing.evaluate(props, self.config)
        self.assertEqual(d.current_vendor, "Proasist")
        self.assertEqual(d.action, "reroute")

    def test_nested_property_dict(self):
        """SMAX bazen iliskili kaydi sozluk olarak dondurur."""
        props = {"Id": "109", "DisplayLabel": "Klima arizasi",
                 "Location": {"DisplayLabel": "MAGAZA-001 Ankara"}, "ExpertGroup": "PRO-1"}
        self.assertEqual(routing.evaluate(props, self.config).action, "reroute")


class TestValidate(unittest.TestCase):
    def test_placeholder_config_reports_problems(self):
        cfg = routing.RulesConfig.load(
            __import__("os").path.join(__import__("os").path.dirname(__file__), "routing_rules.json"))
        problems = cfg.validate()
        self.assertTrue(problems, "Sablon dosyada doldurulmamis alanlar tespit edilmeliydi.")

    def test_complete_config_has_no_problems(self):
        self.assertEqual(make_config().validate(), [])


if __name__ == "__main__":
    unittest.main()
