#!/bin/bash

set -ex

dnf makecache
dnf -y update
dnf -y install dnf-plugins-core
dnf config-manager --set-enabled crb
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
  mariadb \
  mariadb-server \
  mariadb-devel \
  postgresql \
  psmisc \
  bash-completion \
  sudo \
  vim-enhanced \
  http-parser-devel \
  json-c-devel \
  cmake \
  clang-tools-extra \
  procps \
  iputils \
  net-tools \
  openblas-devel \
  jq \
  iputils \
  net-tools \
  libyaml-devel \
  procps \
  lua-devel
dnf clean all
rm -rf /var/cache/dnf

alternatives --install /usr/bin/python3 python3 /usr/bin/python${PYTHON_VERSION} 1
