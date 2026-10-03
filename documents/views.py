from django.contrib import messages
from accounts.access import operator_required as login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import DriverDocumentForm, VehicleDocumentForm
from .models import DriverDocument, VehicleDocument


@login_required
def document_list(request):
    context = {
        "cnhs": DriverDocument.objects.select_related("usuario").all(),
        "crlvs": VehicleDocument.objects.all().select_related("veiculo"),
    }
    return render(request, "documents/list.html", context)


@login_required
def cnh_create(request):
    form = DriverDocumentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.save()
        messages.success(request, "CNH enviada para verificação.")
        return redirect("documents:list")
    return render(request, "shared/form.html", {"form": form, "title": "Enviar CNH"})


@login_required
def crlv_create(request):
    form = VehicleDocumentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "CRLV enviado para verificação.")
        return redirect("documents:list")
    return render(request, "shared/form.html", {"form": form, "title": "Enviar CRLV"})


@login_required
def document_edit(request, kind, pk):
    model, form_class = (DriverDocument, DriverDocumentForm) if kind == 'cnh' else (VehicleDocument, VehicleDocumentForm)
    document = get_object_or_404(model, pk=pk)
    form = form_class(request.POST or None, request.FILES or None, instance=document)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Documento atualizado.')
        return redirect('documents:list')
    return render(request, 'shared/form.html', {'form': form, 'title': f'Editar {kind.upper()}'})
