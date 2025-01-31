from graphtheory.structures.edges import Edge
from graphtheory.structures.graphs import Graph
from graphtheory.structures.factory import GraphFactory
from graphtheory.seriesparallel.sptrees import find_sptree
from graphtheory.seriesparallel.spnodes import node_global_init
import os, json
from pathlib import Path
from json2xml import json2xml
from copy import copy
from tpack_t import circuit_solver_util as cu
import math, cmath

RES_ = 9; CAP_ = 10; IND_ = 11; 
CSOUR_ = 13; VSOUR_ = 14; CGEN_ = 15; VGEN_ = 16; Battery_ = 67
AMPER_METER_ = 6; AMPER_METER2_ = 34

SHORT_CIRCUIT_PREFIX = "Rshortxxx"
OPEN_CIRCUIT_PREFIX = "Ropenxxx"

FLAGS_NONE = 0
FLAGS_NORMAL = 1
FLAGS_SHORT = 2
FLAGS_OPEN = 3

RES_OPEN_CIRCUIT = 1e18

def_weight = 1

split_edge_prop = {
	"label": "<split>",
	"CompId": 0,
	"UniqueID": "<CompNil>",
	"value": 0.0,
	"flags": 0
}

class TCircuitSolverGraph:
	def __init__(self, fn_, opts = None):
		self.yd_log = []; self.graph_update = []; self.resistive_comps = []; self.resistive_comps_ = []; self.gen_comps = []; self.yd_labels = []
		self.graph_debug = []
		self.try_count = 0; self.try_count_Y = 0; self.try_count_D = 0; self.edge_values = []		
		self.fn = fn_
		self.opts = opts
		self.show_graph = 0
		self.show_tree = 0
		self.show_result = 0
		if opts != None:
			self.show_graph = opts['debug_mode'] == 1
			self.show_tree = opts['debug_mode'] == 1
			self.show_result = opts['debug_mode'] == 1

	def prepare(self, circuit_key):
		self.resistive_comps_.append(RES_)
		self.resistive_comps_.append(CAP_)
		self.resistive_comps_.append(IND_)

		self.resistive_comps.append(RES_)
		self.resistive_comps.append(CAP_)
		self.resistive_comps.append(IND_)
		self.resistive_comps.append(AMPER_METER_)
		self.resistive_comps.append(AMPER_METER2_)

		self.gen_comps.append(CSOUR_)
		self.gen_comps.append(VSOUR_)
		self.gen_comps.append(CGEN_)
		self.gen_comps.append(VGEN_)
		self.gen_comps.append(Battery_)

		self.circuit_key = circuit_key
		with open(self.fn, 'r') as f:
			json_data_l = json.load(f)
		self.json_data = json_data_l[circuit_key]
		self.has_expected_key = 'expected' in json_data_l.keys()
		if self.has_expected_key:
			self.expected_key = json_data_l['expected']
		else:
			self.expected_key = {}
		if len(self.json_data['gens']) == 0:
			raise Exception('Generator not found')
		self.gen = self.json_data['gens'][0]

		if self.opts['override_request'] == 1:
			self.request = self.opts['request']
		else:	
			self.request = json_data_l['request']
			
		# options = 'dy': use delta-y conversion if possible	
		if self.request['options'] == 'dy':
			self.opts['test_Y'] = 0
			self.opts['test_D'] = 1
		
		self.request['req_on_gen'] = False
		self.use_superposition = len(self.json_data['gens']) > 1

		# Replacing volt meter labels in request
		self.request['volt_meter_question'] = False
		for item in self.json_data["meters"]:
			prop = item["prop"]
			if self.request["comp"] == prop["label"]:
				self.request["comp_ori"] = self.request["comp"]
				self.request["comp"] = prop["match_label"]
				self.request['volt_meter_question'] = True
				break
		
		cu.dump_list(self.json_data, "temp/input.json")
		return self.has_expected_key, self.expected_key, self.gen, self.request
	
	def debug_graph(self):
		dbg1 = []
		for item in self.json_data["edges"]:
			nodes = item["nodes"]
			i1 = nodes[0]
			i2 = nodes[1]
			prop = item["prop"]
			label = prop["label"]
			new_item = {}
			new_item['label'] = label
			new_item['source'] = i1
			new_item['target'] = i2
			dbg1.append(new_item)
		dbg2 = sorted(dbg1, key=lambda d: d['label']) 
		self.graph_debug.append('Netlist (component name, nodes)')
		for item in dbg1:
			s = "{0} {1} {2}".format(item["label"], item["source"], item["target"])
			self.graph_debug.append(s)	 
		self.graph_debug.append('')

	def find_meter(self, s):
		for item in self.json_data["meters"]:
			prop = item["prop"]
			if prop["label"] == s:
				return True, item
			
		for item in self.amper_meters:
			if item["label"] == s:
				return True, item

		return False, {}	

	def get_graph(self, circuit_key, directed=False):
		N = self.json_data["N"]; self.MaxGR = 0
		self.G = Graph(N, directed=directed)
		self.edges = []; edge_dbg = []
		self.composed_labels = []

		for item in self.json_data["edges"]:
			nodes = item["nodes"]
			i1 = nodes[0]
			i2 = nodes[1]
			prop = item["prop"]
			edge = Edge(i1, i2, def_weight, prop)
			self.edges.append(edge)
			new_item = edge.to_dict()
			edge_dbg.append(new_item)

		if self.show_graph: 
			print("")
			cu.dump_list(edge_dbg, "temp/edge_dbg.json")
		 
		for node in self.json_data["nodes"]:
			self.G.add_node(node)
			if node > self.MaxGR:
				self.MaxGR = node

		for edge in self.edges:
			self.G.add_edge(edge)
		return self.G

	def get_edge(self, node):
		i1 = node.source
		i2 = node.target
		a = self.G[i1][i2]
		return True, a

	def is_resistive_or_ampmet(self, edge):
		return edge.prop['CompId'] in self.resistive_comps and edge.prop['flags'] == FLAGS_NORMAL

	def is_resistive(self, edge):
		return edge.prop['CompId'] in self.resistive_comps_ and edge.prop['flags'] == FLAGS_NORMAL

	def is_resistive_or_ampmet_compid(self, comp_id):
		return comp_id == RES_ or comp_id == AMPER_METER_ or comp_id == AMPER_METER2_
	
	def get_comp_val(self, edge):
		comp_id = edge.prop['CompId']
		ac_gen = self.gen['prop']['ac_gen']
		if ac_gen['mode'] == 1:
			s = complex(0, 2*cmath.pi*ac_gen['Freq'])
			if comp_id == RES_:
				R = edge.prop['value']
				z = complex(R, 0)
			elif comp_id == IND_:
				L = edge.prop['value']
				z = s*L
			elif comp_id == CAP_:
				C = edge.prop['value']
				z = 1/(s*C)
			return z
		else:
			if self.is_resistive_or_ampmet_compid(comp_id):
				R = edge.prop['value']
				v = R
			else:
				raise Exception('Python: sinus generator not found')	
			return v

	def get_edge_val(self, node):
		status, edge = self.get_edge(node)
		if self.is_resistive_or_ampmet(edge):
			return True, self.get_comp_val(edge)
		else:
			return False, 0
		
	def get_edge_prop(self, node):
		status, edge = self.get_edge(node)
		if self.is_resistive_or_ampmet(edge):
			return True, edge.prop
		else:
			return False, edge.prop
		
	def get_node_val(self, node, key):	
		if key in node.prop.keys() and node.prop['valid']:
			return True, node.prop[key]
		else:
			return False, 0

	def get_val(self, node, key):
		if node.type == 'edge':
			return self.get_edge_val(node)
		else:
			return self.get_node_val(node, key)

	def get_vals(self, node1, node2, key):
		m = 0; values = []
		status, value = self.get_val(node1, key)
		if status:
			values.append(value)
		status, value = self.get_val(node2, key)
		if status:
			values.append(value)
		return values	

	def get_directed_nodes(self, top, node):
		m = top.directed_nodes[0]
		n = top.directed_nodes[1]
		a0 = node.source; a1 = node.target
		if m == a0:
			r = [m, a1]
		elif m == a1:
			r = [m, a0]
		elif n == a0:
			r = [a1, n]
		elif n == a1:
			r = [a0, n]
		else:
			raise Exception('get_directed_nodes')	
		return r	

	def set_node_val(self, node, v, label, state, key, directed_nodes_=None, top=None):
		node.prop[key] = v
		node.prop['valid'] = state
		if top != None:
			top_str = top.type
		else:	
			top_str = '<none>'
		if directed_nodes_ != None:
			node.directed_nodes = directed_nodes_
			m = node.directed_nodes[0]
			n = node.directed_nodes[1]
			self.update_nodal_edges(node.directed_nodes, v, key, label)
			self.nodal_voltage_log.append(f"Nodes: {m}, {n}, {key}: {v}, top type: {top_str}")

	def get_label_prop(self, node, calc_impedance=False):
		status = True
		if node.type == "series" or node.type == "parallel":
			if not node.computed:
				node.computed = True
				node.computed_id = self.computed_id
				f,label = self.get_computed_str(node.computed_id)
				self.computed_id = self.computed_id+1
				if f:				
					self.computed_id = self.computed_id+1
			else:	
				f,label = self.get_computed_str(node.computed_id)
		else:				
			status, prop = self.get_edge_prop(node)
			label = prop['label']; comp_id = prop['CompId']
			if calc_impedance:
				ac_gen = self.gen['prop']['ac_gen']
				if ac_gen['mode'] == 1:
					s = "j*w"
					if comp_id == IND_:
						label = f"{s}*{label}"
					elif comp_id == CAP_:
						label = f"1/({s}*{label})"

		return status, label	

	def find_path(self, label, paths):
		for path in paths:
			for node in path:
				if node.type == "edge":
					status, edge = self.get_edge(node)
					if edge.prop['label'] == label:
						return True, path
		return False, []				
	
	def dbg_node(self, node, left, right):
		values = self.get_vals(left, right, 'impedance'); label = []
		status, c = self.get_label_prop(left); label.append(c)
		status, c = self.get_label_prop(right); label.append(c)
		status, c = self.get_label_prop(node); label.append(c)
		n = left; s_left = n.to_str()		
		n = right; s_right = n.to_str()
		n = node; s_target = n.to_str()
		s1 = f"l: {s_left}:{label[0]}:{left.type}, r: {s_right}:{label[1]}:{right.type}, targ: {s_target}:{label[2]}:{node.type}"		
		return s1

	def find_composed_label(self, c):
		found = False
		for i in range(len(self.composed_labels)):
			o = self.composed_labels[i]
			if o['label'] == c:
				return True, o, i
		return False, {}, 0

	def clear_composed_label_marked(self):
		for i in range(len(self.composed_labels)):
			o = self.composed_labels[i]
			o['marked'] = False

	def append_composed_label(self, node, labels):
		status, c = self.get_label_prop(node)
		found, o, i = self.find_composed_label(c)
		nodes = []
		nodes.append(node.source)
		nodes.append(node.target)
		if not found:	
			item = {}
			item['label'] = c
			item['labels'] = labels
			item['node'] = node.id
			item['origin'] = node.type
			item['nodes'] = nodes
			item['marked'] = False
			self.composed_labels.append(item)

	def resolve_composed_labels(self, node, labels):
		i = 0; res = []; fifo = []; fifo.extend(labels); fail = False; first = True; node_type = node.type
		while len(fifo) > 0:
			item = fifo[0]
			found, o, idx = self.find_composed_label(item)
			if not found:
				res.append(item)
			elif found and not o['marked']:
				o['marked'] = True; 
				if node_type != o['origin']:
					fail = True
					break
				for tmp in o['labels']:
					fifo.append(tmp)
			fifo.pop(0)
		self.clear_composed_label_marked()	
		if fail:
			res_ = sorted(labels)
		else:	
			res_ = sorted(res)
		return res_

	def combine_nodes(self, node, left, right):
		if node.type == "series":
			if left.target == right.source:
				return [left.source, right.target]
			elif right.target == left.source:
				return [right.source, left.target]
			else:
				return []
		else:
			return [left.source, left.target]

	def can_combine_nodes(self, node, left, right):
		if node.type == "series":
			return left.target == right.source or right.target == left.source
		else:
			return left.target == right.target and left.source == right.source
	
	def get_unique_labels(self, nodes):
		labels = []
		for node in nodes:
			if node.type == "edge":
				status, prop = self.get_edge_prop(node)
				if status:
					labels.append(prop['UniqueID'])
			else:		
					labels.append('<block>')
		return labels			

	def check_composed_label(self, node, left, right):
		labels = []; labels_ = []; aStatus = []; nodes = []
		status, c = self.get_label_prop(left); labels_.append(c); aStatus.append(status)
		status, c = self.get_label_prop(right); labels_.append(c); aStatus.append(status)
		for i in range(2):
			if aStatus[i]:
				labels.append(labels_[i])
				if i == 0:
					nodes.append(left)
				else:
					nodes.append(right)	

		unique_labels = self.get_unique_labels(nodes)
		status, top_label = self.get_label_prop(node)
		if left.type == "edge" and right.type == "edge":
			item = {}
			item['label'] = top_label
			item['origin'] = node.type
			item['stopped'] = False
			item['labels'] = labels
			item['unique_labels'] = unique_labels
			item['marked'] = False
			item['nodes'] = self.combine_nodes(node, left, right)
			self.composed_labels.append(item)
		elif left.type != "edge" and right.type == "edge" or left.type == "edge" and right.type != "edge":
			if left.type == "edge":
				status, label = self.get_label_prop(left)
				status, tmp = self.get_label_prop(node)
				prev_type = right.type
			else:
				status, label = self.get_label_prop(right)
				status, tmp = self.get_label_prop(node)
				prev_type = left.type
			status, item, idx = self.find_composed_label(tmp)
			if status and node.type != prev_type:
				item['stopped'] = True
			elif node.type == prev_type and self.can_combine_nodes(node, left, right):
				if not status:
					item = {}
					item['label'] = tmp
					item['origin'] = node.type
					item['stopped'] = False
					item['labels'] = labels
					item['marked'] = False
					item['unique_labels'] = unique_labels
					item['nodes'] = self.combine_nodes(node, left, right)
					self.composed_labels.append(item)
				elif status and node.type == item['origin'] and not item['stopped']:
					item['labels'].append(label)
				elif status and node.type != item['origin'] and not item['stopped']:
					item['stopped'] = True

	def create_one_item_list(self, a):
		tmp = []
		tmp.append(a)
		return tmp
	
	def yd_find_unique_labels(self, labels):
		unique_labels = []
		for i in range(len(labels)):
			idx = self.find_in_json(labels[i])
			if idx >= 0:
				e = self.json_data["edges"][idx]
				unique_labels.append(e["prop"]["UniqueID"])
			else:
				unique_labels.append("<none>")	
		return unique_labels		

	def yd_get_labels(self, labels, label_order):
		labels_next = []
		for i in range(len(labels)):
			labels_next.append(labels[label_order[i]])
		return labels_next

	def add_yd_composed_label(self, labels, labels_new, label_order, value_list_new_str_list, id):
		for i in range(len(labels_new)):
			labels_next = self.yd_get_labels(labels, label_order[i])
			item = {}
			item['label'] = labels_new[i]
			item['origin'] = id
			#item['origin2'] = id
			item['labels'] = labels_next
			item['value'] = value_list_new_str_list[i]
			item['unique_labels'] = self.yd_find_unique_labels(labels_next)
			self.yd_labels.append(item)

	def to_edge_dict(self, label, CompId, value, flags):
		item = {}
		item['label'] = label; item['CompId'] = CompId; item['value'] = value; item['flags'] = flags
		item['UniqueID'] = '<block>'
		return item

	def gen_label(self, a, prefix = "xy"):
		f,s = self.get_computed_str(a, prefix)
		return s

	def del_edge(self, edge):
		item = {}
		item['prop'] = edge.prop
		item['key'] = 'deledge'
		self.graph_update.append(item)
		self.G.del_edge(edge)

	def add_edge(self, edge):
		item = {}
		item['prop'] = edge.prop
		item['nodes'] = [edge.source, edge.target]
		item['key'] = 'addedge'
		self.graph_update.append(item)
		self.G.add_edge(edge)

	def del_node(self, node):
		for edge in list(self.G.iterinedges(node)):
			self.del_edge(edge)
		if self.G.is_directed():
			for edge in list(self.G.iteroutedges(node)):
				self.del_edge(edge)
		del self.G[node]

	def reset_YD(self):
		node_global_init()
		y_computed_id = 0
		self.D_results = []; self.graph_update = []; self.yd_log = []
		del self.G; self.G = self.G_orig.copy()

	# Converts D to Y: opts['test_D'] = 1
	def check_D(self, D):
		for i in range(len(D)):
			m = D[i]; j = (i+1) % 3; n = D[j]
			e = self.G[m][n]
			item = e.to_dict(); R = item['prop']['value']; label = item['prop']['label']
			if label == self.request["comp"] or not self.is_resistive(e):
				return False	

		self.reset_YD()
		adjacent = []; edges_old = []; new_edges = []; R_old = []; label_old = []; R_new = []; label_list = []; label_list_new = []; value_list_new = []
		self.MaxGR = self.MaxGR+1; new_node = self.MaxGR; self.G.add_node(new_node)
		if len(D) != 3:
			raise Exception('D: graph error (1)')
		for i in range(len(D)):
			R_old.append(0)
			label_old.append('')
		for i in range(len(D)):
			m = D[i]; j = (i+1) % 3; n = D[j]
			e = self.G[m][n]
			item = e.to_dict(); R = item['prop']['value']; label = item['prop']['label']
			label_list.append(label)
			edges_old.append(item['prop'])	
			if i == 0:
				u = 2
			elif i == 1:
				u = 0
			else:
				u = 1			
			R_old[u] = R; label_old[u] = label
			self.del_edge(e)	

		formulas = []; calc_str = []
		for i in range(3):
			label_list_new.append(self.gen_label(i, "xd"))

		tmp = R_old[0]+R_old[1]+R_old[2]
		tmp_str = f"({label_old[0]}+{label_old[1]}+{label_old[2]})"
		value_list_new.append(R_old[1]*R_old[2]/tmp); tmp_calc = f"{label_old[1]}*{label_old[2]}/{tmp_str}"; calc_str.append(tmp_calc)
		value_list_new.append(R_old[0]*R_old[2]/tmp); tmp_calc = f"{label_old[0]}*{label_old[2]}/{tmp_str}"; calc_str.append(tmp_calc)
		value_list_new.append(R_old[0]*R_old[1]/tmp); tmp_calc = f"{label_old[0]}*{label_old[1]}/{tmp_str}"; calc_str.append(tmp_calc)

		for i in range(3):
			R_new.append(self.to_edge_dict(label_list_new[i], RES_, value_list_new[i], 1))

		for i in range(len(label_list_new)):
			formulas.append(f"{label_list_new[i]}={calc_str[i]}")

		for i in range(len(D)):
			m = D[i]
			edge_prop = R_new[i]
			edge = Edge(m, new_node, def_weight, edge_prop); self.add_edge(edge)

		tmp = []; value_list_new_str_list = []
		for i in range(len(label_list_new)):
			value_list_new_str_list.append(f"{cu.fv(value_list_new[i])} Ohm")
			s = f"{label_list_new[i]}={value_list_new[i]:.2f} Ohm"
			tmp.append(s)

		label_order = []
		label_order.append([1,2,0])	
		label_order.append([0,2,1])	
		label_order.append([0,1,2])	

		self.add_yd_composed_label(label_old, label_list_new, label_order, value_list_new_str_list, 'dy')

		label_list_str = ",".join(label_list)
		label_list_new_str = ",".join(tmp)
		self.yd_log.append("This circuit can not be solved by using the standard series-parallel rules")
		self.yd_log.append(f"The {label_list_str} components form a delta connection. We will convert it to star connection")
		self.yd_log.append(f"So we can use standard series-parallel rules for impedance calculation")
		self.yd_log.append(f"The new components will be: {label_list_new_str}")
		self.yd_log.append(f"The following formulas are used in the delta to star conversion: "); self.yd_log.extend(formulas)
		self.yd_log.append("")
		return True


	# Converts Y to delta: opts['test_Y'] = 1
	def check_Y(self, node):
		for edge in list(self.G.iterinedges(node)):
			if edge.prop["label"] == self.request["comp"] or not self.is_resistive(edge):
				return False
			
		self.reset_YD()
		adjacent = []; edges_old = []; new_edges = []; R_old = []; label_old = []; label_old2 = []; R_new = []; label_list = []; label_list_new = []; value_list_new = []
		for node_adj in self.G.iteradjacent(node):
			adjacent.append(node_adj)
			e = self.G[node][node_adj]
			item = e.to_dict(); R = item['prop']['value']
			label = item['prop']['label']; label_list.append(label)
			edges_old.append(item['prop'])	
			R_old.append(R); label_old.append(label)	
		self.del_node(node)
		new_edges.append([adjacent[0], adjacent[1]])
		new_edges.append([adjacent[1], adjacent[2]])
		new_edges.append([adjacent[2], adjacent[0]])

		for i in range(3):
			label_list_new.append(self.gen_label(i, "xy"))

		calc_str = []; formulas = []
		tmp = R_old[0]*R_old[1]+R_old[1]*R_old[2]+R_old[2]*R_old[0]
		tmp_str = f"({label_old[0]}*{label_old[1]}+{label_old[1]}*{label_old[2]}+{label_old[2]}*{label_old[0]})"
		
		i = 2; value_list_new.append(tmp/R_old[i]); tmp_calc = f"{tmp_str}/{label_old[i]}"; calc_str.append(tmp_calc)
		i = 0; value_list_new.append(tmp/R_old[i]); tmp_calc = f"{tmp_str}/{label_old[i]}"; calc_str.append(tmp_calc)
		i = 1; value_list_new.append(tmp/R_old[i]); tmp_calc = f"{tmp_str}/{label_old[i]}"; calc_str.append(tmp_calc)

		for i in range(3):
			R_new.append(self.to_edge_dict(label_list_new[i], RES_, value_list_new[i], 1)) 

		for i in range(len(label_list_new)):
			formulas.append(f"{label_list_new[i]}={calc_str[i]}")

		tmp = []; value_list_new_str_list = []
		for i in range(len(label_list_new)):
			value_list_new_str_list.append(f"{cu.fv(value_list_new[i])} Ohm")
			s = f"{label_list_new[i]}={value_list_new[i]:.2f} Ohm"
			tmp.append(s)

		label_order = []
		label_order.append([0,1,2])	
		label_order.append([1,2,0])	
		label_order.append([2,0,1])	

		label_list_str = ",".join(label_list)
		label_list_new_str = ",".join(tmp)
		self.yd_log.append("This circuit can not be solved by using the standard series-parallel rules")
		self.yd_log.append(f"The {label_list_str} components form a star connection. We will convert it to delta connection")
		self.yd_log.append(f"So we can use standard series-parallel rules for impedance calculation")
		self.yd_log.append(f"The new components will be: {label_list_new_str}")
		self.yd_log.append(f"The following formulas are used in the star to delta conversion: "); self.yd_log.extend(formulas)
		self.yd_log.append("")

		i = 0
		for source, target in new_edges:
			edge_prop = R_new[i]
			if target in self.G[source]:
				self.MaxGR = self.MaxGR+1; new_node = self.MaxGR; self.G.add_node(new_node)
				edge = Edge(source, new_node, def_weight, edge_prop); self.add_edge(edge)
				edge = Edge(new_node, target, def_weight, split_edge_prop); self.add_edge(edge)
			else:
				edge = Edge(source, target, def_weight, edge_prop); self.add_edge(edge)
			i = i+1	

		self.add_yd_composed_label(label_old, label_list_new, label_order, value_list_new_str_list, 'yd')
		return True

	def find_D_results(self, key):
		for item in self.D_results:
			if item['key'] == key:
				return True
		return False	

	def collect_D_connections(self):
		c = 0
		for x in self.G.iternodes():
			for y in self.G.iternodes():
				for z in self.G.iternodes():
					c = c+1
					if c > 1e6:
						raise Exception('D: graph error')
					value = [x, y, z]
					key = sorted(value)
					if self.G.has_edge([x, y]) and self.G.has_edge([y, z]) and self.G.has_edge([z, x]) and not self.find_D_results(key):
						item = {}; item['key'] = key; item['value'] = value
						self.D_results.append(item)

	def check_YD(self, fixed_ends):
		finished = True
		try:
			T = find_sptree(self.G, fixed_ends); del T
			return 0
		except ValueError as e:
			finished = False

		self.G_orig = self.G.copy()
		iter_nodes = []
		for node in self.G.iternodes():
			iter_nodes.append(node)

		if self.opts['test_Y'] == 1:
			for node in iter_nodes:
				if self.G.degree(node) == 3:

					if self.check_Y(node):
						self.try_count = self.try_count+1	
						self.try_count_Y = self.try_count_Y+1	
						if self.try_count > 1e3:
							del self.G; self.G = self.G_orig
							raise Exception('Y: graph error')
						try:
							T = find_sptree(self.G, fixed_ends); del T
							return 1
						except ValueError as e:
							finished = False

		if self.opts['test_D'] == 1:
			self.D_results = []
			self.collect_D_connections()

			for D in self.D_results:
				if self.check_D(D['value']):
					self.try_count = self.try_count+1	
					self.try_count_D = self.try_count_D+1	
					if self.try_count > 1e6:
						del self.G; self.G = self.G_orig
						raise Exception('D: graph error')
					try:
						T = find_sptree(self.G, fixed_ends); del T
						return 1
					except ValueError as e:
						finished = False

		del self.G; self.G = self.G_orig
		return 0

	def find_in_json(self, a):
		i = 0
		for item in self.json_data["edges"]:
			prop = item["prop"]
			if a == prop["label"]:
				return i
			i = i+1
		return -1	
	
	def find_in_json_by_nodes(self, a):
		i = 0
		for item in self.json_data["edges"]:
			src = item["nodes"]
			if a[0] == src[0] and a[1] == src[1]:
				return i, True
			elif a[1] == src[0] and a[0] == src[1]:
				return i, False
			i = i+1
		return -1, False	
	
	def find_edge_value(self, nodes, label):
		for i in range(len(self.edge_values)):
			item = self.edge_values[i]
			if item['label'] == label and item['nodes'] == nodes:
				return i
		return -1	

	def find_edge_value_by_label(self, label):
		for i in range(len(self.edge_values)):
			item = self.edge_values[i]
			if item['label'] == label:
				return i
		return -1	

	def calc_final_nodal_edges(self, key):
		for i in range(len(self.edge_values)):
			item = self.edge_values[i]
			v = 0.0; new_key = f"{key}_items"
			if new_key in item.keys():
				c = len(item[new_key])
			else:
				c = 0	
			for j in range(c):
				item2 = item[new_key][j]
				if item2['original_dir']:
					v = v+item2[key]
				else:	
					v = v-item2[key]
			item[key] = v

	def update_nodal_edges(self, directed_nodes, v, key, label):
		if key == 'current'and label != '':
			idx = self.find_in_json(label)
		else:	
			idx, original_dir = self.find_in_json_by_nodes(directed_nodes)
		if idx >= 0:
			item = self.json_data["edges"][idx]
			new_item = {}
			new_item['label'] = item['prop']['label']
			new_item['nodes'] = item['nodes']

			#get the direction from 'dctable'
			original_dir = self.getdir_from_dctable(self.i_pass, item['prop']['label'])

			new_item2 = {}
			new_item2[key] = v
			new_item2['original_dir'] = original_dir

			new_key = f"{key}_items"
			idx = self.find_edge_value(new_item['nodes'], new_item['label'])
			if idx >= 0:
				new_item = self.edge_values[idx]
				if new_key in new_item.keys():
					N = len(new_item[new_key]); m = N-1
					if m == self.i_pass:
						new_item[new_key][m] = new_item2
					elif m+1 == self.i_pass:
						new_item[new_key].append(new_item2)
					else:
						pass	
				else:
					new_item[new_key] = []
					new_item[new_key].append(new_item2)
			else:
				new_item[new_key] = []
				new_item[new_key].append(new_item2)
				self.edge_values.append(new_item)

	def update_edges_json(self):
		for item in self.graph_update:
			if item['key'] == 'deledge':		
				idx = self.find_in_json(item['prop']['label'])
				if idx >= 0:
					self.json_data["edges"].pop(idx)
			elif item['key'] == 'addedge':
				new_item = {}
				new_item['prop'] = item['prop']
				new_item['nodes'] = item['nodes']
				self.json_data["edges"].append(new_item)

	def path2str(self, path):
		sPath = ""
		for node in path:
			status,label = self.get_label_prop(node)
			sPath = sPath+str(node)+":"+label+" "
		return sPath

	def get_computed_str(self, a, prefix1 = ""):
		ac_gen = self.gen['prop']['ac_gen']
		if ac_gen['mode'] == 1:
			prefix="Z"
		else:	
			prefix="R"

		if self.use_superposition:
			post_str = str(self.i_pass)
		else:
			post_str = ""	
		f_inc = False
		comp_str = prefix+prefix1
		if a < 25:
			code = chr(97+a)
			if f"{code}" == "l":
				a = a+1
				code = chr(97+a)
				f_inc = True
			s = f"{comp_str}{code}{post_str}"
		else:
			s = f"{comp_str}x{a}{post_str}"
		return f_inc, s

	def create_item(self, gen, m, value, flags):
		item = {}; prop = {}
		item["nodes"] = gen["nodes"]	
		if flags == FLAGS_SHORT:
			prop["label"] = f"{SHORT_CIRCUIT_PREFIX}{m}"
		else:
			prop["label"] = f"{OPEN_CIRCUIT_PREFIX}{m}"
		prop["match_label"] = ""
		prop["CompId"] = RES_
		prop["UniqueID"] = "<none>"
		prop["value"] = value
		prop["flags"] = flags
		item["prop"] = prop
		return item

	def cgen_remove_connected_edges(self, gen):
		fifo = []; edge_list = []
		for node in gen['nodes']:
			m = self.G.degree(node)
			if m != 1:
				raise Exception('Current source: Invalid connections')
			if self.G.degree(node) <= 2:
				fifo.append(node)
		while len(fifo) > 0:
			node = fifo[0]
			for node_adj in self.G.iteradjacent(node):
				e = self.G[node][node_adj]
				edge_list.append(e)
				if self.G.degree(node_adj) <= 2:
					fifo.append(node_adj)
			fifo.pop(0)

		#remove the collected edges	
		for e in edge_list:
			self.G.del_edge(e)	

		#remove orphaned nodes
		node_list=[]
		for node in self.G.iternodes():
			if self.G.degree(node) == 0:
				node_list.append(node)
		for node in node_list:
			self.G.del_node(node)		

	def find_edge_in_G(self, label):
		for e in self.G.iteredges():
			if label == e.prop["label"]:
				return True
		return False	

	def getdir_from_dctable(self, i_pass, label):
		dctable = self.json_data["dctables"][self.i_pass]
		key = "currents"; res = True
		idx = self.find_in_json(label)

		if idx >= 0:
			table = dctable[key]
			for item in table:
				if item['label'] == label:
					res = item['value'] >= 0.0
					break
		return res			

