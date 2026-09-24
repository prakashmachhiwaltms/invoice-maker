"""
WSGI entry point for cPanel's "Setup Python App" (Phusion Passenger).

cPanel's Python App feature looks for this exact filename in the
Application Root directory and imports the callable named in
"Application Entry point" (set that to: application).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
