import pandas as pd
from transformers import pipeline
from deep_translator import GoogleTranslator
import database.database as db

LABELS = ['profile', 'course', 'name', 'level', 'diploma']

classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")

def _classify(sentences: list) -> dict:
    """
    Функция, которая определяет принадлежность заголовка из таблицы к стандартизированным из sql DB
    """
    output = {}
    translator_en = GoogleTranslator(source='auto', target='en')
    for sentence in sentences:
        data = classifier(translator_en.translate(sentence), LABELS)
        output[sentences.index(sentence)] = (sentence, data['scores'][0], data['labels'][0])

    check=[]
    deletion = []
    for key, value in output.items():
        for i in check:
            if i[0][2] == value[2]:
                if i[0][1] > value[1]:
                    deletion.append(key)
                elif i[0][1] == value[1]:
                    pass
                else:
                    deletion.append(i[1])
        check.append([value, key])

    for i in deletion:
        del output[i]

    for key, value in output.items():
        output[key] = value[2]


    return output

def tabulate(xlsx_path: str):
    """
    Функция для преобразорвания информации из excel таблицы в sql
    """
    file = pd.ExcelFile(xlsx_path).parse().ffill()

    labels = _classify([i.replace('\n', ' ') for i in file.columns])

    for row in file.itertuples():
        payload = dict()
        for i in range(1, len(row)):
            try:
                payload[labels[i-1]] = row[i].replace('\n', ' ')
            except KeyError:
                pass

        if payload.get('name', 'null') == 'null': db.add_event(payload)