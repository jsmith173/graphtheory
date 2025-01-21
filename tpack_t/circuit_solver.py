from graphtheory.structures.edges import Edge
from graphtheory.structures.graphs import Graph
from graphtheory.structures.factory import GraphFactory
from graphtheory.seriesparallel.sptrees import find_sptree
from graphtheory.seriesparallel.spnodes import node_global_init
import os, json
from pathlib import Path
from json2xml import json2xml
from tpack_t import circuit_solver_util as cu
from tpack_t.circuit_solver_graph import TCircuitSolverGraph
from tpack_t import circuit_solver_graph as cg
import math, cmath, copy

def_weight = 1

class SolverException(Exception):
    pass
	
class DummyException(Exception):
    pass

class RequestException(Exception):
    pass

class TCircuitSolver:
	def __init__(self, fn_, opts = None):
		node_global_init()
		self.debug_impedance = []; self.debug_test_preorder = []; self.solution_log = []; 
		self.formula = ''; self.lc = 1; self.stop_solver = False

		self.fn = fn_
		fn2 = Path(fn_)
		self.fn_wo_ext = str(fn2.with_suffix(''))
		
		fn2 = Path(self.fn_wo_ext)
		self.fn2_wo_ext = fn2.name
		
		fn2 = Path(self.fn2_wo_ext)
		self.fn_base_wo_ext = str(fn2.with_suffix(''))

		self.opts = opts
		self.graph = TCircuitSolverGraph(self.fn, opts)
		
		self.has_expected_key = False
		self.expected_key = {}; self.block_labels = []

	def prepare_solver(self, circuit_key):
		self.solution = {}
		if not os.path.isfile(self.fn):
			raise Exception(f"File not found: {self.fn}")
		self.has_expected_key, self.expected_key, self.gen, self.request = self.graph.prepare(circuit_key)
		self.last_node = None
		return self.expected_key

	def prepare_calc_str_impedance(self, top, left, right, flag):
		arr = []
		status, tmp = self.graph.get_label_prop(left, flag)
		if status:
			arr.append(tmp)
		status, tmp = self.graph.get_label_prop(right, flag)
		if status:
			arr.append(tmp)
		status, c = self.graph.get_label_prop(top, flag)
		return c, arr

	def make_item_impedance(self, s, one_item=False, s_top="", s_left="", s_right="", top=None, left=None, right=None, labels=None, unique_labels=None, nodes=[]):
		item = {}; item['txt'] = s; item['one_item'] = one_item; item['s_top'] = s_top; item['s_left'] = s_left; item['s_right'] = s_right
		if left != None:
			item['left_type'] = left.type; item['right_type'] = right.type; item['top_type'] = top.type
			item['left_node_id'] = left.detail_id
			item['right_node_id'] = right.detail_id
			item['top_node_id'] = top.detail_id
			item['labels'] = labels
			item['unique_labels'] = unique_labels
			item['nodes'] = nodes
		return item	

	def calc_str_impedance(self, top, left, right, values, v, labels, unique_labels):
		c, arr_left = self.prepare_calc_str_impedance(top, left, right, False)
		c, arr = self.prepare_calc_str_impedance(top, left, right, True)

		nodes = []
		tmp = []; tmp.append(left.source); tmp.append(left.target); nodes.append(tmp)
		tmp = []; tmp.append(right.source); tmp.append(right.target); nodes.append(tmp)

		if len(arr) == 1:
			a = arr[0]
			s = f"{c}={a}"
			one_item = True; s_left = a; s_right = "" 
		else:	
			a = arr[0]; b = arr[1]
			a_l = arr_left[0]; b_l = arr_left[1]
			if top.type == "series":
				s = f"{a_l} and {b_l} connected in series so {c}={a}+{b}={cu.fv(v)}Ohm"	
			if top.type == "parallel":
				s = f"{a_l} and {b_l} connected in parallel so {c}={a}*{b}/({a}+{b})={cu.fv(v)}Ohm"
			tmp = {}; tmp['name'] = c; tmp['value_str'] = f"{cu.fv(v)}Ohm"; self.calc_symbols.append(tmp)
			one_item = False; s_left = a_l; s_right = b_l
		s_top = c	
		item = self.make_item_impedance(s, one_item, s_top, s_left, s_right, top, left, right, labels, unique_labels, nodes)	
		return item

	def is_connected(self, a, b):
		for i in a:
			for j in b:
				if j == i:
					return True
		return False		
	
	def find_in_blocks(self, label):
		i = 0; list_ = self.total_impedance
		while i < len(list_):
			item = list_[i]
			if item['s_top'] == label:
				return True, item
			i = i+1
		return False, {}

	def calc_impedance(self, node, left, right, level):
		values = self.graph.get_vals(left, right, 'impedance')
		v = 0; labels_ = []; labels = []; aStatus = []; nodes = []; edge_series = ["edge", "series"]
		n = left; s_left = n.to_str()		
		n = right; s_right = n.to_str()
		n = node; s_target = n.to_str()

		status, c = self.graph.get_label_prop(left); labels_.append(c); aStatus.append(status)
		status, c = self.graph.get_label_prop(right); labels_.append(c); aStatus.append(status)

		for i in range(2):
			if aStatus[i]:
				labels.append(labels_[i])
				if i == 0:
					nodes.append(left)
				else:
					nodes.append(right)	

		#self.graph.check_composed_label(node, left, right)
		unique_labels = self.graph.get_unique_labels(nodes)

		if node.type == "series":
			for value in values:
				v = v+value
		elif node.type == "parallel":
			if len(values) > 1:
				for value in values:
					v = v+1/value
				v = 1/v	
			elif len(values) == 1:
				v = values[0]	
		valid = len(values) > 0
		self.graph.set_node_val(node, v, valid, 'impedance')		
		item = self.calc_str_impedance(node, left, right, values, v, labels, unique_labels)		
		#s1 = f"lv: {level}, nv: {len(values)}, l: {s_left}, r: {s_right}, targ: {s_target}, ltype: {left.type}, rtype: {right.type}, type: {node.type}, new: {v}"		
		self.total_impedance.append(item)
		if not self.silent:
			s1 = self.graph.dbg_node(node, left, right)
			self.debug_impedance.append(s1)
		self.prev_type = node.type

	def finalize_calc_impedance(self, top):
		status, c = self.graph.get_label_prop(top)
		status, value = self.graph.get_node_val(top, 'impedance')
		s = f"The total {self.get_impedance_str()} is {c} = {cu.fv(value)}Ohm"	
		item = self.make_item_impedance(s)
		self.total_impedance.append(item)
		self.replaced_one_items = self.process_impedance()

	def replace_txt(self, target, src, dest):
		for i in range(len(target)):
			item = target[i]
			if not item['one_item']:
				txt = item['txt']
				item['txt'] = cu.replace_all_whole_words(txt, src, dest)
				target[i] = item

	def get_value_from_calc_str(self, s):
		for item in self.calc_symbols:
			if item['name'] == s:
				return True, item['value_str']
		return False, ''
		
	def process_impedance(self):
		#process 'one_item': remove some rules, replace 'txt'
		self.total_impedance_ori = copy.deepcopy(self.total_impedance); new_list = []
		i = 0; target = self.total_impedance
		while i < len(target):
			item = target[i]
			if item['one_item']:
				if item['s_left'] == "":
					raise Exception('process_impedance')
				self.replace_txt(target, item['s_top'], item['s_left'])
				new_item = {}
				new_item['s_top'] = item['s_top']
				new_item['s_left'] = item['s_left']
				new_list.append(new_item)
				target.pop(i)
			else:
				i = i+1	

		#reprocessing 'new_list'
		target = self.total_impedance
		for new_item in new_list:
			for i in range(len(target)):
				target_item = target[i]
				if target_item['s_top'] != '':
					for j in range(len(target_item['labels'])):
						label = target_item['labels'][j]
						if label == new_item['s_top']:
							target_item['labels'][j] = new_item['s_left']					
							idx = self.graph.find_in_json(new_item['s_left'])
							if idx >= 0:
								e = self.graph.json_data["edges"][idx]
								prop = e["prop"]
								target_item['unique_labels'][j] = prop["UniqueID"]					


		# create 'block_labels'
		self.block_labels.extend(self.graph.yd_labels)
		i = 0; target = self.total_impedance
		while i < len(target):
			item = target[i]
			if item['s_top'] != '':
				f, value = self.get_value_from_calc_str(item['s_top'])
				new_item = {}
				new_item['label'] = item['s_top']
				new_item['origin'] = item['top_type']
				if f:
					new_item['value'] = value
				new_item['labels'] = item['labels']
				new_item['unique_labels'] = item['unique_labels']
				self.block_labels.append(new_item)
			i = i+1
				
		# create 'txt'		
		for item in self.total_impedance_ori:
			self.total_impedance_ori_txt.append(item['txt'])		
		for item in self.total_impedance:
			self.total_impedance_txt.append(item['txt'])		

		return new_list

	def walk_postorder(self, top, level=0):
		if top is None:
			return
		self.walk_postorder(top.left, level+1)
		self.walk_postorder(top.right, level+1)
		if top.type == 'series' or top.type == 'parallel':
			self.calc_impedance(top, top.left, top.right, level)
			need_bracket = True
			if level == 0:
				need_bracket = False
			if top.type == 'series':
				if top.left.formula == "" or top.left.formula == "<split>":
					top.formula = f"{top.right.formula}"
					if top.right.type == "edge":
						need_bracket = False
				elif top.right.formula == "" or top.right.formula == "<split>":
					top.formula = f"{top.left.formula}"
					if top.left.type == "edge":
						need_bracket = False
				else:	
					top.formula = f"{top.left.formula}+{top.right.formula}"
			else:	
				top.formula = f"{top.left.formula}x{top.right.formula}"
			if need_bracket:	
				top.formula = f"({top.formula})"
		else:
			status, formula = self.graph.get_label_prop(top)
			top.formula = formula
			valid, v = self.graph.get_val(top, 'impedance')
			self.graph.set_node_val(top, v, valid, 'impedance') #required if we have one edge only
			node = top; s_node = node.to_str()		
			s = f"lv: {level}, nv: 1, node: {s_node}, type: {node.type}, value: {v}"
			if not self.silent:
				self.debug_impedance.append(s)

	def test_preorder(self, node, left, right, level):
		s1 = self.graph.dbg_node(node, left, right)
		self.debug_test_preorder.append(s1)

	def log(self, s):
		self.solution_log.append(s)

	def log_info(self, s):
		if self.opts['log_info'] == 1:
			self.solution_log.append(s)

	def logl(self, s):
		self.solution_log.extend(s)

	def find_replaced_one_items(self, a):
		for item in self.replaced_one_items:
			if item['s_top'] == a:
				return True, item['s_left']
		return False, a
	
	def calc_circuit(self, node, left, right, level):
		new_val = []; labels = []; labels_ = []; nodes = []; ltype = left.type; rtype = right.type; aStatus = []; labels_z_ = []; labels_z = []

		if self.stop_solver:
			return
		
		impedance = self.graph.get_vals(left, right, 'impedance'); N = len(impedance)

		status, c = self.graph.get_label_prop(left, True); labels_z_.append(c) 
		status, c = self.graph.get_label_prop(right, True); labels_z_.append(c)

		status, c = self.graph.get_label_prop(left); labels_.append(c); aStatus.append(status)
		status, c = self.graph.get_label_prop(right); labels_.append(c); aStatus.append(status)

		status, top_label = self.graph.get_label_prop(node)
		f, top_label = self.find_replaced_one_items(top_label)

		status, voltage = self.graph.get_node_val(node, 'voltage')
		status, current = self.graph.get_node_val(node, 'current')
		status, impedance_parent = self.graph.get_node_val(node, 'impedance')

		sum_impedance = 0
		for i in range(N):
			sum_impedance = sum_impedance+impedance[i]

		is_req_label = False
		for i in range(2):
			if aStatus[i]:
				f, s = self.find_replaced_one_items(labels_[i])
				#s = labels_[i] 
				if self.request['comp'] == labels_[i]:
					is_req_label = True
				labels.append(s)
				labels_z.append(labels_z_[i])
				if i == 0:
					nodes.append(left)
				else:
					nodes.append(right)	

		if node.type == "series" or node.type == "parallel":
			node_list_ = []
			node_list_.append(str(node.source)); node_list_.append(str(node.target))
			parent_node_list = ",".join(node_list_)
			label_list = ",".join(labels)
			#label_list_ = self.graph.resolve_composed_labels(node, labels)
			#label_list = ",".join(label_list_)

		if node.type == "series":
			for i in range(N):
				v = impedance[i]/sum_impedance*voltage; new_val.append(v)

			for i in range(N):
				node_list_ = []
				node_list_.append(str(nodes[i].source)); node_list_.append(str(nodes[i].target))
				node_list = ",".join(node_list_)

				directed_nodes = self.graph.get_directed_nodes(node, nodes[i])
				self.graph.set_node_val(nodes[i], new_val[i], True, 'voltage', directed_nodes, node)
				self.graph.set_node_val(nodes[i], current, True, 'current', directed_nodes, node)
				#status, block_rules = self.resolve_composed_labels_rules(labels)
 
				status, M = cu.in_path(nodes[i], self.request_path)
				if M != "":
					self.last_node = nodes[i]
					M = f"({self.lc}) "; self.lc = self.lc+1
					if len(labels) == 1:
						if top_label != labels[i]:
							self.log(f"{M}The voltage on {labels[i]} is {cu.fv(voltage)}V because the voltage is {cu.fv(voltage)}V on {top_label}") 
					else:
						self.log(f"{M}The components {label_list} connected in series.")
						self.log(f"{M}The voltage between this components starting and ending node is {cu.fv(voltage)}V.") 
						self.log(f"{M}{labels[i]} is in the voltage divider so the voltage on {labels[i]} is " \
			                     f"{labels_z[i]}/{top_label}*{cu.fv(voltage)}V = {cu.fv(new_val[i])}V. ")
					if self.request['cmd'] == 'get_voltage':
						pass
					elif self.request['cmd'] == 'get_current':
						self.log(f"{M}The current on {labels[i]} is the 'voltage on {labels[i]} / {labels_z[i]}' = {cu.fv(new_val[i]/impedance[i])}A .")
					self.log("")

				self.graph.set_node_val(nodes[i], current, True, 'current', directed_nodes, node) 

		elif node.type == "parallel":
			v = impedance_parent/impedance[0]*current; new_val.append(v)
			v = impedance_parent/impedance[1]*current; new_val.append(v)

			for i in range(2):
				directed_nodes = self.graph.get_directed_nodes(node, nodes[i])
				self.graph.set_node_val(nodes[i], voltage, True, 'voltage', directed_nodes, node) 
				self.graph.set_node_val(nodes[i], new_val[i], True, 'current', directed_nodes, node) 
				status, M = cu.in_path(nodes[i], self.request_path)
				if M != "":
					self.last_node = nodes[i]
					if is_req_label:
						s = self.request['comp']
					else:
						s = labels[i]
					M = f"({self.lc}) "; self.lc = self.lc+1
					self.log(f"{M}The components {label_list} connected in parallel. The voltage on {s} is {cu.fv(voltage)}V because the voltage on {top_label} is {cu.fv(voltage)}V")
					self.log("")
					if self.request['cmd'] == 'get_voltage':
						pass
					elif self.request['cmd'] == 'get_current' and nodes[i].type == "edge":
						self.log(f"{M}The current on {labels[i]} is the 'voltage on {labels[i]} / {labels_z[i]}' = {cu.fv(new_val[i])}A .")
		else:
			pass
		if is_req_label:
			self.stop_solver = True

	def walk_preorder(self, top, level=0):
		if top is None or self.stopped:
			return	

		if self.conf_preorder_test == 1:
			if top.left is None:
				status, c = self.graph.get_label_prop(top)
				s_target = top.to_str()
				s1 = f"targ: {s_target}:{c}:{top.type}"		
				self.debug_test_preorder.append(s1)
			else:	
				self.test_preorder(top, top.left, top.right, level)
		else:
			if top.left is None:
				status, c = self.graph.get_label_prop(top)
			else:
				self.calc_circuit(top, top.left, top.right, level)

		self.walk_preorder(top.left, level+1)
		self.walk_preorder(top.right, level+1)

	def get_gen_value(self):
		ac_gen = self.gen['prop']['ac_gen'] 
		comp_id = self.gen['prop']['CompId']
		if ac_gen['mode'] == 1:
			A = ac_gen['AbsV']
			fi = math.radians(ac_gen['Phase'])
			V = cmath.rect(A, fi)
		else:
			V = self.gen['prop']['value']	
		tmp = {}; tmp['value'] = V; 
		if comp_id == cg.CSOUR_ or comp_id == cg.CGEN_:
			tmp['quantity'] = 'current'
			tmp['unit'] = 'A'
		else:	
			tmp['quantity'] = 'voltage'
			tmp['unit'] = 'V'
		return tmp

	def get_impedance_str(self):
		ac_gen = self.gen['prop']['ac_gen']
		if ac_gen['mode'] == 1:
			return 'impedance'
		else:
			return 'resistance'

	def run(self, circuit_key):
		self.gens = self.graph.json_data['gens']
		self.nGens = len(self.graph.json_data['gens'])
		self.solution['superposition'] = []
		self.block_labels = []; self.used_gens = []

		self.graph.debug_graph()

		if self.graph.use_superposition:
			#self.logl(self.graph.graph_debug)
			self.log("We have more than one generator so we are using superposition to calculate voltages/currents.")
			self.log("")

		#replacing generators
		for i in range(len(self.gens)):
			self.gen = self.gens[i]
			self.graph.i_pass = i
			self.run_pass(circuit_key, i)

		comp = self.request["comp"]
		request_txt = cu.get_request_txt(self.request)
		self.graph.calc_final_nodal_edges(request_txt)

		if self.graph.use_superposition:
			self.log(f"")
			self.log(f"Now we are using superposition to calculate the {request_txt} on {comp}")

			idx = self.graph.find_edge_value_by_label(comp)
			if idx < 0:
				raise Exception(f"Comp not found while trying to calculate superposition: {comp}")
			value = self.graph.edge_values[idx]

			self.log(f"Let's summarize the calculations from the previous section.")
			self.log("When you see subtraction here it means that the original direction reversed.")
			#self.log("The direction of voltage/current determined by TINA.")
			v, v_str = self.calc_final_nodal_edge(value, request_txt)
			self.log(f"'{request_txt} on {comp}' = {v_str} = {cu.fv(v)}{self.unit}")

		#after run_pass
		if (self.request['cmd'] == 'get_voltage' and self.request['volt_meter_question'] or \
		    self.request['cmd'] == 'get_current' and self.request['amper_meter_question']):
			self.answer_meter()

		if self.has_expected_key:
			v, v_str = self.get_result()
			v1 = abs(v)
			v2 = abs(self.expected_key['res_req'])
			if abs(v1-v2) > 1e-3:
				self.log_info(f"*** Wrong ***: expected: {cu.fv(self.expected_key['res_req'])}, got: {cu.fv(v)}")
				raise SolverException(f"Solver error: {self.fn}")
			else:
				self.log_info(f"*** Passed ***: expected: {cu.fv(self.expected_key['res_req'])}, got: {cu.fv(v)}")
		
		self.write_log(1, 'OK', 0, True)

	def check_amper_meter_question(self):
		label = self.request['comp']
		idx = self.graph.find_in_json(label)
		if idx >= 0:
			e = self.graph.json_data["edges"][idx]
			prop = e["prop"]; comp_id = prop['CompId'] 
		else:
			comp_id = -1	
		if not self.request['amper_meter_question'] and (comp_id == cg.AMPER_METER_ or comp_id == cg.AMPER_METER2_):
			raise Exception(f"Error while processing ampermeter {label}")

	def get_result(self):
		request_txt = cu.get_request_txt(self.request)
		comp = self.request["comp"]
		idx = self.graph.find_edge_value_by_label(comp)
		if idx < 0:
			raise Exception(f"{comp} not found while trying to calculate the meter {meter_name}")
		value = self.graph.edge_values[idx]
		return self.calc_final_nodal_edge(value, request_txt)
	
	def answer_meter(self):
		request_txt = cu.get_request_txt(self.request)
		if request_txt == "voltage":
			sMeter = "voltmeter"
		else:
			sMeter = "ampermeter"	

		meter_name = self.request["comp_ori"]
		f, meter = self.graph.find_meter(meter_name)

		comp = self.request["comp"]
		idx = self.graph.find_edge_value_by_label(comp)
		if idx < 0:
			raise Exception(f"{comp} not found while trying to calculate the meter {meter_name}")
		value = self.graph.edge_values[idx]
		v, v_str = self.calc_final_nodal_edge(value, request_txt)

		if request_txt == "voltage":
			if value['nodes'] == meter['nodes']:
				polarity = 1.0
			else:
				polarity = -1.0	
			v = v*polarity
			self.log(f"To answer the original question: because the {meter_name} {sMeter} connected to {comp} parallel so the {request_txt} on {meter_name} is {cu.fv(v)}V")
			if polarity < 0:
				self.log(f"We have considered also that the polarity of the {sMeter} does not match the {request_txt} direction on {comp}")
			#if reversed and not self.graph.use_superposition:
			#	self.log(f"We have considered also that the {request_txt} direction on {comp} is reversed")
		else:
			#ampermeters1
			f = False
			for i in range(len(meter['nodes'])):
				item = meter['nodes'][i]
				for j in range(len(value['nodes'])):
					item2 = value['nodes'][j]
					if item2 == item:
						ii = i; jj = j; f = True; break
				if f:
					break
			# ii: 0: plus node, 1: minus node	
			# ii=0,jj=1	
			AM_PLUS_NODE = 0; AM_MINUS_NODE = 1; FIRST_NODE = 0; SECOND_NODE = 1
			if f:
				if ii == AM_PLUS_NODE and jj == SECOND_NODE or ii == AM_MINUS_NODE and jj == FIRST_NODE:
					polarity = 1.0
				elif ii == AM_MINUS_NODE and jj == SECOND_NODE or ii == AM_PLUS_NODE and jj == FIRST_NODE:
					polarity = -1.0
				v = v*polarity
				self.log(f"To answer the original question: because the {meter_name} {sMeter} connected to {comp} in series so the {request_txt} on {meter_name} is {cu.fv(v)}A")
				if polarity < 0:
					self.log(f"We have considered also that the direction of the {sMeter} does not match the {request_txt} direction on {comp}")

		self.log(f"We have considered also the sign of the {request_txt} on {comp}")

	def calc_final_nodal_edge(self, item, key):
		items = item[f"{key}_items"]
		item2 = items[0]
		if item2['original_dir']:
			v0 = item2[key]
		else:	
			v0 = -item2[key]
		v_str = f"{cu.fv(v0)}{self.unit}"
		v = v0; i = 1
		while i < len(items):
			item2 = items[i]
			v0 = item2[key]
			if item2['original_dir']:
				v = v+v0
				v_str = v_str+f"+{cu.fv(v0)}{self.unit}"
			else:	
				v = v-v0
				v_str = v_str+f"-{cu.fv(v0)}{self.unit}"
			i = i+1	
		return v, v_str

	def mark_ampermeters(self):
		i = 0; list_ = self.graph.json_data["edges"]
		for i in range(len(list_)):
			item = list_[i]; comp_id = item["prop"]["CompId"]
			if comp_id == cg.AMPER_METER_ or comp_id == cg.AMPER_METER2_:
				item["prop"]["flags"] = cg.FLAGS_NONE
				list_[i] = item

	def check_ampermeters(self):
		i = 0; list_ = self.graph.json_data["edges"]; f = False
		for i in range(len(list_)):
			item = list_[i]; comp_id = item["prop"]["CompId"]
			if comp_id == cg.AMPER_METER_ or comp_id == cg.AMPER_METER2_:
				f = True
		return f	
	
	def get_amper_meters(self):
		am_edges = []
		for e in self.graph.edges:
			prop = e.prop; comp_id = prop['CompId']
			if comp_id == cg.AMPER_METER_ or comp_id == cg.AMPER_METER2_:
				am_edges.append(e)
		for e in am_edges:		
			found = False
			for node in [e.source, e.target]:
				if node == e.source:
					node_next = e.target
				else:
					node_next = e.source
				am_label = e.prop['label'] 		
				if self.graph.G.degree(node) == 2:
					for node_adj in self.graph.G.iteradjacent(node):
						if node_adj != node_next:
							tmp = [node, node_adj]
							idx, f = self.graph.find_in_json_by_nodes(tmp)
							item = self.graph.json_data["edges"][idx]
							prop = item["prop"]
							if prop["flags"] == cg.FLAGS_NORMAL:
								tmp = {}; tmp['label'] = am_label; tmp['match_label'] = prop['label']; tmp['nodes'] = [e.source, e.target]
								self.graph.amper_meters.append(tmp)
								found = True
								break
				if found:
					break		
			if not found:
				raise Exception(f"Resistive component not found for ampermeter {am_label}")	

	def run_pass(self, circuit_key, i_pass):
		self.graph.computed_id = 0; self.graph.y_computed_id = 0; 
		self.graph.i_pass = i_pass
		self.total_impedance_ori_txt = []
		self.total_impedance_txt = []
		self.total_impedance = []
		self.graph.nodal_voltage_log = []
		self.stop_solver = False; nInserted = 0

		gen_comp_id = self.gen['prop']['CompId']
		is_v_gen_pass = gen_comp_id == cg.VSOUR_ or gen_comp_id == cg.VGEN_
		
		#init 'run_pass'
		#voltage gens: add extra edge before 'get_graph'
		for j in range(len(self.gens)):
			if j != i_pass:
				gen = self.gens[j]

				gen_comp_id = gen['prop']['CompId']
				is_v_gen = gen_comp_id == cg.VSOUR_ or gen_comp_id == cg.VGEN_

				if is_v_gen:
					item = self.graph.create_item(gen, j, 0.0, cg.FLAGS_SHORT)
					self.graph.json_data["edges"].append(item)
					nInserted += 1

		G = self.graph.get_graph(circuit_key)

		#self.solution['gen'] = self.gen
		self.solution['circuit'] = self.graph.graph_debug
		self.solution['request'] = self.request
		self.log_info(f">> Pass{i_pass+1} started ...")
		self.log_info(f">> Gen processing: {self.gen['prop']['label']} ...")
		
		self.mod = []
		#self.set_edge_directions()				
		#G = self.get_graph(circuit_key, True)

		if self.graph.show_tree == 1:
			for e in G.iteredges():
		 		print(e)
			print("")	
			for item in self.graph.graph_debug:
				print(item)
			print("")	

		fixed_ends = tuple(self.gen['nodes'])

		if self.graph.opts['test_Y'] == 1 or self.graph.opts['test_D'] == 1:
			status = self.graph.check_YD(fixed_ends)
			if status == 1:
				self.solution_log.extend(self.graph.yd_log)
				self.graph.update_edges_json()
			G = self.graph.G
		T = find_sptree(G, fixed_ends)

		if self.graph.show_tree == 1:
			cu.btree_print3(T); print("")

		#graph check
		cu.btree_check(T)

		#ampermeters1: processing apmermeters
		if i_pass == 0:
			self.request['amper_meter_question'] = False; self.silent = False
			self.graph.amper_meters = []
			has_amper_meter = self.check_ampermeters()
			if has_amper_meter:
				#get the 'amper_meters'. walk_postorder can not use because it may find another 'series' component (for example 'Shortxx' res) 
				self.get_amper_meters()

				#mark ampetermeters with flags=0
				self.mark_ampermeters()

		if i_pass == 0 and has_amper_meter:
			for item in self.graph.amper_meters:
				if self.request["comp"] == item["label"]:
					self.request["comp_ori"] = self.request["comp"]
					self.request["comp"] = item["match_label"]
					self.request['amper_meter_question'] = True
					break
			self.check_amper_meter_question()

		#get path for 'comp'
		paths = []		
		cu.btree_print_all_path(T, [], paths)
		if self.graph.show_tree == 1:
			for path in paths:
				sPath = self.graph.path2str(path)
				print(sPath)
			print("")

		label = self.request['comp']
		comp_label = self.request['comp']; gen_name = self.gen['prop']['label']
		if gen_name == comp_label:
			self.request['req_on_gen'] = True
		else:	
			status = self.graph.find_edge_in_G(label)
			if not status:
				self.log_info(f"The component {label} removed from the graph so we break this pass.")
				return
			status, self.request_path = self.graph.find_path(label, paths)	
			if not status:
				raise RequestException(f"Request error: {label} not found")
			sPath = self.graph.path2str(self.request_path)
			if self.graph.show_tree == 1:
				print(sPath)

		#calculating the impedance
		self.prev_type = None; self.calc_symbols = []
		self.walk_postorder(T)
		self.finalize_calc_impedance(T)
		if self.has_expected_key:
			T.prop['expected'] = self.expected_key['res_req']
		T.prop['circuit_key'] = circuit_key
		if self.graph.show_result:
			print(""); print(T.prop)

		self.formula = T.formula	
		#if self.has_expected_key and abs(self.expected_key['res_imp']-T.prop['impedance']) > 1e-4:
		#	raise SolverException(f"Solver error: {self.fn}")
		
		#Prepare gen
		gen_new_value = self.get_gen_value()
		ac_gen = self.gen['prop']['ac_gen'] 

		# Prepare log
		if self.request['cmd'] == 'get_voltage':
			self.unit = "V"
		elif self.request['cmd'] == 'get_current':
			self.unit = "A"
		elif self.request['cmd'] == 'get_impedance':
			self.unit = "Ohm"
		comp_label = self.request['comp']; gen_name = self.gen['prop']['label']
		request_txt = cu.get_request_txt(self.request)
		if i_pass == 0:
			if ac_gen['mode'] == 1:
				freq = ac_gen['FreqStr']
				self.log(f"This is an AC calculation")
				self.log(f"We know that generator frequency is f={freq} Hz, w=2*pi*f")
			else:	
				self.log(f"*** Solution by TINA assisted by AI ***")

		# calculating voltage/currents
		# set values on top node
		self.graph.set_node_val(T, gen_new_value['value'], True, gen_new_value['quantity'], self.gen['nodes']) 
		if gen_new_value['quantity'] == 'voltage':
			self.graph.set_node_val(T, T.prop['voltage']/T.prop['impedance'], True, 'current', self.gen['nodes']) 
		else:
			voltage_val = T.prop['current']*T.prop['impedance']	
			self.graph.set_node_val(T, voltage_val, True, 'voltage', self.gen['nodes']) 

		self.log(f"At first we calculate the total {self.get_impedance_str()} between the generator nodes ({gen_name})")
		self.logl(self.total_impedance_txt)
		self.log("")
		self.log(f"Now we calculate the {request_txt} on {comp_label}")

		val_str = f"{cu.fv(gen_new_value['value'])}{gen_new_value['unit']}"
		if gen_new_value['quantity'] == 'voltage':
			self.log(f"We know that the voltage between {gen_name} nodes is {val_str}.")
		else:	
			voltage_str = f"{voltage_val}V"
			self.log( f"We know that the voltage between {gen_name} nodes is {voltage_str}, "
			          f"because the generator current is Igen = {val_str} and the {self.get_impedance_str()} between the generator nodes is Rtot = {cu.fv(T.prop['impedance'])}Ohm so "
				 	  f"the voltage between the generator nodes is Igen*Rtot = {voltage_str}")

		if self.graph.use_superposition:
			gen_comp_id = self.gen['prop']['CompId']
			is_v_gen = gen_comp_id == cg.VSOUR_ or gen_comp_id == cg.VGEN_
			if is_v_gen:
				self.log(f"All voltage generators except for {gen_name} have been replaced with a short circuit.")
				self.log(f"All current generators have been replaced with an open circuit.")
			else:
				self.log(f"All voltage generators have been replaced with a short circuit.")
				self.log(f"All current generators except for {gen_name} have been replaced with an open circuit.")

		self.used_gens.append(gen_name)	
		self.log("")

		if self.request['req_on_gen']:
			status, value = self.graph.get_node_val(T, 'impedance'); impedance = value
			gen_new_value = self.get_gen_value()
			if gen_new_value['quantity'] == 'voltage':
				current = gen_new_value['value']/T.prop['impedance']
				if self.request['cmd'] == 'get_current':
					self.log(f"We know that the voltage between {gen_name} nodes is {cu.fv(gen_new_value['value'])}V.")
					self.log(f"We calculated previously the {self.get_impedance_str()} between {gen_name} nodes: this is {cu.fv(impedance)}Ohm.")
					self.log(f"So the current on {gen_name} is {cu.fv(current)}A.")
		else:
			self.conf_preorder_test = 1; self.stopped = False
			self.walk_preorder(T)
			self.conf_preorder_test = 0; self.stopped = False
			self.walk_preorder(T)
			
		pass_item = {}
		if self.graph.opts['debug_mode']:	
			#pass_item['total_impedance_silent'] = self.total_impedance_silent
			pass_item['total_impedance_ori_txt'] = self.total_impedance_ori_txt
			pass_item['total_impedance_txt'] = self.total_impedance_txt
			pass_item['gen'] = self.gen
			#pass_item['nodal_voltage_log'] = self.graph.nodal_voltage_log
		self.solution['superposition'].append(pass_item)

		self.write_log(1, 'OK', 0, False)

		#finalize 'run_pass'
		for i in range(nInserted):
			list_ = self.graph.json_data["edges"]
			N = len(list_)
			list_.pop(N-1)


	
	def write_log(self, valid, status, error_code=0, save_files=True):
		if error_code > 0:
			self.solution_log.append('Failed: see codes')

		edge_values_ = sorted(self.graph.edge_values, key=lambda d: d['label']) 
		#self.solution['edge_values'] = edge_values_ #tartalmazhat komplex szamokat is, amit a json nem tud kiirni: ne legyen benne a logban

		result = []
		for item in edge_values_:
			new_item = {}; new_item['label'] = item['label']
			for key in ["voltage", "current"]:
				if key in item.keys():
					new_value = {}
					value = item[key]
					if isinstance(value, complex):
						re = value.real; im = value.imag
						new_value['numtype'] = 'complex'
						new_value['re'] = re; new_value['im'] = im
					else:
						new_value['numtype'] = 'real'
						new_value['re'] = value.real
					new_item[key] = new_value
			result.append(new_item)	
		#self.solution['gens'] = self.used_gens
		#self.solution['result'] = result

		calculation = {}
		calculation['solution'] = self.solution_log
		if error_code == 0:	
			calculation['block_labels'] = self.block_labels

		calculation['fn'] = self.fn
		calculation['valid'] = valid
		calculation['error'] = error_code
		calculation['status'] = status

		self.solution['calculation'] = calculation

		if save_files:
			cu.dump_list(self.solution, f"temp/{self.fn_base_wo_ext}-solution.json")
			cu.dump_list(self.solution, f"temp/temp-solution.json")

			if self.opts['mode_all_files'] == 0:
				f = open(f"temp/{self.fn_base_wo_ext}-solution.xml", "w")
				f.write(json2xml.Json2xml(self.solution, wrapper="all", pretty=True, attr_type=False).to_xml())
				f.close()

				f = open(f"temp/temp-solution.xml", "w")
				f.write(json2xml.Json2xml(self.solution, wrapper="top", pretty=True, attr_type=False).to_xml())
				f.close()

