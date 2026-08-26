"""Errores controlados de la integración con Moodle."""


class MoodleError(RuntimeError):
    """Error base que nunca debe contener credenciales ni respuestas completas."""


class MoodleConfigurationError(MoodleError):
    pass


class MoodleDisabledError(MoodleError):
    pass


class MoodleWriteDisabledError(MoodleError):
    pass


class MoodleConnectionError(MoodleError):
    pass


class MoodleTimeoutError(MoodleError):
    pass


class MoodleApiError(MoodleError):
    pass


class MoodleInvalidResponseError(MoodleError):
    pass


class MoodleFunctionNotAllowedError(MoodleError):
    pass


class MoodleFullScanDisabledError(MoodleError):
    pass


class MoodleResultLimitExceededError(MoodleError):
    pass


class MoodleUserNotFoundError(MoodleError):
    pass


class MoodleCourseNotFoundError(MoodleError):
    pass


class MoodleSectionNotFoundError(MoodleError):
    pass


class MoodleResourceNotFoundError(MoodleError):
    pass


class MoodleSectionUpdateError(MoodleError):
    pass


class MoodleUserNotConfirmedError(MoodleError):
    pass


class MoodleInstitutionalEmailNotFoundError(MoodleError):
    pass


class MoodleInstitutionalEmailValidationError(MoodleError):
    pass
