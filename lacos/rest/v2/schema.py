def filter_v2_endpoints(endpoints, **kwargs):
    """Only include /api/v2/ endpoints in the OpenAPI schema."""
    return [
        (path, path_regex, method, callback)
        for path, path_regex, method, callback in endpoints
        if path.startswith("/api/v2/")
    ]
