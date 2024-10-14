FROM python:3.10
WORKDIR /data

RUN set -x \
  && curl -q http://zerossl.crt.sectigo.com/ZeroSSLRSADomainSecureSiteCA.crt | openssl x509 > /usr/local/share/ca-certificates/ZeroSSLRSADomainSecureSiteCA.crt \
  && update-ca-certificates

RUN set -x \
  && apt-get update \
  && apt-get install --no-install-recommends -y \
      dumb-init \
      geoip-database \
      libasound2 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 \
      libcairo2 libcups2 libdbus-1-3 libdrm2 libgbm1 libglib2.0-0 \
      libnspr4 libnss3 libpango-1.0-0 \
      libx11-6 \
      libxcb1 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxkbcommon0 libxrandr2 \
      xvfb \
      fonts-noto-color-emoji fonts-unifont libfontconfig1 libfreetype6 \
      xfonts-scalable fonts-liberation \
      fonts-ipafont-gothic fonts-wqy-zenhei fonts-tlwg-loma-otf fonts-freefont-ttf \
      dos2unix \
      poppler-data poppler-utils libpoppler-cpp0v5 libpoppler-glib8 \
      tesseract-ocr-all \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

ARG PIP_ARGS="--no-cache-dir"
RUN set -x \
  && pip install $PIP_ARGS --upgrade pip

COPY ./requirements.txt ./requirements.txt
RUN set -x \
  && pip install $PIP_ARGS -r ./requirements.txt \
  && rm ./requirements.txt

COPY ./ ./pylon
RUN set -x \
  && pip install $PIP_ARGS ./pylon \
  && rm -r ./pylon

COPY ./entrypoint.sh /usr/local/sbin/entrypoint.sh
RUN set -x \
  && dos2unix /usr/local/sbin/entrypoint.sh \
  && chmod 755 /usr/local/sbin/entrypoint.sh

CMD [ "bash", "/usr/local/sbin/entrypoint.sh" ]
