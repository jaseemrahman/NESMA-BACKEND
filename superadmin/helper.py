from urllib.parse import urlsplit

from django.conf import settings
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

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


def paginate(request, queryset, per_page=20):
    paginator = Paginator(queryset, per_page)
    try:
        return paginator.page(request.GET.get('page', 1))
    except (PageNotAnInteger, EmptyPage):
        return paginator.page(1)


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


def excel_response(filename, headers, rows):
    """
    Stream rows into an .xlsx download using openpyxl's fast write-only mode.
    """
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font

    wb = Workbook(write_only=True)
    ws = wb.create_sheet('Data')
    header_cells = []
    for title in headers:
        cell = WriteOnlyCell(ws, value=title)
        cell.font = Font(bold=True)
        header_cells.append(cell)
    ws.append(header_cells)
    for row in rows:
        ws.append(row)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    stamp = timezone.localtime().strftime('%Y%m%d_%H%M')
    response['Content-Disposition'] = f'attachment; filename="{filename}_{stamp}.xlsx"'
    wb.save(response)
    return response
