import pandas as pd
from transformers import pipeline

LABELS = ['Профиль', 'Направление', 'Название', 'Уровень', 'Диплом']

classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")

def _classify(sentences: list) -> dict:
    """
    Функция, которая определяет принадлежность заголовка из таблицы к стандартизированным из sql DB
    """
    output = {}
    for sentence in sentences:
        data = classifier(sentence, LABELS)
        output[sentence] = (data['labels'][0], data['scores'][0])

    check=[]
    deletion = []
    for key, value in output.items():
        for i in check:
            if i[0][0] == value[0]:
                if i[0][1] > value[1]:
                    deletion.append(key)
                elif i[0][1] == value[1]:
                    pass
                else:
                    deletion.append(i[1])
        check.append([value, key])

    for i in deletion:
        del output[i]

    return output

def tabulate(xlsx_path: str):
    """
    Функция для преобразорвания информации из excel таблицы в sql
    """
    file = pd.ExcelFile(xlsx_path).parse()
    labels = [i.replace('\n', ' ') for i in file.columns]
    print(_classify(labels))

tabulate('../../tables/example/example.xlsx')

#TODO: переделать добавление соббытий согласно инфе из таблицы