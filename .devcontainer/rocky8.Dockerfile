FROM rockylinux:8

ARG PYTHON_VERSION=3.12
ENV PYTHON_VERSION=${PYTHON_VERSION}

COPY .devcontainer/install.rocky8.sh /tmp/install.rocky8.sh
RUN sh /tmp/install.rocky8.sh
