import asyncio
from . import pdf_processing as pdf
from . import sql_processing as sql


async def pdf_to_db(pdfname: str, owner: str):
    """
    Runs the PDF -> Excel -> SQL workflow as a Celery chain.

    extract_data() produces the xlsx path which is passed automatically to
    tabulate() as its first argument; the result of the chain is the list of
    created events (serializable dicts).
    """
    chain = (pdf.extract_data.s(pdfname) | sql.tabulate.s(owner)).apply_async()
    return await asyncio.to_thread(chain.get)

#TODO: add error handling
