import logging
import threading
import Queue
from osci.config import Configuration


class DeleteNodeThread(threading.Thread):
    log = logging.getLogger('citrix.DeleteNodeThread')

    deleteNodeQueue = Queue.Queue()

    def __init__(self, pool):
        threading.Thread.__init__(self, name='DeleteNodeThread')
        self.pool = pool
        self.daemon = True

    def run(self):
        while True:
            try:
                self.pool.reconfigureManagers(self.pool.config)
                with self.pool.getDB().getSession() as session:
                    while True:
                        # Get a new DB Session every 30 seconds
                        # (exception will be caught below)
                        node_id = self.deleteNodeQueue.get(
                            block=True, timeout=30)
                        node = session.getNode(node_id)
                        if node:
                            self.pool.deleteNode(session, node)
            except Queue.Empty, e:
                pass
            except Exception, e:
                self.log.exception(e)


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
        self.deleteNodeThread = None

    def startCleanupThread(self):
        self.deleteNodeThread = DeleteNodeThread(self.pool)
        self.deleteNodeThread.start()

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
        if self.deleteNodeThread is None:
            self.log.info('Starting node cleanup thread')
            self.startCleanupThread()
        self.log.info('Adding node %s to the list to delete' % node_id)
        DeleteNodeThread.deleteNodeQueue.put(node_id)
