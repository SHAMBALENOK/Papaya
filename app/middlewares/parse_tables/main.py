from app.middlewares.task_queue import run_task

from . import pdf_processing as pdf
from . import sql_processing as sql


async def pdf_to_db(pdfname: str, owner: str):
    """Извлечь таблицу из PDF в worker и обработать XLSX без Celery-лимита.

    В Celery отправляется только CPU-intensive OCR. Полученный XLSX затем
    обрабатывается обычной async-функцией в API-процессе, поэтому tabulate не
    наследует worker time limit и не запускает синхронные подзадачи.
    """
    xlsx_path = await run_task(pdf.extract_data, pdfname)
    return await sql.tabulate(xlsx_path, owner)