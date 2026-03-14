import unittest

from app import app
from core.database import set_setting


class OAuthAndRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_vk_auth_uses_public_base_url(self):
        set_setting("public_base_url", "http://127.0.0.1:5000")
        resp = self.client.get("/vk/auth", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        location = resp.headers.get("Location", "")
        self.assertIn("oauth.vk.com/authorize", location)
        self.assertIn("redirect_uri=http://127.0.0.1:5000/vk/callback", location)

    def test_meta_routes_contains_expected_paths(self):
        resp = self.client.get("/api/meta/routes")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, dict)
        self.assertIn("routes", data)
        self.assertIn("/vk/auth", data["routes"])
        self.assertIn("/api/meta/routes", data["routes"])

    def test_system_checks_endpoint(self):
        resp = self.client.get("/api/system/checks")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        checks = data.get("checks", {})
        self.assertTrue(checks.get("vk_groups_has_posts_count"))
        self.assertTrue(checks.get("vk_groups_has_discussions_count"))


if __name__ == "__main__":
    unittest.main()
