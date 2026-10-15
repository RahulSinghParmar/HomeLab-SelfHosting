"""Offline Kuma desired-state and secret-boundary tests."""
import copy
from pathlib import Path
import unittest

from homelab.config import ConfigError, load_json
from homelab import kuma_config as config


EXAMPLE = Path(__file__).resolve().parents[1] / 'modules/uptime-kuma/monitor-config.example.json'


class KumaConfigTests(unittest.TestCase):
    def setUp(self):
        self.value = load_json(EXAMPLE)
        self.secrets = {'private-webhook-url': 'https://hooks.example.test/uptime-kuma'}

    def test_example_validates_and_hash_is_deterministic(self):
        validated = config.validate_config(self.value)
        self.assertEqual(config.configuration_hash(validated), config.configuration_hash(copy.deepcopy(validated)))
        self.assertEqual(config.secret_references(validated), {'private-webhook-url'})

    def test_public_view_redacts_monitor_and_notification_endpoints(self):
        value = copy.deepcopy(self.value)
        value['notifications'][0]['url'] = 'https://hooks.example.test/private'
        value['notifications'][0]['url_secret'] = None
        public = config.public_config(value)
        self.assertTrue(all(row['url'] == '<private-endpoint>' for row in public['monitors']))
        self.assertEqual(public['notifications'][0]['url'], '<private-endpoint>')
        self.assertNotIn('hooks.example.test', str(public))

    def test_materialize_binds_secret_only_at_execution_boundary(self):
        value = config.materialize(self.value, self.secrets)
        notification = value['notifications'][0]
        self.assertEqual(notification['id'], 'private-webhook')
        self.assertEqual(notification['api']['webhookURL'], self.secrets['private-webhook-url'])
        self.assertEqual(value['monitors'][0]['notification_ids'], ['private-webhook'])

    def test_secret_set_must_match_exactly(self):
        for values in ({}, {**self.secrets, 'extra': 'value'}):
            with self.subTest(values=values), self.assertRaises(ConfigError):
                config.materialize(self.value, values)

    def test_duplicate_ids_unknown_refs_and_credentials_in_url_are_refused(self):
        cases = []
        duplicate = copy.deepcopy(self.value)
        duplicate['monitors'][1]['id'] = duplicate['monitors'][0]['id']
        cases.append(duplicate)
        unknown = copy.deepcopy(self.value)
        unknown['monitors'][0]['notification_ids'] = ['missing']
        cases.append(unknown)
        credential = copy.deepcopy(self.value)
        credential['monitors'][0]['url'] = 'https://user:secret@example.test/'
        cases.append(credential)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ConfigError):
                config.validate_config(value)

    def test_http_monitor_cannot_disable_tls_validation(self):
        value = copy.deepcopy(self.value)
        value['monitors'][0]['tls_verify'] = False
        with self.assertRaisesRegex(ConfigError, 'HTTPS'):
            config.validate_config(value)

    def test_smtp_provider_maps_private_fields(self):
        value = copy.deepcopy(self.value)
        value['notifications'] = [{
            'id': 'mail', 'name': 'Private SMTP', 'type': 'smtp', 'enabled': True,
            'host': 'smtp.example.test', 'port': 587, 'secure': False,
            'ignore_tls_errors': False, 'disable_starttls': False,
            'username_secret': 'smtp-user', 'password_secret': 'smtp-password',
            'from_secret': 'smtp-from', 'to_secret': 'smtp-to',
            'cc_secret': None, 'bcc_secret': None, 'custom_subject': '[HomeLab] {NAME}',
            'custom_body': '', 'html_body': False,
        }]
        value['monitors'][0]['notification_ids'] = ['mail']
        secrets = {'smtp-user': 'user', 'smtp-password': 'secret',
                   'smtp-from': 'from@example.test', 'smtp-to': 'to@example.test'}
        materialized = config.materialize(value, secrets)
        api = materialized['notifications'][0]['api']
        self.assertEqual((api['type'], api['smtpHost'], api['smtpPort']), ('smtp', 'smtp.example.test', 587))
        self.assertEqual(api['smtpPassword'], 'secret')

    def test_schema_is_closed_and_bounded(self):
        value = copy.deepcopy(self.value)
        value['unexpected'] = True
        with self.assertRaises(ConfigError):
            config.validate_config(value)
        value = copy.deepcopy(self.value)
        value['monitors'][0]['interval_seconds'] = 1
        with self.assertRaises(ConfigError):
            config.validate_config(value)


if __name__ == '__main__':
    unittest.main()
