"""
URL configuration for NESMA project.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.views.generic.base import RedirectView

urlpatterns = [
    path('superadmin/', include('superadmin.urls')),
    path('api/', include('website.urls')),
    path('', RedirectView.as_view(pattern_name='superadmin:login', permanent=False)),
]

handler404 = 'config.views.error_404'
handler500 = 'config.views.error_500'

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
