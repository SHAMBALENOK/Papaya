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
    mkdir(f'../../tables/{pdfname}')
    # Export to file
    pdf.to_xlsx(f'../../tables/{pdfname}/{pdfname.split(".")[0]}.xlsx',
                ocr=ocr,
                implicit_columns=True,
                borderless_tables=False,
                min_confidence=70)