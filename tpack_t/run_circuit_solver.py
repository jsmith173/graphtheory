from tpack_t.circuit_solver import TCircuitSolver, SolverException, DummyException, RequestException
import json, os


def test_one_file_no_exc(fn, key, opts):
	solver = TCircuitSolver("data/"+fn, opts)
	solver.prepare_solver(key)
	solver.run(key)
	print(f"fn: {fn}, OK")
	print(""); print("")
		
def test_one_file(fn, key, opts):
	try:
		solver = TCircuitSolver("data/"+fn, opts)
		solver.prepare_solver(key)
		solver.run(key)
		print(f"fn: {fn}, OK")
		print(""); print("")
	except SolverException as e:
		solver.write_log(0, str(e))
		print(f"{e}")
		print(""); print("")
	except ValueError as e:
		solver.write_log(0, str(e))
		print(f"fn: {fn}, Value error: {e}")
	except RequestException as e:
		solver.write_log(1, str(e), 1)
		print(f"fn: {fn}, {e}")
	except Exception as e:
		s = "Fatal error"		
		solver.write_log(0, f"{s}: {e}", 1)
		print(f"{s}: {e}")

def test_all_proc(fn, key, opts):
	try:
		solver = TCircuitSolver("data/"+fn, opts)
		expected_key = solver.prepare_solver(key)
		solver.run(key)
		print(f"fn: {fn}, key: {key}, OK")
		print(""); print("")
	except ValueError as e:
		if expected_key['valid'] == 1:
			raise ValueError(f"Valid error: {fn}")
		print(f"fn: {fn}, key: {key}, Value error: {e}")
		print(""); print("")	
	except RequestException as e:
		solver.write_log(1, str(e), 1)
		print(f"fn: {fn}, {e}")
	except SolverException as e:
		solver.write_log(1, str(e), 1)
		print(f"fn: {fn}, {e}")

def test_all(filelist, opts):
	try:
		print(80 * '-')
		for fn in filelist:
			print(f">> fn: {fn}")
			test_all_proc(fn, 'circuit_no_gens', opts)
			print(80 * '-')
		print('>>')
		print('>> ALL TEST PASSED')
		print('>>')
	except ValueError as e:
		print('>>')
		print(f">> TEST FAILED: {e}")
		print('>>')
	except DummyException as e:
		print(f"fn: {fn}, Dummy error: {e}")
	except Exception as e:		
		s = "Fatal error"		
		print(f"{s}: {fn}: {e}")

def run():
	if not os.path.isdir('temp'):
		os.mkdir('temp')

	test_request = {
		"text": "",
		"cmd": "get_current",
		"comp": "R5",
		"options": "<none>",
		"qid": "0"
	}
	test_request_vm = {
		"text": "",
		"cmd": "get_voltage",
		"comp": "VM1",
		"options": "<none>",
		"qid": "0"
	}
	test_request_am = {
		"text": "",
		"cmd": "get_current",
		"comp": "AM1",
		"options": "<none>",
		"qid": "0"
	}

	mode_release = 0

	opts = {}
	opts['mode_all_files'] = 0
	opts['debug_mode'] = 1
	opts['test_Y'] = 1
	opts['test_D'] = 1
	opts['log_info'] = 1
	opts['override_request'] = 1
	opts['request'] = test_request_am

	if mode_release == 1:
		opts['mode_all_files'] = 0
		opts['debug_mode'] = 0
		opts['override_request'] = 0
		opts['log_info'] = 0
		test_file = 'temp.json'	
	else:	
		test_file = 'g-ser-simple-ok.json'	

	if opts['mode_all_files'] == 1:
		opts['override_request'] = 0
		with open('data/filelist.json', 'r') as f:
			json_data_l = json.load(f)
			filelist = json_data_l['filelist']
		test_all(filelist, opts)
	else:	
		test_one_file_no_exc(test_file, 'circuit_no_gens', opts)

if __name__ == "__main__":
	run()
