import unittest
from graphtheory.structures.edges import Edge
from graphtheory.structures.graphs import Graph
from graphtheory.traversing.bfs import BFSWithQueue
from graphtheory.traversing.bfs import SimpleBFS
from graphtheory.traversing.bfs import BFSWithDepthTracker

# 0---1   2---3
# |   | / | / |
# 4   5---6---7

class TestBFS(unittest.TestCase):

    def setUp(self):
        # The graph from Cormen p.607
        self.N = 8           # number of nodes
        self.G = Graph(self.N)
        self.nodes = range(self.N)
        self.edges = [
            Edge(0, 4, 2), Edge(0, 1, 3), Edge(1, 5, 4), Edge(5, 2, 5),
            Edge(5, 6, 6), Edge(2, 6, 7), Edge(2, 3, 8), Edge(6, 3, 9),
            Edge(6, 7, 10), Edge(3, 7, 11)]
        for node in self.nodes:
            self.G.add_node(node)
        for edge in self.edges:
            self.G.add_edge(edge)
        #self.G.show()

    def test_simple_bfs(self):
        pre_order = []
        post_order = []
        algorithm = SimpleBFS(self.G)
        algorithm.run(1, pre_action=lambda node: pre_order.append(node),
                        post_action=lambda node: post_order.append(node))
        order_expected = [1, 0, 5, 4, 2, 6, 3, 7]
        a=1


test = TestBFS()
test.setUp()
test.test_simple_bfs()



