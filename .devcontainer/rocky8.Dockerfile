FROM rockylinux:8

ARG PYTHON_VERSION=3.11
ENV PYTHON_VERSION=${PYTHON_VERSION}

COPY .devcontainer/install.rocky8.sh /tmp/install.rocky8.sh
RUN sh /tmp/install.rocky8.sh

RUN groupadd --gid 1000 devuser && \
  useradd --uid 1000 --gid 1000 -m -s /bin/bash devuser

USER devuser
