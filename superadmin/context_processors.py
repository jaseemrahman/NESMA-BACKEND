from django.core.cache import cache

from superadmin.models import CareerApplication, Enquiry

SIDEBAR_COUNTS_KEY = 'admin:sidebar_counts'


def get_sidebar_counts():
    """
    Unread enquiries + new applications, cached until either table changes
    (cleared by superadmin/signals.py and after bulk .update() calls in views).
    """
    counts = cache.get(SIDEBAR_COUNTS_KEY)
    if counts is None:
        counts = {
            'unread_enquiries': Enquiry.objects.filter(is_read=False).count(),
            'new_applications': CareerApplication.objects.filter(status=CareerApplication.STATUS_NEW).count(),
        }
        cache.set(SIDEBAR_COUNTS_KEY, counts, 300)
    return counts


def clear_sidebar_counts():
    cache.delete(SIDEBAR_COUNTS_KEY)


def sidebar_counts(request):
    """Unread badges for the admin sidebar (logged-in admin pages only)."""
    if not request.path.startswith('/superadmin') or not request.user.is_authenticated:
        return {}
    return get_sidebar_counts()
