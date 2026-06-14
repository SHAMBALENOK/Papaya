import pdf_processing as pdf
import sql_processing as sql

def pdf_to_db(pdfname):
    sql.tabulate(pdf.extract_data(pdfname))

#TODO: add error handling