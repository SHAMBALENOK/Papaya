from img2table.ocr import EasyOCR
from img2table.document import PDF
import os

ocr = EasyOCR(lang=["en", 'ru'])

def mkdir(path):
  try:
    os.makedirs(path)
  except OSError:
    pass

def extract_data(pdfname):
    pdf = PDF(src=pdfname)
    pdfname = pdfname.split('.')[0]
    mkdir(f'../../tables/{pdfname}')
    output_path = f'../../tables/{pdfname}/{pdfname}.xlsx'
    pdf.to_xlsx(output_path,
                ocr=ocr,
                implicit_columns=True,
                borderless_tables=False,
                min_confidence=70)