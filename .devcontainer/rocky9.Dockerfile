FROM rockylinux:9

RUN set -ex \
    && yum makecache \
    && yum -y update \
    && yum -y install dnf-plugins-core \
    && yum config-manager --set-enabled crb \
    && yum -y install \
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
       python3.12-devel \
       python3.12-pip \
       mariadb \
       mariadb-server \
       mariadb-devel \
       postgresql \
       psmisc \
       bash-completion \
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
       lua-devel \
    && yum clean all \
    && rm -rf /var/cache/yum

RUN alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
