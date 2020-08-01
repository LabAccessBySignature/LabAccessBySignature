# LabAcessBySignature
## Install
Download miniconda installer:
[https://docs.conda.io/en/latest/miniconda.html](https://docs.conda.io/en/latest/miniconda.html)
```
sh Miniconda3-latest-Linux-x86_64.sh 
conda install mamba -c conda-forge
conda config --add channels conda-forge
conda create -n sage sage python=3.7
conda activate sage
conda install flask
git clone https://github.com/LabAccessBySignature/LabAccessBySignature.git
```
Run in different terminal tabs
```
python client.py
python id_based_server.py 
python lab_server.py
```
Access client side via [http://127.0.0.1:5081/](http://127.0.0.1:5081/).

Upload 8 certificates from {project_dir}/cert.

Check on the server side [http://127.0.0.1:5082/](http://127.0.0.1:5082/) if lab is open.

## Generate new keys
```
python id_based_server.py -c generate_keys -e emails.txt 
```