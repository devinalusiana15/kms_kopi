import os
from django.conf import settings
from django.shortcuts import render
from .forms import UploadFileForm
from django.contrib import messages

def index(request):
    return render(request, 'Home.html')

def upload_file(request):
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['file']
            # Validasi tipe file harus PDF
            if uploaded_file.content_type != 'application/pdf':
                messages.error(request, 'File must be in PDF format.')
            else:
                # Cek apakah file sudah ada
                upload_dir = os.path.join(settings.BASE_DIR, 'kms_app/uploaded_files')
                if os.path.exists(os.path.join(upload_dir, uploaded_file.name)):
                    messages.error(request, 'File already exists.')
                else:
                    # Simpan file
                    handle_uploaded_file(uploaded_file)
                    messages.success(request, 'New knowledge is added successfully')
                    return render(request, 'pages/addKnowledge.html')
        else:
            messages.error(request, 'Failed to add new knowledge')
    else:
        form = UploadFileForm()
    return render(request, 'pages/addKnowledge.html', {'form': form})

def handle_uploaded_file(file):
    # Get direktori
    upload_dir = os.path.join(settings.BASE_DIR, 'kms_app/uploaded_files')
    # Membuat direktori jika belum ada
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
    # Menyimpan file
    with open(os.path.join(upload_dir, file.name), 'wb+') as destination:
        for chunk in file.chunks():
            destination.write(chunk)
