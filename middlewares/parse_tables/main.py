import pdf_processing as pdf
import image_processing as image
import table_processing as table

def extract_data(pdfname):
    quantity = pdf.convert_to_image(pdfname)
    image.extract_tables(pdfname, quantity)
    table.convert_to_xlsx(pdfname.split(".")[0])

extract_data('example.pdf')

#TODO: make it universal and add error handling