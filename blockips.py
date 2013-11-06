"""
simple middlware to block IP addresses via settings variable BLOCKED_IPS
"""
from django.conf import settings
from django import http

class BlockedIpMiddleware(object):

    def process_request(self, request):
        if (request.META.get('HTTP_X_CLUSTER_CLIENT_IP', '') not in settings.ALLOWED_IPS and len(settings.ALLOWED_IPS) > 0):
            if not request.META['REMOTE_ADDR'] == '127.0.0.1':
                return http.HttpResponseForbidden('<h1>Forbidden</h1>')
        return None
