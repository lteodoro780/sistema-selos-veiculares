from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.views.decorators.cache import never_cache
from accounts.access import operator_required


@never_cache
@operator_required
def download(request, name):
    root = Path(settings.MEDIA_ROOT).resolve()
    candidate = root / name
    if any(part in {'..', '.', ''} for part in name.split('/')) or '\\' in name:
        raise Http404
    if candidate.is_symlink():
        raise Http404
    file = candidate.resolve()
    if not file.is_relative_to(root) or not file.is_file():
        raise Http404
    response = FileResponse(file.open('rb'), as_attachment=True, filename=file.name,
                            content_type='application/octet-stream')
    response['X-Content-Type-Options'] = 'nosniff'
    return response
