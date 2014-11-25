import unittest
import logging
import mock
import Queue

from osci import db
from osci import job_queue
from osci import job
from osci import filesystem_services
from osci import utils
from osci import nodepool_manager
from osci import constants
from osci import time_services

class FakeNodePool(nodepool_manager.NodePool):
    def __init__(self, image):
        self.nodedb = mock.Mock()
        self.nodedb.READY = 'ready'
        self.nodedb.HOLD = 'hold'
        self.pool = mock.Mock()
        self.pool._deleteNode.side_effect = self.mock_delete
        self.image = 'mock_image'
        self.mock_session = mock.Mock()
        self.mock_session.getNodes.side_effect = self.mock_get_nodes
        self.mock_session.getNode.side_effect = self.mock_get_node
        self.nodes = []
        
    def getSession(self):
        mock_ret = mock.Mock()
        mock_ret.__enter__ = mock.Mock(return_value=self.mock_session)
        mock_ret.__exit__ = mock.Mock(return_value=False)
        return mock_ret
    
    def mock_get_node(self, node_id):
        return [x for x in self.nodes if x.id == node_id][0]
    
    def mock_get_nodes(self):
        return self.nodes

    def mock_delete(self, session, node):
        self.nodes = [x for x in self.nodes if x != node]

    def addNode(self, id, ip, state):
        node = mock.Mock()
        node.id = id
        node.ip = ip
        node.state = state
        node.state_time = time_services.time()
        node.label_name = self.image
        self.nodes.append(node)
        

class TestNodepoolManager(unittest.TestCase):
    def test_get_node_none(self):
        self.npm = FakeNodePool('image')
        self.assertEquals((None, None), self.npm.getNode())

    def test_get_node_skip_hold(self):
        self.npm = FakeNodePool('image')
        self.npm.addNode(1, 'ip_1', self.npm.nodedb.HOLD)
        self.npm.addNode(2, 'ip_2', self.npm.nodedb.READY)
        self.assertEquals((2, 'ip_2'), self.npm.getNode())

    def test_get_node_changes_state(self):
        self.npm = FakeNodePool('image')
        self.npm.addNode(1, 'ip_1', self.npm.nodedb.READY)
        self.assertEquals((1, 'ip_1'), self.npm.getNode())
        self.assertEquals(self.npm.nodes[0].state, self.npm.nodedb.HOLD)

    def test_delete_calls_pool_delete(self):
        self.npm = FakeNodePool('image')
        self.npm.addNode(1, 'ip_1', self.npm.nodedb.READY)
        node = self.npm.nodes[0]
        self.npm.deleteNode(1)
        self.npm.pool._deleteNode.assert_called_with(self.npm.mock_session, node)
        self.assertEquals(0, len(self.npm.nodes))

    @mock.patch('osci.time_services.time')
    def test_held_state_age(self, mock_time):
        self.npm = FakeNodePool('image')
        # First two time()'s are for the node state time.
        # Third return value is in getHeldNodes for the current
        # time
        mock_time.side_effect = [5100, 5000, 5105]
        self.npm.addNode(1, 'ip_1', self.npm.nodedb.HOLD)
        self.npm.addNode(2, 'ip_2', self.npm.nodedb.HOLD)
        # With the time at 5105, only node 2 is more than 50
        # seconds old
        nodes = self.npm.getHeldNodes(min_state_age=50)
        self.assertEquals(1, len(nodes))
        self.assertEquals(set([2]), nodes)
