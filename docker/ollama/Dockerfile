FROM ollama/ollama:latest

# Trust corporate SSL-inspection CA (e.g. Zscaler, Netskope) for registry.ollama.ai pulls.
COPY certs/ /tmp/custom-certs/
RUN set -eux; \
    installed=0; \
    for f in /tmp/custom-certs/*.crt; do \
      if [ -f "$f" ]; then \
        cp "$f" /usr/local/share/ca-certificates/; \
        installed=1; \
      fi; \
    done; \
    if [ "$installed" = "1" ]; then update-ca-certificates; fi; \
    rm -rf /tmp/custom-certs
