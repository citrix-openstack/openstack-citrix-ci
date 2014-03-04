import mock
import unittest
import time
import datetime
import json

from osci import constants
from osci import utils
from osci.test import Test
from osci.config import Configuration

class TestGerrit(unittest.TestCase):
    @mock.patch.object(utils, 'get_commit_json')
    def test_get_patchset_details(self, mock_json):
        db = mock.Mock()
        ret_json='{"project":"openstack-infra/tripleo-ci",'+\
                  '"id":"I15431d8ede45a4fde51d0e6baa9e3cdf50c03920",'+\
                  '"number":"68139","patchSets":[{"number":"1",'+\
                  '"revision":"b678325a816c60ad3b0141c6cc6890c7c156f649"},'+\
                  '{"number":"2",'+\
                  '"revision":"430973f7d8499be075569624d0501e549a2208f2"}]}'
        mock_json.return_value = json.loads(ret_json)
        details = utils.get_patchset_details('68139', '2')
        self.assertEqual(details['project'], 'openstack-infra/tripleo-ci')
        self.assertEqual(details['number'], '2')
        self.assertEqual(details['revision'], '430973f7d8499be075569624d0501e549a2208f2')
