import multiprocessing
from dataclasses import dataclass
from functools import wraps
from typing import Any

from . import engine
from .codec import encode_text
from .config import configure
from . import diagnostics
from . import json_backend
from . import batching


@dataclass(slots=True, frozen=True)
class CallFailure:
    """Non-throwing public API failure envelope.

    It is false-valued so legacy ``if result`` checks naturally reject failures,
    while preserving the exception type and message for inspection/logging.
    """
    api: str
    error_type: str
    message: str
    args_repr: str = ""

    ok: bool = False

    def __bool__(self) -> bool:
        return False

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "api": self.api,
            "error_type": self.error_type,
            "message": self.message,
            "args_repr": self.args_repr,
        }

def _failure(api_name: str, exc: BaseException, args=(), kwargs=None) -> CallFailure:
    kwargs = {} if kwargs is None else kwargs
    failure = CallFailure(
        api=api_name,
        error_type=type(exc).__name__,
        message=str(exc),
        args_repr=repr((tuple(args), kwargs))[:2048],
    )
    try:
        diagnostics.emit(
            "api_failure_contained",
            api=api_name,
            error_type=failure.error_type,
            message=failure.message[:1024],
        )
    except Exception:
        pass
    return failure

def _safe_public(function):
    @wraps(function)
    def contained(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception as exc:
            return _failure(function.__name__, exc, args, kwargs)
    return contained

# The following signatures intentionally preserve the original facade.
@_safe_public
def sqtpp_rd1(src):
    """Legacy testing-only interpreter entry point (disabled)."""
    return engine.unsupported("sqtpp_rd1")

@_safe_public
def makevfs(vfsFileName: str, directoryName: str, folderName: str):
    return engine.make_vfs(vfsFileName, directoryName, folderName)

@_safe_public
def setpath(vfsFileName: str, directoryName: str, folderName: str):
    return engine.select_vfs(vfsFileName, directoryName, folderName)

@_safe_public
def corevar(mode: int, varName: str, booleanList: list):
    return engine.core_variable(mode, varName, booleanList)

@_safe_public
def addvar(varName: str, varData: str):
    if batching.enabled():
        return batching.enqueue("addvar", (varName, varData))
    return engine.add_variable(varName, varData)

@_safe_public
def appvar(varNames: list, varDatas: list, varLocks):
    if batching.enabled():
        return batching.enqueue("appvar", (varNames, varDatas, varLocks))
    return engine.add_variables(varNames, varDatas, varLocks)

@_safe_public
def renamevar_stx(varName: str, newVarName):
    if batching.enabled():
        return batching.enqueue("renamevar_stx", (varName, newVarName))
    return engine.rename_variable(varName, newVarName)

@_safe_public
def removevar(varName: str):
    if batching.enabled():
        return batching.enqueue("removevar", (varName,))
    return engine.remove_variable(varName)

@_safe_public
def listvars() -> list:
    _flush_pending_for_consistency("read-listvars")
    return engine.list_variables()

@_safe_public
def listfiles():
    _flush_pending_for_consistency("read-listfiles")
    return engine.list_files()

@_safe_public
def lambdalist(asComplete: bool):
    return engine.unsupported("lambdalist")

@_safe_public
def genicvar(mode: str, varName, varData, varId: list):
    return engine.unsupported("genicvar")

@_safe_public
def joinvars(newVarName: str, varNames: list):
    if batching.enabled():
        return batching.enqueue("joinvars", (newVarName, varNames))
    return engine.join_variables(newVarName, varNames)

@_safe_public
def changevar(varName: str, newVarData: str):
    if batching.enabled():
        return batching.enqueue("changevar", (varName, newVarData))
    return engine.change_variable(varName, newVarData)

@_safe_public
def addtree_stx(treeName: str, initialTreePathList: list):
    return engine.unsupported("addtree_stx")

@_safe_public
def addbranch_stx(treeName: str, branchKey, newBranchKey, newBranchValue):
    return engine.unsupported("addbranch_stx")

@_safe_public
def getbranch_stx(isAlf: bool, treeName: str, branchKey):
    return engine.unsupported("getbranch_stx")

@_safe_public
def vardata_stx(isRegex: bool, varNameList: list, search: str) -> list:
    return engine.search_variable_data(isRegex, varNameList, search)

@_safe_public
def lockvar(varName: str, fncName):
    return engine.add_lock(varName, fncName)

@_safe_public
def locklist(varName: str) -> list:
    return engine.list_locks(varName)

@_safe_public
def lockdel(isDelAll: bool, varName: str, fncName):
    return engine.delete_lock(isDelAll, varName, fncName)

@_safe_public
def keyvar(varName: str, fncName) -> bool:
    return engine.has_lock(varName, fncName)

@_safe_public
def darkvar():
    return engine.unsupported("darkvar")

@_safe_public
def revar(isNewSetVfsPath, newVfsFileName, newVfsDirName, newVfsFldrName):
    return engine.unsupported("revar")

@_safe_public
def findvar(varName: str) -> bool:
    _flush_pending_for_consistency("read-findvar")
    return engine.find_variable(varName)

@_safe_public
def findvar_stx(varNameList: list, stalkVarName: str) -> list:
    return engine.find_variables_stx(varNameList, stalkVarName)

@_safe_public
def loadvar(isAllNumbers: bool, varName: str, mode: str):
    _flush_pending_for_consistency("read-loadvar")
    return engine.load_variable(isAllNumbers, varName, mode)

@_safe_public
def stalkvar(varName: str, varData: str):
    return engine.stalk_variable(varName, varData)

@_safe_public
def lambdavar(lambdaName: str, lambdaParams: list):
    return engine.unsupported("lambdavar")

@_safe_public
def registry(isRead: bool, keyName: str, keyData, harpSchema: str):
    return engine.unsupported("registry")

@_safe_public
def pojishon(mode: str, varData, varName, dirList: list):
    return engine.unsupported("pojishon")

_LEGACY_NAMES = {
    "sqtpp_rd1", "makevfs", "setpath", "corevar", "addvar", "appvar",
    "renamevar_stx", "removevar", "listvars", "listfiles", "lambdalist",
    "genicvar", "joinvars", "changevar", "addtree_stx", "addbranch_stx",
    "getbranch_stx", "vardata_stx", "lockvar", "locklist", "lockdel",
    "keyvar", "darkvar", "revar", "findvar", "findvar_stx", "loadvar",
    "stalkvar", "lambdavar", "registry", "pojishon",
}
_PUBLIC_API = {name: globals()[name] for name in _LEGACY_NAMES}

def invoke_api(api_name, args=(), kwargs=None):
    try:
        if api_name not in _PUBLIC_API:
            raise ValueError(f"unknown Staqtapp API: {api_name}")
        if kwargs is None:
            kwargs = {}
        if not isinstance(args, (tuple, list)) or not isinstance(kwargs, dict):
            raise TypeError("args must be a tuple/list and kwargs must be a dict")
        return _PUBLIC_API[api_name](*args, **kwargs)
    except Exception as exc:
        return _failure(str(api_name), exc, args if isinstance(args, (tuple, list)) else (), kwargs)

def _normalize_api_call(call):
    if isinstance(call, dict):
        return call.get("name"), tuple(call.get("args", ())), dict(call.get("kwargs", {}))
    if isinstance(call, (tuple, list)):
        if len(call) == 1: return call[0], (), {}
        if len(call) == 2: return call[0], tuple(call[1]), {}
        if len(call) == 3: return call[0], tuple(call[1]), dict(call[2])
    raise TypeError("each API call must be a mapping or a 1-3 item tuple/list")

def _invoke_api_call(call):
    try:
        name, args, kwargs = _normalize_api_call(call)
        return invoke_api(name, args, kwargs)
    except Exception as exc:
        return _failure("map_api_calls", exc, (call,), {})

def map_api_calls(calls, processes=None, start_method="spawn", chunksize=1):
    try:
        call_list = list(calls)
    except Exception as exc:
        return [_failure("map_api_calls", exc)]
    if not call_list:
        return []
    if not isinstance(chunksize, int) or chunksize < 1:
        return [_failure("map_api_calls", ValueError("chunksize must be a positive integer")) for _ in call_list]
    try:
        context = multiprocessing.get_context(start_method)
        with context.Pool(processes=processes) as pool:
            return pool.map(_invoke_api_call, call_list, chunksize)
    except Exception as exc:
        diagnostics.emit("map_pool_failure_contained", error_type=type(exc).__name__)
        # A process-pool infrastructure failure must not halt the controller.
        # Fall back to contained in-process execution and retain one result/call.
        return [_invoke_api_call(call) for call in call_list]

def invoke_vfs_api(vfs_file, directory, folder, api_name, args=(), kwargs=None):
    """Invoke one legacy API call inside an explicit VFS context without throwing."""
    try:
        with engine.open_vfs(vfs_file, directory, folder):
            return invoke_api(api_name, args, kwargs)
    except Exception as exc:
        return _failure(str(api_name), exc, args if isinstance(args, (tuple, list)) else (), kwargs)

def _normalize_vfs_api_call(call):
    if isinstance(call, dict):
        return (
            call.get("vfs"), call.get("directory"), call.get("folder"),
            call.get("name"), tuple(call.get("args", ())), dict(call.get("kwargs", {})),
        )
    if isinstance(call, (tuple, list)) and 4 <= len(call) <= 6:
        vfs, directory, folder, name = call[:4]
        args = tuple(call[4]) if len(call) >= 5 else ()
        kwargs = dict(call[5]) if len(call) == 6 else {}
        return vfs, directory, folder, name, args, kwargs
    raise TypeError("each VFS API call must be a mapping or a 4-6 item tuple/list")

def _invoke_vfs_api_call(call):
    try:
        vfs, directory, folder, name, args, kwargs = _normalize_vfs_api_call(call)
        return invoke_vfs_api(vfs, directory, folder, name, args, kwargs)
    except Exception as exc:
        return _failure("map_vfs_api_calls", exc, (call,), {})

def map_vfs_api_calls(calls, processes=None, start_method="spawn", chunksize=1):
    """Execute explicit-VFS calls with one contained result per input call."""
    try:
        call_list = list(calls)
    except Exception as exc:
        return [_failure("map_vfs_api_calls", exc)]
    if not call_list:
        return []
    if not isinstance(chunksize, int) or chunksize < 1:
        return [_failure("map_vfs_api_calls", ValueError("chunksize must be a positive integer")) for _ in call_list]
    try:
        context = multiprocessing.get_context(start_method)
        with context.Pool(processes=processes) as pool:
            return pool.map(_invoke_vfs_api_call, call_list, chunksize)
    except Exception as exc:
        diagnostics.emit("vfs_map_pool_failure_contained", error_type=type(exc).__name__)
        return [_invoke_vfs_api_call(call) for call in call_list]


def _flush_pending_for_consistency(reason="consistency"):
    result = batching.flush_current(reason=reason)
    if not result:
        raise RuntimeError("pending write batch failed to commit")
    return result


@dataclass(slots=True, frozen=True)
class TransactionResult:
    ok: bool
    results: tuple[Any, ...] = ()
    failure: CallFailure | None = None
    operations: int = 0

    def __bool__(self) -> bool:
        return self.ok

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "results": self.results,
            "failure": None if self.failure is None else self.failure.as_dict(),
            "operations": self.operations,
        }

