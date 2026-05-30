import os
import pymupdf

SAVING_PATH = '../../tables/'

def mkdir(path):
  try:
    os.makedirs(path)
  except OSError:
    pass

def convert_to_image(path):
  # Open the PDF
  doc = pymupdf.open(path)
  num = 0
  filename = path.split('.')[0]
  dir = SAVING_PATH+filename+'/images/'
  mkdir(dir)
  for i in doc:
    # Select a page (0 is the first page)
    # page = doc[num]
    # Render the page to a pixmap (image)
    pix = i.get_pixmap(dpi=300)
    # Save the image
    pix.save(f"{dir+filename+str(num)}.png")
    num+=1
  doc.close()
  return num