import os
from datetime import datetime
from collections import defaultdict

import fitz
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.tag import pos_tag

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.shortcuts import render, redirect

from .forms import LoginForm, UploadFileForm
from .models import (
    nlp_default,
    merge_entities,
    Uploader,
    Documents,
    Terms,
    PostingLists,
    DocDetails,
    Refinements,
    TermLemmas,
    PostingListLemmas
)

def login(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            try:
                user = Uploader.objects.get(username=username)
                if user.password == password:
                    request.session['uploader_id'] = user.uploader_id
                    return redirect('uploadKnowledge')
                else:
                    form.add_error(None, 'Invalid username or password')
            except Uploader.DoesNotExist:
                form.add_error(None, 'Invalid username or password')
    else:
        form = LoginForm()
    return render(request, 'pages/uploaders/login.html', {'form': form})

def logout(request):
    del request.session['uploader_id']
    return redirect('login')

def addKnowledge(request):
    return render(request, 'pages/seekers/addKnowledge.html')

def uploadKnowledge(request):
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['file']
            if uploaded_file.content_type != 'application/pdf':
                messages.error(request, 'File must be in PDF format.')
            else:
                upload_dir = os.path.join(settings.BASE_DIR, 'kms_app/uploaded_files')
                if os.path.exists(os.path.join(upload_dir, uploaded_file.name)):
                    messages.error(request, 'File already exists.')
                else:
                    new_document = Documents(document_name=uploaded_file.name, document_path='kms_app/uploaded_files/'+uploaded_file.name)
                    new_document.save()
                    
                    handle_uploaded_file(uploaded_file)                    
                    create_and_save_inverted_index(new_document)
                    
                    messages.success(request, 'New knowledge is added successfully')
                    return render(request, 'pages/uploaders/uploadersAddKnowledge.html')
        else:
            messages.error(request, 'Failed to add new knowledge')
    else:
        form = UploadFileForm()
    return render(request, 'pages/uploaders/uploadersAddKnowledge.html', {'form': form})

def pos_tagging_and_extract_verbs(text):
    tokens = word_tokenize(text)
    stop_words = set(stopwords.words('english'))
    pos_tags = pos_tag(tokens)
    verbs = [word for word, pos in pos_tags if pos.startswith('VB') and word.lower() not in stop_words]
    return verbs

def pos_tagging_and_extract_nouns(text):
    tokens = word_tokenize(text)
    pos_tags = pos_tag(tokens)
    nouns = [word for word, pos in pos_tags if pos.startswith('NN')]

    if len(nouns) == 1 and nouns[0] == "coffee":
        return nouns
    else:
        nouns = [noun for noun in nouns if noun != "coffee"]
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
          return ['PRODUCT', 'VARIETY', 'METHODS', 'BEVERAGE', 'QUANTITY', 'LOC', 'JOB', 'DISTANCE', 'TEMPERATURE']
    else:
        return "Pertanyaan tidak valid"

def find_answer(answer_types, entities):
    answer_types_mapping = {
        'LOC': ['LOC','GPE', 'CONTINENT'],
        'PERSON': ['NORP', 'PERSON','NATIONALITY', 'JOB'],
        'DATE': ['DATE', 'TIME'],
        'PRODUCT': ['PRODUCT', 'VARIETY', 'METHODS', 'BEVERAGE', 'QUANTITY', 'DISTANCE', 'TEMPERATURE'],
    }
    for ent_text, ent_label in entities:
        for answer_type, labels in answer_types_mapping.items():
            if answer_type in answer_types and ent_label in labels:
                return ent_text
    return "Tidak ada informasi yang ditemukan."

def lemmatization(text):
    doc = nlp_default(text)
    filtered_tokens = [token.lemma_ for token in doc if not token.is_stop and not token.is_punct]
    return filtered_tokens

def retrieve_documents(keywords=None, nouns=None):
    relevant_documents = []
    relevant_sentences = []
    
    if keywords is None and nouns is None:
        return relevant_documents, relevant_sentences  # Mengembalikan dua nilai
    
    terms = Terms.objects.none()
    if keywords is not None:
        terms = Terms.objects.filter(term__in=keywords)
    if nouns is not None:
        terms = terms | Terms.objects.filter(term__in=nouns)
    
    if terms.exists():
        posting_entries = PostingLists.objects.filter(term__in=terms)
        for entry in posting_entries:
            doc_detail = entry.docdetail
            document_content = DocDetails.objects.filter(docdetail_id=doc_detail.docdetail_id).values_list('docdetail', flat=True).first()
            relevant_sentence = document_content
            
            # Kalau di luar for nanti related articlenya bakal cuma satu
            relevant_documents.append({
                'detail': entry.docdetail.docdetail_id,
                'document_name': entry.docdetail.document_id,
                'context': document_content,
                'relevant_sentence': relevant_sentence,
                'url': f'/document/{doc_detail.document_id}'
            })
        relevant_sentences.append(relevant_sentence)
    
    return relevant_documents, relevant_sentences

def retrieve_documents_lemmas(keywords=None, nouns=None):
    relevant_documents = []
    relevant_sentences = []

    if keywords is None and nouns is None:
        return relevant_documents, relevant_sentences

    terms_lemma = TermLemmas.objects.none()
    if keywords is not None:
        terms_lemma = TermLemmas.objects.filter(termlemma__in=keywords)
    if nouns is not None:
        terms_lemma = terms_lemma | TermLemmas.objects.filter(termlemma__in=nouns)

    if terms_lemma.exists():
        posting_entries = PostingListLemmas.objects.filter(termlemma__in=terms_lemma)
        for entry in posting_entries:
            doc_detail = entry.docdetail
            document_content = DocDetails.objects.filter(docdetail_id=doc_detail.docdetail_id).values_list('docdetail', flat=True).first()
            relevant_sentence = document_content

            relevant_documents.append({
                'detail': entry.docdetail.docdetail_id,
                'document_name': entry.docdetail.document_id,
                'context': document_content,
                'relevant_sentence': relevant_sentence,
                'url': f'/document/{doc_detail.document_id}'
            })
            relevant_sentences.append(relevant_sentence)

    return relevant_documents, relevant_sentences

def get_answer(question):
    keywords_verbs = pos_tagging_and_extract_verbs(question)
    keywords_nouns = pos_tagging_and_extract_nouns(question)
    response_text = f"Pertanyaan asli: {question}<br>Keywords (Verbs): {keywords_verbs}<br>Keywords (Nouns): {keywords_nouns}<br>"
    
    answer = "Tidak ada informasi yang ditemukan."
    
    search_result_verbs, relevant_sentences_verbs = retrieve_documents(keywords=keywords_verbs)
    
    if not search_result_verbs:
        search_result_nouns, relevant_sentences_nouns = retrieve_documents(nouns=keywords_nouns)
        search_result_verbs.extend(search_result_nouns)
        relevant_sentences_verbs.extend(relevant_sentences_nouns)
    
    if not search_result_verbs:
        lemmatized_verbs = lemmatization(' '.join(keywords_verbs))
        lemmatized_nouns = lemmatization(' '.join(keywords_nouns))

        search_result_lemmas_verbs, relevant_sentences_lemmas_verbs = retrieve_documents_lemmas(keywords=lemmatized_verbs)

        if not search_result_lemmas_verbs:
            search_result_lemmas_nouns, relevant_sentences_lemmas_nouns = retrieve_documents_lemmas(nouns=lemmatized_nouns)
            search_result_lemmas_verbs.extend(search_result_lemmas_nouns)
            relevant_sentences_lemmas_verbs.extend(relevant_sentences_lemmas_nouns)

        search_result_verbs.extend(search_result_lemmas_verbs)
        relevant_sentences_verbs.extend(relevant_sentences_lemmas_verbs)

    if search_result_verbs:
        for i, result in enumerate(search_result_verbs):
            doc_content = result['relevant_sentence']
            doc_entities = merge_entities(nlp_default(doc_content)).ents
            print(f"Entities in document {result['document_name']}: {doc_entities}")

            answer_types = find_answer_type(question)
            print(f"Answer types: {answer_types}")

            answer = find_answer(answer_types, [(ent.text, ent.label_) for ent in doc_entities])
            print(f"Answer found: {answer}")

            if answer != "Tidak ada informasi yang ditemukan.":
                response_text += f"<br>Jawaban: {answer}"
                break
            else:
                response_text += f"<br>Jawaban tidak ditemukan dalam dokumen: {result['document_name']}"
                refine = Refinements(question=question, answer=answer)
                refine.save()
    else:
        response_text += "<br>Dokumen yang relevan tidak ditemukan."
        refine = Refinements(question=question, answer=answer)
        refine.save()

    context = {'response_text': response_text, 'related_articles': search_result_verbs}
    print(context)
    return answer, search_result_verbs


def home(request):
    if request.method == 'POST':
        # search_query = request.POST.get('question')
        question = request.POST.get('question') or ''
        print({"Pertanyaan: ", question})
        answer_context, related_articles = get_answer(question)
        # post = {'question': question}

        context = {
            'question': question,
            'answer': answer_context,
            'related_articles': related_articles
        }
        return render(request, 'Home.html', context)
    else:
        return render(request, 'Home.html', {'related_articles': []})

def handle_uploaded_file(file):
    upload_dir = os.path.join(settings.BASE_DIR, 'kms_app/uploaded_files')
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
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

@transaction.atomic
def create_and_save_inverted_index(document):
    text = extract_text_from_pdf(document.document_path)
    sentences = text.split('.')
    inverted_index = defaultdict(list)
    inverted_index_lemma = defaultdict(list)
    stop_words = set(stopwords.words('english'))

    for sentence_index, sentence in enumerate(sentences, start=1):
        doc_details = DocDetails.objects.create(document=document, docdetail=sentence, position=sentence_index)
        tokens = sentence.lower().split()
        lemmatized_tokens = lemmatization(sentence)

        for token in tokens:
            if token in stop_words:
                continue
            term, created = Terms.objects.get_or_create(term=token)
            PostingLists.objects.create(term=term, docdetail=doc_details)
            inverted_index[token].append((term.term_id, doc_details.docdetail_id))
        
        for lemma in lemmatized_tokens:
            if lemma in stop_words:
                continue
            term_lemma, lemma_created = TermLemmas.objects.get_or_create(termlemma=lemma)
            PostingListLemmas.objects.create(termlemma=term_lemma, docdetail=doc_details)
            inverted_index_lemma[lemma].append((term_lemma.termlemma_id, doc_details.docdetail_id))

    for term, postings in inverted_index.items():
        term_obj = Terms.objects.get(term=term)
        for posting in postings:
            PostingLists.objects.create(term_id=posting[0], docdetail_id=posting[1])
    
    for lemma, postings in inverted_index_lemma.items():
        term_lemma_obj = TermLemmas.objects.get(termlemma=lemma)
        for posting in postings:
            PostingListLemmas.objects.create(termlemma_id=posting[0], docdetail_id=posting[1])

def articles(request):
    documents = Documents.objects.all()
    
    context = []

    for document in documents:
        extracted_text = extract_text_from_pdf(document.document_path)

        truncated_text = extracted_text[:1000]

        # Create dictionary to store document and content details
        article_data = {
            'doc_name': os.path.splitext(document.document_name)[0],
            'context': truncated_text+'...',
            'full_path': document.document_path, 
        }

        context.append(article_data)

    return render(request, 'pages/articles.html', {'articles': context})