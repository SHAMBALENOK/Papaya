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


def extract_tables(file, quantity):
    filename = file.split('.')[0]
    try:
        os.makedirs(os.path.join(SCANNING_PATH, filename, 'tables'))
    except FileExistsError:
        pass

    for i in range(quantity):
        # 2. Load the input image (используем ваш формат с нижним подчеркиванием)
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
                # Исправлено: извлекаем конкретные координаты из списка box
                x_mins.append(box[0])
                y_mins.append(box[1])
                x_maxs.append(box[2])
                y_maxs.append(box[3])
                high_confidence_score = max(high_confidence_score, score.item())

        # 5. Если таблицы найдены, объединяем их координаты в один общий Box с защитой колонок
        if x_mins:
            # Находим базовые крайние точки среди всех фрагментов таблицы
            global_xmin = max(0, min(x_mins))
            global_ymin = max(0, min(y_mins))
            global_xmax = min(img.width, max(x_maxs))
            global_ymax = min(img.height, max(y_maxs))

            # --- АЛГОРИТМ ЗАЩИТЫ ОТ ПОТЕРИ КРАЙНИХ КОЛОНОК ---
            # Вычисляем ширину найденной области
            detected_width = global_xmax - global_xmin

            # Если область занимает более 55% ширины листа, значит таблица широкоформатная,
            # и модель, скорее всего, проигнорировала невидимую левую рамку / скрытые поля.
            if detected_width > (img.width * 0.55):
                print(f"[{filename}_{i}.png] Обнаружена полностраничная таблица. Расширяем границы до краев документа.")
                global_xmin = 0
                global_xmax = img.width
            else:
                # Если таблица занимает лишь часть страницы, даем безопасный боковой отступ в 35 пикселей
                global_xmin = max(0, global_xmin - 35)
                global_xmax = min(img.width, global_xmax + 35)

            # Вертикальный отступ (чтобы гарантированно захватить шапку и нижнюю границу)
            vertical_padding = 20
            global_ymin = max(0, global_ymin - vertical_padding)
            global_ymax = min(img.height, global_ymax + vertical_padding)

            print(
                f"[{filename}_{i}.png] Объединено фрагментов таблицы. Итоговые координаты: [{global_xmin:.1f}, {global_ymin:.1f}, {global_xmax:.1f}, {global_ymax:.1f}]")

            # Вырезаем объединенную таблицу
            cropped_table = img.crop((global_xmin, global_ymin, global_xmax, global_ymax))

            # Сохраняем итоговое изображение в вашу целевую папку
            output_filename = f"table_{filename}_{i}.png"
            output_path = os.path.join(SCANNING_PATH, filename, 'tables', output_filename)
            cropped_table.save(output_path)
            print(f"Успешно сохранено: {output_path}")
        else:
            print(f"[{filename}_{i}.png] Таблицы на изображении не обнаружены.")
