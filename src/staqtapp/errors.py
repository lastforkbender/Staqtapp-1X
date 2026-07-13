"""Typed Staqtapp exceptions."""

class StaqtappError(Exception):
    """Base class for all stable-engine failures."""

class VFSNotFoundError(StaqtappError): pass
class VFSAlreadyExistsError(StaqtappError): pass
class InvalidVFSNameError(StaqtappError): pass
class InvalidPathError(StaqtappError): pass
class PathNotSelectedError(StaqtappError): pass
class FormatError(StaqtappError): pass
class CorruptRecordError(FormatError): pass
class UnsupportedRecordError(FormatError): pass
class DuplicateVariableError(StaqtappError): pass
class VariableNotFoundError(StaqtappError): pass
class VariableLockedError(StaqtappError): pass
class InvalidVariableNameError(StaqtappError): pass
class InvalidValueError(StaqtappError): pass
class ConflictError(StaqtappError): pass
class TransactionError(StaqtappError): pass
class RecoveryError(StaqtappError): pass
class MigrationError(StaqtappError): pass
class UnsupportedLegacyFeatureError(StaqtappError): pass
class UnsafeLegacyContentError(StaqtappError): pass
class UnsafePatternError(StaqtappError): pass

class TypedValueError(InvalidValueError): pass
class RangeReadError(InvalidValueError): pass
