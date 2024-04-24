import os
from django.conf import settings
import fitz
from django.shortcuts import render
from .forms import UploadFileForm
from django.contrib import messages
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.tag import pos_tag
from .models import nlp_custom, nlp_default, document, merge_entities

from django.http import HttpResponse

def pos_tagging_and_extract_verbs(text):
    tokens = word_tokenize(text)
    stop_words = set(stopwords.words('english'))
    pos_tags = pos_tag(tokens)
    verbs = [word for word, pos in pos_tags if pos.startswith('VB') and word.lower() not in stop_words]
    return verbs

def pos_tagging_and_extract_nouns(text):
    not_include = "coffee"
    tokens = word_tokenize(text)
    pos_tags = pos_tag(tokens)
    nouns = [word for word, pos in pos_tags if pos.startswith('NN') and word != not_include]
    return nouns

def find_answer_type(question):
    question = question.lower().split()
    format = ['what', 'when', 'where', 'who', 'why', 'how']
    entities = []
    if question[0] in format:
      if 'where' in question:
          return ['LOC', 'GPE', 'CONTINENT']
      elif 'who' in question:
          return ['NORP', 'PERSON','NATIONALITY']
      elif 'when' in question:
          return ['DATE', 'TIME']
      elif 'what' in question:
          return ['PRODUCT', 'VARIETY', 'METHODS', 'BEVERAGE', 'QUANTITY']
    else:
        return "Pertanyaan tidak valid"

def find_answer(answer_types, entities):
    answer_types_mapping = {
        'LOC': ['LOC','GPE', 'CONTINENT'],
        'PERSON': ['NORP', 'PERSON','NATIONALITY'],
        'DATE': ['DATE', 'TIME'],
        'PRODUCT': ['PRODUCT', 'VARIETY', 'METHODS', 'BEVERAGE', 'QUANTITY']
    }
    for ent_text, ent_label in entities:
        for answer_type, labels in answer_types_mapping.items():
            if answer_type in answer_types and ent_label in labels:
                return ent_text
    return "Tidak ada informasi yang ditemukan."

def lemmatization(text):
    doc = nlp_default(text)
    filtered_tokens = [token.lemma_ for token in doc if token.lemma_ != token.is_stop]
    return ' '.join(filtered_tokens)

def create_inverted_index(documents):
    inverted_index = {}
    for doc_id, document in enumerate(documents):
        tokens = document.lower().split()
        for token in tokens:
            if token not in inverted_index:
                inverted_index[token] = []
            if doc_id not in inverted_index[token]:
                inverted_index[token].append(doc_id)
    return inverted_index

def retrieve_documents(documents, keywords=None, nouns=None):
    result = []
    rel_doc_set = set()
    rel_doc = []
    inv_index = create_inverted_index(documents)

    # Jika tidak ada keyword dan noun
    if keywords is None and nouns is None:
        return result

    # Jika ada keyword (verb)
    if keywords is not None:
        for keyword in keywords:
            rel_doc_set.clear()
            for token, index in inv_index.items():
                if token == keyword:
                    rel_doc_set.update(index)

            # Konversi set ke list
            rel_doc += [(i, documents[i]) for i in rel_doc_set]

    # Jika ada noun
    if nouns is not None:
        for noun in nouns:
            rel_doc_set.clear()
            for token, index in inv_index.items():
                if token == noun:
                    rel_doc_set.update(index)

            # Konversi set ke list
            rel_doc += [(i, documents[i]) for i in rel_doc_set]

    # format hasil pencarian
    for doc_index, doc_content in rel_doc:
        doc_entities = merge_entities(nlp_custom(doc_content))
        entities = [(ent.text, ent.label_) for ent in doc_entities.ents]
        result.append({
            'document_index': doc_index,
            'document_content': doc_content,
            'entities': entities
        })

    return result

def get_answer_new(question):
    # Menghapus stop words
    keywords = pos_tagging_and_extract_verbs(question)
    keyword_noun = pos_tagging_and_extract_nouns(question)

    response_text = f"Pertanyaan asli: {question}<br>Keywords: {keywords, keyword_noun}<br>"

    answer_types = find_answer_type(question)
    answer = None
    search_result = retrieve_documents(document, keywords, keyword_noun)
    
    if search_result is not None:
        for result in search_result:
            doc_index = result['document_index']
            doc_content = result['document_content']
            entities = result['entities']
            # # Menampilkan hasil pencarian
            response_text += f"<br><br>Dokumen ke-{doc_index}: {doc_content}"

            # # Mendapatkan entitas yang sesuai dengan answer_type
            relevant_entities = [(ent_text, ent_label) for ent_text, ent_label in entities if ent_label in answer_types]

            answer = find_answer(answer_types, relevant_entities)

            if answer is not None:
                response_text += f"Jawaban: {answer}"
                break

    if answer is None:
        # Lemmatisasi kata kunci dan dokumen
        lemmatized_keywords = [lemmatization(key) for key in keywords]
        lemmatized_documents = [lemmatization(doc) for doc in document]

        # Lakukan pencarian kembali
        search_result_baru = retrieve_documents(lemmatized_documents, lemmatized_keywords, keyword_noun)
        print(search_result_baru)
        if search_result_baru is not None:
            for result in search_result_baru:
                doc_index = result['document_index']
                doc_content = result['document_content']
                entities = result['entities']
                # Menampilkan hasil pencarian
                response_text += f"<br><br>Dokumen ke-{doc_index}: {doc_content}"

                # Mendapatkan entitas yang sesuai dengan answer_type
                relevant_entities = [(ent_text, ent_label) for ent_text, ent_label in entities if ent_label in answer_types]

                answer = find_answer(answer_types, relevant_entities)

                if answer is not None:
                    response_text += f"Jawaban: {answer}"
                    break  # Keluar dari loop saat entitas cocok
                else:
                    response_text += f"<br>Jawaban tidak ditemukan."

    context = {'response_text': response_text}
    print(context)
    return (answer)

def home(request):
    if request.method == 'POST':
        search_query = request.POST.get('question')
        print({"Pertanyaan: ", search_query})
        answer_context = get_answer_new(search_query)
        return render(request, 'Home.html', {'answer': answer_context})
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
