import logging
import threading

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import close_old_connections, transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def get_language(request):
    """
    Resolve the requested language: `?lang=ar` / `lang` body field first, then Accept-Language header.
    """
    lang = request.query_params.get('lang', '')
    if not lang and request.method == 'POST':
        lang = request.data.get('lang', '')
    lang = (lang or request.META.get('HTTP_ACCEPT_LANGUAGE', 'en'))[:2].lower()
    return 'ar' if lang == 'ar' else 'en'


def run_in_background(func, *args, **kwargs):
    """
    Run `func` in a daemon thread once the current DB transaction commits,
    so API responses are never blocked by slow SMTP servers.
    """
    def target():
        try:
            func(*args, **kwargs)
        except Exception:
            logger.exception('Background task %s failed', func.__name__)

    def threaded():
        try:
            target()
        finally:
            close_old_connections()  # the thread opened its own DB connection

    if settings.ASYNC_NOTIFICATIONS:
        transaction.on_commit(lambda: threading.Thread(target=threaded, daemon=True).start())
    else:
        transaction.on_commit(target)


def send_admin_email(subject, template, context, reply_to=None, attachment=None):
    context = {
        **context,
        'admin_url': settings.SITE_URL + '/superadmin/',
        'current_year': timezone.now().year,
    }
    html_body = render_to_string(template, context)
    msg = EmailMultiAlternatives(
        subject=subject,
        body=strip_tags(html_body),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=settings.ADMIN_NOTIFICATION_EMAIL,
        reply_to=[reply_to] if reply_to else None,
    )
    msg.attach_alternative(html_body, 'text/html')
    if attachment:
        name, content, mimetype = attachment
        msg.attach(name, content, mimetype)
    msg.send()
    logger.info('Admin notification sent: %s', subject)


def notify_new_enquiry(enquiry_id):
    from superadmin.models import Enquiry

    enquiry = Enquiry.objects.get(pk=enquiry_id)
    subject = f'NIT - New {enquiry.get_source_display()} Enquiry from {enquiry.full_name}'
    send_admin_email(subject, 'emails/enquiry_admin.html', {'enquiry': enquiry}, reply_to=enquiry.email)


def notify_new_career_application(application_id):
    from superadmin.models import CareerApplication

    application = CareerApplication.objects.get(pk=application_id)
    attachment = None
    if application.cv:
        with application.cv.open('rb') as f:
            ext = application.cv.name.rsplit('.', 1)[-1].lower()
            mimetype = {
                'pdf': 'application/pdf',
                'doc': 'application/msword',
                'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            }.get(ext, 'application/octet-stream')
            attachment = (f"CV_{application.full_name.replace(' ', '_')}.{ext}", f.read(), mimetype)

    subject = f'NIT - New Career Application: {application.full_name} ({application.degree})'
    send_admin_email(
        subject, 'emails/career_admin.html', {'application': application},
        reply_to=application.email, attachment=attachment,
    )
