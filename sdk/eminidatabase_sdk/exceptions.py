class ApiError(Exception):
    """Raised for any non-2xx response — mirrors the API's own error shape
    (`{"detail": ...}`) rather than forcing callers to inspect status codes
    themselves."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(f"API error {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail
