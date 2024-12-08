import json, os
from pathlib import Path

def dump_list(l1, fn):
	f = open(fn, "w")
	data = json.dumps(l1, indent=4)
	f.write(data)
	f.close()
	
if not os.path.isdir('temp'):
	os.mkdir('temp')
	
if not os.path.isdir('indent'):
	os.mkdir('indent')

with open("data/filelist.json", 'r') as f:
	file_list = json.load(f)

for fn in file_list['filelist']:
	fn_ = f"data/{fn}"
	fn2 = Path(fn_)
	fn_wo_ext = str(fn2.with_suffix(''))
	fn2 = Path(fn_wo_ext)
	fn2_wo_ext = fn2.name

	with open(fn_, 'r') as f:
		json_data = json.load(f)

	dump_list(json_data, 'indent/'+fn2_wo_ext+'-indent.json')