def _normalize_transaction_call(call):
    name, args, kwargs = _normalize_api_call(call)
    if not isinstance(name, str):
        raise TypeError("transaction API name must be a string")
    return name, args, kwargs

def run_transaction(calls):
    """Execute supported mutations as one non-halting, all-or-nothing commit."""
    try:
        _flush_pending_for_consistency("explicit-transaction")
        normalized = [_normalize_transaction_call(call) for call in list(calls)]
        if not normalized:
            return TransactionResult(True, (), None, 0)
        results = engine.run_transaction_calls(normalized)
        return TransactionResult(True, tuple(results), None, len(normalized))
    except Exception as exc:
        failure = _failure("run_transaction", exc, (), {})
        return TransactionResult(False, (), failure, len(locals().get("normalized", ())))

def run_vfs_transaction(vfs_file, directory, folder, calls):
    """Run one all-or-nothing transaction against an explicitly selected VFS."""
    try:
        with engine.open_vfs(vfs_file, directory, folder):
            return run_transaction(calls)
    except Exception as exc:
        failure = _failure("run_vfs_transaction", exc, (), {})
        return TransactionResult(False, (), failure, 0)


batching.install_runner(run_transaction)

QueuedResult = batching.QueuedResult
BatchFlushResult = batching.BatchFlushResult

