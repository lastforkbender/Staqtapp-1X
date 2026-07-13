from __future__ import annotations

import inspect
import staqtapp

EXPECTED = {
    'sqtpp_rd1': '(src)',
    'makevfs': '(vfsFileName: str, directoryName: str, folderName: str)',
    'setpath': '(vfsFileName: str, directoryName: str, folderName: str)',
    'corevar': '(mode: int, varName: str, booleanList: list)',
    'addvar': '(varName: str, varData: str)',
    'appvar': '(varNames: list, varDatas: list, varLocks)',
    'renamevar_stx': '(varName: str, newVarName)',
    'removevar': '(varName: str)',
    'listvars': '() -> list',
    'listfiles': '()',
    'lambdalist': '(asComplete: bool)',
    'genicvar': '(mode: str, varName, varData, varId: list)',
    'joinvars': '(newVarName: str, varNames: list)',
    'changevar': '(varName: str, newVarData: str)',
    'addtree_stx': '(treeName: str, initialTreePathList: list)',
    'addbranch_stx': '(treeName: str, branchKey, newBranchKey, newBranchValue)',
    'getbranch_stx': '(isAlf: bool, treeName: str, branchKey)',
    'vardata_stx': '(isRegex: bool, varNameList: list, search: str) -> list',
    'lockvar': '(varName: str, fncName)',
    'locklist': '(varName: str) -> list',
    'lockdel': '(isDelAll: bool, varName: str, fncName)',
    'keyvar': '(varName: str, fncName) -> bool',
    'darkvar': '()',
    'revar': '(isNewSetVfsPath, newVfsFileName, newVfsDirName, newVfsFldrName)',
    'findvar': '(varName: str) -> bool',
    'findvar_stx': '(varNameList: list, stalkVarName: str) -> list',
    'loadvar': '(isAllNumbers: bool, varName: str, mode: str)',
    'stalkvar': '(varName: str, varData: str)',
    'lambdavar': '(lambdaName: str, lambdaParams: list)',
    'registry': '(isRead: bool, keyName: str, keyData, harpSchema: str)',
    'pojishon': '(mode: str, varData, varName, dirList: list)',
    'invoke_api': '(api_name, args=(), kwargs=None)',
    'map_api_calls': "(calls, processes=None, start_method='spawn', chunksize=1)",
}

def test_version():
    assert staqtapp.__version__ == "1.5.3"

def test_legacy_signatures_are_preserved():
    observed = {name: str(inspect.signature(getattr(staqtapp, name))) for name in EXPECTED}
    assert observed == EXPECTED
