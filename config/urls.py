"""
URL configuration for NESMA project.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

urlpatterns = [
    path('api/', include('website.urls')),
    # Admin panel lives at the site root (the public website is a separate Next.js app)
    path('', include('superadmin.urls')),
]

handler404 = 'config.views.error_404'
handler500 = 'config.views.error_500'

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