# Stable additive API. Public function calls are contained by default.
@_safe_public
def configure(**kwargs):
    backend = kwargs.pop("json_backend", None)
    batch_enabled = kwargs.pop("write_batching", None)
    batch_max_operations = kwargs.pop("batch_max_operations", None)
    batch_max_wait_ms = kwargs.pop("batch_max_wait_ms", None)
    batch_max_bytes = kwargs.pop("batch_max_bytes", None)
    result = None
    if kwargs:
        result = engine.configure(**kwargs) if hasattr(engine, "configure") else __import__("staqtapp.config", fromlist=["configure"]).configure(**kwargs)
    response = result
    if backend is not None:
        response = {"storage": result, "json_backend": json_backend.set_backend(backend)}
    if any(value is not None for value in (batch_enabled, batch_max_operations, batch_max_wait_ms, batch_max_bytes)):
        batch_info = batching.configure(
            enabled=batch_enabled,
            max_operations=batch_max_operations,
            max_wait_ms=batch_max_wait_ms,
            max_bytes=batch_max_bytes,
        )
        if isinstance(response, dict):
            response = {**response, "write_batching": batch_info}
        else:
            response = {"storage": response, "write_batching": batch_info}
    return response


@_safe_public
def json_backend_info():
    return json_backend.backend_info()

