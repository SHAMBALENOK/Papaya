import os
import pymupdf

SAVING_PATH = '../../tables/'

def mkdir(path):
  try:
    os.makedirs(path)
  except OSError:
    pass

def cns(file):
  # Open the PDF
  doc = pymupdf.open(file)
  # Select a page (0 is the first page)
  page = doc[0]
  # Render the page to a pixmap (image)
  pix = page.get_pixmap(dpi=300)
  filename = file.split('.')[0]
  # Save the image
  pix.save(f"{filename}.png")
  doc.close()