import logging
import threading
import Queue
from osci.config import Configuration
from osci import time_services

class NodePool():
    log = logging.getLogger('citrix.nodepool')

    def __init__(self, image):
        from nodepool import nodedb, nodepool
        self.nodedb = nodedb

        self.pool = nodepool.NodePool(Configuration().NODEPOOL_CONFIG)
        config = self.pool.loadConfig()
        self.pool.reconfigureDatabase(config)
        self.pool.setConfig(config)
        self.image = image

    def getNode(self):
        with self.pool.getDB().getSession() as session:
            for node in session.getNodes():
                if node.image_name != self.image:
                    continue
                if node.state != self.nodedb.READY:
                    continue
                # Allocate this node
                node.state = self.nodedb.HOLD
                return node.id, node.ip
        return None, None

    def deleteNode(self, node_id):
        if not node_id:
            return
        self.pool.reconfigureManagers(self.pool.config)
        with self.pool.getDB().getSession() as session:
            node = session.getNode(node_id)
            if node:
                self.pool.deleteNode(session, node)
