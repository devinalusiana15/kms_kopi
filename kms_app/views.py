import os
from django.conf import settings
import fitz
from django.shortcuts import render
from .forms import UploadFileForm
from django.contrib import messages

def find_answer_type(question):
    question = question.lower().split()
    format = ['what', 'when', 'where', 'who', 'why', 'how']
    entities = []
    if question[0] in format:
      if 'where' in question:
          return ['LOC', 'GPE']
      elif 'who' in question:
          return ['NORP', 'PERSON']
      elif 'when' in question:
          return ['DATE', 'TIME']
      elif 'what' in question:
          return ['PRODUCT', 'VARIETY', 'METHODS', 'BEVERAGE', 'QUANTITY']
    else:
        return "Pertanyaan tidak valid"

def find_answer(relevant_sentences, answer_types, entities):
    answer_types_mapping = {
        'LOC': ['LOC','GPE'],
        'PERSON': ['NORP', 'PERSON'],
        'DATE': ['DATE', 'TIME'],
        'PRODUCT': ['PRODUCT', 'VARIETY', 'METHODS', 'BEVERAGE', 'QUANTITY']
    }
    for ent_text, ent_label in entities:
        for answer_type, labels in answer_types_mapping.items():
            if answer_type in answer_types and ent_label in labels:
                return ent_text
    return "Tidak ada informasi yang ditemukan."

def home(request):
    if request.method == 'POST':
        search_query = request.POST.get('default-search')
        print("Nilai default-search:", search_query) # Buat pembuktian dulu
        answer_type = find_answer_type(search_query)
        if answer_type == "Pertanyaan tidak valid":
            answer = "Pertanyaan tidak valid. Silahkan masukkan pertanyaan lagi."
        else:
            # relevant_sentences = []
            # entities = [] 
            # answer = find_answer(relevant_sentences, answer_type, entities)
            # print(answer)
            answer = "Success"
        return render(request, 'Home.html', {'answer': answer})
    else:
        return render(request, 'Home.html')
    
def articles(request):
    context_path = "kms_app/uploaded_files/coffee.pdf" 
    context = extract_text_from_pdf(context_path)
    
    return render(request, 'pages/articles.html', {'context': context})

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

def extract_text_from_pdf(context_path):
    text = ""
    try:
        with fitz.open(context_path) as doc:
            for page in doc:
                text += page.get_text()
    except Exception as e:
        print("Error:", e)
    return text
