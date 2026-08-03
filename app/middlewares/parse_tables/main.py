from . import pdf_processing as pdf
from . import sql_processing as sql

async def pdf_to_db(pdfname: str, session, owner: str):
    data = pdf.extract_data(pdfname)
    return await sql.tabulate(data, session, owner)

#TODO: add error handling