import os
import torch
from PIL import Image
from transformers import AutoModelForObjectDetection, DetrImageProcessor

SCANNING_PATH = '../../tables/'

# 1. Load the TATR detection model and image processor
model_name = "microsoft/table-transformer-detection"
processor = DetrImageProcessor.from_pretrained(model_name)
model = AutoModelForObjectDetection.from_pretrained(model_name)

# Move model to GPU if available
device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)


def detect_and_extract(file, quantity):
    filename = file.split('.')[0]
    try:
        os.makedirs(SCANNING_PATH + f'{filename}/tables')
    except FileExistsError:
        pass
    for i in range(quantity):
        # 2. Load the input image
        img_path = SCANNING_PATH + filename + '/images/' + filename + f'_{i}.png'

        if not os.path.exists(img_path):
            print(f"Файл не найден: {img_path}")
            continue

        img = Image.open(img_path).convert("RGB")

        # 3. Preprocess and run inference
        inputs = processor(images=img, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs)

        # 4. Post-process the object detection bounding boxes
        target_sizes = torch.tensor([img.size[::-1]]).to(device)
        results = processor.post_process_object_detection(outputs, threshold=0.7, target_sizes=target_sizes)[0]

        # Списки для хранения координат всех обнаруженных таблиц на текущей странице
        x_mins, y_mins, x_maxs, y_maxs = [], [], [], []
        high_confidence_score = 0.0

        for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
            label_str = model.config.id2label[label.item()]

            if label_str == "table":
                box = box.tolist()
                x_mins.append(box[0])
                y_mins.append(box[1])
                x_maxs.append(box[2])
                y_maxs.append(box[3])
                high_confidence_score = max(high_confidence_score, score.item())

        # 5. Если таблицы найдены, объединяем их координаты в один общий Box
        if x_mins:
            # Находим крайние точки, чтобы объединить все куски в одно изображение
            global_xmin = max(0, min(x_mins))
            global_ymin = max(0, min(y_mins))
            global_xmax = min(img.width, max(x_maxs))
            global_ymax = min(img.height, max(y_maxs))

            # Добавим небольшой отступ (padding) в 5 пикселей по краям, чтобы текст не прижимался к границе
            padding = 5
            global_xmin = max(0, global_xmin - padding)
            global_ymin = max(0, global_ymin - padding)
            global_xmax = min(img.width, global_xmax + padding)
            global_ymax = min(img.height, global_ymax + padding)

            print(
                f"[{filename}{i}.png] Объединено фрагментов таблицы. Итоговые координаты: [{global_xmin:.1f}, {global_ymin:.1f}, {global_xmax:.1f}, {global_ymax:.1f}]")

            # Вырезаем объединенную таблицу
            cropped_table = img.crop((global_xmin, global_ymin, global_xmax, global_ymax))

            # Сохраняем итоговое изображение
            output_filename = f"table_{filename}_{i}.png"
            cropped_table.save(SCANNING_PATH+f'{filename}/tables/'+output_filename)
            print(f"Успешно сохранено: {output_filename}")
        else:
            print(f"[{filename}{i}.png] Таблицы на изображении не обнаружены.")