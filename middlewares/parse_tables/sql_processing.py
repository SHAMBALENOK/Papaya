import os
import pandas as pd
from huggingface_hub import InferenceClient
import database.database as db
from googletrans import Translator
import asyncio
import uuid

translator = Translator()

client = InferenceClient(
    model="facebook/bart-large-mnli",
    token=os.getenv('HF_TOKEN')
)

LABELS = ['profile', 'course', 'name', 'level', 'diploma']

def translate_text(text):
    translator = Translator()
    result = asyncio.run(translator.translate(text, dest='en'))

    return result.text

def _classify(sentences: list) -> dict:
    """
    Функция, которая определяет принадлежность заголовка из таблицы к стандартизированным из sql DB
    """
    output = {}
    for sentence in sentences:
        data = client.zero_shot_classification(
            translate_text(sentence),
            candidate_labels=LABELS,
            )

        output[sentences.index(sentence)] = (sentence, data[0].score, data[0].label)

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

        idd = str(uuid.uuid4())
        payload['id'] = idd
        if payload.get('name', 'null') != 'null': db.add_event(payload)