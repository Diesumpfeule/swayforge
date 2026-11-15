"""Tiny lint: names that are used but never defined in the module (NameError risk), unused imports."""
import ast, builtins, sys, pathlib
B = set(dir(builtins)) | {"__file__", "__name__", "__doc__"}
bad = 0
for f in sorted(p for a in sys.argv[1:] for p in pathlib.Path(a).rglob("*.py")):
    t = ast.parse(f.read_text())
    defined, used, imports = set(), {}, {}
    for n in ast.walk(t):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(n.name)
            if not isinstance(n, ast.ClassDef):
                a = n.args
                for x in a.posonlyargs + a.args + a.kwonlyargs + ([a.vararg] if a.vararg else []) + ([a.kwarg] if a.kwarg else []):
                    defined.add(x.arg)
        elif isinstance(n, ast.Lambda):
            a = n.args
            for x in a.posonlyargs + a.args + a.kwonlyargs + ([a.vararg] if a.vararg else []) + ([a.kwarg] if a.kwarg else []):
                defined.add(x.arg)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                nm = (al.asname or al.name).split(".")[0]
                defined.add(nm)
                if not (isinstance(n, ast.ImportFrom) and n.module == "__future__"):
                    imports.setdefault(nm, n.lineno)
        elif isinstance(n, ast.Name):
            if isinstance(n.ctx, ast.Store):
                defined.add(n.id)
            else:
                used.setdefault(n.id, n.lineno)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            defined.add(n.name)
        elif isinstance(n, ast.arg):
            defined.add(n.arg)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            defined.update(n.names)
        elif isinstance(n, ast.MatchAs) and n.name:
            defined.add(n.name)
    src = f.read_text().splitlines()
    for nm, ln in sorted(used.items(), key=lambda x: x[1]):
        if nm not in defined and nm not in B:
            print(f"{f}:{ln}: undefined name {nm}"); bad += 1
    allnames = set(used)
    for n in ast.walk(t):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            allnames.add(n.value.id)
    exported = "__all__" in defined
    for nm, ln in imports.items():
        if nm not in allnames and "noqa" not in src[ln - 1] and f.name != "__init__.py" and not exported:
            print(f"{f}:{ln}: unused import {nm}"); bad += 1
sys.exit(1 if bad else 0)
