import pdf_processing as pdf
import image_processing as image

def process(pdfname):
    pdf.cns(pdfname)
    image.finalize()

process('example.pdf')