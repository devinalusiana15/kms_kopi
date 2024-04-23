import os
from django.conf import settings
import fitz
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

from .models import create_inverted_index, merge_entities, nlp_custom, pos_tagging_and_extract_nouns, pos_tagging_and_extract_verbs, document, lemmatization

def home(request):
    context_path = "kms_app/knowledge/coffee.pdf" 
    context = extract_text_from_pdf(context_path)

    if request.method == 'POST':
        search_query = request.POST.get('default-search')
        answer = "Success"
        return render(request, 'Home.html', {'answer': answer, 'context': context})
    else:
        return render(request, 'Home.html', {'context': context})

def extract_text_from_pdf(context_path):
    text = ""
    try:
        with fitz.open(context_path) as doc:
            for page in doc:
                text += page.get_text()
    except Exception as e:
        print("Error:", e)
    return text

def find_answer_type(question):
    question = question.lower()
    entities = []
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
  # Kamus yang memetakan tipe jawaban ke label entitas yang sesuai
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
