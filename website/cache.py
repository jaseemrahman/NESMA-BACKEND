"""
Version-based API response cache.

Every GET response of the public content API is cached under a key that
includes a global "content version". Saving or deleting a Blog / BlogCategory
bumps the version (see superadmin/signals.py), which instantly invalidates
every cached response without having to track individual keys.
"""
import hashlib
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from rest_framework.response import Response

VERSION_KEY = 'api:content:version'
CACHE_QUERY_PARAMS = {'category', 'search', 'exclude', 'page', 'page_size'}


def get_api_cache_version():
    version = cache.get(VERSION_KEY)
    if version is None:
        version = 1
        cache.set(VERSION_KEY, version, None)
    return version


def bump_api_cache_version():
    try:
        cache.incr(VERSION_KEY)
    except ValueError:
        cache.set(VERSION_KEY, 2, None)


def cached_api_response(view_method):
    """
    Cache the `.data` of successful GET responses, keyed by path, known query params and language.
    """
    @wraps(view_method)
    def wrapper(self, request, *args, **kwargs):
        # Only known params are part of the key, so random query strings can't flood the cache
        params = sorted((k, v) for k, v in request.GET.items() if k in CACHE_QUERY_PARAMS)
        raw_key = f'{request.path}|{params}|{self.get_language()}'
        key = f'api:{get_api_cache_version()}:{hashlib.md5(raw_key.encode()).hexdigest()}'
        data = cache.get(key)
        if data is None:
            response = view_method(self, request, *args, **kwargs)
            if response.status_code != 200:
                return response
            data = response.data
            cache.set(key, data, settings.API_CACHE_TIMEOUT)
        response = Response(data)
        response['Cache-Control'] = 'public, max-age=60'
        return response
    return wrapper
