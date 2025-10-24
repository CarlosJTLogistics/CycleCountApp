import re, sys, json, argparse, os, ast
APP = "app.py"
def read(): return open(APP,"r",encoding="utf-8").read()
def write(txt):
    # validate by compiling and AST parse before writing
    try: compile(txt, APP, "exec")
    except SyntaxError as e: print(f"SYNTAX ERROR: line {e.lineno}: {e.msg}"); sys.exit(3)
    try: ast.parse(txt)
    except Exception as e: print(f"AST ERROR: {e}"); sys.exit(4)
    open(APP,"w",encoding="utf-8").write(txt)

def set_assignee_list(names):
    txt = read()
    pat = r'ASSIGN_NAME_OPTIONS\\s*=\\s*\\[[^\\]]*\\]'
    repl = 'ASSIGN_NAME_OPTIONS = [' + ",".join(f'"{n}"' for n in names) + ']'
    if not re.search(pat, txt, flags=re.S): print("ASSIGN_NAME_OPTIONS not found"); sys.exit(6)
    out = re.sub(pat, repl, txt, flags=re.S)
    write(out)

def rename_assignee(old, new):
    txt=read()
    m = re.search(r'ASSIGN_NAME_OPTIONS\\s*=\\s*\\[([^\\]]*)\\]', txt, flags=re.S)
    if not m: print("ASSIGN_NAME_OPTIONS not found"); sys.exit(6)
    body = m.group(1)
    parts = [p.strip().strip('\"\\'') for p in body.split(",") if p.strip()]
    changed = [new if p==old else p for p in parts]
    out = txt[:m.start()] + f'ASSIGN_NAME_OPTIONS = [' + ",".join(f'"{p}"' for p in changed) + ']' + txt[m.end():]
    write(out)

def add_assignee(name):
    txt=read()
    m = re.search(r'ASSIGN_NAME_OPTIONS\\s*=\\s*\\[([^\\]]*)\\]', txt, flags=re.S)
    if not m: print("ASSIGN_NAME_OPTIONS not found"); sys.exit(6)
    body = m.group(1)
    parts = [p.strip().strip('\"\\'') for p in body.split(",") if p.strip()]
    if name not in parts: parts.append(name)
    out = txt[:m.start()] + f'ASSIGN_NAME_OPTIONS = [' + ",".join(f'"{p}"' for p in parts) + ']' + txt[m.end():]
    write(out)

def strip_ps_artifacts():
    txt = read()
    txt = re.sub(r'(?m)^\\s*\\$.*\\n','', txt)
    txt = re.sub(r'Add-Type\\s*-AssemblyName.*\\n','', txt)
    txt = re.sub(r'\\[IO\\.Compression\\.ZipFile\\]::CreateFromDirectory.*\\n','', txt)
    txt = re.sub(r'(?m)^\\s*.*\\n','', txt)
    write(txt)

def insert_after(pattern, block):
    txt=read()
    m = re.search(pattern, txt, flags=re.S)
    if not m: print("Anchor pattern not found"); sys.exit(7)
    indent = re.search(r'\\n(\\s*)$', m.group(0))
    pad = indent.group(1) if indent else "    "
    norm_block = "\\n".join((pad + line) if line.strip() else line for line in block.splitlines())
    out = txt[:m.end()] + "\\n" + norm_block + txt[m.end():]
    write(out)

def remove_between(start_marker, end_marker):
    txt=read()
    pat = re.compile(re.escape(start_marker)+r'.*?'+re.escape(end_marker), re.S)
    if not pat.search(txt): print("Markers not found"); sys.exit(8)
    out = pat.sub('', txt)
    write(out)

if __name__=="__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("set-assignees"); s1.add_argument("names_json")
    s2 = sub.add_parser("rename"); s2.add_argument("old"); s2.add_argument("new")
    s3 = sub.add_parser("add"); s3.add_argument("name")
    s4 = sub.add_parser("strip-ps", help="Remove PS artifacts accidentally inserted")
    s5 = sub.add_parser("insert-after"); s5.add_argument("pattern"); s5.add_argument("block_file")
    s6 = sub.add_parser("remove-between"); s6.add_argument("start_marker"); s6.add_argument("end_marker")
    args = ap.parse_args()
    if args.cmd=="set-assignees": set_assignee_list(json.loads(args.names_json))
    elif args.cmd=="rename": rename_assignee(args.old, args.new)
    elif args.cmd=="add": add_assignee(args.name)
    elif args.cmd=="strip-ps": strip_ps_artifacts()
    elif args.cmd=="insert-after": insert_after(args.pattern, open(args.block_file,"r",encoding="utf-8").read())
    elif args.cmd=="remove-between": remove_between(args.start_marker, args.end_marker)