@_safe_public
def verify_vfs(*args, **kwargs):
    return engine.verify(*args, **kwargs)

@_safe_public
def migrate_vfs(*args, **kwargs):
    return engine.migrate(*args, **kwargs)

@_safe_public
def recover_vfs(*args, **kwargs):
    return engine.recover_current(*args, **kwargs)

@_safe_public
def list_revisions(limit=None):
    return engine.list_revision_history(limit)

@_safe_public
def rollback_revision(revision):
    return engine.rollback_to_revision(revision)

@_safe_public
def prune_revisions(keep=32):
    return engine.prune_revision_history(keep)

@_safe_public
def revision_storage_report():
    return engine.revision_storage_report()

@_safe_public
def encode_value(text):
    return encode_text(text)

@_safe_public
def recent_events(limit=100):
    return diagnostics.recent_events(limit)

@_safe_public
def diagnostic_counts():
    return diagnostics.diagnostic_counts()

@_safe_public
def set_value(name, value):
    if batching.enabled():
        return batching.enqueue("set_value", (name, value))
    return engine.set_typed_value(name, value)
@_safe_public
def get_value(name, expected_type=None):
    _flush_pending_for_consistency("read-get-value")
    return engine.get_typed_value(name, expected_type)
@_safe_public
def inspect_value(name):
    _flush_pending_for_consistency("read-inspect-value")
    return engine.inspect_typed_value(name)
@_safe_public
def validate_value(name):
    _flush_pending_for_consistency("read-validate-value")
    return engine.validate_typed_value(name)
@_safe_public
def read_range(name, start=0, length=None):
    _flush_pending_for_consistency("read-range")
    return engine.read_typed_range(name, start, length)
@_safe_public
def read_payload_range(name, start=0, length=None):
    _flush_pending_for_consistency("read-payload-range")
    return engine.read_payload_range(name, start, length)
@_safe_public
def read_index_info(): return engine.read_index_info()
@_safe_public
def rebuild_read_index(): return engine.rebuild_read_index()
@_safe_public
def iter_value(name, chunk_size=1024*1024): return engine.iter_typed_value(name, chunk_size)

@_safe_public
def flush_writes():
    return batching.flush_all(reason="explicit")

@_safe_public
def pending_writes():
    return batching.pending_writes()

@_safe_public
def write_batching_info():
    return batching.info()

@_safe_public
def optimize_vfs():
    _flush_pending_for_consistency("optimize")
    return engine.optimize_current()

@_safe_public
def compact_vfs(keep_revisions=32):
    _flush_pending_for_consistency("compact")
    return engine.compact_current(keep_revisions=keep_revisions)

@_safe_public
def repair_vfs(strategy="surgical", source="latest-valid-revision"):
    _flush_pending_for_consistency("repair")
    return engine.repair_current(strategy=strategy, source=source)

@_safe_public
def rebuild_integrity_map(): return engine.rebuild_integrity_map()
@_safe_public
def verify_integrity(deep=True):
    _flush_pending_for_consistency("verify-integrity")
    return engine.verify_integrity_map(deep=deep)
@_safe_public
def integrity_report(rebuild_if_missing=False, deep=True): return engine.integrity_report(rebuild_if_missing=rebuild_if_missing, deep=deep)

# Context managers cannot safely suppress a failed __enter__ without allowing
# the body to run against the wrong VFS. Keep this advanced primitive explicit.
open_vfs = engine.open_vfs

__all__ = tuple(sorted(_LEGACY_NAMES)) + (
    "invoke_api", "map_api_calls", "invoke_vfs_api", "map_vfs_api_calls",
    "configure", "open_vfs", "verify_vfs", "CallFailure",
    "migrate_vfs", "recover_vfs", "list_revisions", "rollback_revision", "prune_revisions", "revision_storage_report", "encode_value", "recent_events", "diagnostic_counts",
    "run_transaction", "run_vfs_transaction", "TransactionResult",
    "set_value", "get_value", "inspect_value", "validate_value", "read_range", "read_payload_range", "iter_value", "read_index_info", "rebuild_read_index", "json_backend_info",
    "flush_writes", "pending_writes", "write_batching_info", "QueuedResult", "BatchFlushResult",
    "optimize_vfs", "compact_vfs", "repair_vfs", "rebuild_integrity_map", "verify_integrity", "integrity_report",
)
