from . import pdf_processing as pdf
from . import sql_processing as sql

def pdf_to_db(pdfname, session):
    sql.tabulate(pdf.extract_data(pdfname), session)

#TODO: add error handling