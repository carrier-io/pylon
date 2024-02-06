FROM python:3.10
WORKDIR /data

RUN set -x \
  && curl -q http://zerossl.crt.sectigo.com/ZeroSSLRSADomainSecureSiteCA.crt | openssl x509 > /usr/local/share/ca-certificates/ZeroSSLRSADomainSecureSiteCA.crt \
  && update-ca-certificates

RUN set -x \
  && apt-get update \
  && apt-get install --no-install-recommends -y \
      geoip-database \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

COPY ./ ./pylon
RUN pip install --no-cache-dir ./pylon
RUN rm -r ./pylon

CMD [ "python", "-m", "pylon.main" ]
