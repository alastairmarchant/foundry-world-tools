"""FWT custom exceptions."""


class FWTBaseError(Exception):
    """Common base class for all FWT errros, should not be raised directly."""

    pass


class FWTConfigNoDataDirError(FWTBaseError):
    """Config does not contain ``"dataDir"``."""

    pass


class FWTPathError(FWTBaseError):
    """Path related error."""

    pass


class FWTPathNoProjectError(FWTBaseError):
    """Project does not exist."""

    pass


class FUDNotFoundError(FWTBaseError):
    """User data directory not found."""

    pass


class FWTFileError(FWTBaseError):
    """Error with file/file system."""

    pass
