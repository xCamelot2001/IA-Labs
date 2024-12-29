import zipfile
 
with zipfile.ZipFile("MABLE-0.0.11-py3-none-any.whl") as f:
    f.extractall('.')