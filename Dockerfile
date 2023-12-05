from ghcr.io/translatorsri/renci-python-image:3.11.5



# make a directory for the repo
RUN mkdir /repo

# go to the directory where we are going to upload the repo
WORKDIR /repo

RUN mkdir redis-tpf
RUN chown nru redis-tpf
USER nru

COPY . redis-tpf

WORKDIR redis-tpf

RUN pip install -r requirements.txt

