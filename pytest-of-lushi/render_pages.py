import sys

sys.path.insert(0, '.')
import pypdfium2 as pdfium

path = r'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\original\26-27.pdf'
doc = pdfium.PdfDocument(path)
for page_number in (13, 70, 77):
    page = doc[page_number - 1]
    bitmap = page.render(scale=100 / 72.0)
    image = bitmap.to_pil()
    image.save(f'pytest-of-lushi/orient_{page_number}.png')
    print(page_number, image.size)
doc.close()
