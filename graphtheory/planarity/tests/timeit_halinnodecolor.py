#!/usr/bin/python

import timeit
import random
from graphtheory.structures.edges import Edge
from graphtheory.structures.graphs import Graph
from graphtheory.structures.factory import GraphFactory
from graphtheory.planarity.halinnodecolor import HalinNodeColoring
from graphtheory.planarity.halintools import make_halin_outer
from graphtheory.planarity.halintools import make_halin_cubic_outer

V = 10
graph_factory = GraphFactory(Graph)
G = graph_factory.make_necklace(n=V)   # V even
outer = set(range(0,V,2)) | set([V-1])   # necklace

#G, outer = make_halin_outer(V)
#G, outer = make_halin_cubic_outer(V)
E = G.e()
#G.show()

print ( "Testing HalinNodeColoring ..." )
t1 = timeit.Timer(lambda: HalinNodeColoring(G, outer).run())
print ( "{} {} {}".format(V, E, t1.timeit(1)) )   # single run

# EOF
