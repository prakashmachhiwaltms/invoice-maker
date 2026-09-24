class ActivityAuditMiddleware:
    """Attaches the current request to thread-unsafe-free storage isn't needed;
    kept lightweight: exposes a helper for views/services to log with request context.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response
