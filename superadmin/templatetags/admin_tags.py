from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def url_with_page(context, page):
    """Current query string with `page` replaced, so pagination keeps every active filter."""
    params = context['request'].GET.copy()
    params.pop('_', None)  # jQuery cache-buster from AJAX list reloads
    params['page'] = page
    return '?' + params.urlencode()


@register.simple_tag
def elided_page_range(page_obj):
    return page_obj.paginator.get_elided_page_range(page_obj.number, on_each_side=2, on_ends=1)
