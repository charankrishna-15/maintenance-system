class ApiError(Exception):
    """An error that is safe to show to the API client."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status
