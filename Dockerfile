FROM python:3.10
WORKDIR /data

COPY ./ ./pylon

RUN pip install --upgrade pip
RUN pip install --no-cache-dir ./pylon
RUN rm -r ./pylon

RUN set -x \
  && curl -q http://zerossl.crt.sectigo.com/ZeroSSLRSADomainSecureSiteCA.crt | openssl x509 > /usr/local/share/ca-certificates/ZeroSSLRSADomainSecureSiteCA.crt \
  && update-ca-certificates

CMD [ "python", "-m", "pylon.main" ]
