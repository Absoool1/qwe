import os
import environ
import openai  # تأكد من تثبيت مكتبة openai
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv()
# تهيئة مكتبة environ
env = environ.Env()

# قراءة ملف .env
environ.Env.read_env()

# إعداد مفتاح OpenAI API
OPENAI_API_KEY = env("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OpenAI API key is not set. Please check your .env file.")

# تهيئة مكتبة OpenAI

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# بدلاً من تحديد SECRET_KEY مباشرة، اقرأه من ملف .env
SECRET_KEY = env('SECRET_KEY')

# إعدادات PayPal من ملف .env
PAYPAL_CLIENT_ID = env("PAYPAL_CLIENT_ID")
PAYPAL_SECRET_KEY = env("PAYPAL_SECRET_KEY")

# الإعدادات الأخرى
DEBUG = True

# إعدادات رفع الملفات
MEDIA_URL = '/media/'  # المسار الذي سيتم الوصول منه إلى الملفات المرفوعة
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')  # المجلد حيث يتم تخزين الملفات المرفوعة فعليًا


ALLOWED_HOSTS = ['markettrail.onrender.com', 'localhost', '127.0.0.1']

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]
# تأكد من إعداد مسار إعادة التوجيه بعد تسجيل الدخول


LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'



# إعداد محرك الجلسات
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# تفعيل أمان الكوكيز إذا كنت تستخدم HTTPS
SESSION_COOKIE_SECURE = True  # اجعلها True فقط إذا كنت تستخدم HTTPS
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"  # يُسمح باستخدام Bootstrap 5 فقط
CRISPY_TEMPLATE_PACK = "bootstrap5"           # استخدام Bootstrap 5 كقالب افتراضي

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    'compressor',
    'crispy_forms',
    'crispy_bootstrap5',
    'rest_framework',
    'corsheaders',
]

#MIDDLEWARE.insert(0, 'corsheaders.middleware.CorsMiddleware')

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",  # رابط واجهة React
]

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware', 
    'django.middleware.common.CommonMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    
]

ROOT_URLCONF = 'affiliate_platform.urls'
CORS_ALLOW_ALL_ORIGINS = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'affiliate_platform.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True

STATIC_URL = '/static/'

# مسار تجميع الملفات الثابتة عند تشغيل collectstatic
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# مسار الملفات الثابتة الإضافية التي يمكن أن تتواجد في المجلد `static`
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST', default='smtp.your-email-provider.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='your-email@example.com')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='your-email-password')

LOGGING = {
    'version': 1,  # إصدار نظام السجل
    'disable_existing_loggers': False,  # السماح باستخدام السجلات الحالية
    'handlers': {
        'console': {
            'level': 'WARNING',  # تسجيل التحذيرات والأخطاء فقط
            'class': 'logging.StreamHandler',  # عرض السجلات في التيرمينال
        },
        'file': {
            'level': 'ERROR',  # تسجيل الأخطاء فقط
            'class': 'logging.FileHandler',
            'filename': 'errors.log',  # اسم ملف السجل (سيتم إنشاؤه في نفس المسار)
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],  # عرض السجلات في التيرمينال وحفظها في الملف
            'level': 'ERROR',  # تسجيل الأخطاء فقط
            'propagate': True,  # نشر السجلات إلى المعالجات الأخرى
        },
    },
}


CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}