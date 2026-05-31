from table_transformer import TableExtractionPipeline

SCANNING_PATH = '../../tables/'

pipe = TableExtractionPipeline(det_device='cpu', str_device='cpu',
                               det_model_path='./models/pubtables1m_detection_detr_r18.pth',
                               str_model_path='./models/TATR-v1.1-All-msft.pth')

def detect_and_extract(file, quantity):
    filename = file.split('.')[0]
    for i in range(quantity):
        img = SCANNING_PATH+filename+'/images/'+filename+f'_{i}.png'
        table_objects, table_cells_coordinates, table_cells_text = pipe(img)
        print(table_cells_text)