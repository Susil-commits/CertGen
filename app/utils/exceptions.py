"""Custom application exceptions."""


class AppError(Exception):
    """Base application exception."""
    pass


class JobNotFoundError(AppError):
    """Raised when a requested Job is not found."""
    pass


class CertificateRecordNotFoundError(AppError):
    """Raised when a requested CertificateRecord is not found."""
    pass


class CertificateFileNotReadyError(AppError):
    """Raised when requesting a certificate file that failed or is still pending."""
    pass


class CertificateGenerationError(AppError):
    """Raised when an individual certificate generation fails."""
    pass
