
FROM --platform=$TARGETPLATFORM python:3.10
WORKDIR /usr/src/app

COPY ./ ./pylon
RUN set -x \
  && pip install --upgrade pip \
  && pip install --no-cache-dir ./pylon \
  && rm -r ./pylon

CMD [ "python", "-m", "pylon.main" ]
