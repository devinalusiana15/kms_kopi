# Aplikasi Web KMS Kopi

Petunjuk instalasi:

1. Remove installed apps dan middleware modul Livesync
2. pip install spacy
3. pip install PyMuPDF
4. pip install nltk
5. python -m spacy init config kms_app/training/config.cfg --lang en --pipeline ner --optimize efficiency
6. python -m spacy train config.cfg --output ./ --paths.train ./training_data.spacy --paths.dev ./training_data.spacy
