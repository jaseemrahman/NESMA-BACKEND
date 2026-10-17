"""
Django settings for NESMA (Nesma Infrastructure & Technology) project.
All environment-specific values are read from `.env` via django-environ.
"""

from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

# -----------------------------------------------------------------------------
# 1. PATHS & ENVIRONMENT
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('SECRET_KEY', default='django-insecure-nesma-change-me')
DEBUG = env.bool('DEBUG', default=False)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['127.0.0.1', 'localhost'])
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=['http://127.0.0.1:8000', 'http://localhost:8000'])


# -----------------------------------------------------------------------------
# 2. APPLICATIONS & MIDDLEWARE
# -----------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'superadmin.apps.SuperadminConfig',
    'website.apps.WebsiteConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'superadmin.context_processors.sidebar_counts',
            ],
        },
    },
]

# Cached template loader in production for faster admin rendering
if not DEBUG:
    TEMPLATES[0]['APP_DIRS'] = False
    TEMPLATES[0]['OPTIONS']['loaders'] = [
        ('django.template.loaders.cached.Loader', [
            'django.template.loaders.filesystem.Loader',
            'django.template.loaders.app_directories.Loader',
        ]),
    ]

WSGI_APPLICATION = 'config.wsgi.application'


# -----------------------------------------------------------------------------
# 3. DATABASE & CACHE
# -----------------------------------------------------------------------------
# PostgreSQL only, e.g. DATABASE_URL=postgres://user:password@localhost:5432/nesma
DATABASES = {
    'default': {
        **env.db('DATABASE_URL'),
        'CONN_MAX_AGE': env.int('DB_CONN_MAX_AGE', default=60),
        'CONN_HEALTH_CHECKS': True,
    }
}
if DATABASES['default']['ENGINE'] != 'django.db.backends.postgresql':
    raise ImproperlyConfigured('DATABASE_URL must point to a PostgreSQL database.')

# Local-memory by default; set CACHE_URL=redis://127.0.0.1:6379/1 when running multiple workers
CACHES = {
    'default': env.cache('CACHE_URL', default='locmemcache://nesma'),
}
API_CACHE_TIMEOUT = env.int('API_CACHE_TIMEOUT', default=60 * 15)


# -----------------------------------------------------------------------------
# 4. AUTHENTICATION
# -----------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = 'superadmin:login'


# -----------------------------------------------------------------------------
# 5. INTERNATIONALIZATION
# -----------------------------------------------------------------------------
LANGUAGE_CODE = 'en'
LANGUAGES = [('en', 'English'), ('ar', 'Arabic')]
TIME_ZONE = 'Asia/Riyadh'
USE_I18N = True
USE_TZ = True

DATETIME_FORMAT = 'd/m/Y h:i A'
SHORT_DATETIME_FORMAT = 'd/m/Y h:i A'
TIME_FORMAT = 'h:i A'


# -----------------------------------------------------------------------------
# 6. STATIC & MEDIA FILES
# -----------------------------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
WHITENOISE_MAX_AGE = env.int('WHITENOISE_MAX_AGE', default=60 * 60 * 24)
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'
        if not DEBUG else 'django.contrib.staticfiles.storage.StaticFilesStorage'
    },
}

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
CV_MAX_SIZE_MB = env.int('CV_MAX_SIZE_MB', default=5)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# -----------------------------------------------------------------------------
# 7. REST FRAMEWORK (public website API - no token / no session auth)
# -----------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.AllowAny'],
    'UNAUTHENTICATED_USER': None,
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'] + (
        ['rest_framework.renderers.BrowsableAPIRenderer'] if DEBUG else []
    ),
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ],
    'DEFAULT_PAGINATION_CLASS': 'website.pagination.StandardPagination',
    'PAGE_SIZE': 9,
    'DEFAULT_THROTTLE_RATES': {
        'submissions': env('SUBMISSION_THROTTLE_RATE', default='10/hour'),
    },
}


# -----------------------------------------------------------------------------
# 8. CORS (Next.js frontend)
# -----------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[
    'https://nit-hazel.vercel.app',
    'http://localhost:3000',
])
CORS_URLS_REGEX = r'^/api/.*$'
CORS_ALLOW_HEADERS = ['accept', 'accept-language', 'content-type', 'origin', 'x-requested-with']


# -----------------------------------------------------------------------------
# 9. EMAIL (SMTP)
# -----------------------------------------------------------------------------
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=False)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
EMAIL_TIMEOUT = env.int('EMAIL_TIMEOUT', default=20)
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default=f'NIT <{EMAIL_HOST_USER}>')
ADMIN_NOTIFICATION_EMAIL = env.list('ADMIN_NOTIFICATION_EMAIL', default=['jaseemrahmanjr@gmail.com'])
# Send notification emails in a background thread so API responses stay fast
ASYNC_NOTIFICATIONS = env.bool('ASYNC_NOTIFICATIONS', default=True)


# -----------------------------------------------------------------------------
# 10. SITE URLS
# -----------------------------------------------------------------------------
SITE_URL = env('SITE_URL', default='http://127.0.0.1:8000').rstrip('/')
# Public base URL used to build absolute image / file URLs in API responses.
# Always forced to https (except localhost during development).
MEDIA_DOMAIN = env('MEDIA_DOMAIN', default=SITE_URL).rstrip('/')
FRONTEND_URL = env('FRONTEND_URL', default='https://nit-hazel.vercel.app').rstrip('/')


# -----------------------------------------------------------------------------
# 11. SECURITY (behind Nginx / Cloudflare)
# -----------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'
if not DEBUG:
    SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=True)
    CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=True)


# -----------------------------------------------------------------------------
# 12. LOGGING
# -----------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {'simple': {'format': '[{asctime}] {levelname} {name}: {message}', 'style': '{'}},
    'handlers': {'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}
