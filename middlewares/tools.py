import os

def mkdir(path):
  try:
    os.makedirs(path)
  except OSError:
    pass

def allowed_file(filename, extensions):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in extensions