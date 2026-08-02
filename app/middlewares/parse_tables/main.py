from . import pdf_processing as pdf
from . import sql_processing as sql

def pdf_to_db(pdfname: str, session, owner: str):
    sql.tabulate(pdf.extract_data(pdfname), session, owner)

#TODO: add error handling