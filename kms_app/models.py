import nltk
import spacy
import json
import subprocess
import os.path
from django.db import models
from django.core.validators import MinLengthValidator
from tqdm import tqdm
from spacy.tokens import DocBin, Doc
from django.db import models
from rdflib import Graph, Namespace, Literal, URIRef
import requests

nltk.download('punkt')
nltk.download('averaged_perceptron_tagger')
nltk.download('maxent_ne_chunker')
nltk.download('words')
nltk.download('stopwords')

class Uploader(models.Model):
    uploader_id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=128, validators=[MinLengthValidator(8)])

    def __str__(self):
        return self.username

class Documents(models.Model):
    document_id = models.AutoField(primary_key=True)  # ID unik untuk setiap dokumen
    document_name = models.CharField(max_length=255)  # Nama atau judul dokumen
    document_path = models.CharField(max_length=255)  # Isi dari dokumen tersebut

    def __str__(self):
        return self.document_name
    
class Terms(models.Model):
    term_id = models.AutoField(primary_key=True)  # ID unik untuk setiap term
    term = models.CharField(max_length=255,unique=True)  # Term atau kata kunci yang muncul dalam dokumen

    def __str__(self):
        return self.term

    class Meta:
        indexes = [
            models.Index(fields=['term']),  # Menambahkan indeks pada kolom term
        ]
    
class DocDetails(models.Model):
    docdetail_id = models.AutoField(primary_key=True)  # ID unik untuk setiap dokumen
    document = models.ForeignKey(Documents, on_delete=models.CASCADE)  # ID dokumen yang merujuk ke Tabel Dokumen
    docdetail = models.CharField(max_length=255)  # Isi dari dokumen tersebut
    position = models.IntegerField()

    def __str__(self):
        return self.docdetail

class PostingLists(models.Model):
    postlist_id = models.AutoField(primary_key=True)  # ID unik untuk setiap entri dalam posting list
    term = models.ForeignKey(Terms, on_delete=models.CASCADE,to_field='term', db_column='term')  # ID term yang merujuk ke Tabel Term
    docdetail = models.ForeignKey(DocDetails, on_delete=models.CASCADE)  # Frekuensi kemunculan term dalam dokumen tertentu

    def __str__(self):
        return f"{self.term} - {self.docdetail}"
    
    class Meta:
        indexes = [
            models.Index(fields=['term']),  # Menambahkan indeks pada kolom term
            models.Index(fields=['docdetail']),
        ]
    
class Refinements(models.Model):
    refinement_id = models.AutoField(primary_key=True)
    question = models.CharField(max_length=255)
    answer = models.CharField(max_length=255)

class TermLemmas(models.Model):
    termlemma_id = models.AutoField(primary_key=True)  # ID unik untuk setiap term
    termlemma = models.CharField(max_length=255, unique=True)  # Term atau kata kunci yang muncul dalam dokumen

    def __str__(self):
        return self.termlemma

    class Meta:
        indexes = [
            models.Index(fields=['termlemma']),  # Menambahkan indeks pada kolom termlemma
        ]
    
class PostingListLemmas(models.Model):
    postlistlemma_id = models.AutoField(primary_key=True)  # ID unik untuk setiap entri dalam posting list
    termlemma = models.ForeignKey(TermLemmas, on_delete=models.CASCADE, to_field='termlemma', db_column='termlemma')  # ID term yang merujuk ke Tabel Term
    docdetail = models.ForeignKey(DocDetails, on_delete=models.CASCADE)  # Frekuensi kemunculan term dalam dokumen tertentu

    def __str__(self):
        return f"{self.termlemma} - {self.docdetail}"
    
    class Meta:
        indexes = [
            models.Index(fields=['termlemma']),  # Menambahkan indeks pada kolom termlemma
            models.Index(fields=['docdetail']),
        ]
    
# Model NER Default
nlp_default = spacy.load("en_core_web_sm")

