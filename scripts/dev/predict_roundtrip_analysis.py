"""Conservative syntax evidence for locally saved and restored sklearn pipelines.

This augments the name-based scanner; it does not load or certify pickle files.
Only straight-line dump/load relationships inside one block are admitted.
"""
from __future__ import annotations

import ast


def restored_pipeline_prediction_lines(source: str) -> set[int]:
    """Return lines whose prediction calls all have a local round-trip witness."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    factories = {alias.asname or alias.name
                 for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                 and node.module == 'sklearn.pipeline'
                 for alias in node.names if alias.name in {'Pipeline', 'make_pipeline'}}
    jobs = {alias.asname or alias.name for node in ast.walk(tree)
            if isinstance(node, ast.Import) for alias in node.names if alias.name == 'joblib'}
    safe_calls: set[int] = set()

    def job_call(node, method):
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in jobs and node.func.attr == method)

    def block(statements, pipelines=None, restored=None, saved=None):
        pipelines = set(pipelines or ())
        restored = set(restored or ())
        saved = dict(saved or {})
        for statement in statements:
            # A nested scope starts with no inherited serialization evidence.
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                block(statement.body)
                pipelines.clear(); restored.clear(); saved.clear()
                continue
            expression = statement.test if isinstance(statement, ast.If) else statement
            # Do not count calls from a nested body using the outer state.
            if not isinstance(statement, (ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With)):
                for node in ast.walk(expression):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                            and node.func.attr in {'predict', 'predict_proba'}
                            and isinstance(node.func.value, ast.Name)
                            and node.func.value.id in restored):
                        safe_calls.add(id(node))
            if isinstance(statement, ast.Assign):
                value = statement.value
                is_pipeline = (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                               and value.func.id in factories)
                is_restored = (isinstance(value, ast.Subscript)
                               and isinstance(value.slice, ast.Constant)
                               and job_call(value.value, 'load') and bool(value.value.args)
                               and value.slice.value in saved.get(ast.dump(value.value.args[0]), set()))
                targets = {n.id for t in statement.targets for n in ast.walk(t)
                           if isinstance(n, ast.Name)}
                pipelines -= targets; restored -= targets
                # Any intervening assignment invalidates path-equality evidence.
                saved.clear()
                if len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
                    name = statement.targets[0].id
                    if is_pipeline: pipelines.add(name)
                    if is_restored: restored.add(name)
            elif isinstance(statement, ast.Expr) and job_call(statement.value, 'dump'):
                call = statement.value
                if len(call.args) >= 2:
                    keys = set()
                    if isinstance(call.args[0], ast.Dict):
                        keys = {k.value for k, v in zip(call.args[0].keys, call.args[0].values)
                                if isinstance(k, ast.Constant) and k.value == 'model'
                                and isinstance(v, ast.Name) and v.id in pipelines}
                    saved[ast.dump(call.args[1])] = keys
            elif isinstance(statement, ast.With):
                # Within the with block, acknowledge evidence but do not export changes.
                block(statement.body, pipelines, restored, saved)
                writes = {n.id for n in ast.walk(statement) if isinstance(n, ast.Name)
                          and isinstance(n.ctx, ast.Store)}
                pipelines -= writes; restored -= writes
                if writes: saved.clear()
            elif isinstance(statement, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try)):
                for field in ('body', 'orelse', 'finalbody'):
                    block(getattr(statement, field, []))
                for handler in getattr(statement, 'handlers', []):
                    block(handler.body)
                writes = {n.id for n in ast.walk(statement) if isinstance(n, ast.Name)
                          and isinstance(n.ctx, ast.Store)}
                pipelines -= writes; restored -= writes; saved.clear()
            elif isinstance(statement, (ast.AnnAssign, ast.AugAssign, ast.Delete)):
                pipelines.clear(); restored.clear(); saved.clear()

    block(tree.body)
    calls_by_line: dict[int, list[ast.Call]] = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in {'predict', 'predict_proba'}):
            calls_by_line.setdefault(node.lineno, []).append(node)
    return {line for line, calls in calls_by_line.items()
            if all(id(call) in safe_calls for call in calls)}
