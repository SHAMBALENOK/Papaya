import os
import pandas as pd
from huggingface_hub import InferenceClient
from app.database import events
from app.models import events
from googletrans import Translator
import asyncio
import uuid as uuid_mod

translator = Translator()

client = InferenceClient(
    model="facebook/bart-large-mnli",
    token=os.getenv('HF_TOKEN')
)

LABELS = ['profile', 'course', 'name', 'level', 'diploma']

def translate_text(text):
    """
    Translates text from russian to english
    """
    translator = Translator()
    result = translator.translate(text, dest='en')
    return result.text

def _classify(sentences: list) -> tuple:
    """
    Searches for a name in table headers
    """
    output = {}

    for i, sentence in enumerate(sentences):
        data = client.zero_shot_classification(
            translate_text(sentence),
            candidate_labels=LABELS,
        )

        output[i] = data[0].score

    name = sentences.pop(max(output, key=output.get))

    return name, sentences

async def tabulate(xlsx_path: str, session, owner: str):
    """
    Converting information from an Excel table to SQL
    """
    file = pd.ExcelFile(xlsx_path).parse().ffill()
    created_events = []

    labels = _classify([i.replace('\n', ' ') for i in file.columns])

    for row in file.itertuples():
        payload = dict()
        payload['disc'] = str()
        payload['owner'] = uuid_mod.UUID(owner)
        payload['name'] = getattr(row, labels[0])
        for i in labels[1]:
            payload['disc'] += f'\n{i}: {(getattr(row, i))}'
            # try:
            #     payload[labels[i-1]] = row[i].replace('\n', ' ')
            # except KeyError:
            #     pass

        if payload.get('name', 'null') != 'null': await events.add_event(
            ins=payload,
            session=session,
            model=events.Events
        )
    return created_events