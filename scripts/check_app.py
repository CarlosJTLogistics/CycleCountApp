import re, sys, ast, os

APP_PATH = os.path.join(os.getcwd(), "app.py")
if not os.path.exists(APP_PATH):
    print("ERROR: app.py not found"); sys.exit(2)

src = open(APP_PATH, "rb").read()

# 1) Syntax/indent compile
try:
    compile(src, "app.py", "exec")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e.__class__.__name__} line {e.lineno}: {e.msg}")
    sys.exit(3)

# 2) AST parse
try:
    ast.parse(src)
except Exception as e:
    print(f"AST ERROR: {e}")
    sys.exit(4)

text = src.decode("utf-8", "replace")

# 3) Forbidden markers (prevent stray PowerShell/shell in Python)
forbidden = [
    r'(?m)^\s*\20251024-080254\s*=',
    r'(?m)^\s*\\s*=',
    r'Add-Type\s*-AssemblyName',
    r'ZipFile\]::CreateFromDirectory',
    r'(?m)^\s*',   # backtick-leading lines
]
hits = [pat for pat in forbidden if re.search(pat, text)]
if hits:
    print("FORBIDDEN MARKERS FOUND:")
    for h in hits: print(" -", h)
    sys.exit(5)

# 4) Optional non-blocking hints
if "st.selectbox(" in text and "key=" not in text:
    print("WARN: selectbox without explicit key found (non-blocking)")

print("OK: syntax, AST, and marker checks passed.")