# Model NER Custom
model_path = "kms_app/training/model-best"
if os.path.exists(model_path):
    nlp_custom = spacy.load(model_path)
else:
    # Jika model khusus tidak ditemukan, buat model kosong
    nlp_custom = spacy.blank("en")  

    train_data_path = 'kms_app/training/train_data.json'

    # Cek apakah file JSON ada
    if os.path.exists(train_data_path):
        # Buka file JSON yang berisi data train
        with open(train_data_path, 'r', encoding='utf-8') as f:
            TRAIN_DATA = json.load(f)

        # Filter anotasi untuk menghapus entri null
        filtered_annotations = [annotation for annotation in TRAIN_DATA['annotations'] if annotation is not None]

        # Inisialisasi objek DocBin untuk menyimpan dokumen Spacy
        db = DocBin()

        # Iterasi melalui anotasi yang difilter
        for text, annot in tqdm(filtered_annotations):
            # Buat objek dokumen Spacy dari teks
            doc = nlp_default.make_doc(text)
            ents = []

            # Iterasi melalui entitas yang diberikan dalam anotasi
            for start, end, label in annot["entities"]:
                # Buat objek span untuk entitas
                span = doc.char_span(start, end, label=label, alignment_mode="contract")
                if span is None:
                    print("Melewati entitas")
                else:
                    ents.append(span)

            # Atur entitas yang ditemukan dalam dokumen
            doc.ents = ents
            # Tambahkan dokumen ke DocBin
            db.add(doc)

        # Simpan data pelatihan ke disk dalam format Spacy
        db.to_disk("kms_app/training/training_data.spacy")

        # Eksekusi perintah setelah penyimpanan data ke disk
        init_config_args = "init config kms_app/training/config.cfg --lang en --pipeline ner --optimize efficiency"
        train_args = "train kms_app/training/config.cfg --output kms_app/training/ --paths.train kms_app/training/training_data.spacy --paths.dev kms_app/training/training_data.spacy"

        # Jalankan perintah untuk inisialisasi konfigurasi
        subprocess.run(["python", "-m", "spacy"] + init_config_args.split())

        # Jalankan perintah untuk melatih model
        subprocess.run(["python", "-m", "spacy"] + train_args.split())

def merge_entities(doc):
    combined_entities = []
    entities_custom = {}
    entities_default = {}

    # Entitas dari model NER default
    for ent in nlp_default(doc.text).ents:
        entities_default[(ent.start_char, ent.end_char)] = (ent.label_, ent.text)

    # Entitas dari model NER custom
    for ent in nlp_custom(doc.text).ents:
        entities_custom[(ent.start_char, ent.end_char)] = (ent.label_, ent.text)

    # Gabungkan entitas
    combined_entities = entities_custom.copy()

    for (start_char, end_char), (label, text) in entities_default.items():
        overlap = False
        for (start_custom, end_custom) in entities_custom.keys():
            if start_char < end_custom and start_custom < end_char:
                overlap = True
                break
        if not overlap:
            combined_entities[(start_char, end_char)] = (label, text)

    print(combined_entities)
    # Create a list to store spans
    spans = []

    # Create spans using character offsets directly
    for (start_char, end_char), (label, text) in combined_entities.items():
        span = doc.char_span(start_char, end_char, label=label)
        if span is None:
            print(f"Skipping entity: {text}")
        else:
            spans.append(span)

    # Create a new document with the combined entities
    merged_doc = Doc(doc.vocab, words=[token.text for token in doc])
    merged_doc.ents = spans

    return merged_doc

def get_fuseki_data(query_string):
    endpoint = "http://localhost:3030/kopi/query"

    # send SPARQL query
    r = requests.get(endpoint, params={'query': query_string})
    
    # get query results
    results = []
    if r.status_code == 200:
        response = r.json()
        for result in response['results']['bindings']:
            formatted_result = {}
            for key in result.keys():
                formatted_result[key] = result[key]['value']
            results.append(formatted_result)

    return results