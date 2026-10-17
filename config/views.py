from django.http import HttpResponse, JsonResponse


def error_404(request, exception):
    if request.path.startswith('/api/'):
        return JsonResponse({'status': 'error', 'message': 'Not found.'}, status=404)
    return HttpResponse('<h1>404</h1><p>Page not found.</p><a href="/superadmin/">Go to admin</a>', status=404)


def error_500(request):
    if request.path.startswith('/api/'):
        return JsonResponse({'status': 'error', 'message': 'Server error. Please try again later.'}, status=500)
    return HttpResponse('<h1>500</h1><p>Something went wrong.</p>', status=500)
