import nltk
from nltk.tokenize import word_tokenize
from nltk import ne_chunk
from nltk.tag import pos_tag
from nltk.chunk import tree2conlltags
from nltk.corpus import stopwords

import spacy
import fitz
from spacy.tokens import DocBin
from spacy.tokens import Doc, Span
from tqdm import tqdm

import json
import subprocess
import os.path

from django.db import models

# Load model bahasa Inggris dari Spacy
nlp_default = spacy.load("en_core_web_sm")

# Inisialisasi objek DocBin untuk menyimpan dokumen Spacy
db = DocBin()

# Buka file JSON yang berisi data pelatihan
f = open('kms_app/training/train_data.json')
TRAIN_DATA = json.load(f)

# Filter anotasi untuk menghapus entri null
filtered_annotations = [annotation for annotation in TRAIN_DATA['annotations'] if annotation is not None]

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
            print("Skipping entity")
        else:
            ents.append(span)
    # Atur entitas yang ditemukan dalam dokumen
    doc.ents = ents
    # Tambahkan dokumen ke DocBin
    db.add(doc)

# Simpan data pelatihan ke disk dalam format Spacy
db.to_disk("kms_app/training/training_data.spacy")

# Cek apakah model sudah ada sebelumnya
model_trained = os.path.exists("kms_app/training/model-best")

# Jika model belum ada, maka jalankan proses training
if not model_trained:
    # Eksekusi perintah pertama setelah penyimpanan data ke disk
    init_config_args = "init config kms_app/training/config.cfg --lang en --pipeline ner --optimize efficiency"
    subprocess.run(["python", "-m", "spacy"] + init_config_args.split())

    # Eksekusi perintah kedua setelah penyimpanan data ke disk
    train_args = "train kms_app/training/config.cfg --output kms_app/training/ --paths.train kms_app/training/training_data.spacy --paths.dev kms_app/training/training_data.spacy"
    subprocess.run(["python", "-m", "spacy"] + train_args.split())

##### MENGGABUNGKAN NER DEFAULT & CUSTOM #####
def merge_entities(doc):
    combined_entities = []
    entities_custom = {}
    entities_default = {}

    # Entitas dari model NER default
    for ent in nlp_default(doc.text).ents:
        entities_default[(ent.start_char, ent.end_char)] = (ent.label_, ent.text)

    # Entitas dari model NER train
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

##### MEMASUKKAN PDF SEBAGAI KONTEKS #####
# Model NER Default
nlp_default = spacy.load("en_core_web_sm")

# Model NER Custom
nlp_custom = spacy.load("kms_app/training/model-best")

# Menambahkan sentencizer ke pipeline
if "sentencizer" not in nlp_custom.pipe_names:
    nlp_custom.add_pipe("sentencizer")

pdf_path = "kms_app/uploaded_files/coffee.pdf"

if os.path.exists(pdf_path):
    try:
        doc = fitz.open(pdf_path)

        # Mengambil teks dari halaman PDF
        text = ""
        for page_number in range(doc.page_count):
            page = doc[page_number]
            text += page.get_text()

        text = text.replace('\n', ' ')

        sentences = text.split('.')

        document = []
        for sentence in sentences:
            doc = merge_entities(nlp_custom(sentence))
            document.append(doc.text)
        
        def pos_tagging_and_extract_verbs(text):
            # Tokenisasi teks menjadi kata-kata
            tokens = word_tokenize(text)

            # Mengambil stop words dari NLTK
            stop_words = set(stopwords.words('english'))

            # POS Tagging
            pos_tags = pos_tag(tokens)

            # Ekstraksi kata-kata yang mengandung noun dan bukan stop words
            verbs = [word for word, pos in pos_tags if pos.startswith('VB') and word.lower() not in stop_words]

            return verbs
        
        def pos_tagging_and_extract_nouns(text):
            not_include = "coffee"
            tokens = word_tokenize(text)
            pos_tags = pos_tag(tokens)
            nouns = [word for word, pos in pos_tags if pos.startswith('NN') and word != not_include]
            return nouns
    except Exception as e:
        pass
else:
    pass

