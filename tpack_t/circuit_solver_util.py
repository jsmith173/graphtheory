import os, json, cmath, math, re
import graphtheory.seriesparallel.spnodes as sp
from tpack_t import pack_prefix as p

#for the pack_prefix the actual precision is precision+1 
PRECISION = 3

def btree_print3(top, level=0):
    if top is None:
        return
    btree_print3(top.right, level+1)
    btree_print3(top.left, level+1)
    print ( "{}{}".format('   |' * level + "---", top) )

def btree_check(top):
	list_ = sp.btree_postorder(top)
	for node in list_:
		if node.type == "jackknife":
			raise Exception("Graph error")

def btree_print_all_path(top, path, res):
	if top is None:
		return
	path.append(top)
	if top.left is None and top.right is None:
		res.append(path)
	else:
		btree_print_all_path(top.left, path.copy(), res)	
		btree_print_all_path(top.right, path.copy(), res)	

def dump_list(l1, fn):
	f = open(fn, "w", encoding='utf-8')
	data = json.dumps(l1, ensure_ascii=False, indent=4)
	f.write(data)
	f.close()

def in_path(item, path):
	for node in path:
		if item == node:
			return True, "<M> "
	return False, ""

def get_request_txt(request):
	if request['cmd'] == "get_voltage":
		return "voltage"
	elif request['cmd'] == "get_current":
		return "current"
	elif request['cmd'] == "get_impedance":
		return "impedance"
	else:
		raise Exception('get_request_txt')

def fv(v):
	if type(v) is complex:	
		res = cmath.polar(v)
		r = res[0]; r_num = p.Float(r)
		fi = math.degrees(res[1]); fi_num = p.Float(fi)
		r_str = f'{r_num:.{PRECISION}H}'
		fi_str = f'{fi_num:.{PRECISION}H}'
		return f"'{r_str} / {fi_str}\N{DEGREE SIGN}'"
	else:
		#removing trailing zeros (and .) if needed
		num = p.Float(v)
		v_str = f'{num:.{PRECISION}H}'
		return v_str
	
def replace_all_whole_words(txt, src, repl):
	pattern = r'\b'; pattern = pattern+src; pattern = pattern+r'\b'
	result = re.sub(pattern, repl, txt)
	return result

