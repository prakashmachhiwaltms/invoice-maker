"""
Django settings for the Invoice Generator project.
"""
from pathlib import Path
from decouple import Config, RepositoryEnv, Csv
import os

BASE_DIR = Path(__file__).resolve().parent.parent

env_file = BASE_DIR / '.env'
if env_file.exists():
    config = Config(RepositoryEnv(str(env_file)))
else:
    config = Config(RepositoryEnv(str(BASE_DIR / '.env.example')))

SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key-change-me')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='127.0.0.1,localhost', cast=Csv())

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    'accounts',
    'dashboard',
    'invoices',
    'pdf_editor',
    'settings_app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'accounts.middleware.ActivityAuditMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'settings_app.context_processors.company_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DB_ENGINE = config('DB_ENGINE', default='django.db.backends.mysql')

if DB_ENGINE == 'django.db.backends.sqlite3':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': DB_ENGINE,
            'NAME': config('DB_NAME', default='invoice_app'),
            'USER': config('DB_USER', default='root'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': config('DB_HOST', default='127.0.0.1'),
            'PORT': config('DB_PORT', default='3306'),
            'OPTIONS': {
                'charset': 'utf8mb4',
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'
        if not DEBUG else 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard:index'
LOGOUT_REDIRECT_URL = 'accounts:login'

SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 2 weeks (Remember me)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Security
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'  # the invoice preview page embeds its own PDF-equivalent HTML in an iframe

if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# File upload limits
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = ['.xlsx', '.xls', '.csv']

MAX_PDF_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB per PDF
ALLOWED_PDF_EXTENSIONS = ['.pdf']

EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='no-reply@invoice-generator.local')

# App-level defaults
DEFAULT_TAX_RATE = config('DEFAULT_TAX_RATE', default='18', cast=str)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'app.log',
        },
    },
    'root': {'handlers': ['console', 'file'], 'level': 'INFO'},
    'loggers': {
        'django': {'handlers': ['console', 'file'], 'level': 'INFO', 'propagate': False},
        'invoices': {'handlers': ['console', 'file'], 'level': 'INFO', 'propagate': False},
        'pdf_editor': {'handlers': ['console', 'file'], 'level': 'INFO', 'propagate': False},
    },
}
