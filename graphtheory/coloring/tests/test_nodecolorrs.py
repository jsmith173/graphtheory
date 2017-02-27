#!/usr/bin/python

import unittest
from graphtheory.structures.edges import Edge
from graphtheory.structures.graphs import Graph
from graphtheory.coloring.nodecolorrs import RandomSequentialNodeColoring

# 0 --- 1 --- 2
# |   / |   / |
# |  /  |  /  |
# | /   | /   |
# 3 --- 4 --- 5

class TestNodeColoring(unittest.TestCase):

    def setUp(self):
        self.N = 6
        self.G = Graph(self.N)
        self.nodes = range(self.N)
        self.edges = [
            Edge(0, 1), Edge(0, 3), Edge(1, 3), Edge(1, 4), Edge(1, 2), 
            Edge(2, 4), Edge(2, 5), Edge(3, 4), Edge(4, 5)]
        for node in self.nodes:
            self.G.add_node(node)
        for edge in self.edges:
            self.G.add_edge(edge)
        #self.G.show()
        # Best coloring - 3 colors.
        # color = {0:a, 1:b, 2:c, 3:c, 4:a, 5:b}

    def test_rs_node_coloring(self):
        algorithm = RandomSequentialNodeColoring(self.G)
        algorithm.run()
        # Sprawdzenie, czy kazdy wierzcholek ma kolor.
        for node in self.G.iternodes():
            self.assertNotEqual(algorithm.color[node], None)
        for edge in self.G.iteredges():
            self.assertNotEqual(algorithm.color[edge.source],
                                algorithm.color[edge.target])
        #print algorithm.color
        all_colors = set(algorithm.color[node] for node in self.G.iternodes())
        self.assertTrue(len(all_colors) in set([3, 4]))

    def test_exceptions(self):
        self.assertRaises(ValueError, RandomSequentialNodeColoring,
            Graph(5, directed=True))

    def tearDown(self): pass

if __name__ == "__main__":

    unittest.main()

# EOF
