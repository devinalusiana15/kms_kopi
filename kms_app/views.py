import os
from datetime import datetime
from collections import defaultdict

import fitz
from nltk.tag import pos_tag

import time
from django.utils.safestring import mark_safe
from django.db.models import Prefetch
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.safestring import mark_safe
from rdflib import Graph, URIRef, Namespace, Literal
from owlready2 import onto_path, get_ontology, sync_reasoner

from .forms import LoginForm, UploadFileForm
from .models import (
    nlp_default,
    nlp_custom,
    merge_entities,
    get_fuseki_data,
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

                    text = extract_text_from_pdf(new_document.document_path)
                    document = [merge_entities(nlp_custom(sentence)) for sentence in text.split('.') if sentence.strip()]

                    ontology = generate_ontology(document)
                    save_ontology(ontology)

                    messages.success(request, 'New knowledge is added successfully')
                    return render(request, 'pages/uploaders/uploadersAddKnowledge.html')
        else:
            messages.error(request, 'Failed to add new knowledge')
    else:
        form = UploadFileForm()
    return render(request, 'pages/uploaders/uploadersAddKnowledge.html', {'form': form})

def remove_stopwords(doc):
    return ' '.join([token.text for token in doc if not token.is_stop])

def pos_tagging_and_extract_verbs(text):
    doc = nlp_default(text)
    tokens = [token.text for token in doc]
    stop_words = nlp_default.Defaults.stop_words
    pos_tags = pos_tag(tokens)
    verbs = [word for word, pos in pos_tags if pos.startswith('VB') and word.lower() not in stop_words]
    return verbs

def pos_tagging_and_extract_nouns(text):
    not_include = "coffee"
    doc = nlp_default(text)
    tokens = [token.text for token in doc]
    pos_tags = pos_tag(tokens)
    nouns = [word for word, pos in pos_tags if pos.startswith('NN') and word != not_include]
    return nouns

def pos_tagging_and_extract_nouns_ontology(text):
    not_include = ["coffee", "definition"]
    doc = nlp_default(text)
    tokens = [token.text for token in doc]
    pos_tags = pos_tag(tokens)
    nouns = [word for word, pos in pos_tags if pos.startswith('NN')]

    if len(nouns) == 1 and nouns[0] == "coffee":
        return nouns
    else:
        nouns = [noun for noun in nouns if noun not in not_include]
        return nouns

def find_answer_type(question):

    question = question.lower().split()

    format = ['what', 'when', 'where', 'who', 'why', 'how']

    if question[1] == "are" and question[0] in format:
          return ['axiom']
    elif question[0] in format:
      if 'where' in question:
          return ['LOC', 'GPE', 'CONTINENT', 'LOCATION']
      elif 'who' in question:
          return ['NORP', 'PERSON','NATIONALITY']
      elif 'when' in question:
          return ['DATE', 'TIME']
      elif 'what' in question:
          if 'definition' in question:
            return ['definition']
          else:
            return ['PERCENT', 'PRODUCT', 'VARIETY', 'METHODS', 'BEVERAGE', 'QUANTITY']
      elif 'how' in question:
          return ['direction']
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

def get_answer_new(question):
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
                answer = "Tidak ada informasi yang ditemukan."
    else:
        response_text += "<br>Dokumen yang relevan tidak ditemukan."
        refine = Refinements(question=question, answer=answer)
        refine.save()

    context = {'response_text': response_text, 'related_articles': relevant_sentences_verbs}
    print(context)
    extra_info = get_extra_information(answer.replace(" ", "_"))
    return answer, search_result_verbs, extra_info

def home(request):
    if request.method == 'POST':
        start_time = time.time()  
        search_query = request.POST.get('question')
        print({"Pertanyaan: ", search_query})
        answer_types = find_answer_type(search_query)
        print(answer_types)
        annotation_types = ['definition', 'direction']
        if 'axiom' in answer_types:
            keyword_noun = pos_tagging_and_extract_nouns(search_query)
            print(keyword_noun)
            answer = get_instances(keyword_noun)
            context = {
                'question': search_query,
                'answer': mark_safe(answer),
            }
        elif not any(answer_type in annotation_types for answer_type in answer_types):
            answer_context, related_articles, extra_info = get_answer_new(search_query)
            context = {
                'question': search_query,
                'answer': answer_context,
                'related_articles': related_articles,
                'extra_info': extra_info,
            }
        else:
            answer = get_annotation(search_query, answer_types)
            context = {
                'question': search_query,
                'answer': mark_safe(answer),
                'related_articles': None,
                'extra_info': None
            }
        end_time = time.time() 
        response_time = (end_time - start_time) * 1000
        response_time = round(response_time, 1)
        
        context['response_time'] = response_time

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

def create_and_save_inverted_index(document):
    text = extract_text_from_pdf(document.document_path)
    sentences = text.split('.')
    stop_words = nlp_default.Defaults.stop_words

    with transaction.atomic():
        for sentence_index, sentence in enumerate(sentences, start=1):
            doc_details = DocDetails.objects.create(document=document, docdetail=sentence, position=sentence_index)
            tokens = [token.lower() for token in sentence.split() if token.lower() not in stop_words]
            lemmatized_tokens = lemmatization(sentence)

            for token in tokens:
                term, created = Terms.objects.get_or_create(term=token)
                PostingLists.objects.create(term=term, docdetail=doc_details)

            for lemma in lemmatized_tokens:
                if lemma not in stop_words:
                    term_lemma, lemma_created = TermLemmas.objects.get_or_create(termlemma=lemma)
                    PostingListLemmas.objects.create(termlemma=term_lemma, docdetail=doc_details)
                    

def articles(request):
    documents = Documents.objects.all()
    print(documents)
    
    context = []

    for document in documents:
        extracted_text = extract_text_from_pdf(document.document_path)

        truncated_text = extracted_text[:1000]

        article_data = {
            'doc_name': os.path.splitext(document.document_name)[0],
            'context': truncated_text + '...',
            'full_path': document.document_path,
            'id': document.document_id
        }

        context.append(article_data)

    return render(request, 'pages/articles.html', {'articles': context})

def detailArticle(request, document_id):
    
    document = get_object_or_404(Documents, document_id=document_id)
    extracted_text = extract_text_from_pdf(document.document_path)

    article_data = {
        'doc_name': os.path.splitext(document.document_name)[0],
        'full_text': extracted_text
    }

    return render(request, 'pages/detailArticle.html', {'article': article_data})

""" Ontologi """

def generate_ontology(doc_ontology):
    cleaned_sentences = []
    for sent in doc_ontology:
        cleaned_sentences.append(remove_stopwords(sent))

    clean_ents=[]
    for sent in cleaned_sentences:
        clean_ents.append(merge_entities(nlp_custom(sent)))

    # Proses pembuatan ontologi
    ontology = ""

    classes = set()
    object_properties = set()
    data_properties = set()

    for sent in clean_ents:
        prev_entity = None
        for ent in sent.ents:
            if ent.label_ != '':
                if ent.label_ == 'VERB':
                    if prev_entity:
                        # Next entity
                        next_entity = None
                        for next_ent in sent.ents:
                            if next_ent.start > ent.start:
                                next_entity = next_ent
                                break
                        if next_entity:
                            if next_entity.label_ in ["DATE", "TIME"]:
                                obj_prop = f"{ent.text}_on"
                            elif next_entity.label_ in ["LOC", "GPE"]:
                                obj_prop = f"{ent.text}_in"
                            elif next_entity.label_ in ["NORP", "PERSON"]:
                                obj_prop = f"{ent.text}_by"
                            else:
                                obj_prop = f"{ent.text}"
                        
                            object_properties.add(obj_prop)

                            # Penentuan Domain
                            ontology += f"""
                            <http://www.semanticweb.org/ariana/coffee#{obj_prop}> rdfs:domain <http://www.semanticweb.org/ariana/coffee#{prev_entity.label_}> .
                            """
                            # Penentuan Range
                            ontology += f"""
                                <http://www.semanticweb.org/ariana/coffee#{obj_prop}> rdfs:range <http://www.semanticweb.org/ariana/coffee#{next_entity.label_}> .
                            """
                            # Individual - Object Property - Individual
                            ontology += f"""
                                <http://www.semanticweb.org/ariana/coffee#{prev_entity.text.replace(" ", "_")}> coffee:{obj_prop} <http://www.semanticweb.org/ariana/coffee#{next_entity.text.replace(" ", "_")}> .
                            """
                    prev_entity = None  # Reset prev_entity
                else:
                    prev_entity = ent

    for sent in clean_ents:
        for ent in sent.ents:
            if ent.label_ != '':
                individual_name = ent.text.replace(" ", "_")
                if ent.label_ != 'VERB':
                    classes.add(ent.label_)
                    ontology += f"""
                    <http://www.semanticweb.org/ariana/coffee#{individual_name}> rdf:type <http://www.semanticweb.org/ariana/coffee#{ent.label_}> .
                    """
    return ontology

def save_ontology(ontology):
    owl_directory = os.path.join(settings.BASE_DIR, 'kms_app/owl_file')
    file_path = os.path.join(owl_directory, "Kopi.owl")
    with open(file_path, "a") as output_file:
        output_file.write(ontology)


def get_extra_information(answer):
    COFFEE = Namespace("http://www.semanticweb.org/ariana/coffee#")
    g = Graph()
    g.bind("coffee", COFFEE)

    query = f"""
    PREFIX coffee: <http://www.semanticweb.org/ariana/coffee#>
    SELECT ?p ?o ?s WHERE {{
      {{ coffee:{answer} ?p ?o.
        FILTER (!CONTAINS(LCASE(STR(?p)), "type"))
      }}
      UNION
      {{ ?s ?p coffee:{answer}.
        FILTER (!CONTAINS(LCASE(STR(?p)), "type"))
      }}
    }}
    """
    results = get_fuseki_data(query)

    text_response = ""
    if results:
        for row in results:
            predicate_name = row.get('p', '').split('#')[-1].replace("_", " ") if row.get('p') else None
            object_name = row.get('o', '').split('#')[-1].replace("_", " ") if row.get('o') else None
            subject_name = row.get('s', '').split('#')[-1].replace("_", " ") if row.get('s') else None

            if predicate_name and object_name:
                g.add((COFFEE[answer], URIRef(row['p']), URIRef(row['o'])))
                text_response += f"{answer} {predicate_name} {object_name}. "
            if predicate_name and subject_name:
                g.add((URIRef(row['s']), URIRef(row['p']), COFFEE[answer]))
                text_response += f"{subject_name} {predicate_name} {answer}. "

        rdf_output = g.serialize(format='turtle')
    else:
        rdf_output = None
    
    extra_info = {
        'answer': answer.replace("_", " "),
        'text_response': text_response,
        'rdf_output': rdf_output, 
    }

    return extra_info



def get_annotation(question,annotation):

    keywords_nouns = pos_tagging_and_extract_nouns_ontology(question)

    noun = "_".join(keywords_nouns)
    print(noun)

    response = ""

    query = f"""
    PREFIX coffee: <http://www.semanticweb.org/ariana/coffee#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?s WHERE {{
      coffee:{noun} rdfs:{annotation[0]} ?s
    }}
    """

    try:
        results = get_fuseki_data(query)
    except Exception as e:
        print(f"Error executing query: {e}")
        return "Error executing query"

    if results:
        for row in results:
          response = row['s'].replace("\n", "<br>")
    else:
        response = "Tidak ada jawaban"

    return response

def get_answer_rdf(answer, key_noun):
    print(f'INI KEY NOUN: {key_noun}')
    COFFEE = Namespace("http://www.semanticweb.org/ariana/coffee#")
    g = Graph()
    g.bind("coffee", COFFEE)

    query = f"""
    PREFIX coffee: <http://www.semanticweb.org/ariana/coffee#>
    SELECT ?p ?o ?s WHERE {{
      {{ coffee:{answer} ?p coffee:{key_noun}.
        FILTER (!CONTAINS(LCASE(STR(?p)), "type"))
      }}
      UNION
      {{ coffee:{key_noun} ?p coffee:{answer}.
        FILTER (!CONTAINS(LCASE(STR(?p)), "type"))
      }}
    }}
    """
    results = get_fuseki_data(query)

    if results:
        for row in results:
            predicate = row.get('p')
            object_ = row.get('o')
            subject = row.get('s')

            if predicate and object_:
                g.add((COFFEE[answer], URIRef(predicate), URIRef(object_)))
            if predicate and subject:
                g.add((URIRef(subject), URIRef(predicate), COFFEE[answer]))

        rdf_output = g.serialize(format='turtle')
    else:
        rdf_output = None

    return rdf_output


def get_instances(noun):
    onto_path.append(os.path.join(settings.BASE_DIR, 'kms_app/owl_file'))
    onto = get_ontology("Kopi.rdf").load()

    # Mengaktifkan reasoner
    sync_reasoner()

    # Noun sebagai class yang dicari
    keyword_noun = "".join(noun)

    # Mencari kelas berdasarkan kata kunci
    cls = onto[keyword_noun]
    if not cls:
        return "Class not found"

    instances = list(cls.instances())

    response = f"<br>These are the {keyword_noun}:"

    if instances:
        # Mendapatkan properti yang sama pada setiap instance
        common_properties = None
        for instance in instances:
            instance_properties = set()
            for prop in instance.get_properties():
                instance_properties.add(prop.name)

            if common_properties is None:
                common_properties = instance_properties
            else:
                common_properties = common_properties.intersection(instance_properties)

        # Menampilkan instance - common_properties - value
        if common_properties:
            for prop_name in common_properties:
                for instance in instances:
                    for prop in instance.get_properties():
                        if prop.name == prop_name:
                            for value in prop[instance]:
                                response += f"<br>- {instance.name.replace('_', ' ')} {prop.name} {value.name.replace('_', ' ')} "
    else:
        response += "No instances found."

    return response



