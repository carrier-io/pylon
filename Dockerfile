FROM golang:1.13
WORKDIR /go/src/

COPY project/core/tools/minio/minio_madmin.go .
RUN set -x \
  && go get -d -v github.com/minio/minio/pkg/madmin \
  && go build -o minio_madmin.so -buildmode=c-shared minio_madmin.go

FROM python:3.8
WORKDIR /usr/src/app

COPY requirements.txt ./
RUN set -x \
  && pip install --no-cache-dir -r requirements.txt \
  && rm -f requirements.txt

COPY project/ ./
COPY --from=0 /go/src/minio_madmin.so core/tools/minio/
CMD [ "python", "./main.py" ]
