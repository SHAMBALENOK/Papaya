import os
import pandas as pd
from huggingface_hub import InferenceClient
from app.database import events as db_events
from googletrans import Translator
import uuid as uuid_mod
from app.middlewares.task_queue import task_queue, AsyncCeleryTask, run_task

translator = Translator()

client = InferenceClient(
    model="facebook/bart-large-mnli",
    token=os.getenv('HF_TOKEN')
)

LABELS = ['olympiad']

async def translate_text(text):
    """
    Translates text from russian to english
    """
    translator = Translator()
    result = await translator.translate(text, dest='en')
    return result.text

async def _classify(sentences: list) -> list:
    """
    Searches for a name in table headers and description
    """
    output = {}

    for i, sentence in enumerate(sentences):
        data = client.zero_shot_classification(
            await translate_text(sentence),
            candidate_labels=LABELS,
        )

        output[i] = data[0].score

    name = (sentences.index(sentences[max(output, key=output.get)]) ,sentences.pop(max(output, key=output.get)))
    classified = list()
    classified.append(name)
    for i in sentences:
        classified.append((sentences.index(i), i))

    return classified

@task_queue.task(base=AsyncCeleryTask, time_limit=120, default_retry_delay=30, retry_backoff=True, retry_backoff_max=120, queue="heavy")
async def tabulate(xlsx_path: str, owner: str):
    """
    Converting information from an Excel table to SQL
    """
    file = pd.ExcelFile(xlsx_path).parse().ffill()
    created_events = []

    labels = await _classify([i.replace('\n', ' ') for i in file.columns])

    for row in file.itertuples():
        row_dict = row._asdict()
        payload = dict()
        # for i in range(0, len(row)):
        #     print(row[i])
        payload['disc'] = str()
        payload['owner'] = uuid_mod.UUID(owner)
        payload['name'] = row_dict.get("_"+str(labels[0][0]))
        formated_labels = labels[1:len(labels)]
        for i in formated_labels:
            value = row_dict.get("_"+str(i[0]+1))
            # Пустые/NaN ячейки не должны валить .replace()
            if isinstance(value, float) and pd.isna(value):
                value = ''
            else:
                value = str(value).replace(r"\n", " ")
            payload['disc'] += f'\n{i[1]}: {value}'

        if payload.get('name', 'null') != 'null':
            created = await run_task(db_events.add_event, ins=payload)
            created_events.append(created)
    return created_events