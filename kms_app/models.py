import nltk
import spacy
import fitz
import json
import subprocess
import os.path
from django.db import models
from django.core.validators import MinLengthValidator
from tqdm import tqdm
from spacy.tokens import DocBin, Doc

nltk.download('punkt')
nltk.download('averaged_perceptron_tagger')
nltk.download('maxent_ne_chunker')
nltk.download('words')
nltk.download('stopwords')

class uploader(models.Model):
    uploader_id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=128, validators=[MinLengthValidator(8)])

    def __str__(self):
        return self.username

# Load model bahasa Inggris dari Spacy
nlp_default = spacy.load("en_core_web_sm")

# Menggabungkan entitas dari model NER default dan kustom
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

    # Gabungan entitas
    combined_entities = entities_custom.copy()

    for (start_char, end_char), (label, text) in entities_default.items():
        overlap = False
        for (start_custom, end_custom) in entities_custom.keys():
            if start_char < end_custom and start_custom < end_char:
                overlap = True
                break
        if not overlap:
            combined_entities[(start_char, end_char)] = (label, text)

    # Buat daftar untuk menyimpan span
    spans = []

    # Buat span menggunakan offset karakter langsung
    for (start_char, end_char), (label, text) in combined_entities.items():
        span = doc.char_span(start_char, end_char, label=label)
        if span is None:
            print(f"Melewati entitas: {text}")
        else:
            spans.append(span)

    # Buat dokumen baru dengan entitas yang digabungkan
    merged_doc = Doc(doc.vocab, words=[token.text for token in doc])
    merged_doc.ents = spans

    return merged_doc

# Load model NER custom
nlp_custom = spacy.load("kms_app/training/model-best")

# Tambahkan sentencizer ke pipeline model NER custom
if "sentencizer" not in nlp_custom.pipe_names:
    nlp_custom.add_pipe("sentencizer")

# Path ke file PDF
directory_path = "kms_app/uploaded_files/"

for filename in os.listdir(directory_path):
    if filename.endswith(".pdf"):  # Pastikan itu file PDF
        pdf_path = os.path.join(directory_path, filename)
        if os.path.exists(pdf_path):
            # Jika file PDF sudah ada
            try:
                # Buka file PDF
                doc = fitz.open(pdf_path)
        
                # Ambil teks dari halaman PDF
                for page_number in range(doc.page_count):
                    page = doc[page_number]
                    text = page.get_text()
                    text = text.replace('\n', ' ')
            
                    document = []
            
                    # Bagi teks menjadi kalimat
                    sentences = text.split('.')

                    # Proses setiap kalimat
                    for sentence in sentences:
                        # Gabungkan entitas NER
                        doc = merge_entities(nlp_custom(sentence))
                        document.append(doc.text)
            except Exception as e:
                pass
    else: 
        pass

# Path ke file JSON yang berisi data train
train_data_path = 'kms_app/training/train_data.json'

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

# Cek apakah model sudah ada sebelumnya
model_trained = os.path.exists("kms_app/training/model-best")

# Jika model belum ada, maka jalankan proses training
if not model_trained:
    # Eksekusi perintah setelah penyimpanan data ke disk
    init_config_args = "init config kms_app/training/config.cfg --lang en --pipeline ner --optimize efficiency"
    train_args = "train kms_app/training/config.cfg --output kms_app/training/ --paths.train kms_app/training/training_data.spacy --paths.dev kms_app/training/training_data.spacy"

    # Jalankan perintah untuk inisialisasi konfigurasi
    subprocess.run(["python", "-m", "spacy"] + init_config_args.split())

    # Jalankan perintah untuk melatih model
    subprocess.run(["python", "-m", "spacy"] + train_args.split())