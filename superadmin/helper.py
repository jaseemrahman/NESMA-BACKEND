from urllib.parse import urlsplit

from django.conf import settings
from django.core.paginator import Paginator
from django.utils.http import url_has_allowed_host_and_scheme
from django.shortcuts import render

LOCAL_HOSTS = ('localhost', '127.0.0.1', '0.0.0.0')


def media_base_url():
    """`settings.MEDIA_DOMAIN` forced to https (plain http is kept only for local development)."""
    base = settings.MEDIA_DOMAIN
    if '://' not in base:
        base = 'https://' + base
    parts = urlsplit(base)
    scheme = 'http' if parts.hostname in LOCAL_HOSTS else 'https'
    return f'{scheme}://{parts.netloc}'


def absolute_media_url(file_or_path):
    """Full https URL for a FileField/ImageField value or a '/media/...' path. Empty string when missing."""
    if not file_or_path:
        return ''
    url = file_or_path if isinstance(file_or_path, str) else file_or_path.url
    if url.startswith(('http://', 'https://')):
        return url
    return media_base_url() + url


def renderhelper(request, folder, htmlpage, context=None):
    return render(request, 'superadmin/' + folder + '/' + htmlpage + '.html', context or {})


PAGE_SIZE_CHOICES = (10, 20, 50, 100)
DEFAULT_PAGE_SIZE = 20


def paginate(request, queryset):
    """
    Page of `queryset` for admin lists.
    - `?per_page=` one of PAGE_SIZE_CHOICES (default 20)
    - `?page=` invalid -> first page, past the end (e.g. after deleting the last row) -> last page
    """
    try:
        per_page = int(request.GET.get('per_page', DEFAULT_PAGE_SIZE))
    except (TypeError, ValueError):
        per_page = DEFAULT_PAGE_SIZE
    if per_page not in PAGE_SIZE_CHOICES:
        per_page = DEFAULT_PAGE_SIZE
    page = Paginator(queryset, per_page).get_page(request.GET.get('page'))
    page.per_page = per_page
    page.per_page_choices = PAGE_SIZE_CHOICES
    return page


def safe_next(request, fallback):
    """
    The `next` URL (POST or GET) used to return to the same list page / filters after an action.
    Only same-site relative paths are accepted (never an open redirect).
    """
    value = (request.POST.get('next') or request.GET.get('next') or '').strip()
    if value.startswith('/') and not value.startswith('//') and url_has_allowed_host_and_scheme(
            value, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return value
    return fallback


def filter_by_status(queryset, status_filter):
    if status_filter == 'active':
        return queryset.filter(is_active=True)
    if status_filter == 'inactive':
        return queryset.filter(is_active=False)
    return queryset


def get_client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')
