"""Recommendation Service Application Package."""
import sys

# Compatibilidad con Python 3.14 (PEP 649): evitar que métodos como BaseModel.dict()
# sombreen al tipo builtin `dict` al resolver ForwardRefs en Pydantic / LangChain.
if sys.version_info >= (3, 14):
    import typing

    if hasattr(typing, "ForwardRef") and hasattr(typing.ForwardRef, "evaluate"):
        _orig_eval = typing.ForwardRef.evaluate

        def _patched_eval(self, globals=None, locals=None, type_params=None, owner=None, format=2):
            if locals and "dict" in locals and not isinstance(locals["dict"], type):
                locals = {k: v for k, v in locals.items() if k != "dict"}
            return _orig_eval(self, globals=globals, locals=locals, type_params=type_params, owner=owner, format=format)

        typing.ForwardRef.evaluate = _patched_eval
