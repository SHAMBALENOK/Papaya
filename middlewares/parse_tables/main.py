import pdf_processing as pdf

def pdf_to_db(pdfname):
    pdf.extract_data(pdfname)

pdf_to_db('example.pdf')

#TODO: make it universal and add error handling