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
import graphtheory.seriesparallel.sptrees as spt
import math, cmath, copy

def_weight = 1

def pos_fn(sub, s):
	sub_ = sub.lower()
	s_ = s.lower()
	index = s_.find(sub_)
	return index

class ShortCircuitException(Exception):
    pass
	
class SolverException(Exception):
    pass
	
class DummyException(Exception):
    pass

class RequestException(Exception):
    pass

class TCircuitSolver:
	def __init__(self, fn_, opts = None):
		# one time init
		self.fn = fn_
		fn2 = Path(fn_)
		self.fn_wo_ext = str(fn2.with_suffix(''))
		
		fn2 = Path(self.fn_wo_ext)
		self.fn2_wo_ext = fn2.name
		
		fn2 = Path(self.fn2_wo_ext)
		self.fn_base_wo_ext = str(fn2.with_suffix(''))

		self.opts = opts
		self.rt_log = []
		
		# allocate
		self.graph = TCircuitSolverGraph(self.fn, opts)

		self.node_potentials_dbg = {}
		self.spec_log = []
		self.clean()

		
	def clean(self):
		self.graph.clean()

		node_global_init()
		self.debug_impedance = []; self.debug_test_preorder = []; 
		self.formula = ''; self.lc = 1; self.solver_silent = False

		self.has_expected_key = False
		self.expected_key = {}; self.block_labels = []
		self.ignored_resistances = []
		self.sv = {}
		self.set_sv_prop_i('short_circuit_pass', 0)
		self.set_sv_prop_i('insert_double_rmin', 0)
		self.set_sv_prop_i('open_circuit_pass', 0)
		
		if self.opts != None and 'request' in self.opts.keys():
			if (self.opts['request']['options'] & cg.LLM_LOUD) != 0:
				self.graph.sDiv = ' divided by '
				self.graph.sMul = ' multiplied by '
				self.graph.sOmega = ' omega '
				self.graph.sHz = ' hertz '
				self.graph.loud = True
			else:	
				self.graph.sDiv = '/'
				self.graph.sMul = '*'
				self.graph.sOmega = 'w'
				self.graph.sHz = 'Hz'
				self.graph.loud = False		
		
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

	def lab2res(self, label):
		if self.graph.is_amper_meter_by_label(label) or self.graph.is_volt_meter_by_label(label) or self.graph.is_gen(label):
			return f'R{label}'
		else:
			return label
	
	def calc_str_impedance(self, top, left, right, values, v, labels, unique_labels):
		c, arr_left = self.prepare_calc_str_impedance(top, left, right, False)
		c, arr = self.prepare_calc_str_impedance(top, left, right, True)

		nodes = []
		tmp = []; tmp.append(left.source); tmp.append(left.target); nodes.append(tmp)
		tmp = []; tmp.append(right.source); tmp.append(right.target); nodes.append(tmp)

		if len(arr) == 0:
			#dbg
			c, arr_left = self.prepare_calc_str_impedance(top, left, right, False)
			c, arr = self.prepare_calc_str_impedance(top, left, right, True)
			if not(c in self.ignored_resistances):
				self.log(f"{c} represents a temporary resistance with a value of 0")
				self.ignored_resistances.append(c)

		elif len(arr) == 1:
			a = self.lab2res(arr[0])
			s = f"{c}={a}"
			one_item = True; s_left = a; s_right = "" 
		else:	
			a = self.lab2res(arr[0]); b = self.lab2res(arr[1])
			a_l = arr_left[0]; b_l = arr_left[1]
			
			if pos_fn(cg.SHORT_CIRCUIT_PREFIX, a_l) >= 0:
				v0 = values[1]; values = []; values.append(v0); a = arr[1]
			elif pos_fn(cg.SHORT_CIRCUIT_PREFIX, b_l) >= 0:
				v0 = values[0]; values = []; values.append(v0); a = arr[0]		
			
			if top.type == "series":		
				if len(values) == 2:
					s1 = self.graph.fv(values[0])+"Ohm"; s2 = self.graph.fv(values[1])+"Ohm"
					s = f"{a_l} and {b_l} connected in series so {c}={a}+{b}={s1}+{s2}={self.graph.fv(v)}Ohm"	
				else:	
					s1 = self.graph.fv(values[0])+"Ohm"
					s = f"{c}={a}={s1}={self.graph.fv(v)}Ohm"	
			if top.type == "parallel":
				if len(values) == 2:
					s1 = self.graph.fv(values[0])+"Ohm"; s2 = self.graph.fv(values[1])+"Ohm"
					s = f"{a_l} and {b_l} connected in parallel so {c}={a}{self.graph.sMul}{b}{self.graph.sDiv}({a}+{b})={s1}{self.graph.sMul}{s2}{self.graph.sDiv}({s1}+{s2})={self.graph.fv(v)}Ohm"
				else:	
					s1 = self.graph.fv(values[0])+"Ohm"
					s = f"{c}={a}={s1}={self.graph.fv(v)}Ohm"	
			tmp = {}; tmp['name'] = c; tmp['value_str'] = f"{self.graph.fv(v)}Ohm"; self.calc_symbols.append(tmp)
			one_item = False; s_left = a_l; s_right = b_l
		if len(arr) > 0:
			s_top = c	
			item = self.make_item_impedance(s, one_item, s_top, s_left, s_right, top, left, right, labels, unique_labels, nodes)	
		else:
			item = {}; item['txt'] = ''; item['one_item'] = False; item['s_top'] = ''; item['s_left'] = ''; item['s_right'] = ''
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
				R1 = values[0]; R2 = values[1]
				v = R1*R2/(R1+R2)
			elif len(values) == 1:
				v = values[0]	
		valid = len(values) > 0
		self.graph.set_node_val(node, v, '', valid, 'impedance')		
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
		if self.request['ohm_meter_question']:			
			s = f"The ohm meter shows {c} = {self.graph.fv(value)}Ohm"	
		else:	
			s = f"The total {self.get_impedance_str()} is {c} = {self.graph.fv(value)}Ohm"	
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
			self.graph.set_node_val(top, v, '', valid, 'impedance') #required if we have one edge only
			node = top; s_node = node.to_str()		
			s = f"lv: {level}, nv: 1, node: {s_node}, type: {node.type}, value: {v}"
			if not self.silent:
				self.debug_impedance.append(s)

	def test_preorder(self, node, left, right, level):
		s1 = self.graph.dbg_node(node, left, right)
		self.debug_test_preorder.append(s1)

	def log(self, s):
		if pos_fn('R2 is in the voltage divider so the voltage on R2 is Rf0/Ra0*16 Volt', s) >= 0:
			a=1
		if not self.solver_silent:
			self.graph.log(s)

	def log_info(self, s):
		if self.opts['log_info'] == 1:
			self.graph.solution_log.append(s)

	def logl(self, s):
		self.graph.solution_log.extend(s)

	def find_replaced_one_items(self, a):
		for item in self.replaced_one_items:
			if item['s_top'] == a:
				return True, item['s_left']
		return False, a
	
	def calc_circuit(self, node, left, right, level):
		new_val = []; labels = []; labels_ = []; nodes = []; ltype = left.type; rtype = right.type; aStatus = []; labels_z_ = []; labels_z = []

		#if self.solver_silent:
		#	return
		
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
			label_list = " and ".join(labels)
			#label_list_ = self.graph.resolve_composed_labels(node, labels)
			#label_list = ",".join(label_list_)

		if node.type == "series":
			try:
				current = voltage/sum_impedance
			except ZeroDivisionError as e:
				raise ShortCircuitException("Division by zero in current calculation") from e
								
			for i in range(N):		
				r = impedance[i]/sum_impedance
				v = r*voltage; new_val.append(v)

			for i in range(N):
				node_list_ = []
				node_list_.append(str(nodes[i].source)); node_list_.append(str(nodes[i].target))
				node_list = ",".join(node_list_)

				directed_nodes = self.graph.get_directed_nodes(node, nodes[i])
				self.graph.set_node_val(nodes[i], new_val[i], labels[i], True, 'voltage', directed_nodes, node, f"({label_list} in {node.type})")
				self.graph.set_node_val(nodes[i], current, labels[i], True, 'current', directed_nodes, node)
				#status, block_rules = self.resolve_composed_labels_rules(labels)
 
				status, M = cu.in_path(nodes[i], self.request_path)
				if M != "" or self.request_path == '':
					self.last_node = nodes[i]
					M = f"({self.lc}) "; self.lc = self.lc+1
					
					f, tmp = self.graph.get_item_voltage(labels[i])
					# csak a kiirasba kellene beletenni, elrontja az ertekeket
					if False:
						changed = abs(voltage-tmp) > 1e-6
						#if changed:
						#	self.log(f"xxx Voltage dir change on {labels[i]}: old: {voltage}, new: {tmp}")
						voltage = tmp
						new_val[i] = tmp					
					
					if len(labels) == 1:
						if top_label != labels[i]:
							self.log(f"The voltage on {labels[i]} is {self.graph.fv(voltage)} {cg.uVolt} because the voltage is {self.graph.fv(voltage)} {cg.uVolt} on {top_label}") 
					else:
						self.log(f"The components {label_list} connected in series.")
						
						if self.graph.log_state_v['changed']:
							m = self.graph.log_state_v['i']
							n = self.graph.log_state_v['j']
							s_new_val = self.graph.log_state_v['txt1'] 
							s_nodes = f"(node numbers {m} and {n})"
						else:
							s_new_val = self.graph.fv(new_val[i])
							s_nodes = ""													
							
						self.log(f"The voltage between this components starting and ending node is {self.graph.fv(voltage)} {cg.uVolt}") 
						
						if not self.graph.is_amper_meter_by_label(labels[i]):
							self.log(f"{labels[i]} is in the voltage divider so the voltage on {labels[i]} is " \
									 f"{self.lab2res(labels[i])}{self.graph.sDiv}{top_label}{self.graph.sMul}{self.graph.fv(voltage)} {cg.uVolt} = {s_new_val} {cg.uVolt} {s_nodes}")
								 
					if self.request['cmd'] == 'get_voltage':
						pass
					elif self.request['cmd'] == 'get_current':
					
						if self.graph.is_amper_meter_by_label(labels[i]):
							current_str = f'<patch_AM_{labels[i]}>'
						else:
							current_str = self.graph.fv(current)
					
						self.log(f"The current in branch {top_label} is 'voltage on this branch'{self.graph.sDiv}'impedance in this branch' = {self.graph.fv(voltage)}{self.graph.sDiv}{self.graph.fv(sum_impedance)} = {self.graph.fv(current)} {cg.uCurrent}")
						self.log(f"The current on {labels[i]} is the current on {top_label}. Therefore the current on {labels[i]} is {current_str} {cg.uCurrent}")
					self.log("")

				self.graph.set_node_val(nodes[i], current, labels[i], True, 'current', directed_nodes, node) 

		elif node.type == "parallel":
			if N == 2:
				v = impedance[1]/(impedance[0]+impedance[1])*current; new_val.append(v)
				v = impedance[0]/(impedance[0]+impedance[1])*current; new_val.append(v)
			else:	
				v = current; new_val.append(v)

			for i in range(N):
				directed_nodes = self.graph.get_directed_nodes(node, nodes[i])
				self.graph.set_node_val(nodes[i], voltage, labels[i], True, 'voltage', directed_nodes, node) 
				self.graph.set_node_val(nodes[i], new_val[i], labels[i], True, 'current', directed_nodes, node) 
				status, M = cu.in_path(nodes[i], self.request_path)
				if M != "" or self.request_path == '':
					self.last_node = nodes[i]
					if is_req_label:
						s = self.request['comp']
					else:
						s = labels[i]
					M = f"({self.lc}) "; self.lc = self.lc+1
					
					f, tmp = self.graph.get_item_voltage(labels[i])
					# csak a kiirasba kellene beletenni, elrontja az ertekeket
					if False:
						changed = abs(voltage-tmp) > 1e-6
						#if changed:
						#	self.log(f"xxx Voltage dir change on {labels[i]}: old: {voltage}, new: {tmp}")
						voltage = tmp
						new_val[i] = tmp															
					
					self.log(f"The components {label_list} connected in parallel. The voltage on {s} is {self.graph.fv(voltage)} {cg.uVolt} because the voltage on {top_label} is {self.graph.fv(voltage)} {cg.uVolt}")
					self.log("")
					if self.request['cmd'] == 'get_voltage':
						pass
					elif self.request['cmd'] == 'get_current' and nodes[i].type == "edge":
						self.log(f"The current on {labels[i]} is the voltage on {labels[i]}{self.graph.sDiv}{labels[i]} = {self.graph.fv(new_val[i])} {cg.uCurrent} ")
		else:
			pass
		if is_req_label:
			self.solver_silent = True

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

	def run_proc(self, circuit_key):
		cu.dump_list(self.graph.json_data, 'data/temp'+'-mod.json')
		self.graph.amper_meters = []
		self.get_amper_meters()
		for i in range(len(self.gens)):
			self.gen = self.gens[i]
			self.graph.i_pass = i
			self.run_pass(circuit_key, i)	
		self.solver_silent = False		

	def run_w_check(self, circuit_key):
		i = 0
		in_cycle = True
		RMIN = cg.RMIN_ZERO
		while i < 20 and in_cycle:
			try:
				in_cycle = False
				self.sl(f'run_w_check: {i}')
				self.run(circuit_key, RMIN)
			except ShortCircuitException as e:
				self.sl(f'In {type(e).__name__} exception')
				in_cycle = True
				tmp = self.sv['insert_double_rmin']
				v0, v1, v2 = self.get_sv_props()
				self.clean()
				self.set_sv_props(v0, v1, v2)
				RMIN = cg.RMIN_SMALL
				self.set_sv_prop_i('short_circuit_pass', 1)
				i += 1
			except cg.GraphException as e:
				self.sl(f'In {type(e).__name__} exception')
				in_cycle = True
				v0, v1, v2 = self.get_sv_props()
				self.clean()
				self.set_sv_props(v0, v1, v2)
				RMIN = cg.RMIN_SMALL
				self.set_sv_prop_i('short_circuit_pass', 1)
				self.set_sv_prop_i('insert_double_rmin', 1)
				i += 1
			except ValueError as e:
				msg = str(e)
				if self.sv['open_circuit_pass'] == 0 and (msg == spt.sErrJackknife or msg == spt.sErrNotAnSpGraph):
					self.sl(f'In {type(e).__name__} exception: spec handling open_circuit_pass')
					in_cycle = True
					v0, v1, v2 = self.get_sv_props()
					self.clean()
					self.set_sv_props(v0, v1, v2)
					self.set_sv_prop_i('open_circuit_pass', 1)
					i += 1
				else:
					#self.write_log(1, str(e), 1)
					#self.graph.G.show()
					raise
			except Exception as e:
				self.sl(f'In {type(e).__name__} exception')
				raise	
	
	def run(self, circuit_key, RMIN=0):
		self.gens = self.graph.json_data['gens']
		self.nGens = len(self.graph.json_data['gens'])
		self.solution['superposition'] = []
		self.block_labels = []; self.used_gens = []
		self.graph.RMIN = RMIN

		self.graph.debug_graph()

		if (self.opts['request']['options'] & cg.LLM_ADD_SOL_TXT) != 0:
			self.log(f"Solution by TINA assisted by AI")

		if self.graph.use_superposition:
			#self.logl(self.graph.graph_debug)
			self.log("We have more than one generator so we are using superposition to calculate voltages/currents.")
			self.log(f"Names starting with {cg.SHORT_CIRCUIT_PREFIX} refer to very small resistances, used during superposition.")

		if self.sv['short_circuit_pass'] == 1:
			for item in self.graph.am_edges:
				v = self.graph.RMIN
				meter_name = item['prop']['label']
				meter_name_w_res = f'R{meter_name}'
				value_str = self.graph.fv(v)
				if abs(v) > cg.EPS:
					self.log(f"We assume that the internal resistance of {meter_name} is {meter_name_w_res}={value_str}Ohm")		

		if self.sv['open_circuit_pass'] == 1:
			for item in self.graph.vm_edges:
				v = cg.ROPEN
				meter_name = item['prop']['label']
				meter_name_w_res = f'R{meter_name}'
				value_str = self.graph.fv(v)
				self.log(f"We assume that the internal resistance of {meter_name} is {meter_name_w_res}={value_str}Ohm")		

		if self.graph.use_superposition:
			self.log("")
			
		self.node_potentials_dbg['node_potentials'] = []
		self.node_potentials_dbg['item_voltages'] = []

		# runs 'passes' (for superpositions)
		self.run_proc(circuit_key)

		node_potentials_pass = []
		for i in range(self.graph.max_node+1):
			re = 0.0
			im = 0.0
			flag = True
			for j in range(len(self.gens)):
				flag = flag and self.graph.v_flags[j][i]
				tmp_re = self.graph.v_re[j][i]
				re += tmp_re
				tmp_im = self.graph.v_im[j][i]
				im += tmp_im
				
			self.graph.v_potentials_re[i] = re
			self.graph.v_potentials_im[i] = im
			if abs(im) > 1e-15:
				s0 = self.graph.fv(complex(re, im))
			else:	
				s0 = self.graph.fv(re)
			
			self.graph.v_node_flags[i] = self.graph.v_node_flags[i] or flag
			s = f'VP_{i} = {s0}, assigned (and): {flag}'
			node_potentials_pass.append(s)		
		self.node_potentials_dbg['node_potentials'].append(node_potentials_pass)	
		
		self.write_log(1, 'OK', 0, True)
		a=1

		##
		self.node_potentials_dbg['item_voltages'] = []
		N = len(self.graph.json_data["dctables"])
		if N > 0:
			dctable = self.graph.json_data["dctables"][0]
			table = dctable['other voltages']
			
			self.sl(f'before calc_item_values')
			self.calc_item_values(table, False)
			self.calc_item_values(table, True)
			self.patch_log()
		
		##

		self.write_log(1, 'OK', 0, True)
		a=1

		comp = self.request["comp"]
		request_txt = cu.get_request_txt(self.request)

		meter_question = (self.request['cmd'] == 'get_voltage' and self.request['volt_meter_question'] or \
		                  self.request['cmd'] == 'get_current' and self.request['amper_meter_question'])
			
		if self.graph.use_superposition and not meter_question and not self.request['ohm_meter_question']:
			self.log(f"Now we are using superposition to calculate the {request_txt} on {comp}")
			self.log(f"Let's summarize the calculations from the previous sections. We sum the results of individual superposition runs for the given element.")
			f, v = self.get_final_value(comp, request_txt)
			if f:
				self.log(f"'{request_txt} on {comp}' = {self.graph.fv(v['value'])}{self.unit}")
			else:
				raise Exception(f'Key not found: {comp}')

		#after run_pass
		if (self.request['cmd'] == 'get_voltage' and self.request['volt_meter_question'] or \
		    self.request['cmd'] == 'get_current' and self.request['amper_meter_question']):
			self.answer_meter()

		if self.has_expected_key and not self.request['ohm_meter_question']:
			v, v_str = self.get_result()
			v1 = abs(v)
			v2 = abs(self.expected_key['res_req'])
			if abs(v1-v2) > 1e-3:
				self.log_info(f"*** Wrong ***: expected: {self.graph.fv(self.expected_key['res_req'])}, got: {self.graph.fv(v)}")
				raise SolverException(f"Solver error: {self.fn}")
			else:
				self.log_info(f"*** Passed ***: expected: {self.graph.fv(self.expected_key['res_req'])}, got: {self.graph.fv(v)}")
		
		self.write_log(1, 'OK', 0, True)

	def find_series_comp_proc(self, e):
		label = e['prop']['label']
		f = False
		ser_label = ''
		for item in self.block_labels:
			if item['origin'] == 'series':
				if item['labels'][0] == label:
					ser_label = item['labels'][1]
					f = True
				elif item['labels'][1] == label:
					ser_label = item['labels'][0]
					f = True				
				if f:	
					break	
		return f, ser_label								

	def find_single_label(self, labels, e):
		f = False
		label = ''
		for label in labels:
			idx = self.graph.find_in_json(label)
			e2 = self.graph.json_data["edges"][idx]
			is_single_label = idx >= 0		
			if is_single_label:
				is_connected, normal_polarity = self.graph.is_edges_connected(e, e2)
				if is_connected:
					return is_connected, normal_polarity, label
		return False, False, labels[0]

	def find_composed_label(self, label, e):
		found = False
		for i in range(len(self.block_labels)):
			o = self.block_labels[i]
			if o['origin'] =='series' and o['label'] == label:
				return self.find_single_label(o['labels'], e)
		return False, False, ''

	# In case of superposition find_series_comp may find a wrong component so we should use 'get_amper_meters' on the original graph
	def find_series_comp(self, e):
		fifo = []
		f = False; polarity = False
		ser_label = ''
		
		f, ser_label = self.find_series_comp_proc(e)
		if f:
			idx = self.graph.find_in_json(ser_label)
			e2 = self.graph.json_data["edges"][idx]
			is_single_label = idx >= 0
			if is_single_label:
				is_connected, polarity = self.graph.is_edges_connected(e, e2)
				return is_connected, polarity, ser_label
			else:	
				f, polarity, ser_label = self.find_composed_label(ser_label, e)
		return f, polarity, ser_label		

	def calc_item_values(self, table, calc_amper_meters):
		for item in table:
			new_item = {}
			i = item['nodes'][0]
			j = item['nodes'][1]
			new_item['nodes'] = item['nodes']			
			new_item['label'] = item['label']
			idx = self.graph.find_in_json(item['label'])
			label = item['label']
			
			is_vm_edge = False
			if idx < 0:
				idx = 0
				is_vm_edge, e = self.graph.is_volt_meter_by_edge(label)
			
			if idx >= 0:
				if is_vm_edge:
					is_vm_edge, e = self.graph.is_volt_meter_by_edge(label)
				else:	
					e = self.graph.json_data["edges"][idx]
					
				is_amper_meter = self.graph.is_amper_meter_by_label(label)
				is_resistive_comp = self.graph.is_resistive_or_ampmet_compid(e['prop']['CompId']);
				
				cond = calc_amper_meters and is_amper_meter or not calc_amper_meters and not is_amper_meter
				if is_resistive_comp and cond:
					value = e['prop']['value']
					new_item['value'] = value
					if self.graph.v_node_flags[i] and self.graph.v_node_flags[j]:
						re = self.graph.v_potentials_re[i]-self.graph.v_potentials_re[j]
						im = self.graph.v_potentials_im[i]-self.graph.v_potentials_im[j]					
						if abs(im) > 1e-15:
							r = complex(re, im)
						else:
							r = re					
						new_item['voltage'] = self.graph.fv(r)						
						
						# In case of superposition find_series_comp may find a wrong component so we should use 'get_amper_meters' on the original graph
						calc_current_from_voltage = True
						if calc_amper_meters and (abs(value) < cg.EPS):
							f, polarity, ser_label = self.graph.find_am_ser_comp(e)
							#f, polarity, ser_label = self.find_series_comp(e)
							if f:
								f, v = self.get_final_value(ser_label, 'current')
								current = v['value']
								if not polarity:
									current = -current
								calc_current_from_voltage = False
						
						if calc_current_from_voltage: #or self.graph.use_superposition:
							try:
								current = r/value
							except ZeroDivisionError as exc:
								if not is_vm_edge and not self.graph.is_gen(label):
									raise ShortCircuitException("Division by zero in current calculation") from exc
								else:
									current = 0 # divHACK
									self.sl(f'divHACK: calc_item_values: current: {current}')					
						
						if isinstance(current, complex):
							re = current.real; im = current.imag
						else:
							re = current; im = 0
						
						new_item['current'] = self.graph.fv(current)					
						new_item['current_re'] = re
						new_item['current_im'] = im
					else:	
						new_item['voltage'] = '<unassigned>'
						new_item['current'] = '<unassigned>'
					self.node_potentials_dbg['item_voltages'].append(new_item)
	
	
	def get_result(self):
		request_txt = cu.get_request_txt(self.request)
		comp = self.request["comp"]
		return 0 #TODO
	
	def answer_meter(self):
		if self.graph.use_superposition:
			self.log(f"Let's summarize the calculations from the previous sections. We sum the results of individual superposition runs for the given element.")
	
		request_txt = cu.get_request_txt(self.request)
		if request_txt == "voltage":
			sMeter = "voltmeter"
		elif request_txt == "current":
			sMeter = "ampermeter"
		else:
			sMeter = "ohmmeter"	

		show_meter_name = self.request["comp_ori"]
		if self.request["volt_meter_no_match"]:
			meter_name = self.request["comp"]
			f, meter = self.graph.find_meter(meter_name)

			if request_txt == "voltage":
				m = meter['nodes'][0]
				n = meter['nodes'][1]
				
				v = self.graph.get_diff_v(m, n)			
				self.log(f"To answer the original question: because the {sMeter} connected to node{m} and node{n} so the {request_txt} on {show_meter_name} is V({m},{n})={self.graph.fv(v)} {cg.uVolt}")
		else:
			meter_name = self.request["comp_ori"]
			f, meter = self.graph.find_meter(meter_name)
			if not f and request_txt == "voltage":
				f = self.graph.find_volt_meter()
				meter = self.graph.meter_prop

			comp = self.request["comp"]
			if request_txt == "voltage":
				status, v = self.get_final_value(comp, request_txt)
				polarity = 1.0
				v1 = v['value']*polarity
				self.log(f"To answer the original question: because the {sMeter} connected to {comp} parallel so the {request_txt} on {meter_name} is {self.graph.fv(v1)} {cg.uVolt}")
				#if polarity < 0:
				#	self.log(f"We have considered also that the polarity of the {sMeter} does not match the {request_txt} direction on {comp}")
				#if reversed and not self.graph.use_superposition:
				#	self.log(f"We have considered also that the {request_txt} direction on {comp} is reversed")
			else:
				#ampermeters1
				status, value = self.get_final_value(comp, request_txt)
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
					v1 = value['value']*polarity			
					self.log(f"To answer the original question: because the {meter_name} {sMeter} connected to {comp} in series so the {request_txt} on {meter_name} is {self.graph.fv(v1)} {cg.uCurrent}")
					#if polarity < 0:
					#	self.log(f"We have considered also that the direction of the {sMeter} does not match the {request_txt} direction on {comp}")

		#self.log(f"We have considered also the sign of the {request_txt} on {comp}")

	def match_nodes(self, n1, n2):
		sign_rev = False
		if n1[0] == n2[0] and n1[1] == n2[1]:
			return True, sign_rev
		elif n1[0] == n2[1] and n1[1] == n2[0]:
			sign_rev = True
			return True, sign_rev
		else:
			return False, False
		
	def get_final_value(self, comp, request_txt):
		idx = self.graph.find_in_json(comp)
		is_vm_edge = False
		if idx < 0:
			idx = 0
			is_vm_edge, e = self.graph.is_volt_meter_by_edge(comp)
		v = {}
		if idx >= 0:
			if is_vm_edge:
				is_vm_edge, e = self.graph.is_volt_meter_by_edge(comp)
			else:	
				e = self.graph.json_data["edges"][idx]
			for item in self.node_potentials_dbg['item_voltages']:
				if item['label'] == comp:
					f, sign_rev = self.match_nodes(e['nodes'], item['nodes'])
					if f:
						i = e['nodes'][0]
						j = e['nodes'][1]
						if request_txt == 'voltage':
							re = self.graph.v_potentials_re[i]-self.graph.v_potentials_re[j]
							im = self.graph.v_potentials_im[i]-self.graph.v_potentials_im[j]					
						elif request_txt == 'current':
							re = item['current_re']
							im = item['current_im']
						else:
							re = 0
							im = 0
						if sign_rev:
							re = -re
							im = -im					
						if abs(im) > 1e-15:
							r = complex(re, im)
						else:	
							r = re
						v['value'] = r	
						v['nodes'] = copy.deepcopy(item['nodes'])
						return True, v					
		return False, v					

	def check_ampermeters(self):
		i = 0; list_ = self.graph.json_data["edges"]; f = False
		for i in range(len(list_)):
			item = list_[i]; comp_id = item["prop"]["CompId"]
			if comp_id == cg.AMPER_METER_ or comp_id == cg.AMPER_METER2_:
				f = True
		return f	
	
	# collect amper meters using the original graph (keeping generators)
	def get_amper_meters(self):
		try:
			if self.graph.G != None:
				del self.graph.G
				self.graph.G = None
			G = self.graph.get_graph(self.graph.circuit_key)
			tmp_nodes = []
			MaxGR = self.graph.get_max_graph_number()
			# MaxGR is local var
			for j in range(len(self.gens)):
				gen = self.gens[j]

				gen_comp_id = gen['prop']['CompId']
				is_v_gen = gen_comp_id == cg.VSOUR_ or gen_comp_id == cg.VGEN_ or gen_comp_id == cg.RESMET_ or gen_comp_id == cg.RESMET2_

				if not is_v_gen:
					self.sl(f'get_amper_meters: adding extra edges')					

					tmp_edges = []
					i1 = gen['nodes'][0]
					i2 = MaxGR+1
					i3 = gen['nodes'][1]
					self.graph.G.add_node(i2)
					prop = cg.split_edge_prop
					
					edge = Edge(i1, i2, def_weight, prop)
					tmp_edges.append(edge)
					self.graph.G.add_edge(edge)
					
					edge = Edge(i2, i3, def_weight, prop)
					tmp_edges.append(edge)
					self.graph.G.add_edge(edge)
					
					tmp_nodes.append(i2)
					self.sl(f'MaxGR incremented: {MaxGR+1}')
		
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
								idx, f = self.graph.find_in_json_by_nodes(tmp, True)
								if f:
									item = self.graph.json_data["edges"][idx]
									prop = item["prop"]
									if prop["flags"] == cg.FLAGS_NORMAL:
										e2 = {}
										e2['nodes'] = []
										e2['nodes'].append(e.source)
										e2['nodes'].append(e.target)
										is_connected, polarity = self.graph.is_edges_connected(e2, item)
										tmp = {}; tmp['label'] = am_label; tmp['match_label'] = prop['label']; tmp['nodes'] = [e.source, e.target]
										tmp['connected'] = int(is_connected)
										tmp['polarity'] = int(polarity)
										self.graph.amper_meters.append(copy.deepcopy(tmp))
										found = True
										break
					if found:
						break		
				#if not found:
				#	raise Exception(f"Resistive component not found for ampermeter {am_label}")	
		finally:
			del self.graph.G
			self.graph.G = None
		
	def run_pass(self, circuit_key, i_pass):
		try:
			self.graph.computed_id = 0; self.graph.y_computed_id = 0; 
			self.graph.i_pass = i_pass
			self.total_impedance_ori_txt = []
			self.total_impedance_txt = []
			self.total_impedance = []
			self.graph.nodal_voltage_log = []
			
			# save/restore json in case of superpos (check parh3-ai.tsc)
			if len(self.gens) > 1:	
				self.sl(f'bkp_json_data')
				self.graph.bkp_json_data()
				self.sl(f'run_pass: {i_pass}')
			
			# nInserted is local var
			self.solver_silent = False; nInserted = 0
			self.bkp_request_comp = self.request['comp']

			gen = self.gen
			gen_comp_id = self.gen['prop']['CompId']
			is_v_gen_pass = gen_comp_id == cg.VSOUR_ or gen_comp_id == cg.VGEN_ or gen_comp_id == cg.RESMET_ or gen_comp_id == cg.RESMET2_
			
			#init 'run_pass'
			#voltage gens: add extra edge before 'get_graph'
			for j in range(len(self.gens)):
				if j != i_pass:
					gen = self.gens[j]

					gen_comp_id = gen['prop']['CompId']
					is_v_gen = gen_comp_id == cg.VSOUR_ or gen_comp_id == cg.VGEN_ or gen_comp_id == cg.RESMET_ or gen_comp_id == cg.RESMET2_

					if is_v_gen:
						
						if self.sv['insert_double_rmin'] == 1:
							MaxGR = self.graph.get_max_graph_number()
							i1 = gen['nodes'][0]
							i2 = MaxGR+1
							i3 = gen['nodes'][1]					
							
							nodes = []
							nodes.append(i1)
							nodes.append(i2)						
							item = self.graph.create_item(copy.deepcopy(nodes), j, self.graph.RMIN)
							self.graph.json_data["edges"].append(item)
							nInserted += 1
							
							nodes = []
							nodes.append(i2)
							nodes.append(i3)						
							item = self.graph.create_item(copy.deepcopy(nodes), j, self.graph.RMIN)
							self.graph.json_data["edges"].append(item)
							nInserted += 1
							
							self.graph.set_max_gr(MaxGR+1)				
							
							self.sl(f'MaxGR incremented: {MaxGR+1}')						
							self.sl(f'In gen cycle and is_v_gen and insert_double_rmin: adding extra edges')
						else:	
							i1 = gen['nodes'][0]
							i2 = gen['nodes'][1]					
							
							nodes = []
							nodes.append(i1)
							nodes.append(i2)						
							item = self.graph.create_item(copy.deepcopy(nodes), j, self.graph.RMIN)
							self.graph.json_data["edges"].append(item)
							nInserted += 1
							self.sl(f'In gen cycle and is_v_gen: adding extra edges')
				
					elif self.sv['open_circuit_pass'] == 1:
						prop = gen["prop"]
						gen_name = prop['label']
						gen_name_w_res = self.lab2res(gen_name)				
						value_str = self.graph.fv(cg.ROPEN)
						
						self.log(f"We assume that the internal resistance of {gen_name} is {gen_name_w_res}={value_str}Ohm")				
						i1 = gen['nodes'][0]
						i2 = gen['nodes'][1]					
						
						nodes = []
						nodes.append(i1)
						nodes.append(i2)						
						item = self.graph.create_item(copy.deepcopy(nodes), j, cg.ROPEN, prop['label'])
						self.graph.json_data["edges"].append(item)
						nInserted += 1
						self.sl(f'In gen cycle and is_v_gen open_circuit_pass: adding extra edges')
					
					
			# graph change
			if self.sv['open_circuit_pass'] == 1:
				MaxGR = self.graph.get_max_graph_number()
				i = 0
				while i < len(self.graph.json_data["meters"]):
					item = self.graph.json_data["meters"][i]
					prop = item["prop"]
					if prop["CompId"] == cg.VOLTMET_ or prop["CompId"] == cg.VOLTMET2_:
						i1 = gen['nodes'][0]
						i2 = MaxGR+1
						i3 = gen['nodes'][1]					
						
						nodes = []
						nodes.append(i1)
						nodes.append(i2)						
						item = self.graph.create_item(copy.deepcopy(nodes), j, cg.ROPEN, prop['label'])
						self.graph.json_data["edges"].append(item)
						nInserted += 1
						
						#We have to add another edge here (possible later add_edge conflicts)
						nodes = []
						nodes.append(i2)
						nodes.append(i3)						
						item = self.graph.create_skip_item(copy.deepcopy(nodes))
						self.graph.json_data["edges"].append(item)
						nInserted += 1						
						
						self.graph.json_data["meters"].pop(i)
						self.graph.set_req_prop_b("volt_meter_question", False)
						self.request["volt_meter_no_match"] = False
						
						self.graph.set_max_gr(MaxGR+1)				

						self.sl(f'MaxGR incremented: {MaxGR+1}')
						self.sl(f'In gen cycle and open_circuit_pass: adding extra edges')					
						
					else:
						i += 1												

			cu.dump_list(self.graph.json_data, 'data/temp-mod.json')
			G = self.graph.get_graph(circuit_key)

			#self.solution['gen'] = self.gen
			self.solution['circuit'] = self.graph.graph_debug
			self.solution['request'] = self.request
			if self.graph.use_superposition:
				#self.log(f"Pass{i_pass+1} started")
				self.log(f"###Processing generator {self.gen['prop']['label']}")
			
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
					self.graph.solution_log.extend(self.graph.yd_log)
					self.graph.update_edges_json()
				G = self.graph.G
			T = find_sptree(G, fixed_ends)

			if self.graph.show_tree == 1:
				cu.btree_print3(T); print("")

			#graph check
			cu.btree_check(T)

			#ampermeters1: processing apmermeters
			self.request['amper_meter_question'] = False; self.silent = False
			has_amper_meter = self.check_ampermeters()	
			
			self.graph.modify_amper_meters(self.graph.RMIN)
			cu.dump_list(self.graph.json_data, 'data/temp'+'-mod.json')

			#get path for 'comp'
			paths = []		
			cu.btree_print_all_path(T, [], paths)
			if self.graph.show_tree == 1:
				for path in paths:
					sPath = self.graph.path2str(path)
					print(sPath)
				print("")

			label = self.request['comp']
			comp_label = self.request['comp']; gen_name = self.gen['prop']['label']; self.request_path = ''
			if gen_name == comp_label:
				self.request['req_on_gen'] = True
			elif self.request['cmd'] != 'get_impedance' and self.request['cmd'] != 'get_total_impedance' and False:	#not self.request["volt_meter_no_match"]
				status = self.graph.find_edge_in_G(label)
				if not status:
					raise Exception(f"{label} not found in the circuit. Analysis stopped.")
				status, self.request_path = self.graph.find_path(label, paths)	
				if not status:
					raise RequestException(f"Request error: {label} not found")
				sPath = self.graph.path2str(self.request_path)
				if self.graph.show_tree == 1:
					print(sPath)

			#calculating the impedance
			self.prev_type = None; self.calc_symbols = []
			self.ignored_resistances = []
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
			elif self.request['cmd'] == 'get_impedance' or self.request['cmd'] == 'get_total_impedance':
				self.unit = "Ohm"
			comp_label = self.request['comp']; gen_name = self.gen['prop']['label']
			if self.request["volt_meter_question"] and comp_label == '':
				comp_label = 'voltmeter'
			request_txt = cu.get_request_txt(self.request)
			if i_pass == 0:
				if ac_gen['mode'] == 1:
					freq = self.graph.fv(ac_gen['Freq'])
					self.log(f"This is an AC calculation")
					self.log(f"We know that the generator frequency is f={freq}{self.graph.sHz}, {self.graph.sOmega}=2{self.graph.sMul}pi{self.graph.sMul}f")

			# calculating voltage/currents
			# set values on top node
			#if i_pass == 0:
			#	self.graph.set_v_pot(0, 0.0)		
			#self.log(f"xxx Gen: set voltage...")
			#self.log(f"xxx GND is: {self.gen['nodes'][1]}")
			self.graph.GND[i_pass] = self.gen['nodes'][1]
			#self.graph.set_v_pot(self.gen['nodes'][1], 0)	
			self.graph.set_v_pot(self.graph.GND[i_pass], 0.0, f"(generator {gen_name} negativ pole)", True)		
			if gen_new_value['quantity'] == 'voltage':
				self.graph.set_v_pot(self.gen['nodes'][0], gen_new_value['value'], f"(generator {gen_name} positive pole)")		
			self.graph.set_node_val(T, gen_new_value['value'], '', True, gen_new_value['quantity'], self.gen['nodes']) 
			if gen_new_value['quantity'] == 'voltage':
				#self.graph.set_v(T.target, T.source, T.prop['voltage'])
				self.graph.set_node_val(T, T.prop['voltage']/T.prop['impedance'], '', True, 'current', self.gen['nodes']) 
			else:
				voltage_val = T.prop['current']*T.prop['impedance']	
				self.graph.set_node_val(T, -voltage_val, '', True, 'voltage', self.gen['nodes'], None, f"(generator {gen_name} voltage)") 
			self.log("")

			if not self.request['ohm_meter_question']:
				self.log(f"First we calculate the total {self.get_impedance_str()} between the generator nodes ({gen_name})")
			self.logl(self.total_impedance_txt)
			if self.request['cmd'] != 'get_impedance' and self.request['cmd'] != 'get_total_impedance':
				self.log("")
				self.log(f"Now we calculate the {request_txt} on {comp_label}")

				val_str = f"{self.graph.fv(gen_new_value['value'])}{gen_new_value['unit']}"
				if gen_new_value['quantity'] == 'voltage':
					val_str = f"{self.graph.fv(gen_new_value['value'])} {cg.uVolt}"
					self.log(f"We know that the voltage between {gen_name} nodes is {val_str}.")
				else:	
					voltage_str = f"{self.graph.fv(voltage_val)} {cg.uVolt}"
					self.log( f"We know that the voltage between {gen_name} nodes is {voltage_str}, "
							  f"because the generator current is Igen = {val_str} and the {self.get_impedance_str()} between the generator nodes is Rtot = {self.graph.fv(T.prop['impedance'])}Ohm so "
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
							self.log(f"We know that the voltage between {gen_name} nodes is {self.graph.fv(gen_new_value['value'])} {cg.uVolt}.")
							self.log(f"We calculated previously the {self.get_impedance_str()} between {gen_name} nodes: this is {self.graph.fv(impedance)}Ohm.")
							self.log(f"So the current on {gen_name} is {self.graph.fv(current)} {cg.uCurrent}.")
				else:
					self.conf_preorder_test = 1; self.stopped = False
					self.walk_preorder(T)
					self.conf_preorder_test = 0; self.stopped = False
					self.walk_preorder(T)
				
			pass_item = {}
			if self.graph.opts['debug_mode'] == 1:	
				#pass_item['total_impedance_silent'] = self.total_impedance_silent
				pass_item['total_impedance_ori_txt'] = self.total_impedance_ori_txt
				pass_item['total_impedance_txt'] = self.total_impedance_txt
				pass_item['gen'] = self.gen
				#pass_item['nodal_voltage_log'] = self.graph.nodal_voltage_log
			self.solution['superposition'].append(pass_item)

			self.log("")
			self.write_log(1, 'OK', 0, False)

			#finalize 'run_pass' (one pass)
			node_potentials_pass = []
			ref_node = self.graph.GND[0]
			shift_re = self.graph.v_re[i_pass][ref_node]
			shift_im = self.graph.v_im[i_pass][ref_node]
			a1=1
			for i in range(self.graph.max_node+1):
				flag = self.graph.v_flags[i_pass][i]
				
				re = self.graph.v_re[i_pass][i]-shift_re
				im = self.graph.v_im[i_pass][i]-shift_im
				
				self.graph.v_re[i_pass][i] = re
				self.graph.v_im[i_pass][i] = im
				
				if abs(im) > 1e-15:
					r = complex(re, im)
				else:
					r = re
				
				s0 = self.graph.fv(r)
				
				s = f'VP_{i} = {s0}, assigned: {flag}'
				node_potentials_pass.append(s)		
			self.node_potentials_dbg['node_potentials'].append(node_potentials_pass)	
		finally:
			#finalize 'run_pass' (one pass)
			if i_pass < len(self.gens)-1:	
				self.request['comp'] = self.bkp_request_comp
			if len(self.gens) > 1:	
				#cu.dump_list(self.graph.json_data, f'temp/temp-run-pass-{i_pass}.json')
				self.graph.restore_json_data()
				del self.graph.G
				G = self.graph.get_graph(self.graph.circuit_key)			
				self.sl(f'restore_json_data: all extra edges (like extra VM) are restored')
			#cu.dump_list(self.graph.json_data, 'data/temp'+'-mod.json')
				

	def patch_log(self):
		for item in self.graph.am_edges:
			label = item['prop']['label']	
		
			f, v = self.get_final_value(label, 'current')
			if f:
				current = v['value']		
				current_str = self.graph.fv(current)
				patch_str = f'<patch_AM_{label}>'
				for i in range(len(self.graph.solution_log)):
					line = self.graph.solution_log[i]
					if pos_fn(patch_str, line) >= 0:
						new_line = line.replace(patch_str, current_str)
						self.graph.solution_log[i] = new_line
				
	def write_log(self, valid, status, error_code=0, save_files=True):
		if error_code > 0:
			self.graph.solution_log.append('Failed: see codes')
	
		calculation = {}
		calculation['sv'] =	copy.deepcopy(self.sv)
		calculation['spec_log'] = copy.deepcopy(self.spec_log)
		calculation['solution'] = self.graph.solution_log

		calculation['node_potentials_dbg'] = self.node_potentials_dbg
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
			
			json_array = self.solution["calculation"]["solution"]
			json_string = json.dumps(json_array, indent=4)
			if (self.opts['request']['options'] & cg.LLM_LOUD) != 0:
				fn = 'temp/output_speech.txt'
			else:	
				fn = 'temp/output.txt'
			with open(fn, 'w') as text_file:
				for item in json_array:
					text_file.write(item+'\n')
		
			if self.opts['mode_all_files'] == 0:
				f = open(f"temp/{self.fn_base_wo_ext}-solution.xml", "w")
				f.write(json2xml.Json2xml(self.solution, wrapper="all", pretty=True, attr_type=False).to_xml())
				f.close()

				f = open(f"temp/temp-solution.xml", "w")
				f.write(json2xml.Json2xml(self.solution, wrapper="top", pretty=True, attr_type=False).to_xml())
				f.close()

	def set_sv_prop_i(self, key, value):
		self.sv[key] = value
		self.sl(f'{key} set to {value}')
		
	def get_sv_props(self):
		v0 = self.sv['short_circuit_pass']
		v1 = self.sv['open_circuit_pass']
		v2 = self.sv['insert_double_rmin']
		return v0, v1, v2
		
	def set_sv_props(self, v0, v1, v2):
		self.set_sv_prop_i('short_circuit_pass', v0)
		self.set_sv_prop_i('open_circuit_pass', v1)
		self.set_sv_prop_i('insert_double_rmin', v2)
		
	def sl(self, s):
		self.spec_log.append(s)
