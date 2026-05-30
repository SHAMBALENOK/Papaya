import pdf_processing as pdf
import image_processing as image

def extract_data(pdfname):
    quantity = pdf.convert_to_image(pdfname)
    image.detect_and_extract(pdfname, quantity)

extract_data('example.pdf')

#TODO: make it universal and add error handling