import zipfile
 
with zipfile.ZipFile("MABLE-0.0.9-py3-none-any.whl") as f:
    f.extractall('.')