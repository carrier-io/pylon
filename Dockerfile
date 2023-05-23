FROM python:3.10
WORKDIR /data

COPY ./ ./pylon

RUN pip install --upgrade pip
RUN pip install --no-cache-dir ./pylon
RUN rm -r ./pylon

CMD [ "python", "-m", "pylon.main" ]
