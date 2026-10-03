import unittest

from tools.check_publication import inspect_text


class PublicationTests(unittest.TestCase):
    def test_variable_names_are_not_secret_values(self):
        self.assertEqual(inspect_text("docs/example.md", "APP_KEY, POSTGRES_PASSWORD"), [])

    def test_private_key_rejected(self):
        self.assertTrue(inspect_text("example.txt", "-----BEGIN " + "PRIVATE KEY-----"))

    def test_token_rejected(self):
        self.assertTrue(inspect_text("example.txt", "ghp_" + "A" * 40))

    def test_credentialed_url_rejected(self):
        self.assertTrue(inspect_text("example.txt", "https://" + "user:password@example.com"))

    def test_private_paths_rejected(self):
        for path in (".env", "private/inventory.json", "backup.key", "records.sqlite3", "secrets.clixml"):
            with self.subTest(path=path):
                self.assertTrue(inspect_text(path, ""))

    def test_example_env_allowed(self):
        self.assertEqual(inspect_text("examples/.env.example", "DB_PASSWORD=<generated-locally>"), [])

    def test_findings_do_not_echo_secret_value(self):
        token = "ghp_" + "B" * 40
        self.assertNotIn(token, " ".join(inspect_text("example.txt", token)))


if __name__ == "__main__":
    unittest.main()
