#!/bin/bash

set -ex

dnf makecache
dnf -y update
dnf -y install dnf-plugins-core
dnf config-manager --set-enabled powertools
dnf -y install \
  wget \
  bzip2 \
  perl \
  gcc \
  gcc-c++\
  git \
  gnupg \
  make \
  munge \
  munge-devel \
  python${PYTHON_VERSION}-devel \
  python${PYTHON_VERSION}-pip \
  python${PYTHON_VERSION} \
  mariadb-server \
  mariadb-devel \
  psmisc \
  bash-completion \
  vim-enhanced \
  http-parser-devel \
  json-c-devel
dnf clean all
rm -rf /var/cache/dnf

alternatives --install /usr/bin/python3 python3 /usr/bin/python${PYTHON_VERSION} 1
