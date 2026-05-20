FROM rockylinux:9

ARG PYTHON_VERSION=3.12
ENV PYTHON_VERSION=${PYTHON_VERSION}

COPY .devcontainer/install.rocky9.sh /tmp/install.rocky9.sh
RUN sh /tmp/install.rocky9.sh
